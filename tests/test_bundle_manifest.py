"""What proves a bundled cartridge, and what refuses to — mirroring capdag's
``bundle_manifest`` tests.

Test numbers match the reference. The reference's LOADER tests (TEST1922,
TEST1923) verify a signed chain, which this mirror does not carry: the caller
verifies the signature and hands the verified bytes to
:func:`parse_verified`. What is tested here is what this mirror does: the
CHECK of a directory against a recorded hash, admission against what a
manifest records, and what a verified document is believed in.
"""

import json

import pytest

from capdag.bifaci.bundle_manifest import (
    BUNDLE_MANIFEST_FORMAT,
    BundleContentMismatch,
    BundledCartridge,
    BundleError,
    BundleMalformed,
    BundleManifest,
    BundleNotListed,
    BundleProof,
    BundleRefused,
    BundleUnsupportedFormat,
    BundleWrongChannel,
    BundleWrongEnvironment,
    parse_verified,
    verify_content,
)
from capdag.bifaci.cartridge_json import hash_cartridge_directory
from capdag.cap.definition import Cap
from capdag.urn.cap_urn import CapUrn


def _cartridge_dir(root, contents):
    """Lay down a cartridge directory with ``contents``, and answer its path."""
    d = root / "cart" / "1.0.0"
    d.mkdir(parents=True)
    # Excluded from the hash by `hash_cartridge_directory`, and present because
    # a real cartridge has one.
    (d / "cartridge.json").write_text('{"name":"cart"}', encoding="utf-8")
    for name, body in contents:
        (d / name).write_text(body, encoding="utf-8")
    return d


def _entry(name, version, channel, sha256):
    """One entry as a build records it."""
    return BundledCartridge(
        name=name,
        version=version,
        channel=channel,
        sha256=sha256,
        fabric_manifest_version=1,
        cap_groups=[],
    )


def _document(environment, cartridges):
    """The bytes a build writes for a manifest of ``cartridges`` (each a dict
    in the format's field order), as a signature would cover them."""
    return json.dumps(
        {"format": BUNDLE_MANIFEST_FORMAT, "environment": environment, "cartridges": cartridges},
        indent=2,
    ).encode("utf-8") + b"\n"


def _recorded_entry(name, version, channel, sha256, cap_groups):
    return {
        "name": name,
        "version": version,
        "channel": channel,
        "sha256": sha256,
        "fabric_manifest_version": 1,
        "cap_groups": cap_groups,
    }


# TEST1924: a bundled cartridge is held to the bytes the manifest recorded,
# and the refusal says which cartridge was changed and where.
#
# The manifest is built here rather than loaded, because what is under test is
# the CHECK. The message is what a user reads when a host refuses to start the
# cartridge, so it must name the cartridge and say that its bundle changed.
def test_1924_a_bundled_cartridge_must_match_what_the_manifest_recorded(tmp_path):
    d = _cartridge_dir(tmp_path, [("cart", "the entry point")])
    recorded = hash_cartridge_directory(d)

    verify_content("cart", "1.0.0", d, recorded)

    # Changed after the build recorded it.
    (d / "cart").write_text("something else", encoding="utf-8")
    with pytest.raises(BundleContentMismatch) as refused:
        verify_content("cart", "1.0.0", d, recorded)
    why = refused.value
    assert why.expected == recorded, f"the refusal must name what was recorded, said: {why}"
    said = str(why)
    assert "the bundled cartridge cart 1.0.0 was changed" in said, said
    assert str(d) in said, f"the refusal must say where: {said}"
    assert "is not started" in said, said

    # A file added beside the entry point is a change too.
    (d / "cart").write_text("the entry point", encoding="utf-8")
    verify_content("cart", "1.0.0", d, recorded)
    (d / "extra.dylib").write_text("planted", encoding="utf-8")
    with pytest.raises(BundleContentMismatch):
        verify_content("cart", "1.0.0", d, recorded)


# TEST1929: the manifest admits exactly the cartridges it records, on the
# channel it records them for, without reading a byte of them.
#
# Admission is what discovery does instead of hashing and starting each
# cartridge, so it must refuse everything the old check refused that does not
# need the bytes: a cartridge never recorded, a stale copy of another version,
# and one recorded for the other channel.
def test_1929_the_manifest_admits_only_what_it_records():
    manifest = BundleManifest.create("prod", [_entry("cart", "1.0.0", "release", "a" * 64)])

    admitted = manifest.admit("cart", "1.0.0", "release")
    assert admitted.sha256 == "a" * 64

    with pytest.raises(BundleNotListed):
        manifest.admit("other", "1.0.0", "release")
    # The right cartridge at the wrong version — a stale copy from an earlier
    # build, which a bare per-binary signature would have accepted because it
    # was validly signed once.
    with pytest.raises(BundleNotListed):
        manifest.admit("cart", "0.9.0", "release")
    # A manifest vouches for one channel's artefact, never the other's.
    with pytest.raises(BundleWrongChannel):
        manifest.admit("cart", "1.0.0", "nightly")

    # A root that proves nothing admits nothing, and says why.
    none = BundleProof.none("not a build's bundle")
    with pytest.raises(BundleRefused) as refused:
        none.admit("cart", "1.0.0", "release")
    assert str(refused.value) == "not a build's bundle"
    assert isinstance(refused.value, BundleError)


# TEST1930: a verified document is believed only in this format, for this
# environment, with caps that pass the definition rules.
#
# No earlier format is read: a v1 manifest records no caps and no fabric
# manifest version, so a host reading one would have to start every cartridge
# to learn them, which is what v2 exists to stop.
def test_1930_a_verified_document_is_held_to_the_format_and_the_rules():
    path = "bundle.json"
    good = BundleManifest.create("prod", [_entry("cart", "1.0.0", "release", "a" * 64)])
    good_bytes = _document("prod", [_recorded_entry("cart", "1.0.0", "release", "a" * 64, [])])
    assert parse_verified(good_bytes, path, "prod") == good, "a v2 manifest parses"

    v1 = (
        b'{"format":"capdag.bundle/v1","environment":"prod","cartridges":[{"name":"cart",'
        b'"version":"1.0.0","channel":"release","sha256":"aa"}]}'
    )
    with pytest.raises(BundleUnsupportedFormat) as refused:
        parse_verified(v1, path, "prod")
    assert refused.value.found == "capdag.bundle/v1", "a v1 manifest must be refused for its format"

    with pytest.raises(BundleWrongEnvironment):
        parse_verified(good_bytes, path, "staging")

    # A recorded cap that breaks the definition rules (RULE21: an out= that is
    # not void needs its main output) is refused as an advertised one would be.
    urn = CapUrn.from_string('cap:in="media:enc=utf8";test;out="media:enc=utf8;fmt=json;record"')
    broken_cap = Cap(urn, "Test", ["cmd"])
    broken = _document(
        "prod",
        [
            _recorded_entry(
                "cart",
                "1.0.0",
                "release",
                "a" * 64,
                [{"name": "g", "caps": [broken_cap.to_dict()], "adapter_urns": []}],
            )
        ],
    )
    with pytest.raises(BundleMalformed):
        parse_verified(broken, path, "prod")
