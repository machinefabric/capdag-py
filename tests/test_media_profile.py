"""Tests for media profile schema registry - mirroring capdag Rust tests"""

import pytest
from capdag.media.profile import ProfileSchemaRegistry, is_embedded_profile
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


def create_test_registry():
    """Create a fresh test registry with embedded schemas."""
    return ProfileSchemaRegistry()


# TEST611: is_embedded_profile recognizes all 9 embedded profiles and rejects non-embedded
def test_611_is_embedded_profile_comprehensive():
    all_embedded = [
        PROFILE_STR, PROFILE_INT, PROFILE_NUM, PROFILE_BOOL, PROFILE_OBJ,
        PROFILE_STR_ARRAY, PROFILE_NUM_ARRAY, PROFILE_BOOL_ARRAY, PROFILE_OBJ_ARRAY,
    ]
    for url in all_embedded:
        assert is_embedded_profile(url), f"{url} should be recognized as embedded"

    # Custom/invalid URLs should not be recognized
    assert not is_embedded_profile("https://example.com/schema/custom")
    assert not is_embedded_profile("")
    assert not is_embedded_profile("https://capdag.com/schema/nonexistent")


# TEST612: clear_cache empties all in-memory schemas
def test_612_clear_cache():
    registry = create_test_registry()
    # Embedded schemas should be loaded
    assert len(registry.get_cached_profiles()) > 0
    registry.clear_cache()
    assert len(registry.get_cached_profiles()) == 0


# TEST613: validate_cached validates against cached standard schemas
def test_613_validate_cached():
    registry = create_test_registry()

    # String validation
    assert registry.validate_cached(PROFILE_STR, "hello") is None
    errors = registry.validate_cached(PROFILE_STR, 42)
    assert errors is not None

    # Integer validation
    assert registry.validate_cached(PROFILE_INT, 42) is None

    # Object array validation
    assert registry.validate_cached(PROFILE_OBJ_ARRAY, [{"key": "value"}]) is None
    errors = registry.validate_cached(PROFILE_OBJ_ARRAY, ["not", "objects"])
    assert errors is not None

    # Unknown profile returns None (skip validation)
    assert registry.validate_cached("https://example.com/unknown", "anything") is None


# TEST618: Verify profile schema registry creation succeeds with temp cache
def test_618_registry_creation():
    registry = create_test_registry()
    profiles = registry.get_cached_profiles()
    assert len(profiles) > 0


# TEST619: Verify all 9 embedded standard schemas are loaded on creation
def test_619_embedded_schemas_loaded():
    registry = create_test_registry()
    all_embedded = [
        PROFILE_STR, PROFILE_INT, PROFILE_NUM, PROFILE_BOOL, PROFILE_OBJ,
        PROFILE_STR_ARRAY, PROFILE_NUM_ARRAY, PROFILE_BOOL_ARRAY, PROFILE_OBJ_ARRAY,
    ]
    for url in all_embedded:
        assert registry.schema_exists(url), f"Schema {url} should be loaded"


# TEST620: Verify string schema validates strings and rejects non-strings
def test_620_string_validation():
    registry = create_test_registry()
    assert registry.validate(PROFILE_STR, "hello") is None
    errors = registry.validate(PROFILE_STR, 42)
    assert errors is not None


# TEST621: Verify integer schema validates integers and rejects floats and strings
def test_621_integer_validation():
    registry = create_test_registry()
    assert registry.validate(PROFILE_INT, 42) is None
    errors = registry.validate(PROFILE_INT, 3.14)
    assert errors is not None
    errors = registry.validate(PROFILE_INT, "hello")
    assert errors is not None


# TEST622: Verify number schema validates integers and floats, rejects strings
def test_622_number_validation():
    registry = create_test_registry()
    assert registry.validate(PROFILE_NUM, 42) is None
    assert registry.validate(PROFILE_NUM, 3.14) is None
    errors = registry.validate(PROFILE_NUM, "hello")
    assert errors is not None


# TEST623: Verify boolean schema validates true/false and rejects string "true"
def test_623_boolean_validation():
    registry = create_test_registry()
    assert registry.validate(PROFILE_BOOL, True) is None
    assert registry.validate(PROFILE_BOOL, False) is None
    errors = registry.validate(PROFILE_BOOL, "true")
    assert errors is not None


# TEST624: Verify object schema validates objects and rejects arrays
def test_624_object_validation():
    registry = create_test_registry()
    assert registry.validate(PROFILE_OBJ, {"key": "value"}) is None
    errors = registry.validate(PROFILE_OBJ, [1, 2, 3])
    assert errors is not None


# TEST625: Verify string array schema validates string arrays and rejects mixed arrays
def test_625_string_array_validation():
    registry = create_test_registry()
    assert registry.validate(PROFILE_STR_ARRAY, ["a", "b", "c"]) is None
    errors = registry.validate(PROFILE_STR_ARRAY, ["a", 1, "c"])
    assert errors is not None
    errors = registry.validate(PROFILE_STR_ARRAY, "hello")
    assert errors is not None


# TEST626: Verify unknown profile URL skips validation and returns Ok
def test_626_unknown_profile_skips_validation():
    registry = create_test_registry()
    result = registry.validate("https://example.com/unknown", "anything")
    assert result is None


# TEST627: Verify is_embedded_profile recognizes standard and rejects custom URLs
def test_627_is_embedded_profile():
    assert is_embedded_profile(PROFILE_STR)
    assert is_embedded_profile(PROFILE_INT)
    assert not is_embedded_profile("https://example.com/custom")
