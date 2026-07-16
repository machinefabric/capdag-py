"""Tests for shared cartridge discovery — mirroring capdag's
``cartridge_discovery`` tests.

Test numbers match the reference (4-digit-padded). The fixtures install a
``cartridge.json`` plus an executable ``#!/bin/sh exit 0`` stub entry that
satisfies ``read_from_dir`` but cannot complete a HELLO handshake, so a
cartridge that reaches the probe ends at HANDSHAKE_FAILED — that is how the
scan-all tests prove discovery REACHED a cartridge (vs. rejecting it
earlier with BAD_INSTALLATION).
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
from capdag.bifaci.cartridge_repo import CARTRIDGE_REGISTRY_VERSION, CartridgeChannel
from capdag.bifaci.cartridge_slug import slug_for
from capdag.bifaci.relay_switch import CartridgeAttachmentErrorKind


def _nightly_dev_identity() -> DiscoveryIdentity:
    return DiscoveryIdentity(
        channel=CartridgeChannel.NIGHTLY,
        registry_url=None,
        fabric_manifest_version=1,
        cartridge_registry_version=CARTRIDGE_REGISTRY_VERSION,
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


# TEST92: Channel mismatch is bad installation
def test_0092_channel_mismatch_is_bad_installation(tmp_path):
    # Declares release but lives under nightly/ — host is nightly.
    json_str = _dev_cartridge_json("release", 1)
    _install_fixture(tmp_path, "dev", "nightly", "cart", "1.0.0", json_str, "cart")
    out = discover_cartridges(tmp_path, _nightly_dev_identity())
    _expect_incompatible(out, CartridgeAttachmentErrorKind.BAD_INSTALLATION)


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
    _expect_incompatible(out, CartridgeAttachmentErrorKind.BAD_INSTALLATION)


# TEST1875: scan-all — a registry slug folder AND the dev slot present on disk are BOTH scanned, regardless of the host's own baked registry. The dev cartridge (null registry under dev/) and the registry cartridge (its url hashing to its slug folder) each reach their probe. Both fixtures lack a real bifaci binary, so both end at HandshakeFailed — proving discovery REACHED them (was not filtered out by a registry pin), which is the behavior under test. A registry-pin rejection would instead surface BadInstallation and never probe.
def test_1875_scan_all_reaches_both_dev_and_registry_slugs(tmp_path):
    url = "https://cartridges.example.com/manifest"
    rslug = slug_for(url)
    # Host baked for a DIFFERENT registry than the on-disk registry cartridge.
    host = DiscoveryIdentity(
        channel=CartridgeChannel.NIGHTLY,
        registry_url="https://other.example.com/manifest",
        fabric_manifest_version=1,
        cartridge_registry_version=CARTRIDGE_REGISTRY_VERSION,
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
    _expect_incompatible(out, CartridgeAttachmentErrorKind.BAD_INSTALLATION)


# TEST1878: a cartridge marked `installed_from: bundle` with no baked hash in BUNDLED_CARTRIDGE_HASHES (the const is empty under plain `cargo test`) is rejected as BadInstallation — the bundled-integrity gate fires before the probe. Proves the verify is wired into discovery; a real bundle build bakes the hash so the matching directory passes. Non-macOS only: on macOS the baked-hash path is intentionally absent (OS code-signature is the guard), so a bundled cartridge is accepted there and would instead end at the probe.
@pytest.mark.skipif(sys.platform == "darwin", reason="macOS uses code-signature, not baked hashes")
def test_1878_bundled_cartridge_without_baked_hash_is_rejected(tmp_path):
    # Dev slug (null registry) but installed_from=bundle — placement is
    # self-consistent (null→dev), so it passes read_from_dir and reaches the
    # bundled-hash gate, which has no baked entry → BadInstallation.
    json_str = (
        '{"name":"cart","version":"1.0.0","channel":"nightly","registry_url":null,'
        '"entry":"cart","installed_at":"2024-01-01T00:00:00Z",'
        '"installed_from":"bundle","fabric_manifest_version":1}'
    )
    _install_fixture(tmp_path, "dev", "nightly", "cart", "1.0.0", json_str, "cart")
    out = discover_cartridges(tmp_path, _nightly_dev_identity())
    _expect_incompatible(out, CartridgeAttachmentErrorKind.BAD_INSTALLATION)
    entry = out[0]
    assert "bundled cartridge integrity" in entry.error.message, (
        f"message should name the bundled-integrity failure: {entry.error.message}"
    )
