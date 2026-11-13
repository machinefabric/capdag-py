"""The signed manifest a build ships beside its bundled cartridges.

What this replaces, and why
---------------------------

Bundled cartridges — the ones shipped inside a build's own
``bundled-cartridges/`` tree — have no upstream registry to verify against, so
they need their own integrity proof. That proof used to be a content hash baked
into the build, and it was **disabled on macOS**: the distribution step
re-signs every cartridge when it seals the ``.app``, which rewrites their bytes
long after the build recorded them, so a baked hash could not survive. macOS was
left trusting Gatekeeper instead.

That made Apple's signature the load-bearing check on one platform and ours the
load-bearing check on the others. It is the wrong way round: Apple's signature
is what stops the operating system warning a user; OUR chain is what decides
whether code runs, and it has to say the same thing everywhere.

So the proof is a signed manifest — ``bundle.json`` with a ``bundle.json.sig``
envelope beside it — produced at the END of a build, after every platform
signing step. There is no ordering problem left to have.

What a host learns from it, and when it checks the bytes
--------------------------------------------------------

Each entry records, under the signature, everything discovery decides from:
the cartridge's directory hash, the fabric manifest version it was built
against, and the cap groups it advertises in its HELLO (recorded by the build,
which starts each cartridge once to ask). So discovering a bundle reads one
signed file: it neither hashes a cartridge nor starts one, and a command that
lists or plans pays for no cartridge it does not run.

The bytes are checked when they matter, which is when a host starts a
cartridge: its directory is hashed and held to the recorded value each time it
is spawned, and a cartridge that was changed is refused there, by name
(:func:`verify_content`). Checking at the spawn rather than at discovery also
closes the gap between the two, during which a checked cartridge could be
replaced before it ran.

What this module does and does not do
-------------------------------------

It reads and applies a manifest. It does **not** verify the signature: this
mirror carries no chain verification (``release_cert.rs`` in the Rust library is
the only implementation of it), and a mirror that stubbed one would be worse
than a mirror that has none. The order is the reference's: the caller reads
the bytes (:func:`read_bundle_manifest`), verifies the signature over exactly
those bytes, and only then parses them (:func:`parse_verified`) and builds a
:class:`BundleProof` from the result. The only way to get a proven one is to
have proven it.

It does not write a manifest either: the build writes it, through the
reference library, so the thing that writes the manifest and the thing that
checks it hash the same way by construction.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Tuple, Union

from capdag.bifaci.cartridge_json import hash_cartridge_directory
from capdag.bifaci.manifest import CapGroup

#: The ``format`` every bundle manifest carries. A manifest without exactly
#: this is refused rather than interpreted: the shape is the contract between
#: the build that writes it and the runtime that reads it.
BUNDLE_MANIFEST_FORMAT = "capdag.bundle/v2"

#: The manifest's name inside the bundled-cartridges root.
BUNDLE_MANIFEST_FILE = "bundle.json"

#: The signature envelope's name, beside the manifest.
BUNDLE_MANIFEST_SIG_FILE = "bundle.json.sig"


@dataclass(frozen=True)
class BundledCartridge:
    """One cartridge a build ships."""

    name: str
    version: str
    #: ``release`` or ``nightly``. Stated so a manifest cannot vouch for a
    #: cartridge from the other channel.
    channel: str
    #: The directory hash, as :func:`hash_cartridge_directory` computes it —
    #: sorted relative paths and file contents, ``cartridge.json`` excluded.
    #: That exclusion is what lets a build write the manifest without changing
    #: what the manifest attests.
    sha256: str
    #: The fabric manifest version the cartridge was built against.
    #:
    #: Its ``cartridge.json`` states it too, but that file is outside the hash;
    #: recorded here it is signed, and a host pinned to another version refuses
    #: the cartridge without starting it.
    fabric_manifest_version: int
    #: The cap groups the cartridge advertises in its HELLO, as the build read
    #: them by starting it. Discovery takes them from here instead of starting
    #: every bundled cartridge to ask again; they are a function of the bytes
    #: :attr:`sha256` covers, which are checked before the cartridge runs.
    cap_groups: List[CapGroup]


class BundleError(Exception):
    """Why a bundled cartridge could not be proven.

    Every subclass is a refusal. There is no advisory state and no "verified
    except" — a bundled cartridge either has a chain that reaches the roots
    this build trusts, or it does not run. Mirrors the reference
    ``BundleError``.
    """


class BundleRefused(BundleError):
    """Nothing under this root can vouch for a bundled cartridge; the message
    is the reason the :class:`BundleProof` carries."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class BundleMissing(BundleError):
    def __init__(self, path: str):
        super().__init__(
            f"no bundle manifest at {path} — this build shipped cartridges it cannot vouch for"
        )
        self.path = path


class BundleUnsigned(BundleError):
    def __init__(self, path: str):
        super().__init__(f"no signature at {path} — an unsigned bundle manifest proves nothing")
        self.path = path


class BundleUnreadable(BundleError):
    def __init__(self, path: str, cause: Exception):
        super().__init__(f"cannot read {path}: {cause}")
        self.path = path
        self.cause = cause


class BundleMalformed(BundleError):
    def __init__(self, path: str, reason: str):
        super().__init__(f"{path} is not a bundle manifest: {reason}")
        self.path = path
        self.reason = reason


class BundleUnsupportedFormat(BundleError):
    def __init__(self, found: str):
        super().__init__(
            f"bundle manifest has format '{found}' (expected '{BUNDLE_MANIFEST_FORMAT}')"
        )
        self.found = found


class BundleWrongEnvironment(BundleError):
    def __init__(self, manifest: str, build: str):
        super().__init__(
            f"bundle manifest was built for the '{manifest}' signing environment and this "
            f"build is '{build}'"
        )
        self.manifest = manifest
        self.build = build


class BundleNotListed(BundleError):
    def __init__(self, name: str, version: str):
        super().__init__(
            f"the bundle manifest does not list {name} {version}; this build ships a "
            "cartridge it did not record"
        )
        self.name = name
        self.version = version


class BundleWrongChannel(BundleError):
    def __init__(self, name: str, version: str, recorded: str, found: str):
        super().__init__(
            f"the bundle manifest records {name} {version} for the '{recorded}' channel, "
            f"and this cartridge is on the '{found}' channel"
        )
        self.name = name
        self.version = version
        self.recorded = recorded
        self.found = found


class BundleContentMismatch(BundleError):
    def __init__(self, directory: str, name: str, version: str, expected: str, actual: str):
        super().__init__(
            f"the bundled cartridge {name} {version} was changed after its build recorded "
            f"it, so it is not started: its directory {directory} hashes to {actual}, and "
            f"the build's signed bundle manifest records {expected}. Reinstall the "
            "application it is bundled with"
        )
        self.directory = directory
        self.name = name
        self.version = version
        self.expected = expected
        self.actual = actual


@dataclass(frozen=True)
class BundleManifest:
    """What a build ships beside its executable."""

    format: str
    #: The signing environment this bundle was built for. Checked against the
    #: build's own (:func:`parse_verified`), so a staging bundle cannot be
    #: believed by a prod build even under valid signatures.
    environment: str
    cartridges: List[BundledCartridge] = field(default_factory=list)

    @staticmethod
    def create(environment: str, cartridges: List[BundledCartridge]) -> "BundleManifest":
        """A manifest in a stable order, so the same tree produces the same
        bytes and therefore the same signature."""
        return BundleManifest(
            format=BUNDLE_MANIFEST_FORMAT,
            environment=environment,
            cartridges=sorted(cartridges, key=lambda one: (one.name, one.version)),
        )

    def entry(self, name: str, version: str) -> Optional[BundledCartridge]:
        """What this manifest says about one cartridge, if it says anything."""
        for one in self.cartridges:
            if one.name == name and one.version == version:
                return one
        return None

    def admit(self, name: str, version: str, channel: str) -> BundledCartridge:
        """The entry for one bundled cartridge, held to the channel it is on.

        Unlisted, or listed at another version, is a cartridge the build did
        not record — a stale copy left from an earlier build among them
        (:class:`BundleNotListed`). Listed for the other channel is a manifest
        vouching for an artefact it did not describe
        (:class:`BundleWrongChannel`).
        """
        entry = self.entry(name, version)
        if entry is None:
            raise BundleNotListed(name, version)
        if entry.channel != channel:
            raise BundleWrongChannel(name, version, entry.channel, channel)
        return entry


@dataclass(frozen=True)
class BundleProof:
    """What a discovery run knows about the bundle it is scanning.

    Carried rather than looked up. Verification is one act per discovery — a
    chain check per cartridge would do the same work repeatedly and give as
    many chances to disagree — and making it a value means the thing that
    *loads* a manifest and the thing that *uses* one are separable.
    """

    manifest: Optional[BundleManifest] = None
    #: Why nothing can be proven, when ``manifest`` is ``None``.
    reason: str = ""

    @staticmethod
    def none(reason: str) -> "BundleProof":
        """A root that ships no bundle at all.

        The operator's installed-cartridges directory is one: nothing there was
        put there by a build, so a cartridge claiming to be bundled is in the
        wrong place and is refused saying so.
        """
        return BundleProof(manifest=None, reason=reason)

    @staticmethod
    def proven(manifest: BundleManifest) -> "BundleProof":
        """A root whose bundled cartridges are held to ``manifest``.

        Only a caller that has verified the manifest's signature may construct
        this. This module cannot: it carries no chain verification, and
        stubbing one would turn a refusal into a pass.
        """
        return BundleProof(manifest=manifest, reason="")

    def admit(self, name: str, version: str, channel: str) -> BundledCartridge:
        """What this proof records about one bundled cartridge, which
        discovery takes its caps and its fabric manifest version from.

        Reads nothing on disk. The cartridge's bytes are held to the recorded
        hash when a host starts it (:func:`verify_content`), not here. Raises
        :class:`BundleRefused` with this proof's reason when it proves nothing,
        and what :meth:`BundleManifest.admit` raises otherwise.
        """
        if self.manifest is None:
            raise BundleRefused(self.reason or "nothing proves the bundled cartridges under this root")
        return self.manifest.admit(name, version, channel)


def bundle_manifest_paths(bundled_root: str) -> Tuple[str, str]:
    """Where the manifest and its signature live under a bundled-cartridges
    root."""
    return (
        os.path.join(bundled_root, BUNDLE_MANIFEST_FILE),
        os.path.join(bundled_root, BUNDLE_MANIFEST_SIG_FILE),
    )


def is_bundle_manifest_file(file_name: str) -> bool:
    """Whether a name in a bundled-cartridges root belongs to this mechanism.

    Discovery reports unmanaged files in that directory; these two are managed,
    and a warning about them on every startup would train an operator to ignore
    the one that matters.
    """
    return file_name in (BUNDLE_MANIFEST_FILE, BUNDLE_MANIFEST_SIG_FILE)


def read_bundle_manifest(bundled_root: str) -> Tuple[bytes, str]:
    """Read the manifest's exact bytes and its signature envelope under a
    bundled-cartridges root.

    Believes nothing in them. The caller verifies the envelope over exactly
    these bytes, with a chain verifier this mirror does not have, and only
    then parses them with :func:`parse_verified` — parsing first and verifying
    second would mean acting on an attacker's document for as long as it took
    to decide not to. The signature file's presence IS checked here: an
    unsigned manifest proves nothing, and reporting that here means a caller
    cannot forget to look.
    """
    manifest_path, sig_path = bundle_manifest_paths(bundled_root)
    if not os.path.isfile(manifest_path):
        raise BundleMissing(manifest_path)
    if not os.path.isfile(sig_path):
        raise BundleUnsigned(sig_path)
    try:
        with open(manifest_path, "rb") as handle:
            manifest_bytes = handle.read()
    except OSError as e:
        raise BundleUnreadable(manifest_path, e) from e
    try:
        with open(sig_path, "r", encoding="utf-8") as handle:
            envelope = handle.read()
    except (OSError, UnicodeDecodeError) as e:
        raise BundleUnreadable(sig_path, e) from e
    return manifest_bytes, envelope


def _field(raw: Any, key: str, kind: Union[type, Tuple[type, ...]], where: str) -> Any:
    """One required field of the document, of the type the format declares."""
    if not isinstance(raw, dict):
        raise ValueError(f"{where} is not an object")
    if key not in raw:
        raise ValueError(f"{where} has no '{key}'")
    value = raw[key]
    if not isinstance(value, kind) or isinstance(value, bool):
        raise ValueError(f"{where}'s '{key}' is not a {getattr(kind, '__name__', kind)}")
    return value


def _bundled_cartridge(raw: Any, index: int) -> BundledCartridge:
    where = f"cartridges[{index}]"
    fabric_manifest_version = _field(raw, "fabric_manifest_version", int, where)
    if not 0 <= fabric_manifest_version <= 0xFFFFFFFF:
        raise ValueError(f"{where}'s 'fabric_manifest_version' {fabric_manifest_version} is out of range")
    cap_groups = _field(raw, "cap_groups", list, where)
    return BundledCartridge(
        name=_field(raw, "name", str, where),
        version=_field(raw, "version", str, where),
        channel=_field(raw, "channel", str, where),
        sha256=_field(raw, "sha256", str, where),
        fabric_manifest_version=fabric_manifest_version,
        cap_groups=[CapGroup.from_dict(group) for group in cap_groups],
    )


def parse_verified(
    manifest_bytes: bytes, path: Union[str, Path], build_environment: str
) -> BundleManifest:
    """The document a verified signature covers, held to this format, this
    build's environment, and the cap definition rules.

    The format is read first and on its own, so a manifest in another format
    — an earlier one included; none is read — is refused for being one
    (:class:`BundleUnsupportedFormat`), rather than as a document that fails
    to parse. The environment the manifest SAYS is pinned to the build's, so a
    manifest signed for one environment cannot claim to describe another. And
    the recorded caps cross from the cartridge that advertised them to every
    host that reads them here, so they are held to the definition rules as an
    advertised manifest is (``CapManifest.from_advertised``).
    """
    path = str(path)
    try:
        raw = json.loads(manifest_bytes)
        found = _field(raw, "format", str, "the manifest")
    except ValueError as e:
        raise BundleMalformed(path, str(e)) from e
    if found != BUNDLE_MANIFEST_FORMAT:
        raise BundleUnsupportedFormat(found)
    try:
        manifest = BundleManifest(
            format=found,
            environment=_field(raw, "environment", str, "the manifest"),
            cartridges=[
                _bundled_cartridge(one, index)
                for index, one in enumerate(_field(raw, "cartridges", list, "the manifest"))
            ],
        )
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise BundleMalformed(path, str(e)) from e
    if manifest.environment != build_environment:
        raise BundleWrongEnvironment(manifest.environment, build_environment)

    from capdag.cap.validation import ValidationError, validate_cap_definition

    for cartridge in manifest.cartridges:
        for group in cartridge.cap_groups:
            for cap in group.caps:
                try:
                    validate_cap_definition(cap)
                except ValidationError as e:
                    raise BundleMalformed(path, f"{cartridge.name} {cartridge.version}: {e}") from e
    return manifest


def verify_content(name: str, version: str, version_dir: Union[str, Path], recorded: str) -> None:
    """Hold a bundled cartridge's directory to the hash its build recorded.

    A host calls this each time it starts a bundled cartridge, which is the
    moment the bytes are about to run. Raises :class:`BundleContentMismatch`
    naming the cartridge and its directory when they differ, and
    :class:`BundleUnreadable` when the directory cannot be hashed.
    """
    try:
        actual = hash_cartridge_directory(Path(version_dir))
    except OSError as e:
        raise BundleUnreadable(str(version_dir), e) from e
    if actual != recorded:
        raise BundleContentMismatch(str(version_dir), name, version, recorded, actual)
