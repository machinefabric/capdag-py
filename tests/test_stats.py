"""Tests for bifaci.stats - mirroring capdag Rust tests

Tests use # TEST###: comments matching the Rust implementation for cross-tracking.
"""

from capdag.bifaci.frame import DropReason, FlowKey, FrameType
from capdag.bifaci.stats import (
    DropCounters,
    DropSnapshot,
    StragglerCounters,
    StragglerSnapshot,
    TerminatedFlows,
)


# TEST7019: Drop counters record per-reason × per-frame-type exactly once
# per drop; the snapshot totals all of them, breaks each reason down by
# frame type, and omits zero-count entries.
def test_7019_drop_counters_record_and_snapshot():
    counters = DropCounters()
    assert counters.total() == 0
    assert counters.snapshot() == DropSnapshot()

    assert counters.record(DropReason.NO_ROUTE, FrameType.CHUNK) == 1
    assert counters.record(DropReason.NO_ROUTE, FrameType.CREDIT) == 2
    assert counters.record(DropReason.CHANNEL_CLOSED, FrameType.LOG) == 1

    assert counters.get(DropReason.NO_ROUTE) == 2
    assert counters.get(DropReason.CHANNEL_CLOSED) == 1
    assert counters.get(DropReason.CANCELLED) == 0
    assert counters.get_frame(DropReason.NO_ROUTE, FrameType.CHUNK) == 1
    assert counters.get_frame(DropReason.NO_ROUTE, FrameType.CREDIT) == 1
    assert counters.get_frame(DropReason.NO_ROUTE, FrameType.END) == 0
    assert counters.total() == 3

    snap = counters.snapshot()
    assert snap.total == 3
    assert snap.by_reason.get("no_route") == 2
    assert snap.by_reason.get("channel_closed") == 1
    assert "cancelled" not in snap.by_reason, (
        "zero-count reasons are omitted from the snapshot"
    )
    no_route = snap.by_reason_frame_type["no_route"]
    assert no_route.get("chunk") == 1
    assert no_route.get("credit") == 1
    assert "end" not in no_route, (
        "zero-count frame types are omitted from the breakdown"
    )


# TEST8127: Straggler counters — the benign post-terminal category is
# separate from drops, counted per frame type, and its snapshot names what
# crossed the terminal (late credit vs late chunk) while omitting
# zero-count types.
def test_8127_straggler_counters_record_and_snapshot():
    stragglers = StragglerCounters()
    assert stragglers.total() == 0
    assert stragglers.snapshot() == StragglerSnapshot()

    assert stragglers.record(FrameType.CREDIT) == 1
    assert stragglers.record(FrameType.CREDIT) == 2
    assert stragglers.record(FrameType.CHUNK) == 3

    assert stragglers.get(FrameType.CREDIT) == 2
    assert stragglers.get(FrameType.CHUNK) == 1
    assert stragglers.get(FrameType.END) == 0

    snap = stragglers.snapshot()
    assert snap.total == 3
    assert snap.by_frame_type.get("credit") == 2
    assert snap.by_frame_type.get("chunk") == 1
    assert "end" not in snap.by_frame_type, (
        "zero-count frame types are omitted from the snapshot"
    )


# TEST7029: TerminatedFlows membership is exact up to capacity and evicts
# strictly oldest-first beyond it.
def test_7029_terminated_flows_capacity_and_eviction():
    flows = TerminatedFlows(2)

    def k(n: int) -> FlowKey:
        return FlowKey(rid=str(n), xid="")

    flows.insert(k(1))
    flows.insert(k(1))  # duplicate insert is a no-op
    flows.insert(k(2))
    assert flows.len() == 2
    assert flows.contains(k(1)) and flows.contains(k(2))

    flows.insert(k(3))  # evicts k(1), the oldest
    assert flows.len() == 2
    assert not flows.contains(k(1))
    assert flows.contains(k(2)) and flows.contains(k(3))

    # XID-bearing key is a distinct flow from the bare-RID key
    with_xid = FlowKey(rid=str(2), xid=str(9))
    assert not flows.contains(with_xid)
