"""Shared cartridge discovery.

The on-disk scan + identity validation + HELLO probe that classifies each
installed cartridge version directory as attachable (``Directory``) or
``Incompatible``. This is the single source of truth used by both the
engine (for the bundled ``bundled-cartridges/`` tree next to its binary) and the
daemon (for the user-installed cartridge tree).

Keeping one implementation guarantees the two hosts accept exactly the
same cartridges and reject the rest with byte-identical verdicts. The
host's identity (channel / registry URL / fabric manifest version) is
passed in via :class:`DiscoveryIdentity` rather than read from a
compile-time constant, so the same code serves a host built for any
channel/registry.

Managed layout (relative to the root passed to :func:`discover_cartridges`)::

    {root}/{slug}/{channel}/{name}/{version}/cartridge.json
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

from capdag.bifaci.bundled_cartridge_hashes import bundled_cartridge_expected_hash
from capdag.bifaci.cartridge_json import (
    CartridgeInstallSource,
    CartridgeJsonError,
    CartridgeJsonRegistrySlugMismatch,
    RegistryUrlSchemeResult,
    hash_cartridge_directory,
    read_cartridge_json_from_dir,
    validate_registry_url_scheme,
)
from capdag.bifaci.cartridge_repo import CartridgeChannel
from capdag.bifaci.cartridge_slug import slug_for
from capdag.bifaci.io import FrameReader, FrameWriter, handshake, verify_identity
from capdag.bifaci.relay_switch import (
    CartridgeAttachmentError,
    CartridgeAttachmentErrorKind,
)

logger = logging.getLogger(__name__)


@dataclass
class DiscoveryIdentity:
    """The identity a host accepts cartridges for. A cartridge whose
    ``cartridge.json`` diverges from this on channel, registry URL,
    registry scheme, or fabric manifest version is surfaced as
    ``Incompatible`` — never hosted."""

    channel: CartridgeChannel
    #: ``str`` for release/nightly hosts, ``None`` for dev hosts
    #: (cartridges then live under the reserved dev slug and any
    #: registry scheme is allowed).
    registry_url: Optional[str]
    fabric_manifest_version: int
    #: Cartridge registry regime version this host speaks — an on-disk PATH
    #: level: cartridges live under ``{slug}/v{cartridge_registry_version}/
    #: {channel}/…``, pinned like the channel so a v1 host never scans a v2 tree.
    cartridge_registry_version: int

    def slug(self) -> str:
        """On-disk top-level slug for THIS host's own baked registry
        (``dev`` when ``registry_url`` is None). Discovery does not
        restrict scanning to this slug — it enumerates every slug folder
        and validates each cartridge against the folder it sits under.
        Retained for callers that need the host's own slug."""
        return slug_for(self.registry_url)


@dataclass
class DiscoveredCartridgeDirectory:
    """A discovered cartridge that passed every identity check and whose
    HELLO probe succeeded. Its caps will be registered for dispatch."""

    entry_point: Path
    version_dir: Path
    id: str
    channel: CartridgeChannel
    registry_url: Optional[str]
    version: str
    cap_groups: List[Any]


@dataclass
class DiscoveredCartridgeIncompatible:
    """A discovered cartridge found on disk but failed a check. NOT
    spawned, caps never enter the dispatch graph; surfaced with a
    structured ``error`` so the UI can render the reason. This is the
    uniform surface for every discovery-time rejection — no silent
    log-and-skip."""

    version_dir: Path
    id: str
    channel: CartridgeChannel
    registry_url: Optional[str]
    version: str
    error: CartridgeAttachmentError


# A discovered cartridge is one of the two classified shapes above.
DiscoveredCartridge = Any


def _unix_seconds_now() -> int:
    """Current wall-clock time as Unix seconds, for stamping
    ``CartridgeAttachmentError.detected_at_unix_seconds``. A pre-epoch
    clock returns 0 (display-ordering only)."""
    try:
        return int(time.time())
    except Exception:
        return 0


def probe_cartridge_cap_groups(path: Path) -> List[Any]:
    """Probe a cartridge binary for its capability surface.

    Spawns the binary, performs the bifaci HELLO handshake, parses the
    manifest, returns its full ``cap_groups``, then kills the process. A
    binary that fails to spawn, fails HELLO, or returns an unparseable
    manifest raises — the caller surfaces it as ``HANDSHAKE_FAILED``.
    """
    try:
        child = subprocess.Popen(
            [str(path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
        )
    except OSError as e:
        raise RuntimeError(f"Failed to spawn cartridge {path}: {e}") from e

    if child.stdin is None or child.stdout is None:
        child.kill()
        raise RuntimeError(f"cartridge {path} stdin/stdout pipe missing")

    reader = FrameReader(child.stdout)
    writer = FrameWriter(child.stdin)

    try:
        result = handshake(reader, writer)
        verify_identity(reader, writer)
    except Exception as e:
        try:
            child.kill()
        except Exception:
            pass
        raise RuntimeError(f"cartridge {path} HELLO failed: {e}") from e
    finally:
        # SIGKILL immediately — we have the manifest and don't wait for a
        # clean exit.
        try:
            child.kill()
        except Exception:
            pass

    manifest = result.manifest
    try:
        parsed = json.loads(manifest)
    except Exception as e:
        preview = manifest[: min(len(manifest), 500)]
        raise RuntimeError(f"cartridge {path} invalid manifest ({e}): {preview!r}") from e

    cap_groups = parsed.get("cap_groups")
    if cap_groups is None:
        raise RuntimeError(f"cartridge {path} manifest missing cap_groups")
    return cap_groups


def discover_cartridges(
    cartridges_root: Path,
    identity: DiscoveryIdentity,
) -> List[DiscoveredCartridge]:
    """Discover every cartridge under ``{cartridges_root}/{slug}/{channel}/``.

    Each cartridge name directory's newest version is validated against
    ``identity`` and probed; the result is the full classified roster
    (attachable + incompatible). An empty/absent scan root is not an
    error — it yields an empty roster. A real IO failure reading an
    existing scan root IS an error (it would otherwise masquerade as "no
    cartridges installed").

    Discovery scans EVERY slug folder present on disk — full parity with
    the reference host. The host's baked ``identity.registry_url`` does
    NOT restrict which slugs are scanned; each cartridge is instead
    validated in place against the slug folder it sits under (the
    three-place rule), so a registry-installed cartridge, the reserved
    ``dev/`` slot (null registry_url), and the engine's bundled cartridges
    all coexist and load together. The channel folder IS still pinned to
    the host's channel — release and nightly artefacts never mix.
    """
    discovered: List[DiscoveredCartridge] = []
    if not cartridges_root.is_dir():
        return discovered

    try:
        slug_entries = sorted(cartridges_root.iterdir())
    except OSError as e:
        raise RuntimeError(f"read_dir({cartridges_root}): {e}") from e

    for slug_dir in slug_entries:
        if not slug_dir.is_dir():
            if slug_dir.name != ".DS_Store":
                logger.error(
                    "Unmanaged file in cartridges root — only registry-slug / dev "
                    "directories belong here: %s",
                    slug_dir,
                )
            continue
        expected_slug = slug_dir.name
        # {slug}/v{cartridge_registry_version}/{channel}/… — the registry regime
        # version is a path level pinned to the host's version (like channel).
        scan_root = slug_dir / f"v{identity.cartridge_registry_version}" / identity.channel.value
        if not scan_root.is_dir():
            # This slug has no subtree for the host's (version, channel) — skip.
            continue
        _scan_channel_root(scan_root, expected_slug, identity, discovered)

    return discovered


def _scan_channel_root(
    scan_root: Path,
    expected_slug: str,
    identity: DiscoveryIdentity,
    discovered: List[DiscoveredCartridge],
) -> None:
    """Scan one ``{slug}/{channel}/`` root: classify each cartridge name
    directory's newest version against the host identity and the slug
    folder it sits under. Appends results to ``discovered``."""
    try:
        name_entries = sorted(scan_root.iterdir())
    except OSError as e:
        raise RuntimeError(f"read_dir({scan_root}): {e}") from e

    for name_dir in name_entries:
        if not name_dir.is_dir():
            if name_dir.name != ".DS_Store":
                logger.error(
                    "Unmanaged file in {slug}/{channel}/ — only cartridge name "
                    "directories belong here: %s",
                    name_dir,
                )
            continue

        try:
            sub_entries = list(name_dir.iterdir())
        except OSError as e:
            logger.error("Cannot read cartridge name directory %s: %s", name_dir, e)
            continue

        version_dirs: List[Path] = []
        for sub_path in sub_entries:
            if sub_path.is_dir():
                version_dirs.append(sub_path)
            elif sub_path.name != ".DS_Store":
                logger.error(
                    "Unmanaged file inside cartridge name directory — only version "
                    "directories belong here: %s",
                    sub_path,
                )

        if not version_dirs:
            logger.error(
                "Cartridge name directory contains no version subdirectories: %s",
                name_dir,
            )
            continue

        # Prefer the newest version (lexical-descending on the version
        # folder name).
        version_dirs.sort(key=lambda p: p.name, reverse=True)
        version_dir = version_dirs[0]

        path_derived_name = name_dir.name or "unknown"
        path_derived_version = version_dir.name or "unknown"
        detected_at = _unix_seconds_now()

        # ``read_cartridge_json_from_dir`` enforces the three-place rule
        # against the ACTUAL slug folder (``expected_slug``): the
        # cartridge's declared registry_url must hash to it. A non-null
        # registry_url under ``dev/`` (or any slug != slug_for(registry_url))
        # fails here as a slug mismatch — surfaced incompatible and logged,
        # never hosted. A null registry_url is valid only under the
        # reserved ``dev/`` slot.
        try:
            cj = read_cartridge_json_from_dir(version_dir, expected_slug)
        except CartridgeJsonError as e:
            # A slug mismatch (declared registry_url doesn't hash to this
            # folder) is a bad INSTALL CONTEXT, distinct from an
            # unreadable/garbage cartridge.json (ManifestInvalid). Both are
            # surfaced + logged, never hosted.
            if isinstance(e, CartridgeJsonRegistrySlugMismatch):
                kind = CartridgeAttachmentErrorKind.BAD_INSTALLATION
            else:
                kind = CartridgeAttachmentErrorKind.MANIFEST_INVALID
            logger.error(
                "cartridge.json invalid or mis-placed under slug '%s' (%s) — surfacing "
                "as incompatible: %s",
                expected_slug,
                version_dir,
                e,
            )
            discovered.append(
                DiscoveredCartridgeIncompatible(
                    version_dir=version_dir,
                    id=path_derived_name,
                    channel=identity.channel,
                    registry_url=identity.registry_url,
                    version=path_derived_version,
                    error=CartridgeAttachmentError(
                        kind=kind,
                        message=f"cartridge.json failed to load under slug '{expected_slug}': {e}",
                        detected_at_unix_seconds=detected_at,
                    ),
                )
            )
            continue

        cj_channel = CartridgeChannel(cj.channel)
        if cj_channel != identity.channel:
            discovered.append(
                DiscoveredCartridgeIncompatible(
                    version_dir=version_dir,
                    id=cj.name,
                    channel=cj_channel,
                    registry_url=cj.registry_url,
                    version=cj.version,
                    error=CartridgeAttachmentError(
                        kind=CartridgeAttachmentErrorKind.BAD_INSTALLATION,
                        message=(
                            f"Channel mismatch: cartridge declares '{cj.channel}' but host "
                            f"is pinned to '{identity.channel.value}'. Release and nightly "
                            f"artefacts must not mix."
                        ),
                        detected_at_unix_seconds=detected_at,
                    ),
                )
            )
            continue

        # NO registry pin: the host's baked registry does NOT restrict
        # which registries' cartridges are discovered. A self-consistent
        # cartridge (its registry_url hashes to its slug folder, validated
        # above) from any registry present on disk is accepted; whether its
        # version is actually LISTED upstream is the verdict layer's call,
        # applied after discovery.

        # Scheme check is per-cartridge: a dev cartridge (null registry_url)
        # never reaches here; a registry cartridge must use https
        # (dev_mode=False — the scheme relaxation only ever applied to
        # null-registry dev cartridges).
        if cj.registry_url is not None:
            scheme_result = validate_registry_url_scheme(cj.registry_url, False)
            if scheme_result.non_https_scheme is not None:
                discovered.append(
                    DiscoveredCartridgeIncompatible(
                        version_dir=version_dir,
                        id=cj.name,
                        channel=cj_channel,
                        registry_url=cj.registry_url,
                        version=cj.version,
                        error=CartridgeAttachmentError(
                            kind=CartridgeAttachmentErrorKind.INCOMPATIBLE,
                            message=(
                                f"registry_url uses '{scheme_result.non_https_scheme}' scheme, "
                                f"must be https in non-dev builds. Rebuild the cartridge with an "
                                f"https registry URL."
                            ),
                            detected_at_unix_seconds=detected_at,
                        ),
                    )
                )
                continue
            if scheme_result.not_a_url is not None:
                discovered.append(
                    DiscoveredCartridgeIncompatible(
                        version_dir=version_dir,
                        id=cj.name,
                        channel=cj_channel,
                        registry_url=cj.registry_url,
                        version=cj.version,
                        error=CartridgeAttachmentError(
                            kind=CartridgeAttachmentErrorKind.INCOMPATIBLE,
                            message=f"registry_url '{scheme_result.not_a_url}' is not a well-formed URL.",
                            detected_at_unix_seconds=detected_at,
                        ),
                    )
                )
                continue

        if cj.fabric_manifest_version != identity.fabric_manifest_version:
            discovered.append(
                DiscoveredCartridgeIncompatible(
                    version_dir=version_dir,
                    id=cj.name,
                    channel=cj_channel,
                    registry_url=cj.registry_url,
                    version=cj.version,
                    error=CartridgeAttachmentError(
                        kind=CartridgeAttachmentErrorKind.FABRIC_MANIFEST_VERSION_MISMATCH,
                        message=(
                            f"Cartridge built against fabric manifest version "
                            f"{cj.fabric_manifest_version}, but host is pinned to "
                            f"{identity.fabric_manifest_version}. Rebuild the cartridge with "
                            f"MFR_FABRIC_MANIFEST_VERSION={identity.fabric_manifest_version}."
                        ),
                        detected_at_unix_seconds=detected_at,
                    ),
                )
            )
            continue

        # Bundled-cartridge integrity. A cartridge marked
        # ``installed_from: bundle`` is shipped INSIDE this build, not
        # user-installed, and has no upstream registry to verify against —
        # so it needs its own integrity proof. Platform-split by necessity:
        #
        # - macOS: the OS code-signature IS the guard (notarized .app). A
        #   content hash would be re-broken by Apple's (re)signing, so macOS
        #   does NOT bake or verify hashes. We log that we are trusting the
        #   signature — an explicit, visible rule, not a silent skip.
        # - Linux/Windows: binaries are unsigned, so the integrity proof is a
        #   content hash baked into the build (BUNDLED_CARTRIDGE_HASHES). The
        #   on-disk directory must hash to the baked value; a mismatch or an
        #   entry absent from the baked set means the shipped cartridge was
        #   tampered with or the build failed to record it — surfaced
        #   incompatible + logged, never hosted.
        if cj.installed_from == CartridgeInstallSource.BUNDLE:
            if sys.platform == "darwin":
                logger.info(
                    "bundled cartridge integrity on macOS is the OS code-signature "
                    "(notarized .app); baked-hash verification is intentionally skipped: "
                    "%s (%s %s)",
                    version_dir,
                    cj.name,
                    cj.version,
                )
            else:
                reason = _verify_bundled_cartridge_hash(cj.name, cj.version, version_dir)
                if reason is not None:
                    logger.error(
                        "bundled cartridge hash verification failed (%s, %s %s) — "
                        "surfacing as incompatible: %s",
                        version_dir,
                        cj.name,
                        cj.version,
                        reason,
                    )
                    discovered.append(
                        DiscoveredCartridgeIncompatible(
                            version_dir=version_dir,
                            id=cj.name,
                            channel=cj_channel,
                            registry_url=cj.registry_url,
                            version=cj.version,
                            error=CartridgeAttachmentError(
                                kind=CartridgeAttachmentErrorKind.BAD_INSTALLATION,
                                message=f"bundled cartridge integrity check failed: {reason}",
                                detected_at_unix_seconds=detected_at,
                            ),
                        )
                    )
                    continue

        entry_point = cj.resolve_entry_point(version_dir)
        try:
            cap_groups = probe_cartridge_cap_groups(entry_point)
        except Exception as e:
            logger.error(
                "Failed to probe cartridge entry point (%s) — surfacing as incompatible: %s",
                version_dir,
                e,
            )
            discovered.append(
                DiscoveredCartridgeIncompatible(
                    version_dir=version_dir,
                    id=cj.name,
                    channel=cj_channel,
                    registry_url=cj.registry_url,
                    version=cj.version,
                    error=CartridgeAttachmentError(
                        kind=CartridgeAttachmentErrorKind.HANDSHAKE_FAILED,
                        message=f"HELLO handshake / cap discovery probe failed: {e}",
                        detected_at_unix_seconds=detected_at,
                    ),
                )
            )
            continue

        discovered.append(
            DiscoveredCartridgeDirectory(
                entry_point=entry_point,
                version_dir=version_dir,
                id=cj.name,
                channel=cj_channel,
                registry_url=cj.registry_url,
                version=cj.version,
                cap_groups=cap_groups,
            )
        )


def _verify_bundled_cartridge_hash(name: str, version: str, version_dir: Path) -> Optional[str]:
    """Verify a bundled cartridge's on-disk content against the hash baked
    into this build. ``None`` when the directory hashes to the expected
    value for ``(name, version)``; a reason string when the pair is absent
    from the baked set or the hash differs (tamper / corruption /
    unrecorded build).

    Non-macOS only: macOS bundled-cartridge integrity is the OS
    code-signature (see the discovery call site), so the host there
    neither bakes nor checks these hashes.
    """
    expected = bundled_cartridge_expected_hash(name, version)
    if expected is None:
        return (
            f"no baked hash for bundled cartridge {name} {version} — this build did not "
            f"record it (MFR_BUNDLED_CARTRIDGE_HASHES)"
        )
    try:
        actual = hash_cartridge_directory(version_dir)
    except Exception as e:
        return f"failed to hash bundled cartridge directory: {e}"
    if actual == expected:
        return None
    return (
        f"content hash mismatch — baked {expected}, on-disk {actual}; the shipped cartridge "
        f"differs from what this build was compiled to ship"
    )
