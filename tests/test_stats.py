"""Tests for bifaci.stats - mirroring capdag Rust tests

Tests use # TEST###: comments matching the Rust implementation for cross-tracking.
"""

from capdag.bifaci.frame import DropReason, FlowKey
from capdag.bifaci.stats import DropCounters, DropSnapshot, TerminatedFlows


# TEST7019: Drop counters record per-reason exactly once per drop, and the
# snapshot omits zero-count reasons while totalling all of them.
def test_7019_drop_counters_record_and_snapshot():
    counters = DropCounters()
    assert counters.total() == 0
    assert counters.snapshot() == DropSnapshot()

    assert counters.record(DropReason.POST_TERMINAL) == 1
    assert counters.record(DropReason.POST_TERMINAL) == 2
    assert counters.record(DropReason.CHANNEL_CLOSED) == 1

    assert counters.get(DropReason.POST_TERMINAL) == 2
    assert counters.get(DropReason.CHANNEL_CLOSED) == 1
    assert counters.get(DropReason.NO_ROUTE) == 0
    assert counters.total() == 3

    snap = counters.snapshot()
    assert snap.total == 3
    assert snap.by_reason.get("post_terminal") == 2
    assert snap.by_reason.get("channel_closed") == 1
    assert "no_route" not in snap.by_reason, (
        "zero-count reasons are omitted from the snapshot"
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
