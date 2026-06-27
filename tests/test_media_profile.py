"""Tests for media profile schema registry — mirroring capdag Rust tests.

The registry no longer bundles JSON Schema bodies. Tests that exercise
validation seed the registry explicitly via ``insert_schema`` so they
hit a real compiled schema rather than the unknown-URL skip path."""

import pytest
from capdag.media.profile import ProfileSchemaRegistry, ProfileSchemaError
from capdag.media.spec import (
    PROFILE_STR,
    PROFILE_INT,
    PROFILE_NUM,
    PROFILE_BOOL,
    PROFILE_OBJ,
    PROFILE_STR_ARRAY,
    PROFILE_NUM_ARRAY,
    PROFILE_BOOL_ARRAY,
    PROFILE_OBJ_ARRAY,
)


_STANDARD_SCHEMAS = {
    PROFILE_STR: {"$schema": "https://json-schema.org/draft/2020-12/schema",
                  "$id": PROFILE_STR, "type": "string"},
    PROFILE_INT: {"$schema": "https://json-schema.org/draft/2020-12/schema",
                  "$id": PROFILE_INT, "type": "integer"},
    PROFILE_NUM: {"$schema": "https://json-schema.org/draft/2020-12/schema",
                  "$id": PROFILE_NUM, "type": "number"},
    PROFILE_BOOL: {"$schema": "https://json-schema.org/draft/2020-12/schema",
                   "$id": PROFILE_BOOL, "type": "boolean"},
    PROFILE_OBJ: {"$schema": "https://json-schema.org/draft/2020-12/schema",
                  "$id": PROFILE_OBJ, "type": "object"},
    PROFILE_STR_ARRAY: {"$schema": "https://json-schema.org/draft/2020-12/schema",
                        "$id": PROFILE_STR_ARRAY, "type": "array",
                        "items": {"type": "string"}},
    PROFILE_NUM_ARRAY: {"$schema": "https://json-schema.org/draft/2020-12/schema",
                        "$id": PROFILE_NUM_ARRAY, "type": "array",
                        "items": {"type": "number"}},
    PROFILE_BOOL_ARRAY: {"$schema": "https://json-schema.org/draft/2020-12/schema",
                         "$id": PROFILE_BOOL_ARRAY, "type": "array",
                         "items": {"type": "boolean"}},
    PROFILE_OBJ_ARRAY: {"$schema": "https://json-schema.org/draft/2020-12/schema",
                        "$id": PROFILE_OBJ_ARRAY, "type": "array",
                        "items": {"type": "object"}},
}


def create_test_registry():
    """Create a registry seeded with the well-known scalar/array schemas."""
    registry = ProfileSchemaRegistry()
    for url, schema in _STANDARD_SCHEMAS.items():
        registry.insert_schema(url, schema)
    return registry


def create_empty_test_registry():
    """Create a registry with no schemas seeded."""
    return ProfileSchemaRegistry()


# TEST611: insert_schema seeds the cache so subsequent validation hits a real
# compiled schema rather than the skip-on-unknown path. A registry that
# silently dropped inserts would let validation calls return None even for
# inputs that violate the schema.
def test_611_insert_schema_populates_cache():
    registry = create_empty_test_registry()
    assert not registry.schema_exists(PROFILE_STR)

    registry.insert_schema(PROFILE_STR, _STANDARD_SCHEMAS[PROFILE_STR])

    assert registry.schema_exists(PROFILE_STR)
    assert registry.validate_cached(PROFILE_STR, "ok") is None
    errors = registry.validate_cached(PROFILE_STR, 7)
    assert errors is not None, "Number must not validate against the string schema"


# TEST612: clear_cache empties all in-memory schemas
def test_612_clear_cache():
    registry = create_test_registry()
    assert len(registry.get_cached_profiles()) > 0
    registry.clear_cache()
    assert len(registry.get_cached_profiles()) == 0


# TEST613: validate_cached validates against seeded schemas
def test_613_validate_cached():
    registry = create_test_registry()

    assert registry.validate_cached(PROFILE_STR, "hello") is None
    assert registry.validate_cached(PROFILE_STR, 42) is not None

    assert registry.validate_cached(PROFILE_INT, 42) is None

    assert registry.validate_cached(PROFILE_OBJ_ARRAY, [{"key": "value"}]) is None
    assert registry.validate_cached(PROFILE_OBJ_ARRAY, ["not", "objects"]) is not None

    # Unknown profile returns None (skip validation)
    assert registry.validate_cached("https://example.com/unknown", "anything") is None


# TEST6607: A freshly constructed registry is operational and reports an empty
# cache. Schemas must be inserted explicitly — none are bundled.
def test_6607_registry_creation():
    registry = create_empty_test_registry()
    assert registry.get_cached_profiles() == []


# TEST6608: A freshly constructed registry has no cached schemas. The well-known
# profile URLs are not bundled into the library; callers must seed them
# (via insert_schema) or fetch and seed from the public registry.
def test_6608_fresh_registry_cache_is_empty():
    registry = create_empty_test_registry()
    assert registry.get_cached_profiles() == [], (
        "Fresh registry must have no cached schemas; nothing is bundled into the library"
    )
    assert not registry.schema_exists(PROFILE_STR)
    assert not registry.schema_exists(PROFILE_OBJ_ARRAY)


# TEST620: Verify string schema validates strings and rejects non-strings
def test_620_string_validation():
    registry = create_test_registry()
    assert registry.validate(PROFILE_STR, "hello") is None
    assert registry.validate(PROFILE_STR, 42) is not None


# TEST621: Verify integer schema validates integers and rejects floats and strings
def test_621_integer_validation():
    registry = create_test_registry()
    assert registry.validate(PROFILE_INT, 42) is None
    assert registry.validate(PROFILE_INT, 3.14) is not None
    assert registry.validate(PROFILE_INT, "hello") is not None


# TEST622: Verify number schema validates integers and floats, rejects strings
def test_622_number_validation():
    registry = create_test_registry()
    assert registry.validate(PROFILE_NUM, 42) is None
    assert registry.validate(PROFILE_NUM, 3.14) is None
    assert registry.validate(PROFILE_NUM, "hello") is not None


# TEST623: Verify boolean schema validates true/false and rejects string "true"
def test_623_boolean_validation():
    registry = create_test_registry()
    assert registry.validate(PROFILE_BOOL, True) is None
    assert registry.validate(PROFILE_BOOL, False) is None
    assert registry.validate(PROFILE_BOOL, "true") is not None


# TEST624: Verify object schema validates objects and rejects arrays
def test_624_object_validation():
    registry = create_test_registry()
    assert registry.validate(PROFILE_OBJ, {"key": "value"}) is None
    assert registry.validate(PROFILE_OBJ, [1, 2, 3]) is not None


# TEST625: Verify string array schema validates string arrays and rejects mixed arrays
def test_625_string_array_validation():
    registry = create_test_registry()
    assert registry.validate(PROFILE_STR_ARRAY, ["a", "b", "c"]) is None
    assert registry.validate(PROFILE_STR_ARRAY, ["a", 1, "c"]) is not None
    assert registry.validate(PROFILE_STR_ARRAY, "hello") is not None


# TEST626: Verify unknown profile URL skips validation and returns None
def test_626_unknown_profile_skips_validation():
    registry = create_empty_test_registry()
    assert registry.validate("https://example.com/unknown", "anything") is None


# TEST627: insert_schema rejects malformed JSON Schemas instead of caching them.
# Silent acceptance of an invalid schema would hide the configuration error
# until the first validation call against it.
def test_627_insert_schema_rejects_invalid_schema():
    registry = create_empty_test_registry()
    bad = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": 99}
    with pytest.raises(ProfileSchemaError):
        registry.insert_schema("https://capdag.com/schema/bad", bad)
    assert not registry.schema_exists("https://capdag.com/schema/bad"), (
        "Failed insert must not leave the URL in the cache"
    )
