"""Tests for the unified request table (protocol v3, L7/L8) — TEST7030-7033,
TEST7087, TEST7088, TEST7092. Mirrors capdag/src/bifaci/request_state.rs
(and the capdag-objc RequestStateTests.swift mirror).
"""

import time

import pytest

from capdag.bifaci.frame import (
    CreditDirection,
    Frame,
    MessageId,
    compute_checksum,
)
from capdag.bifaci.request_state import (
    RECENT_TERMINATED_CAP,
    FrameDirection,
    RequestPhase,
    RequestState,
    RequestStateError,
    RequestTable,
    RoutingEntry,
    TerminalKind,
)


def _key(x: int, r: int):
    return (MessageId(x), MessageId(r))


def _state(dest: int, origin, is_peer: bool) -> RequestState:
    return RequestState(
        routing=RoutingEntry(source_master_idx=origin, destination_master_idx=dest),
        origin=origin,
        external_channel=None,
        is_peer=is_peer,
    )


# TEST7092: A request registered with its originating REQ's cap URN carries that
# identity through the ACTIVE snapshot and into the terminated ring — observability
# surfaces can always NAME a request (background chatter vs run traffic), never just
# show a bare rid. A request registered without one (pre-attribution mirror, unknown
# origin) snapshots with cap_urn null — absent, never invented.
def test_7092_cap_urn_attribution_survives_lifecycle():
    table = RequestTable()
    named = _key(1, 9)
    table.register(named, _state(0, 1, False).with_cap_urn("cap:effect=none"))
    anonymous = _key(2, 10)
    table.register(anonymous, _state(0, 1, True))

    snapshot = table.snapshot()
    by_rid = {r.rid: r for r in snapshot.active}
    assert by_rid["9"].cap_urn == "cap:effect=none", "active snapshot names the request's cap"
    assert by_rid["10"].cap_urn is None, "unknown identity stays absent"

    assert table.terminate(named, TerminalKind.END) is not None
    snapshot = table.snapshot()
    assert (
        snapshot.recent_terminated[0].cap_urn == "cap:effect=none"
    ), "the terminated ring keeps the cap identity"


# TEST7087: Protocol stats snapshots serialize with stable field names — the
# snapshot shape is the mirror contract.
def test_7087_snapshot_field_names_are_stable():
    table = RequestTable()
    k = _key(1, 9)
    table.register(k, _state(0, 1, True))
    rid = MessageId(9)
    ss = Frame.stream_start(rid, "s", "media:enc=utf-8", False)
    table.record_frame(k, FrameDirection.INBOUND, ss)

    snap = table.snapshot().to_dict()
    for field in ["active", "recent_terminated", "total_registered", "terminated_by_kind"]:
        assert field in snap, f"missing top-level field {field}"
    req = snap["active"][0]
    for field in [
        "xid",
        "rid",
        "phase",
        "is_peer",
        "origin_master",
        "destination_master",
        "age_ms",
        "idle_ms",
        "children",
        "streams",
    ]:
        assert field in req, f"missing request field {field}"
    assert req["phase"] == "streaming", "phase serializes snake_case"
    stream = req["streams"][0]
    for field in [
        "stream_id",
        "frames_in",
        "frames_out",
        "bytes_in",
        "bytes_out",
        "chunks_in",
        "chunks_out",
        "credit_outstanding",
        "unbounded",
        "ended",
    ]:
        assert field in stream, f"missing stream field {field}"

    assert table.terminate(k, TerminalKind.MASTER_DIED) is not None
    snap = table.snapshot().to_dict()
    summary = snap["recent_terminated"][0]
    for field in [
        "xid",
        "rid",
        "kind",
        "is_peer",
        "lifetime_ms",
        "frames_in",
        "frames_out",
        "bytes_in",
        "bytes_out",
    ]:
        assert field in summary, f"missing summary field {field}"
    assert summary["kind"] == "master_died", "kind serializes snake_case"


# TEST7088: last_activity is monotonic non-decreasing across a long-lived streaming
# request — idle time resets on every recorded frame and never runs backwards.
def test_7088_last_activity_monotonic():
    table = RequestTable()
    k = _key(1, 5)
    table.register(k, _state(0, None, False))
    rid = MessageId(5)

    last_activity_points = []
    for i in range(3):
        time.sleep(0.015)
        payload = bytes(4)
        checksum = compute_checksum(payload)
        chunk = Frame.chunk(rid, "s", i, payload, i, checksum)
        table.record_frame(k, FrameDirection.INBOUND, chunk)
        entry = table.get(k)
        assert entry.last_activity >= entry.created_at, "activity never precedes creation"
        last_activity_points.append(entry.last_activity)
    for prev, curr in zip(last_activity_points, last_activity_points[1:]):
        assert curr >= prev, "last_activity must be monotonic non-decreasing"

    # idle_ms in the snapshot reflects the LAST activity, not the first:
    # it must be (much) smaller than the request's age.
    time.sleep(0.015)
    snap = table.snapshot()
    req = snap.active[0]
    assert req.idle_ms <= req.age_ms, f"idle {req.idle_ms}ms cannot exceed age {req.age_ms}ms"
    assert req.age_ms >= 45, "age accumulates across the request lifetime"


# TEST7030: A request registers exactly once and terminates exactly once — duplicate
# registration and double termination are rejected, and after terminate zero state
# remains for the key.
def test_7030_register_once_terminate_once():
    table = RequestTable()
    k = _key(1, 100)

    table.register(k, _state(0, None, False))
    assert table.contains(k)
    assert table.xid_for_rid(MessageId(100)) == MessageId(1)

    # Duplicate registration of a live key is a protocol violation.
    with pytest.raises(RequestStateError) as exc_info:
        table.register(k, _state(0, None, False))
    assert "already registered" in str(exc_info.value)

    # Same RID under a different XID is rejected while live.
    with pytest.raises(RequestStateError) as exc_info:
        table.register(_key(2, 100), _state(0, None, False))
    assert "already indexed" in str(exc_info.value)

    removed = table.terminate(k, TerminalKind.END)
    assert removed is not None, "live entry"
    assert not removed.is_peer
    assert not table.contains(k), "no entry remains after terminate"
    assert table.xid_for_rid(MessageId(100)) is None, "rid index removed with the entry (L7)"
    assert table.terminate(k, TerminalKind.END) is None, "termination happens exactly once"


# TEST7031: The rid index and the entry table never disagree across register/terminate
# cycles, and a terminated rid is immediately reusable.
def test_7031_rid_index_consistency():
    table = RequestTable()
    for round_ in range(3):
        for n in range(10):
            k = _key(round_ * 100 + n, n)
            table.register(k, _state(0, None, False))
        for n in range(10):
            k = _key(round_ * 100 + n, n)
            xid = table.xid_for_rid(MessageId(n))
            assert xid is not None, "indexed"
            assert xid == k[0], "index resolves to the live entry's xid"
            assert table.contains((xid, MessageId(n)))
            assert table.terminate(k, TerminalKind.END) is not None
            assert table.xid_for_rid(MessageId(n)) is None
    assert table.is_empty()
    assert table.snapshot().total_registered == 30


# TEST7032: record_frame accumulates per-stream frame/byte/chunk counters by direction,
# flips phase Created->Streaming on the first flow frame, and tracks
# unbounded/ended/credit stream markers.
def test_7032_record_frame_stats_and_phase():
    table = RequestTable()
    k = _key(1, 7)
    table.register(k, _state(0, None, False))
    assert table.get(k).phase == RequestPhase.CREATED

    rid = MessageId(7)
    ss = Frame.stream_start_unbounded(rid, "s1", "media:enc=utf-8", None)
    table.record_frame(k, FrameDirection.INBOUND, ss)
    assert table.get(k).phase == RequestPhase.STREAMING

    payload = bytes(100)
    checksum = compute_checksum(payload)
    chunk = Frame.chunk(rid, "s1", 0, payload, 0, checksum)
    table.record_frame(k, FrameDirection.INBOUND, chunk)
    table.record_frame(k, FrameDirection.OUTBOUND, chunk)

    credit = Frame.credit(rid, "s1", 4, CreditDirection.RESPONSE)
    table.record_frame(k, FrameDirection.OUTBOUND, credit)

    se = Frame.stream_end_unbounded(rid, "s1")
    table.record_frame(k, FrameDirection.INBOUND, se)

    entry = table.get(k)
    s1 = entry.streams["s1"]
    assert s1.frames_in == 3, "stream_start + chunk + stream_end"
    assert s1.frames_out == 2, "chunk + credit"
    assert s1.chunks_in == 1
    assert s1.chunks_out == 1
    assert s1.bytes_in == 100
    assert s1.bytes_out == 100
    assert s1.unbounded
    assert s1.ended
    # +4 granted, -1 consumed inbound chunk
    assert s1.credit_outstanding == 3


# TEST7033: Terminated requests leave a bounded ring of summaries carrying kind,
# lifetime, and flow totals, and the ring evicts oldest-first at capacity.
def test_7033_terminated_summaries_ring():
    table = RequestTable()
    for n in range(RECENT_TERMINATED_CAP + 3):
        k = _key(n, n)
        table.register(k, _state(0, 2, True))
        payload = bytes(10)
        checksum = compute_checksum(payload)
        chunk = Frame.chunk(MessageId(n), "s", 0, payload, 0, checksum)
        table.record_frame(k, FrameDirection.INBOUND, chunk)
        assert table.terminate(k, TerminalKind.CANCELLED) is not None

    snap = table.snapshot()
    assert len(snap.recent_terminated) == RECENT_TERMINATED_CAP
    # Oldest evicted: first retained summary is rid "3"
    assert snap.recent_terminated[0].rid == MessageId(3).to_string()
    last = snap.recent_terminated[-1]
    assert last.kind == TerminalKind.CANCELLED
    assert last.is_peer
    assert last.frames_in == 1
    assert last.bytes_in == 10
    assert snap.terminated_by_kind.get("cancelled") == RECENT_TERMINATED_CAP + 3
