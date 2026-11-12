"""Tests for shared cartridge discovery — mirroring capdag's
``cartridge_discovery`` tests.

Test numbers match the reference (4-digit-padded). The fixtures install a
``cartridge.json`` plus an executable ``#!/bin/sh exit 0`` stub entry that
satisfies ``read_from_dir`` but cannot complete a HELLO handshake, so a
cartridge that reaches the probe ends at HANDSHAKE_FAILED — that is how the
scan-all tests prove discovery REACHED a cartridge (vs. rejecting it
earlier with MISPLACED).
"""

import stat
import sys

import pytest

from capdag.bifaci.cartridge_discovery import (
    DiscoveredCartridgeDirectory,
    DiscoveredCartridgeIncompatible,
    DiscoveryIdentity,
    discover_cartridges,
)
from capdag.bifaci.bundle_manifest import BundleManifest, BundledCartridge, BundleProof
from capdag.bifaci.cartridge_repo import CARTRIDGE_REGISTRY_VERSION, CartridgeChannel
from capdag.bifaci.manifest import CapGroup
from capdag.cap.definition import Cap
from capdag.standard.caps import CAP_IDENTITY
from capdag.urn.cap_urn import CapUrn
from capdag.bifaci.relay_switch import CartridgeAttachmentErrorKind
from tests.charter_fixtures import (
    CARTRIDGES_ANCHOR,
    CARTRIDGES_SLUG,
    cartridges_charter,
    store_test_charter,
)


def _nightly_dev_identity() -> DiscoveryIdentity:
    return DiscoveryIdentity(
        channel=CartridgeChannel.NIGHTLY,
        registry_url=None,
        fabric_manifest_version=1,
        cartridge_registry_version=CARTRIDGE_REGISTRY_VERSION,
        # A root that ships no bundle. Every test that is not ABOUT the bundle
        # scans a tree nothing built, so a cartridge claiming to be bundled
        # there is in the wrong place — which is what this says.
        bundle=BundleProof.none("this directory is not a build's bundle"),
    )


def _bundled_identity(manifest: BundleManifest) -> DiscoveryIdentity:
    """An identity whose bundled cartridges are proven by ``manifest``.

    Built here rather than verified, because what is under test is what
    discovery DOES with a proof. This mirror carries no chain verification at
    all — the Rust library is the only implementation of it — which is exactly
    why the proof is a parameter.
    """
    identity = _nightly_dev_identity()
    return DiscoveryIdentity(
        channel=identity.channel,
        registry_url=identity.registry_url,
        fabric_manifest_version=identity.fabric_manifest_version,
        cartridge_registry_version=identity.cartridge_registry_version,
        bundle=BundleProof.proven(manifest),
    )


def _install_fixture(root, slug, channel_folder, name, version, cartridge_json, entry):
    """Lay down {root}/{slug}/v{CARTRIDGE_REGISTRY_VERSION}/{channel_folder}/{name}/{version}/
    — the version level pins to the host build's registry version, exactly where
    discovery scans. When ``cartridge_json`` is not None, also write it plus an
    executable ``entry`` stub so ``read_from_dir`` accepts the directory and
    discovery reaches its own identity checks."""
    d = root / slug / f"v{CARTRIDGE_REGISTRY_VERSION}" / channel_folder / name / version
    d.mkdir(parents=True, exist_ok=True)
    if cartridge_json is not None:
        (d / "cartridge.json").write_text(cartridge_json, encoding="utf-8")
        entry_path = d / entry
        entry_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        entry_path.chmod(entry_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _dev_cartridge_json(channel, fabric_manifest_version):
    return (
        '{"name":"cart","version":"1.0.0","channel":"%s","registry_url":null,'
        '"entry":"cart","installed_at":"2024-01-01T00:00:00Z",'
        '"fabric_manifest_version":%d}' % (channel, fabric_manifest_version)
    )


def _registry_cartridge_json(url, channel, fmv):
    return (
        '{"name":"cart","version":"1.0.0","channel":"%s","registry_url":"%s",'
        '"entry":"cart","installed_at":"2024-01-01T00:00:00Z",'
        '"fabric_manifest_version":%d}' % (channel, url, fmv)
    )


def _expect_incompatible(out, kind):
    assert len(out) == 1, f"expected exactly one discovered entry, got {out!r}"
    entry = out[0]
    assert isinstance(entry, DiscoveredCartridgeIncompatible), (
        f"expected Incompatible({kind}), got {entry!r}"
    )
    assert entry.error.kind == kind, f"wrong attachment-error kind: {entry.error.message}"


# TEST90: Absent scan root yields empty roster
def test_0090_absent_scan_root_yields_empty_roster(tmp_path):
    out = discover_cartridges(tmp_path / "nope", _nightly_dev_identity())
    assert out == [], "no install tree must be an empty roster, not an error"


# TEST91: Missing cartridge json is manifest invalid
def test_0091_missing_cartridge_json_is_manifest_invalid(tmp_path):
    _install_fixture(tmp_path, "dev", "nightly", "cart", "1.0.0", None, "cart")
    out = discover_cartridges(tmp_path, _nightly_dev_identity())
    _expect_incompatible(out, CartridgeAttachmentErrorKind.MANIFEST_INVALID)


# TEST92: Channel mismatch is a misplaced install
def test_0092_channel_mismatch_is_misplaced(tmp_path):
    # Declares release but lives under nightly/ — host is nightly.
    json_str = _dev_cartridge_json("release", 1)
    _install_fixture(tmp_path, "dev", "nightly", "cart", "1.0.0", json_str, "cart")
    out = discover_cartridges(tmp_path, _nightly_dev_identity())
    _expect_incompatible(out, CartridgeAttachmentErrorKind.MISPLACED)


# TEST94: Fabric manifest mismatch is flagged
def test_0094_fabric_manifest_mismatch_is_flagged(tmp_path):
    json_str = _dev_cartridge_json("nightly", 999)
    _install_fixture(tmp_path, "dev", "nightly", "cart", "1.0.0", json_str, "cart")
    out = discover_cartridges(tmp_path, _nightly_dev_identity())
    _expect_incompatible(out, CartridgeAttachmentErrorKind.FABRIC_MANIFEST_VERSION_MISMATCH)


# TEST120: Registry url under dev slug is rejected
def test_0120_registry_url_under_dev_slug_is_rejected(tmp_path):
    # A non-null registry_url placed under the reserved dev folder violates
    # the charter rule — read_from_dir rejects it as a bad install context
    # (Misplaced), surfaced + logged, never hosted.
    json_str = (
        '{"name":"cart","version":"1.0.0","channel":"nightly",'
        '"registry_url":"https://registry.example/cartridges",'
        '"entry":"cart","installed_at":"2024-01-01T00:00:00Z",'
        '"fabric_manifest_version":1}'
    )
    _install_fixture(tmp_path, "dev", "nightly", "cart", "1.0.0", json_str, "cart")
    out = discover_cartridges(tmp_path, _nightly_dev_identity())
    _expect_incompatible(out, CartridgeAttachmentErrorKind.MISPLACED)


# TEST1875: scan-all — a chartered registry folder AND the dev slot present on disk are BOTH scanned, regardless of the host's own baked registry. The dev cartridge (null registry under dev/) and the registry cartridge (its url the anchor of its folder's charter) each reach their probe. Both fixtures lack a real bifaci binary, so both end at HandshakeFailed — proving discovery REACHED them (was not filtered out by a registry pin), which is the behavior under test. A registry-pin rejection would instead surface BadInstallation and never probe.
def test_1875_scan_all_reaches_both_dev_and_registry_slugs(tmp_path):
    store_test_charter(tmp_path, CARTRIDGES_SLUG)
    url = CARTRIDGES_ANCHOR
    rslug = CARTRIDGES_SLUG
    # Host baked for a DIFFERENT registry than the on-disk registry cartridge.
    base = _nightly_dev_identity()
    host = DiscoveryIdentity(
        channel=base.channel,
        registry_url="https://other.example.com/cartridges",
        fabric_manifest_version=base.fabric_manifest_version,
        cartridge_registry_version=base.cartridge_registry_version,
        bundle=base.bundle,
    )
    _install_fixture(
        tmp_path, "dev", "nightly", "devcart", "1.0.0",
        _dev_cartridge_json("nightly", 1), "cart",
    )
    _install_fixture(
        tmp_path, rslug, "nightly", "regcart", "1.0.0",
        _registry_cartridge_json(url, "nightly", 1), "cart",
    )
    out = discover_cartridges(tmp_path, host)
    assert len(out) == 2, f"both slugs must be scanned, got: {out!r}"
    for c in out:
        assert isinstance(c, DiscoveredCartridgeIncompatible), (
            f"expected probe-stage Incompatible, got {c!r}"
        )
        assert c.error.kind == CartridgeAttachmentErrorKind.HANDSHAKE_FAILED, (
            f"both reached the probe (not registry-pin-rejected): {c.error.message}"
        )


# TEST1876: only the host's channel subtree is scanned. A cartridge under a slug's `release/` folder is invisible to a nightly host even though the slug folder is present (its `nightly/` subtree is absent).
def test_1876_other_channel_subtree_is_skipped(tmp_path):
    store_test_charter(tmp_path, CARTRIDGES_SLUG)
    url = CARTRIDGES_ANCHOR
    rslug = CARTRIDGES_SLUG
    _install_fixture(
        tmp_path, rslug, "release", "regcart", "1.0.0",
        _registry_cartridge_json(url, "release", 1), "cart",
    )
    out = discover_cartridges(tmp_path, _nightly_dev_identity())
    assert out == [], (
        f"a release-only slug must be invisible to a nightly host, got: {out!r}"
    )


# TEST1877: a registry cartridge hand-copied into the folder of ANOTHER registry fails the charter rule (Misplaced) — scan-all does not mean "accept anywhere", placement must still be self-consistent.
def test_1877_registry_cartridge_under_wrong_slug_is_bad_install(tmp_path):
    store_test_charter(tmp_path, CARTRIDGES_SLUG)
    json_str = _registry_cartridge_json("https://somewhere-else.example/cartridges", "nightly", 1)
    _install_fixture(tmp_path, CARTRIDGES_SLUG, "nightly", "cart", "1.0.0", json_str, "cart")
    out = discover_cartridges(tmp_path, _nightly_dev_identity())
    _expect_incompatible(out, CartridgeAttachmentErrorKind.MISPLACED)


# TEST12923: a registry folder is what its stored charter proves, never what its name says. The same cartridge, recording the same anchor, is misplaced in a folder with no charter and in a folder whose charter is stored under another name; it reaches its probe only in the folder its charter names.
def test_12923_a_registry_folder_is_proven_by_its_charter_not_its_name(tmp_path):
    json_str = _registry_cartridge_json(CARTRIDGES_ANCHOR, "nightly", 1)

    # A folder named for the registry, holding no charter.
    unchartered = tmp_path / "unchartered"
    _install_fixture(unchartered, CARTRIDGES_SLUG, "nightly", "cart", "1.0.0", json_str, "cart")
    out = discover_cartridges(unchartered, _nightly_dev_identity())
    _expect_incompatible(out, CartridgeAttachmentErrorKind.MISPLACED)
    assert "no charter that reads" in out[0].error.message

    # The registry's charter, stored in a folder of another name.
    renamed = tmp_path / "renamed"
    store_test_charter(renamed, "cartridges.example.com", cartridges_charter())
    _install_fixture(renamed, "cartridges.example.com", "nightly", "cart", "1.0.0", json_str, "cart")
    out = discover_cartridges(renamed, _nightly_dev_identity())
    _expect_incompatible(out, CartridgeAttachmentErrorKind.MISPLACED)

    # Its charter, in the folder the charter names: placement holds, and
    # discovery goes on to probe the (fake) binary.
    placed = tmp_path / "placed"
    store_test_charter(placed, CARTRIDGES_SLUG)
    _install_fixture(placed, CARTRIDGES_SLUG, "nightly", "cart", "1.0.0", json_str, "cart")
    out = discover_cartridges(placed, _nightly_dev_identity())
    _expect_incompatible(out, CartridgeAttachmentErrorKind.HANDSHAKE_FAILED)


def _bundled_cartridge_json() -> str:
    """The cartridge.json of a bundled cartridge in the dev slot: placement is
    self-consistent (null registry -> dev slug), so it passes every earlier
    check and reaches the bundled-integrity gate."""
    return (
        '{"name":"cart","version":"1.0.0","channel":"nightly","registry_url":null,'
        '"entry":"cart","installed_at":"2024-01-01T00:00:00Z",'
        '"installed_from":"bundle","fabric_manifest_version":1}'
    )


# TEST1878: a bundled cartridge in a root that proves nothing is refused — on
# every platform.
#
# This is the check macOS did not have. The old rule was platform-split: Linux
# and Windows verified a baked content hash and macOS verified nothing of ours,
# trusting Gatekeeper instead — so this test skipped itself on darwin. It runs
# everywhere now because the guard does.
def test_1878_a_bundled_cartridge_is_refused_where_nothing_proves_it(tmp_path):
    _install_fixture(
        tmp_path, "dev", "nightly", "cart", "1.0.0", _bundled_cartridge_json(), "cart"
    )
    out = discover_cartridges(tmp_path, _nightly_dev_identity())
    _expect_incompatible(out, CartridgeAttachmentErrorKind.MISPLACED)
    entry = out[0]
    assert "bundled cartridge integrity" in entry.error.message, (
        f"message should name the bundled-integrity failure: {entry.error.message}"
    )


def _recorded_cap_groups():
    """The cap groups a build recorded for the fixture cartridge: one cap,
    which discovery must hand back as recorded."""
    identity = CapUrn.from_string(CAP_IDENTITY)
    return [CapGroup(name="cart", caps=[Cap(identity, "Identity", ["identity"])])]


def _recorded(sha256: str, fabric_manifest_version: int) -> BundleManifest:
    """A manifest recording the fixture cartridge at ``sha256``, built for
    fabric manifest version ``fabric_manifest_version``."""
    return BundleManifest.create(
        "dev",
        [
            BundledCartridge(
                name="cart",
                version="1.0.0",
                channel="nightly",
                sha256=sha256,
                fabric_manifest_version=fabric_manifest_version,
                cap_groups=_recorded_cap_groups(),
            )
        ],
    )


def _install_unstartable_bundled(root):
    """Lay down the bundled fixture cartridge with an entry point that cannot
    be started on any platform: marked executable, as an installed entry point
    must be, and not a program. A discovery that started it would end at
    HANDSHAKE_FAILED."""
    d = root / "dev" / f"v{CARTRIDGE_REGISTRY_VERSION}" / "nightly" / "cart" / "1.0.0"
    d.mkdir(parents=True)
    (d / "cartridge.json").write_text(_bundled_cartridge_json(), encoding="utf-8")
    entry = d / "cart"
    entry.write_bytes(b"not a program")
    entry.chmod(0o755)
    return d


# TEST1928: a bundled cartridge is admitted exactly when the manifest records
# it, and refused, before anything runs, when it does not.
#
# The other half of TEST1878, and the one that proves the gate is a real check
# rather than a refusal of everything: the same tree, the same cartridge, and
# the only difference is what the build recorded about it.
def test_1928_a_bundled_cartridge_passes_exactly_when_the_manifest_records_it(tmp_path):
    _install_unstartable_bundled(tmp_path)

    out = discover_cartridges(tmp_path, _bundled_identity(_recorded("a" * 64, 1)))
    assert len(out) == 1
    assert isinstance(out[0], DiscoveredCartridgeDirectory), (
        f"a recorded bundled cartridge must be admitted: {out[0]!r}"
    )

    # Recorded under another name: this build ships a cartridge it did not
    # record.
    other = BundleManifest.create(
        "dev",
        [
            BundledCartridge(
                name="other",
                version="1.0.0",
                channel="nightly",
                sha256="a" * 64,
                fabric_manifest_version=1,
                cap_groups=_recorded_cap_groups(),
            )
        ],
    )
    out = discover_cartridges(tmp_path, _bundled_identity(other))
    _expect_incompatible(out, CartridgeAttachmentErrorKind.MISPLACED)
    assert "bundled cartridge integrity" in out[0].error.message, (
        f"a cartridge the manifest does not record must be refused: {out[0].error.message}"
    )


# TEST1931: discovering a bundle neither starts nor hashes a cartridge: its
# caps and its content hash are the ones the signed manifest records.
#
# The entry point cannot be started, so a discovery that probed it would report
# HANDSHAKE_FAILED; and the recorded hash is not the directory's, so a
# discovery that hashed it would refuse it. The hash is held to the directory
# when a host starts the cartridge (TEST1962's half).
def test_1931_bundled_discovery_reads_the_manifest_and_starts_nothing(tmp_path):
    d = _install_unstartable_bundled(tmp_path)

    out = discover_cartridges(tmp_path, _bundled_identity(_recorded("f" * 64, 1)))
    assert len(out) == 1 and isinstance(out[0], DiscoveredCartridgeDirectory), (
        f"expected the bundled cartridge admitted from its manifest, got {out!r}"
    )
    found = out[0]
    assert found.cap_groups == [group.to_dict() for group in _recorded_cap_groups()], (
        "the caps must be the recorded ones"
    )
    assert found.bundle_sha256 == "f" * 64
    assert found.version_dir == d
    assert found.entry_point == d / "cart"


# TEST1932: a bundled cartridge whose build recorded another fabric manifest
# version is refused as built for another fabric, without being started.
#
# Its cartridge.json says the host's version; the signed record says otherwise,
# and the signed record is what discovery believes, since cartridge.json is
# outside the hash.
def test_1932_a_bundled_cartridge_built_for_another_fabric_is_refused_unstarted(tmp_path):
    _install_unstartable_bundled(tmp_path)

    out = discover_cartridges(tmp_path, _bundled_identity(_recorded("a" * 64, 2)))
    _expect_incompatible(out, CartridgeAttachmentErrorKind.FABRIC_MANIFEST_VERSION_MISMATCH)
    assert "fabric manifest version 2" in out[0].error.message, out[0].error.message
