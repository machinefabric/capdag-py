"""Tests for ResponseWrapper - mirroring capdag Rust tests

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
import json
from dataclasses import dataclass
from capdag.cap.response import ResponseWrapper


@dataclass
class SampleStruct:
    """Sample structure for JSON deserialization testing"""
    name: str
    value: int


# TEST168: Test ResponseWrapper from JSON deserializes to correct structured type
def test_168_json_response():
    test_data = SampleStruct(name="test", value=42)
    json_str = json.dumps({"name": "test", "value": 42})
    response = ResponseWrapper.from_json(json_str.encode('utf-8'))

    parsed = response.as_type(SampleStruct)
    assert parsed.name == test_data.name
    assert parsed.value == test_data.value


# TEST169: Test ResponseWrapper converts to primitive types integer, float, boolean, string
def test_169_primitive_types():
    # Test integer
    response = ResponseWrapper.from_text(b"42")
    assert response.as_int() == 42

    # Test float
    response = ResponseWrapper.from_text(b"3.14")
    assert response.as_float() == 3.14

    # Test boolean
    response = ResponseWrapper.from_text(b"true")
    assert response.as_bool() is True

    # Test string
    response = ResponseWrapper.from_text(b"hello world")
    assert response.as_string() == "hello world"


# TEST170: Test ResponseWrapper from binary stores and retrieves raw bytes correctly
def test_170_binary_response():
    binary_data = bytes([0x89, 0x50, 0x4E, 0x47])  # PNG header
    response = ResponseWrapper.from_binary(binary_data)

    retrieved = response.as_bytes()
    assert retrieved == binary_data
    assert len(retrieved) == 4
    assert retrieved[0] == 0x89


# TEST599: is_empty returns true for empty response, false for non-empty
def test_599_is_empty():
    empty_json = ResponseWrapper.from_json(b"")
    assert empty_json.is_empty()

    empty_text = ResponseWrapper.from_text(b"")
    assert empty_text.is_empty()

    empty_binary = ResponseWrapper.from_binary(b"")
    assert empty_binary.is_empty()

    non_empty = ResponseWrapper.from_text(b"x")
    assert not non_empty.is_empty()


# TEST600: size returns exact byte count for all content types
def test_600_size():
    text = ResponseWrapper.from_text(b"hello")
    assert text.size() == 5

    json_resp = ResponseWrapper.from_json(b"{}")
    assert json_resp.size() == 2

    binary = ResponseWrapper.from_binary(bytes(1024))
    assert binary.size() == 1024

    empty = ResponseWrapper.from_text(b"")
    assert empty.size() == 0


# TEST601: get_content_type returns correct MIME type for each variant
def test_601_get_content_type():
    json_resp = ResponseWrapper.from_json(b"{}")
    assert json_resp.get_content_type() == "application/json"

    text = ResponseWrapper.from_text(b"hello")
    assert text.get_content_type() == "text/plain"

    binary = ResponseWrapper.from_binary(bytes([0xFF]))
    assert binary.get_content_type() == "application/octet-stream"


# TEST602: as_type on binary response returns error (cannot deserialize binary)
def test_602_as_type_binary_error():
    binary = ResponseWrapper.from_binary(bytes([0x89, 0x50]))
    with pytest.raises(ValueError) as exc_info:
        binary.as_type(SampleStruct)
    assert "binary" in str(exc_info.value).lower(), \
        f"Error should mention binary: {exc_info.value}"


# TEST603: as_bool handles all accepted truthy/falsy variants and rejects garbage
def test_603_as_bool_edge_cases():
    # Truthy values
    for input_val in [b"true", b"TRUE", b"True", b"1", b"yes", b"YES", b"y", b"Y"]:
        resp = ResponseWrapper.from_text(input_val)
        assert resp.as_bool() is True, f"'{input_val.decode()}' should be truthy"

    # Falsy values
    for input_val in [b"false", b"FALSE", b"False", b"0", b"no", b"NO", b"n", b"N"]:
        resp = ResponseWrapper.from_text(input_val)
        assert resp.as_bool() is False, f"'{input_val.decode()}' should be falsy"

    # Garbage input should error
    garbage = ResponseWrapper.from_text(b"maybe")
    with pytest.raises(ValueError):
        garbage.as_bool()

    # Whitespace-padded should still work
    padded = ResponseWrapper.from_text(b"  true  ")
    assert padded.as_bool() is True
