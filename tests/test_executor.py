"""Tests for planner executor helper behavior."""

from capdag.planner.executor import apply_edge_type, extract_json_path
from capdag.planner.plan import EdgeType
from capdag.planner.error import InternalError


# TEST804: Tests basic JSON path extraction with dot notation for nested objects Verifies that simple paths like "data.message" correctly extract values from nested JSON structures
def test_804_extract_json_path_simple():
    data = {"data": {"message": "hello world"}}
    assert extract_json_path(data, "data.message") == "hello world"


# TEST805: Tests JSON path extraction with array indexing syntax Verifies that bracket notation like "items[0].name" correctly accesses array elements and their nested fields
def test_805_extract_json_path_with_array():
    data = {"items": [{"name": "first"}, {"name": "second"}]}
    assert extract_json_path(data, "items[0].name") == "first"


# TEST806: Tests error handling when JSON path references non-existent fields Verifies that accessing missing fields returns an appropriate error message
def test_806_extract_json_path_missing_field():
    data = {"data": {}}
    try:
        extract_json_path(data, "data.nonexistent")
        assert False, "expected missing-field failure"
    except InternalError as exc:
        assert "Field 'nonexistent' not found" in str(exc)


# TEST807: Tests EdgeType::Direct passes JSON values through unchanged Verifies that Direct edge type acts as a transparent passthrough without transformation
def test_807_apply_edge_type_direct():
    value = {"test": "value"}
    assert apply_edge_type(value, EdgeType.direct()) == value


# TEST808: Tests EdgeType::JsonField extracts specific top-level fields from JSON objects Verifies that JsonField edge type correctly isolates a single named field from the source output
def test_808_apply_edge_type_json_field():
    value = {"test": "value", "other": "data"}
    assert apply_edge_type(value, EdgeType.json_field("test")) == "value"


# TEST809: Tests EdgeType::JsonField error handling for missing fields Verifies that attempting to extract a non-existent field returns an error
def test_809_apply_edge_type_json_field_missing():
    value = {"test": "value"}
    try:
        apply_edge_type(value, EdgeType.json_field("missing"))
        assert False, "expected missing-field failure"
    except InternalError:
        pass


# TEST810: Tests EdgeType::JsonPath extracts values using nested path expressions Verifies that JsonPath edge type correctly navigates through multiple levels like "data.nested.value"
def test_810_apply_edge_type_json_path():
    value = {"data": {"nested": {"value": 42}}}
    assert apply_edge_type(value, EdgeType.json_path("data.nested.value")) == 42


# TEST811: Tests EdgeType::Iteration preserves array values for iterative processing Verifies that Iteration edge type passes through arrays unchanged to enable ForEach patterns
def test_811_apply_edge_type_iteration():
    value = [1, 2, 3]
    assert apply_edge_type(value, EdgeType.iteration()) == value


# TEST812: Tests EdgeType::Collection preserves collected values without transformation Verifies that Collection edge type maintains structure for aggregation patterns
def test_812_apply_edge_type_collection():
    value = {"collected": [1, 2, 3]}
    assert apply_edge_type(value, EdgeType.collection()) == value


# TEST813: Tests JSON path extraction through deeply nested object hierarchies (4+ levels) Verifies that paths can traverse multiple nested levels like "level1.level2.level3.level4.value"
def test_813_extract_json_path_deeply_nested():
    data = {"level1": {"level2": {"level3": {"level4": {"value": "deep"}}}}}
    assert extract_json_path(data, "level1.level2.level3.level4.value") == "deep"


# TEST814: Tests error handling when array index exceeds available elements Verifies that out-of-bounds array access returns a descriptive error message
def test_814_extract_json_path_array_out_of_bounds():
    data = {"items": [{"name": "first"}]}
    try:
        extract_json_path(data, "items[5].name")
        assert False, "expected bounds failure"
    except InternalError as exc:
        assert "out of bounds" in str(exc)


# TEST815: Tests JSON path extraction with single-level paths (no nesting) Verifies that simple field names without dots correctly extract top-level values
def test_815_extract_json_path_single_segment():
    assert extract_json_path({"value": 123}, "value") == 123


# TEST816: Tests JSON path extraction preserves special characters in string values Verifies that quotes, backslashes, and other special characters are correctly maintained
def test_816_extract_json_path_with_special_characters():
    data = {"data": {"message": "hello \"world\" with 'quotes' and \\ backslashes"}}
    assert extract_json_path(data, "data.message") == "hello \"world\" with 'quotes' and \\ backslashes"


# TEST817: Tests JSON path extraction correctly handles explicit null values Verifies that null is returned as serde_json::Value::Null rather than an error
def test_817_extract_json_path_with_null_value():
    data = {"data": {"nullable": None}}
    assert extract_json_path(data, "data.nullable") is None


# TEST818: Tests JSON path extraction correctly returns empty arrays Verifies that zero-length arrays are extracted as valid empty array values
def test_818_extract_json_path_with_empty_array():
    data = {"data": {"items": []}}
    assert extract_json_path(data, "data.items") == []


# TEST819: Tests JSON path extraction handles various numeric types correctly Verifies extraction of integers, floats, negative numbers, and zero
def test_819_extract_json_path_with_numeric_types():
    data = {"integers": 42, "floats": 3.14159, "negative": -100, "zero": 0}
    assert extract_json_path(data, "integers") == 42
    assert extract_json_path(data, "floats") == 3.14159
    assert extract_json_path(data, "negative") == -100
    assert extract_json_path(data, "zero") == 0


# TEST820: Tests JSON path extraction correctly handles boolean values Verifies that true and false are extracted as proper boolean JSON values
def test_820_extract_json_path_with_boolean():
    data = {"flags": {"enabled": True, "disabled": False}}
    assert extract_json_path(data, "flags.enabled") is True
    assert extract_json_path(data, "flags.disabled") is False


# TEST821: Tests JSON path extraction with multi-dimensional arrays (matrix access) Verifies that nested array structures like "matrix[1]" correctly extract inner arrays
def test_821_extract_json_path_with_nested_arrays():
    data = {"matrix": [[1, 2, 3], [4, 5, 6]]}
    assert extract_json_path(data, "matrix[1]") == [4, 5, 6]


# TEST822: Tests error handling for non-numeric array indices Verifies that invalid indices like "items[abc]" return a descriptive parse error
def test_822_extract_json_path_invalid_array_index():
    data = {"items": [1, 2, 3]}
    try:
        extract_json_path(data, "items[abc]")
        assert False, "expected parse failure"
    except InternalError as exc:
        assert "Invalid array index" in str(exc)
