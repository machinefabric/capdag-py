"""Tests for cartridge_host_runtime module

Tests for CartridgeHostRuntime, ResponseChunk, CartridgeResponse, and error types.
"""

import pytest

from capdag.bifaci.host_runtime import (
    ResponseChunk,
    CartridgeResponse,
    CartridgeHostRuntime,
    AsyncHostError,
    CborErrorWrapper,
    IoError,
    CartridgeError,
    UnexpectedFrameType,
    ProcessExited,
    Handshake,
    Closed,
    SendError,
    RecvError,
)
from capdag.bifaci.frame import FrameType, MessageId


def seed_incoming_rxids_for_test(runtime, count):
    """Seed the incoming_rxids table with ``count`` entries, key i aged at i.

    Bypasses ``touch_incoming_rxid`` so the test controls which entry is
    "oldest": direct-seeding the touched map with the insertion index
    produces the same ordering the production monotonic counter would have
    produced if entries had been inserted at exactly these times. Returns
    the seeded keys in insertion (age) order.
    """
    keys = []
    for i in range(count):
        key = (MessageId(i), MessageId(i))
        runtime.incoming_rxids[key] = 0
        runtime.incoming_rxids_touched[key] = i
        keys.append(key)
    return keys


# TEST235: Test ResponseChunk stores payload, seq, offset, len, and eof fields correctly
def test_235_response_chunk():
    chunk = ResponseChunk(
        payload=b"hello",
        seq=0,
        offset=None,
        len=None,
        is_eof=False,
    )

    assert chunk.payload == b"hello"
    assert chunk.seq == 0
    assert chunk.offset is None
    assert chunk.len is None
    assert not chunk.is_eof


# TEST236: Test ResponseChunk with all fields populated preserves offset, len, and eof
def test_236_response_chunk_with_all_fields():
    chunk = ResponseChunk(
        payload=b"data",
        seq=5,
        offset=1024,
        len=8192,
        is_eof=True,
    )

    assert chunk.payload == b"data"
    assert chunk.seq == 5
    assert chunk.offset == 1024
    assert chunk.len == 8192
    assert chunk.is_eof


# TEST237: Test CartridgeResponse::Single final_payload returns the single payload slice
def test_237_cartridge_response_single():
    response = CartridgeResponse.single(b"result")
    assert response.final_payload() == b"result"
    assert response.concatenated() == b"result"


# TEST238: Test CartridgeResponse::Single with empty payload returns empty slice and empty vec
def test_238_cartridge_response_single_empty():
    response = CartridgeResponse.single(b"")
    assert response.final_payload() == b""
    assert response.concatenated() == b""


# TEST239: Test CartridgeResponse::Streaming concatenated joins all chunk payloads in order
def test_239_cartridge_response_streaming():
    chunks = [
        ResponseChunk(
            payload=b"hello",
            seq=0,
            offset=0,
            len=11,
            is_eof=False,
        ),
        ResponseChunk(
            payload=b" ",
            seq=1,
            offset=5,
            len=11,
            is_eof=False,
        ),
        ResponseChunk(
            payload=b"world",
            seq=2,
            offset=6,
            len=11,
            is_eof=True,
        ),
    ]

    response = CartridgeResponse.streaming(chunks)

    # Verify concatenated joins all payloads in order
    assert response.concatenated() == b"hello world"

    # Verify final_payload returns last chunk's payload
    assert response.final_payload() == b"world"


# TEST240: Test CartridgeResponse::Streaming final_payload returns the last chunk's payload
def test_240_cartridge_response_streaming_final_payload():
    chunks = [
        ResponseChunk(
            payload=b"first",
            seq=0,
            offset=0,
            len=16,
            is_eof=False,
        ),
        ResponseChunk(
            payload=b"second",
            seq=1,
            offset=5,
            len=16,
            is_eof=False,
        ),
        ResponseChunk(
            payload=b"last",
            seq=2,
            offset=11,
            len=16,
            is_eof=True,
        ),
    ]

    response = CartridgeResponse.streaming(chunks)

    # final_payload should return the last chunk's payload
    assert response.final_payload() == b"last"


# TEST241: Test CartridgeResponse::Streaming with empty chunks vec returns empty concatenation
def test_241_cartridge_response_streaming_empty():
    response = CartridgeResponse.streaming([])
    assert response.final_payload() is None
    assert response.concatenated() == b""


# TEST242: Test CartridgeResponse::Streaming concatenated capacity is pre-allocated correctly for large payloads
def test_242_cartridge_response_streaming_large():
    # Create chunks with substantial data
    chunks = [
        ResponseChunk(
            payload=b"x" * 1000,
            seq=0,
            offset=0,
            len=3000,
            is_eof=False,
        ),
        ResponseChunk(
            payload=b"y" * 1000,
            seq=1,
            offset=1000,
            len=3000,
            is_eof=False,
        ),
        ResponseChunk(
            payload=b"z" * 1000,
            seq=2,
            offset=2000,
            len=3000,
            is_eof=True,
        ),
    ]

    response = CartridgeResponse.streaming(chunks)

    concatenated = response.concatenated()
    assert len(concatenated) == 3000
    assert concatenated[:1000] == b"x" * 1000
    assert concatenated[1000:2000] == b"y" * 1000
    assert concatenated[2000:3000] == b"z" * 1000


# TEST243: Test AsyncHostError variants display correct error messages
def test_243_async_host_error_variants():
    # Test CartridgeError
    err = CartridgeError("CODE", "message")
    assert err.code == "CODE"
    assert err.error_message == "message"
    assert "[CODE]" in str(err)
    assert "message" in str(err)

    # Test UnexpectedFrameType
    err2 = UnexpectedFrameType(FrameType.LOG)
    assert "LOG" in str(err2) or "5" in str(err2)  # Either name or value

    # Test ProcessExited
    err3 = ProcessExited()
    assert "exited" in str(err3).lower()

    # Test Closed
    err4 = Closed()
    assert "closed" in str(err4).lower()

    # Test SendError
    err5 = SendError()
    assert "send" in str(err5).lower() or "channel" in str(err5).lower()

    # Test RecvError
    err6 = RecvError()
    assert "recv" in str(err6).lower() or "channel" in str(err6).lower()


# TEST244: Test AsyncHostError::from converts CborError to Cbor variant
def test_244_async_host_error_from_cbor():
    # Create a CborError and wrap it
    cbor_msg = "CBOR encoding failed"
    host_err = CborErrorWrapper(cbor_msg)
    assert cbor_msg in str(host_err)


# TEST245: Test AsyncHostError::from converts io::Error to Io variant
def test_245_async_host_error_from_io():
    io_msg = "pipe broken"
    host_err = IoError(io_msg)
    assert io_msg in str(host_err)


# TEST246: Test AsyncHostError Clone implementation produces equal values
def test_246_async_host_error_equality():
    # Python doesn't have explicit Clone trait, but we can test equality
    err1 = CartridgeError("ERR", "msg")
    err2 = CartridgeError("ERR", "msg")
    # Python exceptions don't have built-in equality, but we can test string representation
    assert str(err1) == str(err2)
    assert err1.code == err2.code
    assert err1.error_message == err2.error_message


# TEST247: Test ResponseChunk Clone produces independent copy with same data
def test_247_response_chunk_copy():
    chunk = ResponseChunk(
        payload=b"data",
        seq=3,
        offset=100,
        len=500,
        is_eof=True,
    )

    # Python dataclasses support shallow copy via copy module
    import copy
    cloned = copy.copy(chunk)

    # Verify all fields match
    assert cloned.payload == chunk.payload
    assert cloned.seq == chunk.seq
    assert cloned.offset == chunk.offset
    assert cloned.len == chunk.len
    assert cloned.is_eof == chunk.is_eof

    # Verify it's an independent copy (not the same object)
    assert cloned is not chunk


# TEST119: CartridgeResponse::Streaming concatenated() and final_payload() diverge for multi-chunk
def test_119_concatenated_vs_final_payload_divergence():
    chunks = [
        ResponseChunk(payload=b"AAAA", seq=0, offset=None, len=None, is_eof=False),
        ResponseChunk(payload=b"BBBB", seq=1, offset=None, len=None, is_eof=False),
        ResponseChunk(payload=b"CCCC", seq=2, offset=None, len=None, is_eof=True),
    ]

    response = CartridgeResponse(chunks)

    # concatenated() returns ALL chunk data joined
    assert response.concatenated() == b"AAAABBBBCCCC"

    # final_payload() returns ONLY the last chunk's data
    assert response.final_payload() == b"CCCC"

    # They must NOT be equal (this is the divergence the large_payload bug exposed)
    assert response.concatenated() != response.final_payload(), \
        "concatenated and final_payload must diverge for multi-chunk responses"


# TEST988: GC keeps the table strictly below the hard cap and the single soft-watermark pass evicts exactly EVICTION_FRACTION of the pre-state.
def test_988_gc_reduces_table_below_soft_watermark_in_one_pass():
    runtime = CartridgeHostRuntime()
    pre_count = CartridgeHostRuntime.ROUTING_TABLE_SOFT_WATERMARK + 256
    assert pre_count < CartridgeHostRuntime.ROUTING_TABLE_HARD_CAP, (
        "Test precondition: pre_count must stay under the hard cap so we verify "
        "the SOFT watermark path, not the secondary hard-cap pass."
    )

    seed_incoming_rxids_for_test(runtime, pre_count)
    assert len(runtime.incoming_rxids) == pre_count, (
        "Seeder must populate exactly pre_count entries before the GC runs"
    )

    runtime.gc_routing_tables_if_needed()

    assert len(runtime.incoming_rxids) < CartridgeHostRuntime.ROUTING_TABLE_HARD_CAP, (
        f"Post-GC table size {len(runtime.incoming_rxids)} must stay strictly under "
        f"the hard cap ({CartridgeHostRuntime.ROUTING_TABLE_HARD_CAP})."
    )
    assert runtime.routing_gc_runs_total == 1, (
        f"Exactly one GC pass should have fired; {runtime.routing_gc_runs_total} "
        "runs means the single-pass invariant has changed."
    )
    expected_evicted = max(
        1,
        int(pre_count * CartridgeHostRuntime.ROUTING_TABLE_GC_EVICTION_FRACTION),
    )
    assert runtime.routing_gc_evicted_total == expected_evicted, (
        f"GC pass evicted {runtime.routing_gc_evicted_total} entries; expected "
        f"{expected_evicted} (eviction fraction "
        f"{CartridgeHostRuntime.ROUTING_TABLE_GC_EVICTION_FRACTION} of pre_count {pre_count})."
    )


# TEST129: The GC drops the OLDEST entries by touch-sequence, not arbitrary keys; the post-GC keyset is exactly what the test computes should survive.
def test_129_gc_evicts_oldest_entries_by_touch_sequence():
    runtime = CartridgeHostRuntime()
    pre_count = CartridgeHostRuntime.ROUTING_TABLE_SOFT_WATERMARK + 256
    eviction_count = max(
        1,
        int(pre_count * CartridgeHostRuntime.ROUTING_TABLE_GC_EVICTION_FRACTION),
    )

    # Seed: key i has touched_at == i. Smallest i means oldest.
    # Expected victims: keys 0 ..< eviction_count.
    # Expected survivors: keys eviction_count ..< pre_count.
    keys = seed_incoming_rxids_for_test(runtime, pre_count)

    runtime.gc_routing_tables_if_needed()

    for i, key in enumerate(keys[:eviction_count]):
        assert key not in runtime.incoming_rxids, (
            f"Key index {i} should have been evicted (touched_at={i}, one of the "
            f"{eviction_count} oldest), but it survived the GC."
        )
        assert key not in runtime.incoming_rxids_touched, (
            f"Touched-map entry for key index {i} must be removed alongside the "
            "primary entry."
        )
    for i, key in enumerate(keys[eviction_count:], start=eviction_count):
        assert key in runtime.incoming_rxids, (
            f"Key index {i} should have survived the GC (touched_at={i}, one of the "
            f"{pre_count - eviction_count} most-recently-touched), but was evicted."
        )


# TEST987: The secondary hard-cap pass kicks in if the table exceeds HARD_CAP — a single eviction-fraction pass is not enough to recover headroom.
def test_987_gc_secondary_pass_enforces_hard_cap():
    runtime = CartridgeHostRuntime()
    # Size the seed so a SINGLE eviction-fraction pass is NOT enough to
    # bring the table under the hard cap: pre >= hard_cap / (1 - fraction),
    # plus 256 headroom so a small fraction change doesn't accidentally let
    # the primary pass alone succeed.
    one_minus_fraction = 1.0 - CartridgeHostRuntime.ROUTING_TABLE_GC_EVICTION_FRACTION
    import math
    pre_count = (
        math.ceil(CartridgeHostRuntime.ROUTING_TABLE_HARD_CAP / one_minus_fraction)
        + 256
    )
    seed_incoming_rxids_for_test(runtime, pre_count)
    assert len(runtime.incoming_rxids) >= CartridgeHostRuntime.ROUTING_TABLE_HARD_CAP, (
        "Seeder must populate at or above the hard cap so the secondary pass "
        "actually fires."
    )

    runtime.gc_routing_tables_if_needed()

    assert len(runtime.incoming_rxids) < CartridgeHostRuntime.ROUTING_TABLE_HARD_CAP, (
        f"Post-GC table size {len(runtime.incoming_rxids)} must be strictly under "
        f"the hard cap ({CartridgeHostRuntime.ROUTING_TABLE_HARD_CAP})."
    )
    # The secondary pass uses the same evicted counter but does not
    # increment runs_total; verify the eviction count exceeds one full
    # eviction-fraction pass over the pre-count.
    single_pass_max = int(
        pre_count * CartridgeHostRuntime.ROUTING_TABLE_GC_EVICTION_FRACTION
    )
    assert runtime.routing_gc_evicted_total > single_pass_max, (
        f"Total evicted {runtime.routing_gc_evicted_total} should exceed single-pass "
        f"max {single_pass_max} (the secondary pass must have evicted additional entries)."
    )


# TEST462: An attached cartridge (pre-connected over raw streams, no on-disk
# anchor) gets a resolvable install identity derived from its HELLO manifest.
# Identity gates advertisement, so a None record means the cartridge is
# silently dropped from every RelayNotify and the engine can never route to
# it. Locks the attached-cartridge identity path (the swift mirror regressed
# here: attached cartridges returned nil and never reached the engine).
# Mirrors the reference installed_cartridge_record_from_manifest.
def test_462_attached_cartridge_identity_from_manifest():
    from capdag.bifaci.host_runtime import _installed_cartridge_record_from_manifest
    from capdag.bifaci.relay_switch import CartridgeLifecycle

    manifest = (
        b'{"name":"TestCart","version":"1.2.3","channel":"nightly",'
        b'"registry_url":null,"description":"d","cap_groups":[{"name":"g",'
        b'"caps":[{"urn":"cap:effect=none","title":"Identity","aliases":["identity"]}]}]}'
    )

    rec = _installed_cartridge_record_from_manifest(manifest)
    assert rec is not None, "attached cartridge identity must be derivable from a valid manifest (else it is dropped from advertisement)"
    assert rec.id == "TestCart"
    assert rec.version == "1.2.3"
    assert rec.channel == "nightly"
    assert rec.registry_url is None
    assert rec.sha256, "sha256 taken over manifest bytes"
    # Attached ⇒ HELLO + identity verification already succeeded ⇒ operational.
    assert rec.lifecycle == CartridgeLifecycle.OPERATIONAL

    # An unparseable manifest yields no record (honestly absent, not a
    # fabricated id) — the producer must surface the gap, not hide it.
    assert _installed_cartridge_record_from_manifest(b"{not json") is None


# =============================================================================
# Protocol v3 (L6/L8/L11): CREDIT routing, terminal drain, protocol_stats()
# =============================================================================
#
# These exercise CartridgeHostRuntime.route_continuation_frame /
# record_response_terminal / protocol_stats — the pure routing-table
# counterpart of the reference handle_relay_frame PATH C and
# handle_cartridge_frame response-terminal bookkeeping (host_runtime.rs).
# No single reference test number covers this logic in isolation (it ships
# embedded in the full frame-I/O loop); these are new, descriptively named
# tests rather than numbered parity ports.

from capdag.bifaci.frame import CreditDirection, DropReason


def _seed_incoming(runtime, xid, rid, cartridge_idx):
    key = (xid, rid)
    runtime.incoming_rxids[key] = cartridge_idx
    runtime.touch_incoming_rxid(key)


def _seed_outgoing(runtime, rid, cartridge_idx):
    runtime.outgoing_rids[rid] = cartridge_idx
    runtime.touch_outgoing_rid(rid)


def test_route_continuation_frame_data_then_terminal_stays_alive_for_response():
    """A request-body terminal (END) routed via incoming_rxids marks the key
    body-done but does NOT release the entry — the handler's response is
    still flowing and its output CREDIT grants must keep routing through
    it. Only the response's own terminal (record_response_terminal) with
    the body already done releases the entry."""
    runtime = CartridgeHostRuntime()
    xid, rid = MessageId.new_uuid(), MessageId.new_uuid()
    _seed_incoming(runtime, xid, rid, cartridge_idx=3)

    result = runtime.route_continuation_frame(xid, rid, FrameType.CHUNK)
    assert result == (3, True)
    assert (xid, rid) not in runtime.incoming_body_done

    result = runtime.route_continuation_frame(xid, rid, FrameType.END)
    assert result == (3, True)
    assert (xid, rid) in runtime.incoming_body_done, "body END must mark body-done"
    assert (xid, rid) in runtime.incoming_rxids, (
        "the entry must survive the body terminal — the response phase is still open"
    )

    # The handler's response terminal passes outbound: body already done ⇒
    # release immediately.
    runtime.record_response_terminal(xid, rid)
    assert (xid, rid) not in runtime.incoming_rxids
    assert (xid, rid) not in runtime.incoming_body_done


def test_route_continuation_frame_response_first_race_releases_on_body_end():
    """Response-first race: the handler's response terminates BEFORE the
    request body END arrives. record_response_terminal must not release the
    entry yet (the body is still open); the body END that follows must
    release it immediately."""
    runtime = CartridgeHostRuntime()
    xid, rid = MessageId.new_uuid(), MessageId.new_uuid()
    _seed_incoming(runtime, xid, rid, cartridge_idx=1)

    runtime.record_response_terminal(xid, rid)
    assert (xid, rid) in runtime.incoming_rxids, "body still open — must not release yet"
    assert (xid, rid) in runtime.incoming_response_done

    result = runtime.route_continuation_frame(xid, rid, FrameType.END)
    assert result == (1, True)
    assert (xid, rid) not in runtime.incoming_rxids, (
        "body END with response already done must release the entry immediately"
    )
    assert (xid, rid) not in runtime.incoming_response_done
    assert (xid, rid) not in runtime.incoming_body_done


def test_route_continuation_frame_self_loop_peer_response_after_body_done():
    """After the request body is done (self-loop peer call), a data frame
    for the same (xid, rid) that also has an outgoing_rids entry is the
    peer's RESPONSE and must route via outgoing_rids, not incoming_rxids —
    and its terminal cleans up outgoing_rids, not the still-open incoming
    entry."""
    runtime = CartridgeHostRuntime()
    xid, rid = MessageId.new_uuid(), MessageId.new_uuid()
    _seed_incoming(runtime, xid, rid, cartridge_idx=0)  # handler
    _seed_outgoing(runtime, rid, cartridge_idx=5)  # requester (self-loop)

    # Body completes.
    result = runtime.route_continuation_frame(xid, rid, FrameType.END)
    assert result == (0, True)
    assert (xid, rid) in runtime.incoming_body_done

    # A CHUNK for the same key now prefers outgoing (peer response).
    result = runtime.route_continuation_frame(xid, rid, FrameType.CHUNK)
    assert result == (5, False)

    # The peer response's own terminal cleans up outgoing_rids only.
    result = runtime.route_continuation_frame(xid, rid, FrameType.END)
    assert result == (5, False)
    assert rid not in runtime.outgoing_rids
    assert (xid, rid) in runtime.incoming_rxids, (
        "the request's own incoming entry is untouched by the peer response terminal"
    )


def test_route_continuation_frame_credit_direction_selects_side():
    """A CREDIT frame's direction (L11), not table-preference, selects the
    route: `response` credits the handler (incoming side) even for a
    self-loop key that also has an outgoing entry; `request` credits the
    requester (outgoing side)."""
    runtime = CartridgeHostRuntime()
    xid, rid = MessageId.new_uuid(), MessageId.new_uuid()
    _seed_incoming(runtime, xid, rid, cartridge_idx=7)
    _seed_outgoing(runtime, rid, cartridge_idx=9)

    result = runtime.route_continuation_frame(
        xid, rid, FrameType.CREDIT, credit_direction=CreditDirection.RESPONSE
    )
    assert result == (7, True)

    result = runtime.route_continuation_frame(
        xid, rid, FrameType.CREDIT, credit_direction=CreditDirection.REQUEST
    )
    assert result == (9, False)


def test_route_continuation_frame_credit_without_direction_is_counted_drop():
    """A CREDIT frame with no direction cannot be routed (v3 requires
    credit_dir) — it is a counted no_route drop, never a silent loss."""
    runtime = CartridgeHostRuntime()
    xid, rid = MessageId.new_uuid(), MessageId.new_uuid()
    _seed_incoming(runtime, xid, rid, cartridge_idx=2)

    before = runtime.drops.get(DropReason.NO_ROUTE)
    result = runtime.route_continuation_frame(xid, rid, FrameType.CREDIT, credit_direction=None)
    assert result is None
    assert runtime.drops.get(DropReason.NO_ROUTE) == before + 1


def test_route_continuation_frame_no_route_is_counted_drop():
    """A continuation frame with no routing entry in either table (already
    cleaned up) is a counted no_route drop."""
    runtime = CartridgeHostRuntime()
    xid, rid = MessageId.new_uuid(), MessageId.new_uuid()

    before = runtime.drops.get(DropReason.NO_ROUTE)
    result = runtime.route_continuation_frame(xid, rid, FrameType.CHUNK)
    assert result is None
    assert runtime.drops.get(DropReason.NO_ROUTE) == before + 1


def test_death_cleanup_helper_clears_v3_terminal_markers():
    """remove_incoming_rxid — the death/cancellation cleanup helper — clears
    incoming_body_done / incoming_response_done alongside incoming_rxids, so
    a dying cartridge's markers never outlive the entry."""
    runtime = CartridgeHostRuntime()
    xid, rid = MessageId.new_uuid(), MessageId.new_uuid()
    key = (xid, rid)
    _seed_incoming(runtime, xid, rid, cartridge_idx=4)
    runtime.incoming_body_done.add(key)
    runtime.incoming_response_done.add(key)

    runtime.remove_incoming_rxid(key)
    assert key not in runtime.incoming_rxids
    assert key not in runtime.incoming_rxids_touched
    assert key not in runtime.incoming_body_done
    assert key not in runtime.incoming_response_done


def test_protocol_stats_reflects_tables_drops_and_gc_totals():
    """protocol_stats() reports the drop-counter snapshot, the live
    routing-table sizes, and the GC totals — the L8 observability contract."""
    runtime = CartridgeHostRuntime()
    xid, rid = MessageId.new_uuid(), MessageId.new_uuid()
    _seed_incoming(runtime, xid, rid, cartridge_idx=0)
    _seed_outgoing(runtime, MessageId.new_uuid(), cartridge_idx=1)
    runtime.drops.record(DropReason.NO_ROUTE)
    runtime.routing_gc_runs_total = 2
    runtime.routing_gc_evicted_total = 10

    stats = runtime.protocol_stats()
    assert stats.drops.total == 1
    assert stats.drops.by_reason.get(DropReason.NO_ROUTE.value) == 1
    assert stats.incoming_rxids == 1
    assert stats.outgoing_rids == 1
    assert stats.incoming_to_peer_rids == 0
    assert stats.outgoing_max_seq == 0
    assert stats.routing_gc_runs_total == 2
    assert stats.routing_gc_evicted_total == 10


def test_set_static_inventory_records_stores_records():
    """set_static_inventory_records replaces the stored list wholesale (the
    caller supplies the full desired set on each call, like the CartridgeHost
    counterpart)."""
    runtime = CartridgeHostRuntime()
    assert runtime.static_inventory_records == []
    runtime.set_static_inventory_records(["a", "b"])
    assert runtime.static_inventory_records == ["a", "b"]
    runtime.set_static_inventory_records([])
    assert runtime.static_inventory_records == []
