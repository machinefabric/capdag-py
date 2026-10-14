"""Tests for how a run's progress is mapped into the range of its part."""

from capdag.orchestrator.executor import map_progress, ProgressMapper


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
