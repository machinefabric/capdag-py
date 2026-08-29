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

What this module does and does not do
-------------------------------------

It reads and applies a manifest. It does **not** verify the signature: this
mirror carries no chain verification (``release_cert.rs`` in the Rust library is
the only implementation of it), and a mirror that stubbed one would be worse
than a mirror that has none. The caller supplies a :class:`BundleProof`, and the
only way to get a proven one is to have proven it.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from capdag.bifaci.cartridge_json import hash_cartridge_directory

#: The ``format`` every bundle manifest carries. A manifest without exactly
#: this is refused rather than interpreted.
BUNDLE_MANIFEST_FORMAT = "capdag.bundle/v1"

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


@dataclass(frozen=True)
class BundleManifest:
    """What a build ships beside its executable."""

    format: str
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

    def check(self, name: str, version: str, version_dir: str) -> Optional[str]:
        """Hold one bundled cartridge to what this proof allows. ``None`` when
        it passes, the reason when it does not."""
        if self.manifest is None:
            return self.reason or "nothing proves the bundled cartridges under this root"
        entry = self.manifest.entry(name, version)
        if entry is None:
            return (
                f"the bundle manifest does not list {name} {version}; this build "
                "ships a cartridge it did not record"
            )
        try:
            actual = hash_cartridge_directory(version_dir)
        except OSError as e:
            return f"failed to hash bundled cartridge directory: {e}"
        if actual != entry.sha256:
            return (
                f"{name} {version} does not match the bundle manifest: recorded "
                f"{entry.sha256}, on disk {actual}"
            )
        return None


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


def read_bundle_manifest(bundled_root: str) -> Tuple[BundleManifest, bytes, str]:
    """Read and shape-check the manifest under a bundled-cartridges root.

    Does **not** verify the signature — the caller does that with a chain
    verifier this mirror does not have, and only then builds a proven
    :class:`BundleProof`. The signature file's presence IS checked: an unsigned
    manifest proves nothing, and reporting that here means a caller cannot
    forget to look.
    """
    manifest_path, sig_path = bundle_manifest_paths(bundled_root)
    try:
        with open(manifest_path, "rb") as handle:
            manifest_bytes = handle.read()
    except OSError as e:
        raise ValueError(
            f"no bundle manifest at {manifest_path} — this build shipped "
            f"cartridges it cannot vouch for: {e}"
        ) from e
    try:
        with open(sig_path, "r", encoding="utf-8") as handle:
            envelope = handle.read()
    except OSError as e:
        raise ValueError(
            f"no signature at {sig_path} — an unsigned bundle manifest proves nothing: {e}"
        ) from e

    try:
        raw = json.loads(manifest_bytes)
    except json.JSONDecodeError as e:
        raise ValueError(f"{manifest_path} is not a bundle manifest: {e}") from e
    fmt = raw.get("format")
    if fmt != BUNDLE_MANIFEST_FORMAT:
        raise ValueError(
            f"bundle manifest has format {fmt!r} (expected {BUNDLE_MANIFEST_FORMAT!r})"
        )
    manifest = BundleManifest(
        format=fmt,
        environment=raw.get("environment", ""),
        cartridges=[
            BundledCartridge(
                name=one.get("name", ""),
                version=one.get("version", ""),
                channel=one.get("channel", ""),
                sha256=one.get("sha256", ""),
            )
            for one in raw.get("cartridges", [])
        ],
    )
    return manifest, manifest_bytes, envelope
