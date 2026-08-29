"""Tests for shared cartridge discovery — mirroring capdag's
``cartridge_discovery`` tests.

Test numbers match the reference (4-digit-padded). The fixtures install a
``cartridge.json`` plus an executable ``#!/bin/sh exit 0`` stub entry that
satisfies ``read_from_dir`` but cannot complete a HELLO handshake, so a
cartridge that reaches the probe ends at HANDSHAKE_FAILED — that is how the
scan-all tests prove discovery REACHED a cartridge (vs. rejecting it
earlier with MISPLACED).
"""

import os
import stat
import sys

import pytest

from capdag.bifaci.cartridge_discovery import (
    DiscoveredCartridgeIncompatible,
    DiscoveryIdentity,
    discover_cartridges,
)
from capdag.bifaci.bundle_manifest import BundleManifest, BundledCartridge, BundleProof
from capdag.bifaci.cartridge_json import hash_cartridge_directory
from capdag.bifaci.cartridge_repo import CARTRIDGE_REGISTRY_VERSION, CartridgeChannel
from capdag.bifaci.cartridge_slug import slug_for
from capdag.bifaci.relay_switch import CartridgeAttachmentErrorKind


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
    # A non-null registry_url placed under the reserved dev slug violates
    # the three-place rule — read_from_dir rejects it as a bad install
    # context (BadInstallation), surfaced + logged, never hosted.
    json_str = (
        '{"name":"cart","version":"1.0.0","channel":"nightly",'
        '"registry_url":"https://cartridges.example.com/manifest",'
        '"entry":"cart","installed_at":"2024-01-01T00:00:00Z",'
        '"fabric_manifest_version":1}'
    )
    _install_fixture(tmp_path, "dev", "nightly", "cart", "1.0.0", json_str, "cart")
    out = discover_cartridges(tmp_path, _nightly_dev_identity())
    _expect_incompatible(out, CartridgeAttachmentErrorKind.MISPLACED)


# TEST1875: scan-all — a registry slug folder AND the dev slot present on disk are BOTH scanned, regardless of the host's own baked registry. The dev cartridge (null registry under dev/) and the registry cartridge (its url hashing to its slug folder) each reach their probe. Both fixtures lack a real bifaci binary, so both end at HandshakeFailed — proving discovery REACHED them (was not filtered out by a registry pin), which is the behavior under test. A registry-pin rejection would instead surface BadInstallation and never probe.
def test_1875_scan_all_reaches_both_dev_and_registry_slugs(tmp_path):
    url = "https://cartridges.example.com/manifest"
    rslug = slug_for(url)
    # Host baked for a DIFFERENT registry than the on-disk registry cartridge.
    base = _nightly_dev_identity()
    host = DiscoveryIdentity(
        channel=base.channel,
        registry_url="https://other.example.com/manifest",
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
    url = "https://cartridges.example.com/manifest"
    rslug = slug_for(url)
    _install_fixture(
        tmp_path, rslug, "release", "regcart", "1.0.0",
        _registry_cartridge_json(url, "release", 1), "cart",
    )
    out = discover_cartridges(tmp_path, _nightly_dev_identity())
    assert out == [], (
        f"a release-only slug must be invisible to a nightly host, got: {out!r}"
    )


# TEST1877: a registry cartridge hand-copied under the WRONG registry slug folder fails the three-place rule (BadInstallation) — scan-all does not mean "accept anywhere", placement must still be self-consistent.
def test_1877_registry_cartridge_under_wrong_slug_is_bad_install(tmp_path):
    url = "https://cartridges.example.com/manifest"
    wrong_slug = slug_for("https://somewhere-else.example.com/manifest")
    json_str = _registry_cartridge_json(url, "nightly", 1)
    _install_fixture(tmp_path, wrong_slug, "nightly", "cart", "1.0.0", json_str, "cart")
    out = discover_cartridges(tmp_path, _nightly_dev_identity())
    _expect_incompatible(out, CartridgeAttachmentErrorKind.MISPLACED)


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


# TEST1928: a bundled cartridge the manifest records passes, and one it records
# differently does not.
#
# The other half of TEST1878, and the one that proves the gate is a real check
# rather than a refusal of everything: the same tree, the same cartridge, and
# the only difference is what the build recorded about it. A gate that always
# said no would pass TEST1878 alone.
def test_1928_a_bundled_cartridge_passes_exactly_when_the_manifest_records_it(tmp_path):
    _install_fixture(
        tmp_path, "dev", "nightly", "cart", "1.0.0", _bundled_cartridge_json(), "cart"
    )
    version_dir = os.path.join(
        str(tmp_path), "dev", f"v{CARTRIDGE_REGISTRY_VERSION}", "nightly", "cart", "1.0.0"
    )
    recorded = hash_cartridge_directory(version_dir)

    def listed(sha256: str) -> DiscoveryIdentity:
        return _bundled_identity(
            BundleManifest.create(
                "dev",
                [
                    BundledCartridge(
                        name="cart", version="1.0.0", channel="nightly", sha256=sha256
                    )
                ],
            )
        )

    # Recorded as it is on disk: past the gate. It still ends at the HELLO
    # probe, because the fixture's entry point is not a cartridge — what
    # matters is that the failure is no longer the integrity one.
    out = discover_cartridges(tmp_path, listed(recorded))
    assert len(out) == 1
    assert "bundled cartridge integrity" not in out[0].error.message, (
        "a cartridge the manifest records must get past the integrity gate: "
        f"{out[0].error.message}"
    )

    # Recorded as something else — the cartridge was changed after the build
    # recorded it.
    out = discover_cartridges(tmp_path, listed("f" * 64))
    _expect_incompatible(out, CartridgeAttachmentErrorKind.MISPLACED)
    assert "bundled cartridge integrity" in out[0].error.message, (
        f"a cartridge that differs from the manifest must be refused: {out[0].error.message}"
    )
