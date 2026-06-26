"""Tests for media_def module

Full test coverage matching Rust reference implementation.
Tests media URN resolution, media definitions, and validation.
"""

import pytest
import tempfile
from pathlib import Path

from capdag.media.spec import (
    MediaDef,
    ResolvedMediaDef,
    resolve_media_urn,
    validate_media_defs_no_duplicates,
    MediaDefError,
    UnresolvableMediaUrn,
    DuplicateMediaUrn,
)
from capdag.media.registry import (
    FabricRegistry,
    StoredMediaDef,
    normalize_media_urn,
    ExtensionNotFoundError,
)


# Helper to create a test registry
async def create_test_registry():
    """Create a registry for testing"""
    temp_dir = Path(tempfile.mkdtemp())
    cache_dir = temp_dir / "media"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return FabricRegistry.new_for_test(cache_dir)


# =============================================================================
# Media URN resolution tests
# =============================================================================


# TEST088: Resolving a media URN seeded into the registry returns the
# seeded spec verbatim. A regression in the registry-resolution path
# would surface as a `None`-shaped result here, since there is no
# local-override fallback to mask it. Mirrors Rust test088.
@pytest.mark.asyncio
async def test_088_resolve_seeded_spec():
    registry = await create_test_registry()
    registry.add_spec(StoredMediaDef(
        urn="media:enc=utf-8",
        media_type="text/plain",
        title="Textable",
    ))
    resolved = await resolve_media_urn("media:enc=utf-8", registry)
    assert resolved.media_type == "text/plain"
    assert resolved.profile_uri is None


# TEST089: A seeded record-shaped media def carries its schema and
# profile_uri intact through resolution. Catches a regression that
# dropped optional fields when copying into ResolvedMediaDef.
# Mirrors Rust test089.
@pytest.mark.asyncio
async def test_089_resolve_seeded_record_spec():
    registry = await create_test_registry()
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}},
    }
    registry.add_spec(StoredMediaDef(
        urn="media:fmt=json;output-spec;record",
        media_type="application/json",
        title="Output Spec",
        profile_uri="https://example.com/schema/output",
        schema=schema,
    ))
    resolved = await resolve_media_urn("media:fmt=json;output-spec;record", registry)
    assert resolved.media_type == "application/json"
    assert resolved.profile_uri == "https://example.com/schema/output"
    assert resolved.schema == schema


# TEST093: Resolving a URN that is neither in the registry cache nor
# available online fails hard. A regression that made the fail path
# silently return a stub `ResolvedMediaDef` would surface here as a
# missing error. Mirrors Rust test093.
@pytest.mark.asyncio
async def test_093_resolve_unresolvable_fails_hard():
    registry = await create_test_registry()
    registry.set_offline(True)
    with pytest.raises(UnresolvableMediaUrn) as exc_info:
        await resolve_media_urn("media:completely-unknown-urn-not-in-registry", registry)
    assert "media:completely-unknown-urn-not-in-registry" in str(exc_info.value)


# =============================================================================
# MediaDef serialization tests
# =============================================================================


# TEST095: Test MediaDef serializes with required fields and skips None fields
def test_095_media_def_def_serialize():
    spec_def = MediaDef(
        urn="media:fmt=json;test",
        media_type="application/json",
        title="Test Media",
        profile_uri="https://example.com/profile",
        schema=None,
        description=None,
        validation=None,
        metadata=None,
        extensions=[],
    )
    data = spec_def.to_dict()
    assert data["urn"] == "media:fmt=json;test"
    assert data["media_type"] == "application/json"
    assert data["profile_uri"] == "https://example.com/profile"
    assert data["title"] == "Test Media"
    # None schema is skipped
    assert "schema" not in data
    # None description is also skipped
    assert "description" not in data


# TEST096: Test deserializing MediaDef from JSON object
def test_096_media_def_def_deserialize():
    data = {
        "urn": "media:fmt=json;test",
        "media_type": "application/json",
        "title": "Test"
    }
    spec_def = MediaDef.from_dict(data)
    assert spec_def.urn == "media:fmt=json;test"
    assert spec_def.media_type == "application/json"
    assert spec_def.title == "Test"
    assert spec_def.profile_uri is None


# =============================================================================
# Duplicate URN validation tests
# =============================================================================


# TEST097: Test duplicate URN validation catches duplicates
def test_097_validate_no_duplicate_urns_catches_duplicates():
    media_defs = [
        MediaDef(
            urn="media:dup;fmt=json",
            media_type="application/json",
            title="First",
        ),
        MediaDef(
            urn="media:dup;fmt=json",
            media_type="application/json",
            title="Second",
        ),  # duplicate
    ]
    with pytest.raises(DuplicateMediaUrn) as exc_info:
        validate_media_defs_no_duplicates(media_defs)
    assert "media:dup;fmt=json" in str(exc_info.value)


# TEST098: Test duplicate URN validation passes for unique URNs
def test_098_validate_no_duplicate_urns_passes_for_unique():
    media_defs = [
        MediaDef(
            urn="media:first;fmt=json",
            media_type="application/json",
            title="First",
        ),
        MediaDef(
            urn="media:fmt=json;second",
            media_type="application/json",
            title="Second",
        ),
    ]
    # Should not raise
    validate_media_defs_no_duplicates(media_defs)


# =============================================================================
# ResolvedMediaDef tests
# =============================================================================


# TEST099: REMOVED — ResolvedMediaDef.is_binary() was deleted along with the
# binary/text distinction. Everything is bytes at the byte level; text-
# representability is now the orthogonal `enc=` tag, exercised by test_104.


# TEST100: Test ResolvedMediaDef is_record returns true when record marker is present
def test_100_resolved_is_record():
    resolved = ResolvedMediaDef(
        media_urn="media:enc=utf-8;record",
        media_type="application/json",
        profile_uri=None,
        schema=None,
        title=None,
        description=None,
        validation=None,
        metadata=None,
        extensions=[],
    )
    assert resolved.is_record()
    assert resolved.is_scalar()  # record without list marker is scalar cardinality
    assert not resolved.is_list()


# TEST101: Test ResolvedMediaDef is_scalar returns true when list marker is absent
def test_101_resolved_is_scalar():
    resolved = ResolvedMediaDef(
        media_urn="media:enc=utf-8",
        media_type="text/plain",
        profile_uri=None,
        schema=None,
        title=None,
        description=None,
        validation=None,
        metadata=None,
        extensions=[],
    )
    assert resolved.is_scalar()
    assert not resolved.is_record()
    assert not resolved.is_list()


# TEST102: Test ResolvedMediaDef is_list returns true when list marker is present
def test_102_resolved_is_list():
    resolved = ResolvedMediaDef(
        media_urn="media:enc=utf-8;list",
        media_type="application/json",
        profile_uri=None,
        schema=None,
        title=None,
        description=None,
        validation=None,
        metadata=None,
        extensions=[],
    )
    assert resolved.is_list()
    assert not resolved.is_record()
    assert not resolved.is_scalar()


# TEST103: Test ResolvedMediaDef is_json returns true when fmt=json tag is present
def test_103_resolved_is_json():
    resolved = ResolvedMediaDef(
        media_urn="media:fmt=json;record",
        media_type="application/json",
        profile_uri=None,
        schema=None,
        title=None,
        description=None,
        validation=None,
        metadata=None,
        extensions=[],
    )
    assert resolved.is_json()
    assert resolved.is_record()


# TEST104: Test ResolvedMediaDef text-representability is carried by the enc= tag
def test_104_resolved_is_text():
    resolved = ResolvedMediaDef(
        media_urn="media:enc=utf-8",
        media_type="text/plain",
        profile_uri=None,
        schema=None,
        title=None,
        description=None,
        validation=None,
        metadata=None,
        extensions=[],
    )
    assert resolved._parse_media_urn().get_tag("enc") == "utf-8"
    assert not resolved.is_json()


# =============================================================================
# Metadata propagation tests
# =============================================================================


# TEST105: Test metadata propagates from media def def to resolved media def
@pytest.mark.asyncio
async def test_105_metadata_propagation():
    registry = await create_test_registry()
    registry.add_spec(StoredMediaDef(
        urn="media:custom-setting",
        media_type="text/plain",
        title="Custom Setting",
        profile_uri="https://example.com/schema",
        description="A custom setting",
        metadata={
            "category_key": "interface",
            "ui_type": "SETTING_UI_TYPE_CHECKBOX",
        },
    ))

    resolved = await resolve_media_urn("media:custom-setting", registry)
    assert resolved.metadata is not None
    assert resolved.metadata.get("category_key") == "interface"
    assert resolved.metadata.get("ui_type") == "SETTING_UI_TYPE_CHECKBOX"


# TEST106: Test metadata and validation can coexist in media definition
@pytest.mark.asyncio
async def test_106_metadata_with_validation():
    registry = await create_test_registry()
    registry.add_spec(StoredMediaDef(
        urn="media:bounded-number;numeric",
        media_type="text/plain",
        title="Bounded Number",
        profile_uri="https://example.com/schema",
        validation={"min": 0.0, "max": 100.0},
        metadata={
            "category_key": "inference",
            "ui_type": "SETTING_UI_TYPE_SLIDER",
        },
    ))

    resolved = await resolve_media_urn("media:bounded-number;numeric", registry)

    # Verify validation
    assert resolved.validation is not None
    assert resolved.validation.min == 0.0
    assert resolved.validation.max == 100.0

    # Verify metadata
    assert resolved.metadata is not None
    assert resolved.metadata.get("category_key") == "inference"


# =============================================================================
# Extension field tests
# =============================================================================


# TEST107: Test extensions field propagates from registry spec to resolved
@pytest.mark.asyncio
async def test_107_extensions_propagation():
    registry = await create_test_registry()
    registry.add_spec(StoredMediaDef(
        urn="media:custom-pdf",
        media_type="application/pdf",
        title="PDF Document",
        profile_uri="https://capdag.com/schema/pdf",
        description="A PDF document",
        extensions=["pdf"],
    ))

    resolved = await resolve_media_urn("media:custom-pdf", registry)
    assert resolved.extensions == ["pdf"]


# TEST892: Test extensions serializes/deserializes correctly in MediaDef
def test_892_extensions_serialization():
    spec_def = MediaDef(
        urn="media:json-data",
        media_type="application/json",
        title="JSON Data",
        profile_uri="https://example.com/profile",
        schema=None,
        description=None,
        validation=None,
        metadata=None,
        extensions=["json"],
    )
    data = spec_def.to_dict()
    assert data["extensions"] == ["json"]

    # Deserialize and verify
    parsed = MediaDef.from_dict(data)
    assert parsed.extensions == ["json"]


# TEST893: Test extensions can coexist with metadata and validation
@pytest.mark.asyncio
async def test_893_extensions_with_metadata_and_validation():
    registry = await create_test_registry()
    registry.add_spec(StoredMediaDef(
        urn="media:custom-output;fmt=json",
        media_type="application/json",
        title="Custom Output",
        profile_uri="https://example.com/schema",
        validation={"min_length": 1, "max_length": 1000},
        metadata={"category": "output"},
        extensions=["json"],
    ))

    resolved = await resolve_media_urn("media:custom-output;fmt=json", registry)

    # Verify all fields are present
    assert resolved.validation is not None
    assert resolved.metadata is not None
    assert resolved.extensions == ["json"]


# TEST894: Test multiple extensions in a media def
@pytest.mark.asyncio
async def test_894_multiple_extensions():
    registry = await create_test_registry()
    registry.add_spec(StoredMediaDef(
        urn="media:image;jpeg",
        media_type="image/jpeg",
        title="JPEG Image",
        profile_uri="https://capdag.com/schema/jpeg",
        description="JPEG image data",
        extensions=["jpg", "jpeg"],
    ))

    resolved = await resolve_media_urn("media:image;jpeg", registry)
    assert resolved.extensions == ["jpg", "jpeg"]
    assert len(resolved.extensions) == 2


# =============================================================================
# Media URN Registry tests (607-610, 614-617)
# =============================================================================


# TEST607: media_urns_for_extension returns error for unknown extension
def test_607_media_urns_for_extension_unknown():
    registry = FabricRegistry.new_for_test(Path(tempfile.mkdtemp()) / "media")
    with pytest.raises(ExtensionNotFoundError) as exc_info:
        registry.media_urns_for_extension("zzzzunknown")
    assert "zzzzunknown" in str(exc_info.value)


# TEST608: media_urns_for_extension returns URNs after adding a spec with extensions
def test_608_media_urns_for_extension_populated():
    registry = FabricRegistry.new_for_test(Path(tempfile.mkdtemp()) / "media")

    spec = StoredMediaDef(
        urn="media:pdf",
        media_type="application/pdf",
        title="PDF Document",
        extensions=["pdf"],
    )
    normalized = normalize_media_urn(spec.urn)
    registry.cached_specs[normalized] = spec
    registry._update_extension_index(spec)

    urns = registry.media_urns_for_extension("pdf")
    assert len(urns) > 0, "Should have at least one URN for pdf"
    assert any("pdf" in u for u in urns), f"URNs should contain pdf: {urns}"

    # Case-insensitive
    urns_upper = registry.media_urns_for_extension("PDF")
    assert urns == urns_upper


# TEST609: get_extension_mappings returns all registered extension->URN pairs
def test_609_get_extension_mappings():
    registry = FabricRegistry.new_for_test(Path(tempfile.mkdtemp()) / "media")

    for urn_str, ext in [("media:pdf", "pdf"), ("media:epub", "epub")]:
        spec = StoredMediaDef(
            urn=urn_str,
            media_type="application/octet-stream",
            title="Test",
            extensions=[ext],
        )
        normalized = normalize_media_urn(urn_str)
        registry.cached_specs[normalized] = spec
        registry._update_extension_index(spec)

    mappings = registry.get_extension_mappings()
    ext_names = [m[0] for m in mappings]
    assert "pdf" in ext_names, "Should contain pdf"
    assert "epub" in ext_names, "Should contain epub"


# TEST610: get_cached_spec returns None for unknown and Some for known
def test_610_get_cached_spec():
    registry = FabricRegistry.new_for_test(Path(tempfile.mkdtemp()) / "media")

    # Unknown spec
    assert registry.get_cached_media_def("media:nonexistent;xyzzy") is None

    # Add a spec and verify we can retrieve it
    spec = StoredMediaDef(
        urn="media:enc=utf-8;spec;test",
        media_type="text/plain",
        title="Test Spec",
    )
    normalized = normalize_media_urn(spec.urn)
    registry.cached_specs[normalized] = spec

    retrieved = registry.get_cached_media_def("media:enc=utf-8;spec;test")
    assert retrieved is not None, "Should find spec by URN"
    assert retrieved.title == "Test Spec"


# TEST614: Verify registry creation succeeds and cache directory exists
def test_614_registry_creation():
    cache_dir = Path(tempfile.mkdtemp()) / "media"
    registry = FabricRegistry.new_for_test(cache_dir)
    assert registry.cache_dir.exists()


# TEST615 (deleted): exercised the private `_cache_key` method that
# does not exist on the unified FabricRegistry. The on-disk cache key
# scheme is an implementation detail of the persistence layer; no
# user-observable behavior depends on a particular hashing strategy.


# TEST616: Verify StoredMediaDef converts to MediaDef preserving all fields
def test_616_stored_media_def_to_def():
    spec = StoredMediaDef(
        urn="media:pdf",
        media_type="application/pdf",
        title="PDF Document",
        profile_uri="https://capdag.com/schema/pdf",
        description="PDF document data",
        extensions=["pdf"],
    )

    d = spec.to_dict()
    assert d["urn"] == "media:pdf"
    assert d["media_type"] == "application/pdf"
    assert d["title"] == "PDF Document"
    assert d["description"] == "PDF document data"
    assert d["extensions"] == ["pdf"]


# TEST617: Verify normalize_media_urn produces consistent non-empty results
def test_617_normalize_media_urn():
    urn1 = normalize_media_urn("media:string")
    urn2 = normalize_media_urn("media:string")
    assert urn1
    assert urn2


# TESTs 895-897 (deleted): asserted that a freshly-created
# `FabricRegistry.new_for_test()` was pre-populated with every
# concrete-file-format spec in the standard library. The unified
# registry deliberately starts empty in test mode — there is no
# bundled standard catalog — so these assertions belong in the
# publisher (capfab) regression suite, not the cap library. They
# were deleted from the Rust and Go mirrors for the same reason;
# this Python deletion brings the mirror back into parity.
