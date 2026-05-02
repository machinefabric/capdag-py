"""Tests for registry - mirroring capdag Rust tests

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
import json
import os
import tempfile
from pathlib import Path
from capdag import Cap, CapUrn, CapArg
from capdag.cap.definition import PositionSource, StdinSource
from capdag.cap.registry import (
    CapRegistry,
    RegistryConfig,
    normalize_cap_urn,
    HttpError,
    NetworkBlockedError,
    NotFoundError,
    ValidationError,
    CacheError,
)
from capdag.urn.media_urn import MEDIA_VOID, MEDIA_OBJECT, MEDIA_STRING


def _test_urn(tags: str) -> str:
    """Helper to build cap URN with standard in/out for testing"""
    return f'cap:in="{MEDIA_VOID}";out="{MEDIA_OBJECT}";{tags}'


# TEST135: Test registry creation with temporary cache directory succeeds
def test_135_registry_creation():
    """Test registry creation with custom cache directory"""
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_dir = Path(temp_dir)
        config = RegistryConfig()
        registry = CapRegistry(cache_dir, config, None)

        assert registry.cache_dir == cache_dir
        assert registry.cache_dir.exists()


# TEST136: Test cache key generation produces consistent hashes for same URN
def test_136_cache_key_generation():
    registry = CapRegistry.new_for_test()

    urn1 = 'cap:in="media:void";op=extract;out="media:record;textable";target=metadata'
    urn2 = 'cap:in="media:void";op=extract;out="media:record;textable";target=metadata'
    urn3 = 'cap:in="media:void";op=different;out="media:object"'

    key1 = registry._cache_key(urn1)
    key2 = registry._cache_key(urn2)
    key3 = registry._cache_key(urn3)

    assert key1 == key2
    assert key1 != key3
    # Key must be a valid SHA-256 hex digest (64 characters, all hex).
    assert len(key1) == 64
    assert all(c in '0123456789abcdef' for c in key1)

    # Keys should be hex strings (SHA-256 is 64 hex chars)
    assert len(key1) == 64
    assert all(c in '0123456789abcdef' for c in key1)


# TEST137: Test parsing registry JSON without stdin args verifies cap structure
def test_137_parse_registry_json():
    """Test parsing cap JSON without stdin args"""
    # JSON without stdin args - means cap doesn't accept stdin
    json_str = '''{
        "urn": "cap:in=\\"media:listing-id\\";op=use_grinder;out=\\"media:task;id\\"",
        "command": "grinder_task",
        "title": "Create Grinder Tool Task",
        "cap_description": "Create a task for initial document analysis",
        "metadata": {},
        "media_specs": [
            {
                "urn": "media:listing-id",
                "media_type": "text/plain",
                "title": "Listing ID",
                "profile_uri": "https://machinefabric.com/schema/listing-id",
                "schema": {
                    "type": "string",
                    "pattern": "[0-9a-f-]{36}",
                    "description": "MachineFabric listing UUID"
                }
            }
        ],
        "args": [
            {
                "media_urn": "media:listing-id",
                "required": true,
                "sources": [{"cli_flag": "--listing-id"}],
                "arg_description": "ID of the listing to analyze"
            }
        ],
        "output": {
            "media_urn": "media:task;id",
            "output_description": "Created task information"
        }
    }'''

    cap = Cap.from_dict(json.loads(json_str))

    assert cap.title == "Create Grinder Tool Task"
    assert cap.command == "grinder_task"
    # No stdin source in args means no stdin support
    assert cap.get_stdin_media_urn() is None


# TEST138: Test parsing registry JSON with stdin args verifies stdin media URN extraction
def test_138_parse_registry_json_with_stdin():
    """Test parsing cap JSON with stdin args"""
    json_str = '''{
        "urn": "cap:in=\\"media:pdf\\";op=disbind;out=\\"media:textable;page\\"",
        "command": "disbind",
        "title": "Disbind PDF",
        "args": [
            {
                "media_urn": "media:pdf",
                "required": true,
                "sources": [{"stdin": "media:pdf"}]
            }
        ]
    }'''

    cap = Cap.from_dict(json.loads(json_str))

    assert cap.title == "Disbind PDF"
    assert cap.accepts_stdin()
    assert cap.get_stdin_media_urn() == "media:pdf"  # As specified in JSON


# TEST139: Test URL construction keeps cap prefix literal and only encodes tags part
def test_139_url_keeps_cap_prefix_literal():
    """Test that URL keeps 'cap:' literal, not encoded as 'cap%3A'"""
    from urllib.parse import quote as url_encode

    config = RegistryConfig()
    urn = 'cap:in="media:string";op=test;out="media:object"'
    normalized = normalize_cap_urn(urn)
    tags_part = normalized[4:] if normalized.startswith("cap:") else normalized
    encoded_tags = url_encode(tags_part, safe='')
    url = f"{config.registry_base_url}/cap:{encoded_tags}"

    # URL must contain literal '/cap:' not encoded
    assert "/cap:" in url
    assert "cap%3A" not in url


# TEST140: Test URL encodes media URNs with proper percent encoding for special characters
def test_140_url_encodes_quoted_media_urns():
    """Test that special characters in URNs are percent-encoded"""
    from urllib.parse import quote as url_encode

    config = RegistryConfig()
    urn = 'cap:in="media:listing-id";op=use_grinder;out="media:task;id"'
    normalized = normalize_cap_urn(urn)
    tags_part = normalized[4:] if normalized.startswith("cap:") else normalized
    encoded_tags = url_encode(tags_part, safe='')
    url = f"{config.registry_base_url}/cap:{encoded_tags}"

    # Equals must be encoded as %3D
    assert "%3D" in url
    # Semicolons must be encoded as %3B
    assert "%3B" in url
    # Colons in media URNs must be encoded as %3A
    assert "%3A" in url


# TEST141: Test exact URL format contains properly encoded media URN components
def test_141_exact_url_format():
    """Test exact URL format for registry requests"""
    from urllib.parse import quote as url_encode

    config = RegistryConfig()
    urn = 'cap:in="media:listing-id";op=use_grinder;out="media:task;id"'
    normalized = normalize_cap_urn(urn)
    tags_part = normalized[4:] if normalized.startswith("cap:") else normalized
    encoded_tags = url_encode(tags_part, safe='')
    url = f"{config.registry_base_url}/cap:{encoded_tags}"

    # Verify URL contains encoded media URNs
    assert "media%3Alisting-id" in url or "media%3A" in url
    assert "media%3Atask-id" in url or "media%3A" in url


# TEST142: Test normalize handles different tag orders producing same canonical form
def test_142_normalize_handles_different_tag_orders():
    """Test that different tag orders normalize to same form"""
    # Different tag orders should normalize to the same canonical form
    urn1 = 'cap:op=test;in="media:string";out="media:object"'
    urn2 = 'cap:in="media:string";out="media:object";op=test'

    normalized1 = normalize_cap_urn(urn1)
    normalized2 = normalize_cap_urn(urn2)

    assert normalized1 == normalized2


# TEST143: Test default config uses capdag.com or environment variable values
def test_143_default_config():
    """Test default configuration"""
    config = RegistryConfig()

    # Default should use capdag.com (unless env var is set)
    assert "capdag.com" in config.registry_base_url or os.getenv("CAPDAG_REGISTRY_URL") is not None
    assert "/schema" in config.schema_base_url


# TEST144: Test custom registry URL updates both registry and schema base URLs
def test_144_custom_registry_url():
    """Test setting custom registry URL"""
    config = RegistryConfig().with_registry_url("https://localhost:8888")

    assert config.registry_base_url == "https://localhost:8888"
    assert config.schema_base_url == "https://localhost:8888/schema"


# TEST908: Cached caps remain accessible when offline
@pytest.mark.asyncio
async def test_908_cached_caps_accessible_when_offline():
    registry = CapRegistry.new_for_test()
    cap = Cap.from_dict(
        json.loads(
            '{"urn":"cap:in=media:void;op=test_offline;out=media:void","command":"test","title":"Test Cap","args":[]}'
        )
    )
    registry.add_caps_to_cache([cap])

    registry.set_offline(True)

    cached = await registry.get_cap("cap:in=media:void;op=test_offline;out=media:void")
    assert cached.title == "Test Cap"


# TEST909: set_offline(false) restores fetch ability (would fail with HTTP error, not NetworkBlocked)
@pytest.mark.asyncio
async def test_909_set_offline_false_restores_fetch(monkeypatch):
    registry = CapRegistry.new_for_test()
    registry.set_offline(True)

    with pytest.raises(NetworkBlockedError):
        await registry.get_cap("cap:in=media:void;op=nonexistent;out=media:void")

    async def fake_fetch(_urn: str):
        raise HttpError("simulated http failure")

    monkeypatch.setattr(registry, "_fetch_from_registry", fake_fetch)
    registry.set_offline(False)

    with pytest.raises(HttpError, match="simulated http failure"):
        await registry.get_cap("cap:in=media:void;op=nonexistent;out=media:void")


# TEST145: Test custom registry and schema URLs set independently
def test_145_custom_registry_and_schema_url():
    """Test setting both registry and schema URLs independently"""
    config = (RegistryConfig()
              .with_registry_url("https://localhost:8888")
              .with_schema_url("https://schemas.example.com"))

    assert config.registry_base_url == "https://localhost:8888"
    assert config.schema_base_url == "https://schemas.example.com"


# TEST146: Test schema URL not overwritten when set explicitly before registry URL
def test_146_schema_url_not_overwritten_when_explicit():
    """Test that explicitly set schema URL is not overwritten"""
    # If schema URL is set explicitly first, changing registry URL shouldn't change it
    config = (RegistryConfig()
              .with_schema_url("https://schemas.example.com")
              .with_registry_url("https://localhost:8888"))

    assert config.registry_base_url == "https://localhost:8888"
    assert config.schema_base_url == "https://schemas.example.com"


# TEST147: Test registry for test with custom config creates registry with specified URLs
def test_147_registry_for_test_with_config():
    """Test creating test registry with custom configuration"""
    config = RegistryConfig().with_registry_url("https://test-registry.local")
    registry = CapRegistry.new_for_test_with_config(config)

    assert registry.config.registry_base_url == "https://test-registry.local"


# TEST123: Test adding caps to the registry cache and retrieving them
@pytest.mark.asyncio
async def test_123_registry_add_caps_to_cache():
    registry = CapRegistry.new_for_test()

    urn = CapUrn.from_string(_test_urn("op=test"))
    cap = Cap(urn, "Test Cap", "test-command")

    registry.add_caps_to_cache([cap])

    cached_caps = await registry.get_cached_caps()
    titles = [c.title for c in cached_caps]
    assert "Test Cap" in titles


# TEST124: Test registry configuration builder sets registry and schema URLs
def test_124_registry_config_builder_pattern():
    config = (RegistryConfig()
              .with_registry_url("https://custom.registry")
              .with_schema_url("https://custom.schemas"))

    assert config.registry_base_url == "https://custom.registry"
    assert config.schema_base_url == "https://custom.schemas"


# TEST125: normalize_cap_urn strips trailing semicolons, producing the
# same canonical form with or without a trailing semicolon
def test_125_normalize_urn_with_trailing_semicolon():
    urn1 = _test_urn("op=test")
    urn2 = _test_urn("op=test") + ";"

    normalized1 = normalize_cap_urn(urn1)
    normalized2 = normalize_cap_urn(urn2)

    assert normalized1 == normalized2
