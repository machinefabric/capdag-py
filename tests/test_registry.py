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
    FabricRegistry,
    RegistryConfig,
    normalize_cap_urn,
    NetworkBlockedError,
    NotFoundError,
    ParseError,
    ValidationError,
    CacheError,
)
from capdag.urn.media_urn import MEDIA_VOID, MEDIA_OBJECT, MEDIA_STRING


def _test_urn(tags: str) -> str:
    """Helper to build cap URN with standard in/out for testing"""
    return f'cap:in="{MEDIA_VOID}";out="{MEDIA_OBJECT}";{tags}'


# TEST614: Verify registry creation succeeds and cache directory exists
def test_614_registry_creation():
    """Test registry creation with custom cache directory"""
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_dir = Path(temp_dir)
        config = RegistryConfig()
        registry = FabricRegistry(cache_dir, config, None)

        assert registry.cache_dir == cache_dir
        assert registry.cache_dir.exists()


# TEST136 (deleted): exercised the private `_cache_key` method on
# the unified FabricRegistry. The on-disk cache filename scheme is
# an implementation detail of the persistence layer; equivalent
# behavior — that two equivalent URNs land in the same cache slot
# — is covered observably by tests that round-trip caps through
# the public API (e.g. `get_cap` returning the same definition for
# semantically-equal URN spellings).


# TEST6382: Test parsing registry JSON without stdin args verifies cap structure
def test_6382_parse_registry_json():
    """Test parsing cap JSON without stdin args"""
    # JSON without stdin args - means cap doesn't accept stdin
    json_str = '''{
        "urn": "cap:in=\\"media:listing-id\\";use-grinder;out=\\"media:task;id\\"",
        "command": "grinder_task",
        "title": "Create Grinder Tool Task",
        "cap_description": "Create a task for initial document analysis",
        "metadata": {},
        "media_defs": [
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
        "urn": "cap:in=\\"media:ext=pdf\\";disbind;out=\\"media:enc=utf-8;page\\"",
        "command": "disbind",
        "title": "Disbind PDF",
        "args": [
            {
                "media_urn": "media:ext=pdf",
                "required": true,
                "sources": [{"stdin": "media:ext=pdf"}]
            }
        ]
    }'''

    cap = Cap.from_dict(json.loads(json_str))

    assert cap.title == "Disbind PDF"
    assert cap.accepts_stdin()
    assert cap.get_stdin_media_urn() == "media:ext=pdf"  # As specified in JSON


# TEST6388: Per-cap URLs use SHA-256 of the canonical URN as the path key.
# The path scheme is /caps/<sha256-hex> — no colons, no quotes, no
# percent-encoding gymnastics. Same hash function across every capdag
# implementation guarantees a single bucket key per equivalence class.
def test_6388_per_cap_url_uses_sha256():
    """Per-cap lookup URL is /caps/<sha256-of-canonical-urn>"""
    import hashlib
    config = RegistryConfig()
    urn = 'cap:in="media:string";test;out="media:object"'
    normalized = normalize_cap_urn(urn)
    digest = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
    url = f"{config.registry_base_url}/caps/{digest}"

    assert "/caps/" in url
    # The URL must NOT contain any URN-grammar characters now that
    # hashing replaces percent-encoding entirely.
    assert "cap:" not in url[len(config.registry_base_url):]
    assert "%3A" not in url
    assert "%3B" not in url
    assert "%3D" not in url
    # The hash is 64 hex chars.
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


# TEST6189: Different URN spellings of the same cap (different tag order,
# whitespace, quoting) MUST produce the same SHA-256 hash, because the
# canonicaliser reduces them to the same string before hashing. This is
# the property that makes cross-language lookups land at the same
# registry key regardless of which capdag implementation issued the
# request.
def test_6189_same_cap_different_spellings_same_hash():
    """Equivalent URNs hash identically after canonicalisation"""
    import hashlib
    urn_a = 'cap:in="media:listing-id";use-grinder;out="media:task;id"'
    urn_b = 'cap:out="media:task;id";in="media:listing-id";use-grinder'

    canonical_a = normalize_cap_urn(urn_a)
    canonical_b = normalize_cap_urn(urn_b)

    digest_a = hashlib.sha256(canonical_a.encode('utf-8')).hexdigest()
    digest_b = hashlib.sha256(canonical_b.encode('utf-8')).hexdigest()

    assert canonical_a == canonical_b, f"canonical forms diverged: {canonical_a!r} vs {canonical_b!r}"
    assert digest_a == digest_b, f"hashes diverged: {digest_a} vs {digest_b}"


def cap_registry_url(config: "RegistryConfig", cap_urn: str) -> str:
    """Build the per-cap registry URL: <base>/caps/<sha256-of-canonical-urn>.

    Mirrors the Rust test helper of the same name, which constructs the
    URL the same way `cap_url_and_cache_path` does in production: canonicalise
    the URN, SHA-256 it, and hex-encode under the `/caps/` prefix.
    """
    import hashlib
    digest = hashlib.sha256(normalize_cap_urn(cap_urn).encode("utf-8")).hexdigest()
    return f"{config.registry_base_url}/caps/{digest}"


# TEST6391: Equivalent URNs (different tag order, etc.) hash to the same key.
def test_6391_same_cap_different_spellings_same_url():
    config = RegistryConfig()
    a = cap_registry_url(config, 'cap:in="media:listing-id";use-grinder;out="media:id;task"')
    b = cap_registry_url(config, 'cap:out="media:id;task";in="media:listing-id";use-grinder')
    assert a == b, "equivalent URNs must hash to the same registry key"


# TEST141: URL has the right shape — protocol, host, /caps/ prefix,
# 64 hex chars, no extension. Mirrors Go's Test141_per_cap_url_shape
# and ObjC's test141_perCapURLShape; the previous Python TEST141
# (`different_caps_different_hashes`) was renumbered to TEST938 to
# resolve a cross-mirror collision on this number.
def test_141_per_cap_url_shape():
    """URL is well-formed: https + fabric.capdag.com host + /caps/<64-hex>"""
    import hashlib
    from urllib.parse import urlparse
    urn = 'cap:in="media:listing-id";use-grinder;out="media:task;id"'
    digest = hashlib.sha256(normalize_cap_urn(urn).encode('utf-8')).hexdigest()
    registry_url = f"https://fabric.capdag.com/caps/{digest}"
    parsed = urlparse(registry_url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "fabric.capdag.com"
    assert parsed.path.startswith("/caps/")
    hash_part = parsed.path[len("/caps/"):]
    assert len(hash_part) == 64, "SHA-256 hex digest is 64 characters"
    assert all(c in "0123456789abcdef" for c in hash_part)


# TEST938: Two genuinely different caps must hash to different keys.
# If the canonical-form algorithm ever drifts to coalesce
# non-equivalent URNs (e.g. by stripping a tag that has functional
# meaning), this test fails immediately. Renumbered from TEST141 to
# resolve a collision with Go/ObjC's TEST141 (URL-shape).
def test_938_different_caps_different_hashes():
    """Non-equivalent URNs must NOT collide under SHA-256"""
    import hashlib
    urn_a = 'cap:in="media:string";name=summarize;out="media:summary"'
    urn_b = 'cap:in="media:string";name=translate;out="media:summary"'
    digest_a = hashlib.sha256(normalize_cap_urn(urn_a).encode('utf-8')).hexdigest()
    digest_b = hashlib.sha256(normalize_cap_urn(urn_b).encode('utf-8')).hexdigest()
    assert digest_a != digest_b


# TEST142: Test normalize handles different tag orders producing same canonical form
def test_142_normalize_handles_different_tag_orders():
    """Test that different tag orders normalize to same form"""
    # Different tag orders should normalize to the same canonical form
    urn1 = 'cap:test;in="media:string";out="media:object"'
    urn2 = 'cap:in=media:string;out=media:object;test'

    normalized1 = normalize_cap_urn(urn1)
    normalized2 = normalize_cap_urn(urn2)

    assert normalized1 == normalized2


# TEST143: Default config points at https://fabric.capdag.com/ unless overridden by CDG_FABRIC_REGISTRY_URL.
def test_143_default_config():
    """Test default configuration"""
    config = RegistryConfig()

    # Default points at the canonical registry host. The env-var
    # override path stays open for tests / staging deploys.
    if os.getenv("CDG_FABRIC_REGISTRY_URL") is None:
        assert config.registry_base_url == "https://fabric.capdag.com"
    else:
        assert config.registry_base_url == os.getenv("CDG_FABRIC_REGISTRY_URL")
    assert "/schema" in config.schema_base_url


# TEST144: Test custom registry URL updates both registry and schema base URLs
def test_144_custom_registry_url():
    """Test setting custom registry URL"""
    config = RegistryConfig().with_registry_url("https://localhost:8888")

    assert config.registry_base_url == "https://localhost:8888"
    assert config.schema_base_url == "https://localhost:8888/schema"


# TEST908: cached caps remain accessible while offline.
@pytest.mark.asyncio
async def test_908_cached_caps_accessible_when_offline():
    registry = FabricRegistry.new_for_test()
    cap = Cap.from_dict(
        json.loads(
            '{"urn":"cap:in=media:void;test-offline;out=media:void","command":"test","title":"Test Cap","args":[]}'
        )
    )
    registry.add_caps_to_cache([cap])

    registry.set_offline(True)

    cached = await registry.get_cap("cap:in=media:void;test-offline;out=media:void")
    assert cached.title == "Test Cap"


# TEST909 (deleted): monkey-patched the private `_fetch_from_registry`
# method on the unified FabricRegistry. The method no longer exists
# and re-asserting the behavior observably would either require a
# real network round-trip or instrument the public HTTP client (an
# implementation detail). End-to-end fetch behavior is exercised by
# integration tests against a live test fixture. The TEST908 pair
# above (cached caps remain accessible while offline) carries the
# offline-mode behavior contract on its own.


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
    registry = FabricRegistry.new_for_test_with_config(config)

    assert registry.config.registry_base_url == "https://test-registry.local"


# TEST6333: Test adding caps to the registry cache and retrieving them
@pytest.mark.asyncio
async def test_6333_registry_add_caps_to_cache():
    registry = FabricRegistry.new_for_test()

    urn = CapUrn.from_string(_test_urn("test"))
    cap = Cap(urn, "Test Cap", "test-command")

    registry.add_caps_to_cache([cap])

    cached_caps = await registry.get_cached_caps()
    titles = [c.title for c in cached_caps]
    assert "Test Cap" in titles


# TEST6336: Test registry configuration builder sets registry and schema URLs
def test_6336_registry_config_builder_pattern():
    config = (RegistryConfig()
              .with_registry_url("https://custom.registry")
              .with_schema_url("https://custom.schemas"))

    assert config.registry_base_url == "https://custom.registry"
    assert config.schema_base_url == "https://custom.schemas"


# TEST6340: normalize_cap_urn strips trailing semicolons, producing the
# same canonical form with or without a trailing semicolon
def test_6340_normalize_urn_with_trailing_semicolon():
    urn1 = _test_urn("test")
    urn2 = _test_urn("test") + ";"

    normalized1 = normalize_cap_urn(urn1)
    normalized2 = normalize_cap_urn(urn2)

    assert normalized1 == normalized2


# TEST6396: A malformed cap URN must FAIL HARD with a ParseError, not be
# passed through raw (the old fallback) and surface later as a misleading
# NotFound. The `out` value below contains an unquoted `=`, which the cap
# grammar rejects. Against the old `except Exception: return urn` fallback,
# normalize_cap_urn returned the raw string and _cap_defver then reported
# "not part of manifest" (a NotFoundError); this test asserts the truthful
# error type on both the direct and the public (get_cap) paths.
@pytest.mark.asyncio
async def test_6396_malformed_cap_urn_fails_hard():
    malformed = 'cap:coerce;in="media:integer;numeric";out=media:enc=utf-8'

    # Direct normalization path must raise ParseError, NOT return the raw URN.
    with pytest.raises(ParseError):
        normalize_cap_urn(malformed)

    # Public path (get_cap) must surface ParseError, NOT NotFoundError.
    registry = FabricRegistry.new_for_test()
    with pytest.raises(ParseError):
        await registry.get_cap(malformed)


# TEST1893: Cache root is namespaced per registry origin. Without the
# per-origin namespace, a cache populated from one registry (prod) is
# reused to satisfy a lookup against a different registry (staging) — and
# they serve different bytes for the same URN/version, so the lookup
# resolves against the wrong snapshot. This pins three properties: distinct
# origins must NOT share a cache root; the same origin must map to a stable
# (deterministic) root, or caching never hits; and the slug is the same
# slug_for(url) scheme the cartridge registry layout uses, living directly
# under the shared "capdag" cache directory.
def test_1893_cache_root_is_namespaced_per_registry_origin():
    from capdag.bifaci.cartridge_slug import slug_for

    prod_url = "https://fabric.capdag.com"
    staging_url = "https://fabric-staging.capdag.com"

    prod = FabricRegistry._get_cache_dir(prod_url)
    staging = FabricRegistry._get_cache_dir(staging_url)
    staging_again = FabricRegistry._get_cache_dir(staging_url)

    # Distinct origins → distinct cache roots: prod and staging serve
    # different bytes for the same URN/version, so they must never share.
    assert prod != staging, (
        "prod and staging must not share a cache root — they serve "
        "different bytes for the same URN/version"
    )
    # Same origin → identical (deterministic) root, or caching never hits.
    assert staging == staging_again, (
        "the same registry origin must map to a stable cache root, or "
        "caching never hits"
    )

    # The final path component is exactly the cartridge-registry slug of the
    # origin URL — one slug scheme across the codebase.
    assert staging.name == slug_for(staging_url), (
        "cache root must end in slug_for(registry_url)"
    )
    # And the parent of that slug is the shared "capdag" cache directory.
    assert staging.parent.name == "capdag", (
        "the per-origin slug must live under the capdag cache directory"
    )
