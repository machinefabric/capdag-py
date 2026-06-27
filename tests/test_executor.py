"""Tests for planner executor helper behavior."""

from capdag.planner.executor import apply_edge_type, extract_json_path
from capdag.planner.plan import EdgeType
from capdag.planner.error import InternalError
from capdag.orchestrator.executor import map_progress, ProgressMapper


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


# TEST1126: map_progress is deterministic — same inputs always produce same output
def test_1126_map_progress_deterministic():
    for i in range(100):
        p = i / 100.0
        a = map_progress(p, 0.1, 0.8)
        b = map_progress(p, 0.1, 0.8)
        assert a == b, f"map_progress must be deterministic for p={p}"


# TEST910: map_progress output is monotonic for monotonically increasing input
def test_910_map_progress_monotonic():
    prev = map_progress(0.0, 0.1, 0.7)
    for i in range(1, 101):
        p = i / 100.0
        curr = map_progress(p, 0.1, 0.7)
        assert curr >= prev, f"map_progress must be monotonic: p={p}, prev={prev}, curr={curr}"
        prev = curr


# TEST911: map_progress output is bounded within [base, base+weight]
def test_911_map_progress_bounded():
    base = 0.15
    weight = 0.55
    for i in range(-10, 111):
        p = i / 100.0
        result = map_progress(p, base, weight)
        assert base <= result <= base + weight, (
            f"map_progress({p}, {base}, {weight}) = {result} must be in [{base}, {base + weight}]"
        )


# TEST912: ProgressMapper correctly maps through a CapProgressFn
def test_912_progress_mapper_reports_through_parent():
    reported = []

    def parent(p, _cap, msg):
        reported.append((p, msg))

    mapper = ProgressMapper(parent, 0.2, 0.6)
    mapper.report(0.0, "", "start")
    mapper.report(0.5, "", "half")
    mapper.report(1.0, "", "done")

    assert len(reported) == 3
    assert abs(reported[0][0] - 0.2) < 0.001, "0% maps to base=0.2"
    assert abs(reported[1][0] - 0.5) < 0.001, "50% maps to 0.5"
    assert abs(reported[2][0] - 0.8) < 0.001, "100% maps to base+weight=0.8"


# TEST913: ProgressMapper.as_cap_progress_fn produces same mapping
def test_913_progress_mapper_as_cap_progress_fn():
    reported = []

    def parent(p, _cap, _msg):
        reported.append(p)

    mapper = ProgressMapper(parent, 0.1, 0.3)
    pfn = mapper.as_cap_progress_fn()

    pfn(0.0, "", "a")
    pfn(0.5, "", "b")
    pfn(1.0, "", "c")

    assert len(reported) == 3
    assert abs(reported[0] - 0.1) < 0.001
    assert abs(reported[1] - 0.25) < 0.001
    assert abs(reported[2] - 0.4) < 0.001


# TEST914: ProgressMapper.sub_mapper chains correctly
def test_914_progress_mapper_sub_mapper():
    reported = []

    def parent(p, _cap, _msg):
        reported.append(p)

    # Parent maps [0, 1] to [0.2, 0.8] (base=0.2, weight=0.6)
    mapper = ProgressMapper(parent, 0.2, 0.6)

    # Sub-mapper maps [0, 1] to the second half of parent's range
    # sub_base=0.5, sub_weight=0.5 -> [0.2 + 0.5*0.6, 0.2 + (0.5+0.5)*0.6] = [0.5, 0.8]
    sub = mapper.sub_mapper(0.5, 0.5)
    sub.report(0.0, "", "sub_start")
    sub.report(1.0, "", "sub_end")

    assert len(reported) == 2
    assert abs(reported[0] - 0.5) < 0.001, "sub 0% maps to 0.5"
    assert abs(reported[1] - 0.8) < 0.001, "sub 100% maps to 0.8"


# TEST915: Per-group subdivision produces monotonic, bounded progress for N groups Uses pre-computed boundaries (same pattern as production code) to guarantee monotonicity regardless of f32 rounding.
def test_915_per_group_subdivision_monotonic_bounded():
    all_progress = []

    def parent(p, _cap, _msg):
        all_progress.append(p)

    n_groups = 5
    boundaries = [i / n_groups for i in range(n_groups + 1)]

    for i in range(n_groups):
        base = boundaries[i]
        weight = boundaries[i + 1] - base
        mapper = ProgressMapper(parent, base, weight)

        # Each group reports 0%, 50%, 100%
        mapper.report(0.0, "", "start")
        mapper.report(0.5, "", "half")
        mapper.report(1.0, "", "done")

    assert len(all_progress) == 15  # 5 groups * 3 reports

    # Verify monotonicity
    for i in range(1, len(all_progress)):
        assert all_progress[i] >= all_progress[i - 1], (
            f"monotonic violation at index {i}: {all_progress[i]} < {all_progress[i - 1]}"
        )

    # Verify bounded [0.0, 1.0]
    for i, p in enumerate(all_progress):
        assert 0.0 <= p <= 1.0, f"Progress[{i}]={p} must be in [0.0, 1.0]"

    # First should be 0.0 (group 0, 0%)
    assert abs(all_progress[0] - 0.0) < 0.001
    # Last should be 1.0 (group 4, 100%)
    assert abs(all_progress[14] - 1.0) < 0.001


# TEST917: High-frequency progress emission does not violate bounds (Regression test for the deadlock scenario — verifies computation stays bounded)
def test_917_high_frequency_progress_bounded():
    state = {"count": 0, "max": float("-inf"), "min": float("inf")}

    def parent(p, _cap, _msg):
        state["count"] += 1
        if p > state["max"]:
            state["max"] = p
        if p < state["min"]:
            state["min"] = p

    mapper = ProgressMapper(parent, 0.1, 0.8)

    # Simulate 100,000 rapid progress updates (like model download without throttle)
    for i in range(100_000):
        p = i / 100_000.0
        mapper.report(p, "", "downloading")

    assert state["count"] == 100_000
    assert state["min"] >= 0.1, f"min {state['min']} must be >= base 0.1"
    assert state["max"] <= 0.9, f"max {state['max']} must be <= base+weight 0.9"
