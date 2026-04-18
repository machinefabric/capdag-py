"""Tests for CapManifest - mirroring capdag Rust tests

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
import json
from capdag import CapUrn
from capdag.cap.definition import Cap, CapArg, StdinSource
from capdag.bifaci.manifest import CapManifest, CapGroup, default_group
from capdag.urn.media_urn import MEDIA_VOID, MEDIA_OBJECT


def _test_urn(tags: str) -> str:
    """Helper to build cap URN with standard in/out for testing"""
    return f'cap:in="{MEDIA_VOID}";out="{MEDIA_OBJECT}";{tags}'


# TEST148: Manifest creation with cap groups
def test_148_cap_manifest_creation():
    urn = CapUrn.from_string(_test_urn("op=extract;target=metadata"))
    cap = Cap(urn, "Extract Metadata", "extract-metadata")

    manifest = CapManifest(
        name="TestComponent",
        version="0.1.0",
        description="A test component for validation",
        cap_groups=[default_group([cap])],
    )

    assert manifest.name == "TestComponent"
    assert manifest.version == "0.1.0"
    assert manifest.description == "A test component for validation"
    assert len(manifest.cap_groups) == 1
    assert len(manifest.all_caps()) == 1
    assert manifest.author is None


# TEST149: Author field
def test_149_cap_manifest_with_author():
    urn = CapUrn.from_string(_test_urn("op=extract;target=metadata"))
    cap = Cap(urn, "Extract Metadata", "extract-metadata")

    manifest = CapManifest(
        name="TestComponent",
        version="0.1.0",
        description="A test component",
        cap_groups=[default_group([cap])],
    ).with_author("Test Author")

    assert manifest.author == "Test Author"


# TEST150: JSON roundtrip
def test_150_cap_manifest_json_serialization():
    urn = CapUrn.from_string(_test_urn("op=extract;target=metadata"))
    cap = Cap(urn, "Extract Metadata", "extract-metadata")

    cap.add_arg(CapArg(
        media_urn="media:pdf",
        required=True,
        sources=[StdinSource("media:pdf")],
    ))

    manifest = CapManifest(
        name="TestComponent",
        version="0.1.0",
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


# TEST151: Missing required fields fail
def test_151_cap_manifest_required_fields():
    invalid_json = '{"name": "TestComponent"}'
    with pytest.raises((KeyError, json.JSONDecodeError, TypeError)):
        CapManifest.from_json(invalid_json)


# TEST152: Multiple caps across groups
def test_152_cap_manifest_with_multiple_caps():
    id1 = CapUrn.from_string(_test_urn("op=extract;target=metadata"))
    cap1 = Cap(id1, "Extract Metadata", "extract-metadata")

    id2 = CapUrn.from_string(_test_urn("op=extract;target=outline"))
    metadata = {"supports_outline": "true"}
    cap2 = Cap.with_metadata(id2, "Extract Outline", "extract-outline", metadata)

    manifest = CapManifest(
        name="MultiCapComponent",
        version="1.0.0",
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
        version="1.0.0",
        description="Component with no caps",
        cap_groups=[],
    )

    assert len(manifest.all_caps()) == 0

    json_str = manifest.to_json()
    deserialized = CapManifest.from_json(json_str)
    assert len(deserialized.all_caps()) == 0


# TEST154: Optional author field omitted in serialization
def test_154_cap_manifest_optional_fields():
    urn = CapUrn.from_string(_test_urn("op=test"))
    cap = Cap(urn, "Test", "test")

    manifest = CapManifest(
        name="TestComponent",
        version="1.0.0",
        description="Test",
        cap_groups=[default_group([cap])],
    )

    json1 = manifest.to_json()
    assert '"author"' not in json1
    assert '"page_url"' not in json1


# TEST155: ComponentMetadata pattern
def test_155_cap_manifest_complex_roundtrip():
    urn = CapUrn.from_string(_test_urn("op=process"))
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
        version="2.0.0",
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
    manifest = CapManifest("TestCartridge", "1.0.0", "Test", [default_group([identity_cap])])
    # Should succeed without raising
    manifest.validate()


# TEST476: validate() fails without CAP_IDENTITY
def test_476_validate_fails_without_identity():
    specific_urn = CapUrn.from_string(_test_urn("op=convert"))
    specific_cap = Cap(specific_urn, "Convert", "convert")
    manifest = CapManifest("TestCartridge", "1.0.0", "Test", [default_group([specific_cap])])

    with pytest.raises(ValueError) as exc_info:
        manifest.validate()

    assert "CAP_IDENTITY" in str(exc_info.value)


# TEST1284: Cap group with adapter URNs serializes and deserializes correctly
def test_1284_cap_group_with_adapter_urns():
    urn = CapUrn.from_string(_test_urn("op=convert"))
    cap = Cap(urn, "Convert", "convert")

    group = CapGroup(
        name="data-formats",
        caps=[cap],
        adapter_urns=["media:json", "media:csv"],
    )

    manifest = CapManifest("TestCartridge", "1.0.0", "Test", [group])

    json_str = manifest.to_json()
    assert '"adapter_urns"' in json_str
    assert "media:json" in json_str
    assert "media:csv" in json_str

    deserialized = CapManifest.from_json(json_str)
    assert len(deserialized.cap_groups[0].adapter_urns) == 2
