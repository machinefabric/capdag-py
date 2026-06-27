"""Tests for CapManifest - mirroring capdag Rust tests

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
import json
from capdag import CapUrn
from capdag.cap.definition import Cap, CapArg, StdinSource, CliFlagSource
from capdag.bifaci.manifest import (
    CapManifest,
    CapGroup,
    default_group,
    registry_url_from_build_env,
)
from capdag.urn.media_urn import MEDIA_VOID, MEDIA_OBJECT


def _test_urn(tags: str) -> str:
    """Helper to build cap URN with standard in/out for testing"""
    return f'cap:in="{MEDIA_VOID}";out="{MEDIA_OBJECT}";{tags}'


# TEST148: Manifest creation with cap groups
def test_148_cap_manifest_creation():
    urn = CapUrn.from_string(_test_urn("extract;target=metadata"))
    cap = Cap(urn, "Extract Metadata", "extract-metadata")

    manifest = CapManifest(
        name="TestComponent",
        version="0.1.0", channel="release",
            registry_url=None,
            description="A test component for validation",
        cap_groups=[default_group([cap])],
    )

    assert manifest.name == "TestComponent"
    assert manifest.version == "0.1.0"
    assert manifest.channel == "release"
    assert manifest.description == "A test component for validation"
    assert len(manifest.cap_groups) == 1
    assert len(manifest.all_caps()) == 1
    assert manifest.author is None


# TEST117: A manifest's channel round-trips through serde and the serialized form uses the canonical lowercase wire word ("release" / "nightly"). A missing or unrecognized channel is a hard parse error — no defaults.
def test_117_cap_manifest_channel_roundtrip():
    urn = CapUrn.from_string(_test_urn("extract;target=metadata"))
    cap = Cap(urn, "Extract Metadata", "extract-metadata")

    manifest = CapManifest(
        name="TestComponent",
        version="0.1.0",
        channel="nightly",
        registry_url="https://cartridges.machinefabric.com/manifest",
        description="Channel round-trip",
        cap_groups=[default_group([cap])],
    )
    json_str = manifest.to_json()
    assert '"channel": "nightly"' in json_str or '"channel":"nightly"' in json_str
    assert "cartridges.machinefabric.com" in json_str

    deserialized = CapManifest.from_json(json_str)
    assert deserialized.channel == "nightly"
    assert deserialized.registry_url == "https://cartridges.machinefabric.com/manifest"

    # Bogus channel must fail hard.
    with pytest.raises((ValueError, KeyError)):
        CapManifest(
            name="TestComponent",
            version="0.1.0",
            channel="staging",
            registry_url=None,
            description="bogus channel",
            cap_groups=[default_group([cap])],
        )

    # Missing channel key must fail to parse.
    no_channel = '{"name":"X","version":"1.0.0","registry_url":null,"description":"x","cap_groups":[]}'
    with pytest.raises((KeyError, ValueError)):
        CapManifest.from_json(no_channel)

    # Missing registry_url key must fail to parse.
    no_registry = '{"name":"X","version":"1.0.0","channel":"nightly","description":"x","cap_groups":[]}'
    with pytest.raises((KeyError, ValueError)):
        CapManifest.from_json(no_registry)


# TEST118: A dev manifest (built without `MFR_CARTRIDGE_REGISTRY_URL`) carries `registry_url: null` and serializes the field explicitly. The null-vs-absent distinction matters because the parser refuses to accept absent (test117) — so an old SDK can't accidentally pass for a dev build.
def test_118_dev_manifest_registry_url_is_explicit_null():
    urn = CapUrn.from_string(_test_urn("dev"))
    cap = Cap(urn, "Dev", "dev")
    manifest = CapManifest(
        name="DevComponent",
        version="0.1.0",
        channel="nightly",
        registry_url=None,
        description="Dev build",
        cap_groups=[default_group([cap])],
    )
    json_str = manifest.to_json()
    assert '"registry_url": null' in json_str or '"registry_url":null' in json_str
    deserialized = CapManifest.from_json(json_str)
    assert deserialized.registry_url is None


# TEST149: Author field
def test_149_cap_manifest_with_author():
    urn = CapUrn.from_string(_test_urn("extract;target=metadata"))
    cap = Cap(urn, "Extract Metadata", "extract-metadata")

    manifest = CapManifest(
        name="TestComponent",
        version="0.1.0", channel="release",
            registry_url=None,
            description="A test component",
        cap_groups=[default_group([cap])],
    ).with_author("Test Author")

    assert manifest.author == "Test Author"


# TEST150: JSON roundtrip
def test_150_cap_manifest_json_serialization():
    urn = CapUrn.from_string(_test_urn("extract;target=metadata"))
    cap = Cap(urn, "Extract Metadata", "extract-metadata")

    cap.add_arg(CapArg(
        media_urn="media:ext=pdf",
        required=True,
        sources=[StdinSource("media:ext=pdf")],
    ))
    cap.add_arg(CapArg(
        media_urn="media:chunk-size;numeric",
        required=False,
        sources=[CliFlagSource("--chunk-size")],
        arg_description="Chunk size",
        default_value=400,
        metadata={"unit": "words"},
    ))
    cap.add_arg(CapArg(
        media_urn="media:bool;enc=utf-8;timestamps",
        required=False,
        sources=[CliFlagSource("--timestamps")],
        arg_description="Include timestamps",
        default_value=False,
    ))

    manifest = CapManifest(
        name="TestComponent",
        version="0.1.0", channel="release",
            registry_url=None,
            description="A test component",
        cap_groups=[default_group([cap])],
    ).with_author("Test Author")

    json_str = manifest.to_json()
    assert '"name": "TestComponent"' in json_str or '"name":"TestComponent"' in json_str
    assert '"author": "Test Author"' in json_str or '"author":"Test Author"' in json_str
    assert '"cap_groups"' in json_str

    deserialized = CapManifest.from_json(json_str)
    assert deserialized.name == manifest.name
    assert len(deserialized.all_caps()) == len(manifest.all_caps())
    decoded_cap = deserialized.all_caps()[0]
    assert decoded_cap.args[1].default_value == 400
    assert decoded_cap.args[1].metadata == {"unit": "words"}
    assert decoded_cap.args[2].default_value is False


# TEST151: Missing required fields fail
def test_151_cap_manifest_required_fields():
    invalid_json = '{"name": "TestComponent"}'
    with pytest.raises((KeyError, json.JSONDecodeError, TypeError, ValueError)):
        CapManifest.from_json(invalid_json)


# TEST152: Multiple caps across groups
def test_152_cap_manifest_with_multiple_caps():
    id1 = CapUrn.from_string(_test_urn("extract;target=metadata"))
    cap1 = Cap(id1, "Extract Metadata", "extract-metadata")

    id2 = CapUrn.from_string(_test_urn("extract;target=outline"))
    metadata = {"supports_outline": "true"}
    cap2 = Cap.with_metadata(id2, "Extract Outline", "extract-outline", metadata)

    manifest = CapManifest(
        name="MultiCapComponent",
        version="1.0.0", channel="release",
            registry_url=None,
            description="Component with multiple caps",
        cap_groups=[default_group([cap1, cap2])],
    )

    all_caps = manifest.all_caps()
    assert len(all_caps) == 2
    assert "target=metadata" in all_caps[0].urn_string()
    assert "target=outline" in all_caps[1].urn_string()
    assert all_caps[1].has_metadata("supports_outline")


# TEST153: Empty cap groups
def test_153_cap_manifest_empty_cap_groups():
    manifest = CapManifest(
        name="EmptyComponent",
        version="1.0.0", channel="release",
            registry_url=None,
            description="Component with no caps",
        cap_groups=[],
    )

    assert len(manifest.all_caps()) == 0

    json_str = manifest.to_json()
    deserialized = CapManifest.from_json(json_str)
    assert len(deserialized.all_caps()) == 0


# TEST154: Optional author field omitted in serialization
def test_154_cap_manifest_optional_fields():
    urn = CapUrn.from_string(_test_urn("test"))
    cap = Cap(urn, "Test", "test")

    manifest = CapManifest(
        name="TestComponent",
        version="1.0.0", channel="release",
            registry_url=None,
            description="Test",
        cap_groups=[default_group([cap])],
    )

    json1 = manifest.to_json()
    assert '"author"' not in json1
    assert '"page_url"' not in json1


# TEST155: ComponentMetadata trait
def test_155_cap_manifest_complex_roundtrip():
    urn = CapUrn.from_string(_test_urn("process"))
    cap = Cap(urn, "Process", "process")
    cap.set_description("A processing capability")

    stdin_arg = CapArg(
        media_urn="media:",
        required=True,
        sources=[StdinSource("media:")],
        arg_description="Input data",
    )
    cap.add_arg(stdin_arg)

    manifest = CapManifest(
        name="ComplexComponent",
        version="2.0.0", channel="release",
            registry_url=None,
            description="Complex test component",
        cap_groups=[default_group([cap])],
    ).with_author("Test Author").with_page_url("https://example.com")

    json_str = manifest.to_json()
    restored = CapManifest.from_json(json_str)

    assert restored.name == manifest.name
    assert restored.version == manifest.version
    assert restored.description == manifest.description
    assert restored.author == manifest.author
    assert restored.page_url == manifest.page_url
    assert len(restored.all_caps()) == len(manifest.all_caps())
    assert restored.all_caps()[0].title == manifest.all_caps()[0].title
    assert restored.all_caps()[0].command == manifest.all_caps()[0].command
    assert len(restored.all_caps()[0].get_args()) == len(manifest.all_caps()[0].get_args())


# TEST475: validate() passes with CAP_IDENTITY in a cap group
def test_475_validate_passes_with_identity():
    from capdag.standard.caps import CAP_IDENTITY

    identity_urn = CapUrn.from_string(CAP_IDENTITY)
    identity_cap = Cap(identity_urn, "Identity", "identity")
    manifest = CapManifest("TestCartridge", "1.0.0", "release", None, "Test", [default_group([identity_cap])])
    # Should succeed without raising
    manifest.validate()


# TEST476: validate() fails without CAP_IDENTITY
def test_476_validate_fails_without_identity():
    specific_urn = CapUrn.from_string(_test_urn("convert"))
    specific_cap = Cap(specific_urn, "Convert", "convert")
    manifest = CapManifest("TestCartridge", "1.0.0", "release", None, "Test", [default_group([specific_cap])])

    with pytest.raises(ValueError) as exc_info:
        manifest.validate()

    assert "CAP_IDENTITY" in str(exc_info.value)


# TEST1284: Cap group with adapter URNs serializes and deserializes correctly
def test_1284_cap_group_with_adapter_urns():
    urn = CapUrn.from_string(_test_urn("convert"))
    cap = Cap(urn, "Convert", "convert")

    group = CapGroup(
        name="data-formats",
        caps=[cap],
        adapter_urns=["media:fmt=json", "media:fmt=csv"],
    )

    manifest = CapManifest("TestCartridge", "1.0.0", "release", None, "Test", [group])

    json_str = manifest.to_json()
    assert '"adapter_urns"' in json_str
    assert "media:fmt=json" in json_str
    assert "media:fmt=csv" in json_str

    deserialized = CapManifest.from_json(json_str)
    assert len(deserialized.cap_groups[0].adapter_urns) == 2


# TEST1872: `registry_url_from_build_env` passes a non-empty registry URL through unchanged. This is the function that decides the engine's baked PRIMARY registry (surfaced over SystemService.HealthStatus); a published build must report exactly the URL it was compiled with.
def test_1872_registry_url_from_build_env_passes_through_nonempty():
    url = "https://cartridges.machinefabric.com/manifest"
    assert registry_url_from_build_env(url) == url


# TEST1873: an unset env (None) yields None — a dev build has no baked registry, so the engine reports an empty primary-registry URL and loads only `dev/` cartridges. This is the dev-engine contract the registry sheets rely on to omit the read-only "Primary · built-in" row.
def test_1873_registry_url_from_build_env_none_for_dev():
    assert registry_url_from_build_env(None) is None


# TEST6363: Cap manifest with page_url — the optional page_url is carried
# and serialized as `page_url`.
def test_6363_cap_manifest_with_page_url():
    urn = CapUrn.from_string(_test_urn("extract;target=metadata"))
    cap = Cap(urn, "Metadata Extractor", "extract-metadata")
    manifest = CapManifest(
        name="TestComponent",
        version="0.1.0",
        channel="release",
        registry_url=None,
        description="A test component for validation",
        cap_groups=[default_group([cap])],
    ).with_author("Test Author").with_page_url("https://github.com/example/test")

    assert manifest.page_url == "https://github.com/example/test"
    json_str = manifest.to_json()
    assert (
        '"page_url": "https://github.com/example/test"' in json_str
        or '"page_url":"https://github.com/example/test"' in json_str
    ), f"expected page_url in serialized form, got: {json_str}"


# TEST6371: Cap manifest compatibility — cartridge-style and provider-style
# manifests serialize to the same JSON shape (same keys).
def test_6371_cap_manifest_compatibility():
    urn = CapUrn.from_string(_test_urn("process"))
    cap = Cap(urn, "Data Processor", "process")
    cartridge = CapManifest(
        name="CartridgeComponent",
        version="0.1.0",
        channel="release",
        registry_url=None,
        description="Cartridge-style component",
        cap_groups=[default_group([cap])],
    )
    provider = CapManifest(
        name="ProviderComponent",
        version="0.1.0",
        channel="release",
        registry_url=None,
        description="Provider-style component",
        cap_groups=[default_group([cap])],
    )
    cartridge_map = json.loads(cartridge.to_json())
    provider_map = json.loads(provider.to_json())
    assert len(cartridge_map) == len(provider_map)
    for key in ("name", "version", "description", "cap_groups", "channel"):
        assert key in cartridge_map, f"missing key {key}"
        assert key in provider_map, f"missing key {key}"


# TEST1874: an exported-but-empty env (`Some("")`) is neither a dev build nor a valid identity and MUST fail hard at compile time, so the build can never silently hash the empty string into a fake registry slug. We assert the panic rather than letting a bogus empty primary registry ship.
def test_1874_registry_url_from_build_env_rejects_empty_string():
    with pytest.raises(ValueError) as exc_info:
        registry_url_from_build_env("")
    assert "MFR_CARTRIDGE_REGISTRY_URL must be unset" in str(exc_info.value)
