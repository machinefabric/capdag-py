"""Shared cartridge discovery.

The on-disk scan + identity validation + HELLO probe that classifies each
installed cartridge version directory as attachable (``Directory``) or
``Incompatible``. A bundled cartridge is not probed: its build's signed bundle
manifest records what the probe would learn, and its bytes are held to that
manifest when a host starts it. This is the single source of truth used by
both the engine (for the bundled ``bundled-cartridges/`` tree next to its
binary) and the daemon (for the user-installed cartridge tree).

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
import time
from dataclasses import dataclass, field
from functools import cmp_to_key
from pathlib import Path
from typing import Any, List, Optional, Union

from capdag.bifaci.bundle_manifest import BundledCartridge, BundleError, BundleProof
from capdag.bifaci.cartridge_json import (
    CartridgeInstallSource,
    CartridgeJsonError,
    CartridgeJsonRegistryFolderMismatch,
    read_cartridge_json_from_dir,
)
from capdag.bifaci import launch
from capdag.bifaci.cartridge_repo import CartridgeChannel, compare_versions
from capdag.bifaci.charter import CharterError, RegistryFolder
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
    #: What proves the bundled cartridges under the root being scanned.
    #: Carried rather than looked up, because verification is one act per
    #: discovery and because the caller is the only thing that knows what this
    #: root IS: a build's own bundled-cartridges tree carries a verified
    #: manifest, and the operator's installed-cartridges directory carries
    #: ``BundleProof.none`` — so a cartridge claiming to be bundled while
    #: sitting there is refused for exactly that reason instead of being
    #: hosted because nobody asked.
    bundle: BundleProof



@dataclass(frozen=True)
class AttachTerms:
    """What a host holds a cartridge to before it attaches it, from what the
    cartridge's ``cartridge.json`` says: the part of a host's identity that
    :func:`admission` reads."""

    channel: CartridgeChannel
    fabric_manifest_version: int
    #: What proves a cartridge that says it was bundled; see
    #: :attr:`DiscoveryIdentity.bundle`.
    bundle: BundleProof

    @classmethod
    def of(cls, identity: "DiscoveryIdentity") -> "AttachTerms":
        """The terms the host ``identity`` attaches cartridges on."""
        return cls(
            channel=identity.channel,
            fabric_manifest_version=identity.fabric_manifest_version,
            bundle=identity.bundle,
        )


@dataclass(frozen=True)
class Refusal:
    """Why a host does not attach a cartridge."""

    kind: CartridgeAttachmentErrorKind
    message: str

    def at(self, detected_at_unix_seconds: int) -> CartridgeAttachmentError:
        """The refusal as the attachment error a roster carries."""
        return CartridgeAttachmentError(
            kind=self.kind,
            message=self.message,
            detected_at_unix_seconds=detected_at_unix_seconds,
        )


@dataclass(frozen=True)
class Admission:
    """How a host attaches a cartridge it does not refuse."""

    #: For a bundled cartridge, what its build's signed bundle manifest
    #: records of it, which it is attached as: its caps are the recorded ones,
    #: and a host holds its directory to the recorded hash each time it starts
    #: it (:func:`~capdag.bifaci.bundle_manifest.verify_content`). ``None`` for
    #: any other cartridge: nothing vouches for its caps, and the host learns
    #: them by starting it.
    bundled: Optional[BundledCartridge]


def admission(cj: Any, terms: AttachTerms) -> Union[Admission, Refusal]:
    """Whether, and how, a cartridge whose ``cartridge.json`` reads as ``cj``
    is attached under ``terms``: the :class:`Refusal` when it is not.

    The one rule every host decides by: discovery's roster and a run that
    attaches the installed cartridge a cap needs both call it, so a cartridge
    one of them refuses is never run by the other. It reads nothing on disk."""
    if CartridgeChannel(cj.channel) != terms.channel:
        return Refusal(
            kind=CartridgeAttachmentErrorKind.MISPLACED,
            message=(
                f"Channel mismatch: cartridge declares '{cj.channel}' but host "
                f"is pinned to '{terms.channel.value}'. Release and nightly "
                f"artefacts must not mix."
            ),
        )

    # NO registry pin: the host's baked registry does NOT restrict which
    # registries' cartridges are attached. Whether a version is actually
    # LISTED upstream is the verdict layer's call.

    bundled = cj.installed_from == CartridgeInstallSource.BUNDLE
    if cj.fabric_manifest_version != terms.fabric_manifest_version:
        ours = terms.fabric_manifest_version
        # What to do differs by where the cartridge came from, told as every
        # host tells it: ``installed_from: bundle`` is the one provenance with
        # meaning, and otherwise a registry_url is a registry install and none
        # a dev cartridge.
        if bundled:
            remedy = (
                "The build that bundled it is inconsistent: its bundle holds a "
                "cartridge for another fabric manifest."
            )
        elif cj.registry_url is not None:
            remedy = "Remove it and install it again from its registry."
        else:
            remedy = f"Rebuild it with MFR_FABRIC_MANIFEST_VERSION={ours} and install it again."
        return Refusal(
            kind=CartridgeAttachmentErrorKind.FABRIC_MANIFEST_VERSION_MISMATCH,
            message=(
                f"{cj.name} {cj.version} was installed for fabric manifest "
                f"{cj.fabric_manifest_version}, and this host reads fabric manifest "
                f"{ours}. {remedy}"
            ),
        )

    # A bundled cartridge. A cartridge marked `installed_from: bundle` is
    # shipped INSIDE this build, not user-installed, and has no upstream
    # registry to verify against — so it needs its own proof.
    #
    # ONE mechanism, on every platform: the build's signed bundle manifest.
    # The proof was established when this host started (see BundleProof);
    # here it is applied to the cartridge in hand. Apple's signature still
    # matters, and it is what stops the operating system warning a user; it
    # is not what decides whether code runs here.
    #
    # The manifest records what a probe would learn — the caps the cartridge
    # advertises, and the fabric manifest version it was built for — so the
    # cartridge is attached from that record without being started or hashed.
    if bundled:
        try:
            recorded = terms.bundle.admit(cj.name, cj.version, cj.channel)
        except BundleError as reason:
            return Refusal(
                kind=CartridgeAttachmentErrorKind.MISPLACED,
                message=f"bundled cartridge integrity check failed: {reason}",
            )
        # cartridge.json is outside the hash, so what it says of the fabric
        # was checked above only as far as it goes: the signed record is what
        # is believed.
        if recorded.fabric_manifest_version != terms.fabric_manifest_version:
            return Refusal(
                kind=CartridgeAttachmentErrorKind.FABRIC_MANIFEST_VERSION_MISMATCH,
                message=(
                    f"{cj.name} {cj.version} was built for fabric manifest "
                    f"{recorded.fabric_manifest_version}, as its build's signed bundle "
                    f"manifest records, and this host reads fabric manifest "
                    f"{terms.fabric_manifest_version}. The build that bundled it is "
                    f"inconsistent: its bundle holds a cartridge for another fabric manifest."
                ),
            )
        return Admission(bundled=recorded)

    return Admission(bundled=None)


def newest_version_dir(version_dirs: List[Path]) -> Optional[Path]:
    """The newest of a cartridge's installed version directories, by their
    names, in the order the registry gives versions (:func:`compare_versions`:
    dotted numbers compared as numbers, so ``1.174.0`` is newer than
    ``1.99.0``). Every host attaches this one and only this one, so what a
    roster shows for a cartridge is what a run uses. ``None`` for no
    directories."""
    if not version_dirs:
        return None
    return max(version_dirs, key=cmp_to_key(lambda a, b: compare_versions(a.name, b.name)))


@dataclass
class DiscoveredCartridgeDirectory:
    """A discovered cartridge that passed every identity check and whose caps
    are known: from its HELLO probe, or, for a bundled cartridge, from its
    build's signed bundle manifest. Its caps will be registered for
    dispatch."""

    entry_point: Path
    version_dir: Path
    id: str
    channel: CartridgeChannel
    registry_url: Optional[str]
    version: str
    cap_groups: List[Any]
    #: For a bundled cartridge, the directory hash its build's signed bundle
    #: manifest records; ``None`` for an installed or dev one.
    #:
    #: Discovery does not hash a bundled cartridge. A host holds its directory
    #: to this value each time it starts the cartridge
    #: (:func:`capdag.bifaci.bundle_manifest.verify_content`), and refuses to
    #: start one that was changed.
    bundle_sha256: Optional[str]


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
        # Through the launcher, because a dev cartridge's entry may be a
        # script and Windows cannot execute one. See `capdag.bifaci.launch`.
        child = subprocess.Popen(
            launch.command(path),
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
        # clean exit — then reap the process and release its pipes, so no
        # pipe outlives the probe. Bytes still buffered for a child that
        # already died cannot be delivered, and need not be: the probe is
        # over either way.
        try:
            child.kill()
        except Exception:
            pass
        child.wait()
        try:
            child.stdin.close()
        except BrokenPipeError:
            pass
        child.stdout.close()

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
    ``identity`` and probed (a bundled one is admitted from its build's signed
    bundle manifest instead); the result is the full classified roster
    (attachable + incompatible). An empty/absent scan root is not an
    error — it yields an empty roster. A real IO failure reading an
    existing scan root IS an error (it would otherwise masquerade as "no
    cartridges installed").

    Discovery scans EVERY registry folder present on disk — full parity
    with the reference host. The host's baked ``identity.registry_url``
    does NOT restrict which folders are scanned; each cartridge is instead
    validated in place against the registry folder it sits under, as the
    charter stored there names it (the charter rule), so a registry-installed cartridge, the reserved
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
        # The folder is what its stored charter names, never what its own
        # name says. A folder whose charter is missing or refused still has
        # its cartridges surfaced — each as misplaced, with the reason — so
        # the operator sees what is there and why none of it runs.
        try:
            folder: Optional[RegistryFolder] = RegistryFolder.open(slug_dir)
            folder_error: Optional[CharterError] = None
        except CharterError as e:
            folder, folder_error = None, e
        # {slug}/v{cartridge_registry_version}/{channel}/… — the registry regime
        # version is a path level pinned to the host's version (like channel).
        scan_root = slug_dir / f"v{identity.cartridge_registry_version}" / identity.channel.value
        if not scan_root.is_dir():
            # This slug has no subtree for the host's (version, channel) — skip.
            continue
        _scan_channel_root(scan_root, slug_dir, folder, folder_error, identity, discovered)

    return discovered


def _scan_channel_root(
    scan_root: Path,
    slug_dir: Path,
    folder: Optional[RegistryFolder],
    folder_error: Optional[CharterError],
    identity: DiscoveryIdentity,
    discovered: List[DiscoveredCartridge],
) -> None:
    """Scan one ``{slug}/{channel}/`` root: classify each cartridge name
    directory's newest version against the host identity and the registry
    folder it sits under — opened through the charter stored in it, or
    ``folder_error`` why it could not be. Appends results to
    ``discovered``."""
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

        version_dir = newest_version_dir(version_dirs)

        path_derived_name = name_dir.name or "unknown"
        path_derived_version = version_dir.name or "unknown"
        detected_at = _unix_seconds_now()

        # A folder with no charter that reads makes every cartridge in it
        # misplaced, for the charter's reason.
        if folder is None:
            logger.error(
                "registry folder %s has no charter that reads (%s) — surfacing as "
                "incompatible: %s",
                slug_dir,
                version_dir,
                folder_error,
            )
            discovered.append(
                DiscoveredCartridgeIncompatible(
                    version_dir=version_dir,
                    id=path_derived_name,
                    channel=identity.channel,
                    registry_url=identity.registry_url,
                    version=path_derived_version,
                    error=CartridgeAttachmentError(
                        kind=CartridgeAttachmentErrorKind.MISPLACED,
                        message=f"the registry folder {slug_dir} has no charter that reads: {folder_error}",
                        detected_at_unix_seconds=detected_at,
                    ),
                )
            )
            continue

        # ``read_cartridge_json_from_dir`` enforces the charter rule against
        # the folder the cartridge ACTUALLY sits in: its declared registry_url
        # must be the folder's anchor. A non-null registry_url under ``dev/``,
        # or another registry's anchor, fails here as misplaced — surfaced
        # incompatible and logged, never hosted. A null registry_url is valid
        # only under the reserved ``dev/`` slot.
        try:
            cj = read_cartridge_json_from_dir(version_dir, folder)
        except CartridgeJsonError as e:
            # A folder mismatch is a bad INSTALL CONTEXT, distinct from an
            # unreadable/garbage cartridge.json (ManifestInvalid). Both are
            # surfaced + logged, never hosted.
            if isinstance(e, CartridgeJsonRegistryFolderMismatch):
                kind = CartridgeAttachmentErrorKind.MISPLACED
            else:
                kind = CartridgeAttachmentErrorKind.MANIFEST_INVALID
            logger.error(
                "cartridge.json invalid or mis-placed in the registry folder '%s' (%s) — "
                "surfacing as incompatible: %s",
                folder.slug,
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
                        message=f"cartridge.json failed to load in the registry folder '{folder.slug}': {e}",
                        detected_at_unix_seconds=detected_at,
                    ),
                )
            )
            continue

        admitted = admission(cj, AttachTerms.of(identity))
        if isinstance(admitted, Refusal):
            refused = admitted
            logger.error(
                "cartridge refused (%s, %s %s) — surfacing as incompatible: %s",
                version_dir,
                cj.name,
                cj.version,
                refused.message,
            )
            discovered.append(
                DiscoveredCartridgeIncompatible(
                    version_dir=version_dir,
                    id=cj.name,
                    channel=CartridgeChannel(cj.channel),
                    registry_url=cj.registry_url,
                    version=cj.version,
                    error=refused.at(detected_at),
                )
            )
            continue

        cj_channel = CartridgeChannel(cj.channel)
        # A bundled cartridge is neither started nor hashed here: its build's
        # signed bundle manifest records the caps a probe would learn, and a
        # host holds its bytes to the recorded hash when it starts it, which
        # is when they are about to run.
        if admitted.bundled is not None:
            discovered.append(
                DiscoveredCartridgeDirectory(
                    entry_point=cj.resolve_entry_point(version_dir),
                    version_dir=version_dir,
                    id=cj.name,
                    channel=cj_channel,
                    registry_url=cj.registry_url,
                    version=cj.version,
                    # The wire shape a HELLO probe yields, so a bundled
                    # cartridge's caps reach the host as a probed one's do.
                    cap_groups=[group.to_dict() for group in admitted.bundled.cap_groups],
                    bundle_sha256=admitted.bundled.sha256,
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
                bundle_sha256=None,
            )
        )


