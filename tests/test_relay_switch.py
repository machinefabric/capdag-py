"""Tests for RelaySwitch — TEST426-TEST435, TEST7025/7035-7038/7085/7091/7093"""

import itertools
import json
import socket
import threading
import time
from io import BytesIO

import pytest

from capdag.bifaci.frame import Frame, FrameType, Limits, MessageId, compute_checksum, DropReason
from capdag.bifaci.io import FrameReader, FrameWriter
from capdag.bifaci.relay_switch import (
    RelaySwitch,
    SocketPair,
    NoHandlerError,
    ProtocolError,
    _parse_relay_notify_payload,
)
from capdag.bifaci.request_state import RequestState, RoutingEntry
from capdag.bifaci.stats import DropCounters

CAP_IDENTITY = "cap:effect=none"
CAP_GENERIC = "cap:echo"


def send_notify(writer: FrameWriter, manifest_json: dict, limits: Limits):
    """Helper to send RelayNotify"""
    manifest_bytes = json.dumps(manifest_json).encode("utf-8")
    notify = Frame.relay_notify(
        manifest_bytes,
        limits.max_frame,
        limits.max_chunk,
        limits.max_reorder_buffer,
    )
    writer.write(notify)


_make_manifest_counter = itertools.count(1)


def make_manifest(*caps: str) -> dict:
    """Build a RelayNotify-shaped manifest dict from a flat cap-urn list.

    The wire schema embeds caps inside ``installed_cartridges[*].cap_groups``,
    so this helper wraps the test's flat list (always prepended with
    CAP_IDENTITY) in a single synthetic installed-cartridge.

    Each call gets a unique ``id`` so aggregate-capability tests that
    register multiple slaves see them as distinct installed cartridges
    (the production dedup is by ``(id, version)``).
    """
    all_caps = [CAP_IDENTITY, *caps]
    group_caps = [
        {"urn": urn, "title": "test", "aliases": ["test"], "args": []}
        for urn in all_caps
    ]
    cartridge_id = f"test-cartridge-{next(_make_manifest_counter)}"
    return {
        "installed_cartridges": [
            {
                "registry_url": None,
                "channel": "release",
                "id": cartridge_id,
                "version": "0.0.0",
                "sha256": "0" * 64,
                "cap_groups": [
                    {
                        "name": "test",
                        "caps": group_caps,
                        "adapter_urns": [],
                    },
                ],
            }
        ]
    }


def complete_identity_verification(reader: FrameReader, writer: FrameWriter) -> None:
    req = reader.read()
    assert req is not None
    assert req.frame_type == FrameType.REQ
    assert req.cap == CAP_IDENTITY

    stream_start = reader.read()
    chunk = reader.read()
    stream_end = reader.read()
    end = reader.read()

    assert stream_start is not None and stream_start.frame_type == FrameType.STREAM_START
    assert chunk is not None and chunk.frame_type == FrameType.CHUNK
    assert stream_end is not None and stream_end.frame_type == FrameType.STREAM_END
    assert end is not None and end.frame_type == FrameType.END

    response_stream_id = stream_start.stream_id or "identity-verify"
    payload = chunk.payload or b""
    writer.write(Frame.stream_start(req.id, response_stream_id, "media:"))
    writer.write(
        Frame.chunk(
            req.id,
            response_stream_id,
            0,
            payload,
            0,
            compute_checksum(payload),
        )
    )
    writer.write(Frame.stream_end(req.id, response_stream_id, 1))
    writer.write(Frame.end(req.id, None))


_build_switch_counter = itertools.count(1)


def _build_switch_with_n_masters(n: int, capless: bool = False) -> RelaySwitch:
    """Build a RelaySwitch over ``n`` connected, healthy masters.

    Each master sends a RelayNotify and completes identity verification so
    its slot goes healthy. With ``capless=True`` the master registers an
    EMPTY cap set (only CAP_IDENTITY, which make_manifest always prepends) —
    mirroring the real-world "cartridges still inspecting / verifying" state
    where a master has connected but no cartridge has reached Operational.
    Returns the switch ready for set_expected_master_count / all_masters_ready
    calls.
    """
    pairs = []
    dones = []
    batch = next(_build_switch_counter)
    for i in range(n):
        engine_read, slave_write = socket.socketpair()
        slave_read, engine_write = socket.socketpair()
        done = threading.Event()
        dones.append(done)

        caps = () if capless else (f'cap:in="media:t{i}";noop;out="media:t{i}"',)

        def slave_thread(sr=slave_read, sw=slave_write, dn=done, cps=caps):
            reader = FrameReader(sr.makefile("rb"))
            writer = FrameWriter(sw.makefile("wb"))
            send_notify(writer, make_manifest(*cps), Limits.default())
            dn.set()
            complete_identity_verification(reader, writer)

        threading.Thread(target=slave_thread, daemon=True).start()
        pairs.append(SocketPair(
            id=f"ready-master-b{batch}-{i}",
            read=engine_read.makefile("rb"),
            write=engine_write.makefile("wb"),
        ))

    for done in dones:
        done.wait(timeout=2)

    return RelaySwitch(pairs)


# TEST426: Single master REQ/response routing
def test_426_single_master_req_response():
    """Verify basic single-master request/response flow"""
    # Create socket pair for master
    engine_read, slave_write = socket.socketpair()
    slave_read, engine_write = socket.socketpair()

    done = threading.Event()

    # Spawn mock slave that sends RelayNotify then echoes frames
    def slave_thread():
        reader = FrameReader(slave_read.makefile('rb'))
        writer = FrameWriter(slave_write.makefile('wb'))

        manifest = make_manifest(CAP_GENERIC)
        send_notify(writer, manifest, Limits.default())
        done.set()
        complete_identity_verification(reader, writer)

        # Read one REQ and send response. A real host echoes the incoming
        # REQ's routing_id (XID) on every response frame — the switch's
        # unified request table routes replies by that XID, matching real
        # cartridge_runtime.py behavior.
        frame = reader.read()
        if frame and frame.frame_type == FrameType.REQ:
            response = Frame.end(frame.id, bytes([42]))
            response.routing_id = frame.routing_id
            writer.write(response)

    threading.Thread(target=slave_thread, daemon=True).start()

    # Wait for RelayNotify
    done.wait(timeout=2)

    # Create RelaySwitch
    switch = RelaySwitch([SocketPair(id="test-master-0", read=engine_read.makefile('rb'), write=engine_write.makefile('wb'))])

    # Send REQ
    req = Frame.req(
        MessageId(1),
        CAP_GENERIC,
        bytes([1, 2, 3]),
        "text/plain"
    )
    switch.send_to_master(req)

    # Read response
    response = switch.read_from_masters()
    assert response is not None
    assert response.frame_type == FrameType.END
    assert response.id.to_string() == MessageId(1).to_string()
    assert response.payload == bytes([42])


# TEST427: Multi-master cap routing
def test_427_multi_master_cap_routing():
    """Verify routing to correct master based on cap URN"""
    # Create two masters with different caps
    engine_read1, slave_write1 = socket.socketpair()
    slave_read1, engine_write1 = socket.socketpair()
    engine_read2, slave_write2 = socket.socketpair()
    slave_read2, engine_write2 = socket.socketpair()

    done1 = threading.Event()
    done2 = threading.Event()

    # Spawn slave 1 (echo cap)
    def slave1_thread():
        reader = FrameReader(slave_read1.makefile('rb'))
        writer = FrameWriter(slave_write1.makefile('wb'))

        manifest = make_manifest(CAP_GENERIC)
        send_notify(writer, manifest, Limits.default())
        done1.set()
        complete_identity_verification(reader, writer)

        while True:
            frame = reader.read()
            if not frame:
                break
            if frame.frame_type == FrameType.REQ:
                response = Frame.end(frame.id, bytes([1]))
                response.routing_id = frame.routing_id
                writer.write(response)

    # Spawn slave 2 (double cap)
    def slave2_thread():
        reader = FrameReader(slave_read2.makefile('rb'))
        writer = FrameWriter(slave_write2.makefile('wb'))

        manifest = make_manifest('cap:in="media:void";double;out="media:void"')
        send_notify(writer, manifest, Limits.default())
        done2.set()
        complete_identity_verification(reader, writer)

        while True:
            frame = reader.read()
            if not frame:
                break
            if frame.frame_type == FrameType.REQ:
                response = Frame.end(frame.id, bytes([2]))
                response.routing_id = frame.routing_id
                writer.write(response)

    threading.Thread(target=slave1_thread, daemon=True).start()
    threading.Thread(target=slave2_thread, daemon=True).start()

    done1.wait(timeout=2)
    done2.wait(timeout=2)

    switch = RelaySwitch([
        SocketPair(id="test-master-1", read=engine_read1.makefile('rb'), write=engine_write1.makefile('wb')),
        SocketPair(id="test-master-2", read=engine_read2.makefile('rb'), write=engine_write2.makefile('wb')),
    ])

    # Send REQ for echo cap → routes to master 1
    req1 = Frame.req(
        MessageId(1),
        CAP_GENERIC,
        bytes(),
        "text/plain"
    )
    switch.send_to_master(req1)

    resp1 = switch.read_from_masters()
    assert resp1.payload == bytes([1])

    # Send REQ for double cap → routes to master 2
    req2 = Frame.req(
        MessageId(2),
        'cap:in="media:void";double;out="media:void"',
        bytes(),
        "text/plain"
    )
    switch.send_to_master(req2)

    resp2 = switch.read_from_masters()
    assert resp2.payload == bytes([2])


# TEST428: Unknown cap returns error
def test_428_unknown_cap_returns_error():
    """Verify NoHandlerError for unknown cap"""
    engine_read, slave_write = socket.socketpair()
    slave_read, engine_write = socket.socketpair()

    done = threading.Event()

    def slave_thread():
        reader = FrameReader(slave_read.makefile('rb'))
        writer = FrameWriter(slave_write.makefile('wb'))

        manifest = make_manifest(CAP_GENERIC)
        send_notify(writer, manifest, Limits.default())
        done.set()
        complete_identity_verification(reader, writer)

    threading.Thread(target=slave_thread, daemon=True).start()

    done.wait(timeout=2)

    switch = RelaySwitch([SocketPair(id="test-master-3", read=engine_read.makefile('rb'), write=engine_write.makefile('wb'))])

    # Send REQ for unknown cap
    req = Frame.req(
        MessageId(1),
        'cap:in="media:void";unknown;out="media:void"',
        bytes(),
        "text/plain"
    )

    with pytest.raises(NoHandlerError):
        switch.send_to_master(req)


# TEST429: Cap routing logic (find_master_for_cap)
def test_429_find_master_for_cap():
    """Verify find_master_for_cap logic with exact and URN matching"""
    # Create two masters with different caps
    engine_read1, slave_write1 = socket.socketpair()
    slave_read1, engine_write1 = socket.socketpair()
    engine_read2, slave_write2 = socket.socketpair()
    slave_read2, engine_write2 = socket.socketpair()

    done1 = threading.Event()
    done2 = threading.Event()

    def slave1_thread():
        reader = FrameReader(slave_read1.makefile('rb'))
        writer = FrameWriter(slave_write1.makefile('wb'))
        manifest = make_manifest(CAP_GENERIC)
        send_notify(writer, manifest, Limits.default())
        done1.set()
        complete_identity_verification(reader, writer)

    def slave2_thread():
        reader = FrameReader(slave_read2.makefile('rb'))
        writer = FrameWriter(slave_write2.makefile('wb'))
        manifest = make_manifest('cap:in="media:void";double;out="media:void"')
        send_notify(writer, manifest, Limits.default())
        done2.set()
        complete_identity_verification(reader, writer)

    threading.Thread(target=slave1_thread, daemon=True).start()
    threading.Thread(target=slave2_thread, daemon=True).start()

    done1.wait(timeout=2)
    done2.wait(timeout=2)

    switch = RelaySwitch([
        SocketPair(id="test-master-4", read=engine_read1.makefile('rb'), write=engine_write1.makefile('wb')),
        SocketPair(id="test-master-5", read=engine_read2.makefile('rb'), write=engine_write2.makefile('wb')),
    ])

    # Verify routing
    assert switch._find_master_for_cap(CAP_GENERIC) == 0
    assert switch._find_master_for_cap('cap:in="media:void";double;out="media:void"') == 1
    assert switch._find_master_for_cap('cap:in="media:void";unknown;out="media:void"') is None

    # Verify aggregate capabilities. The wire payload carries caps
    # inside `installed_cartridges[*].cap_groups[*].caps`; flatten the
    # union across all masters and assert against the canonical URN
    # strings.
    payload = json.loads(switch.capabilities())
    cap_list = []
    for ic in payload.get("installed_cartridges", []):
        for group in ic.get("cap_groups", []):
            for cap in group.get("caps", []):
                cap_list.append(cap["urn"])
    # Each slave contributes its own cap; identity (`cap:`) is
    # included once per slave under canonical normalization, so the
    # flat union is 2 (one identity + one specific cap each).
    assert CAP_IDENTITY in cap_list
    assert "cap:double;in=media:void;out=media:void" in cap_list


# TEST437: find_master_for_cap with preferred_cap routes to generic handler With is_dispatchable semantics: - Generic candidate (in=media:) CAN dispatch specific request (in="media:ext=pdf") because media: (wildcard) accepts any input type - Preference routes to preferred among dispatchable candidates
def test_437_preferred_cap_routes_to_generic():
    engine_read1, slave_write1 = socket.socketpair()
    slave_read1, engine_write1 = socket.socketpair()
    engine_read2, slave_write2 = socket.socketpair()
    slave_read2, engine_write2 = socket.socketpair()

    done1 = threading.Event()
    done2 = threading.Event()

    def slave1_thread():
        reader = FrameReader(slave_read1.makefile('rb'))
        writer = FrameWriter(slave_write1.makefile('wb'))
        send_notify(writer, make_manifest(CAP_GENERIC), Limits.default())
        done1.set()
        complete_identity_verification(reader, writer)

    def slave2_thread():
        reader = FrameReader(slave_read2.makefile('rb'))
        writer = FrameWriter(slave_write2.makefile('wb'))
        send_notify(writer, make_manifest('cap:in=\"media:ext=pdf\";out=media:'), Limits.default())
        done2.set()
        complete_identity_verification(reader, writer)

    threading.Thread(target=slave1_thread, daemon=True).start()
    threading.Thread(target=slave2_thread, daemon=True).start()
    done1.wait(timeout=2)
    done2.wait(timeout=2)

    switch = RelaySwitch([
        SocketPair(id="test-master-6", read=engine_read1.makefile('rb'), write=engine_write1.makefile('wb')),
        SocketPair(id="test-master-7", read=engine_read2.makefile('rb'), write=engine_write2.makefile('wb')),
    ])

    assert switch._find_master_for_cap(
        'cap:in=\"media:ext=pdf\";out=media:',
        preferred_cap=CAP_GENERIC,
    ) == 0


# TEST438: find_master_for_cap with preference falls back to closest-specificity when preferred cap is not in the comparable set
def test_438_preferred_cap_falls_back_when_not_comparable():
    engine_read1, slave_write1 = socket.socketpair()
    slave_read1, engine_write1 = socket.socketpair()
    engine_read2, slave_write2 = socket.socketpair()
    slave_read2, engine_write2 = socket.socketpair()

    done1 = threading.Event()
    done2 = threading.Event()

    def slave1_thread():
        reader = FrameReader(slave_read1.makefile('rb'))
        writer = FrameWriter(slave_write1.makefile('wb'))
        send_notify(writer, make_manifest('cap:in=\"media:text\";out=media:text'), Limits.default())
        done1.set()
        complete_identity_verification(reader, writer)

    def slave2_thread():
        reader = FrameReader(slave_read2.makefile('rb'))
        writer = FrameWriter(slave_write2.makefile('wb'))
        send_notify(writer, make_manifest(CAP_GENERIC), Limits.default())
        done2.set()
        complete_identity_verification(reader, writer)

    threading.Thread(target=slave1_thread, daemon=True).start()
    threading.Thread(target=slave2_thread, daemon=True).start()
    done1.wait(timeout=2)
    done2.wait(timeout=2)

    switch = RelaySwitch([
        SocketPair(id="test-master-8", read=engine_read1.makefile('rb'), write=engine_write1.makefile('wb')),
        SocketPair(id="test-master-9", read=engine_read2.makefile('rb'), write=engine_write2.makefile('wb')),
    ])

    assert switch._find_master_for_cap(
        'cap:in=\"media:text\";out=media:text',
        preferred_cap='cap:in=\"media:ext=pdf\";out=\"media:ext=pdf\"',
    ) == 0


# TEST439: Generic candidate CAN dispatch specific request (but only matches if no more specific candidate exists) With is_dispatchable: generic candidate (in=media:) CAN handle specific request (in="media:ext=pdf") because media: accepts any input type. With preference, can route to generic even when more specific exists.
def test_439_generic_candidate_can_dispatch_specific_request():
    engine_read1, slave_write1 = socket.socketpair()
    slave_read1, engine_write1 = socket.socketpair()
    engine_read2, slave_write2 = socket.socketpair()
    slave_read2, engine_write2 = socket.socketpair()

    done1 = threading.Event()
    done2 = threading.Event()

    def slave1_thread():
        reader = FrameReader(slave_read1.makefile('rb'))
        writer = FrameWriter(slave_write1.makefile('wb'))
        send_notify(writer, make_manifest(CAP_GENERIC), Limits.default())
        done1.set()
        complete_identity_verification(reader, writer)

    def slave2_thread():
        reader = FrameReader(slave_read2.makefile('rb'))
        writer = FrameWriter(slave_write2.makefile('wb'))
        send_notify(writer, make_manifest('cap:in=\"media:ext=pdf\";out=media:'), Limits.default())
        done2.set()
        complete_identity_verification(reader, writer)

    threading.Thread(target=slave1_thread, daemon=True).start()
    threading.Thread(target=slave2_thread, daemon=True).start()
    done1.wait(timeout=2)
    done2.wait(timeout=2)

    switch = RelaySwitch([
        SocketPair(id="test-master-10", read=engine_read1.makefile('rb'), write=engine_write1.makefile('wb')),
        SocketPair(id="test-master-11", read=engine_read2.makefile('rb'), write=engine_write2.makefile('wb')),
    ])

    assert switch._find_master_for_cap('cap:in=\"media:ext=pdf\";out=media:') == 1
    assert switch._find_master_for_cap(
        'cap:in=\"media:ext=pdf\";out=media:',
        preferred_cap=CAP_GENERIC,
    ) == 0


# TEST430: Tie-breaking (same cap on multiple masters - first match wins, routing is consistent)
def test_430_tie_breaking_same_cap_multiple_masters():
    """Verify consistent routing when multiple masters advertise same cap"""
    # Create two masters with the SAME cap
    engine_read1, slave_write1 = socket.socketpair()
    slave_read1, engine_write1 = socket.socketpair()
    engine_read2, slave_write2 = socket.socketpair()
    slave_read2, engine_write2 = socket.socketpair()

    done1 = threading.Event()
    done2 = threading.Event()

    same_cap = CAP_GENERIC

    # Spawn slave 1
    def slave1_thread():
        reader = FrameReader(slave_read1.makefile('rb'))
        writer = FrameWriter(slave_write1.makefile('wb'))
        manifest = make_manifest(same_cap)
        send_notify(writer, manifest, Limits.default())
        done1.set()
        complete_identity_verification(reader, writer)

        # Echo with marker 1
        while True:
            frame = reader.read()
            if not frame:
                break
            if frame.frame_type == FrameType.REQ:
                response = Frame.end(frame.id, bytes([1]))
                response.routing_id = frame.routing_id
                writer.write(response)

    # Spawn slave 2
    def slave2_thread():
        reader = FrameReader(slave_read2.makefile('rb'))
        writer = FrameWriter(slave_write2.makefile('wb'))
        manifest = make_manifest(same_cap)
        send_notify(writer, manifest, Limits.default())
        done2.set()
        complete_identity_verification(reader, writer)

        # Echo with marker 2 (should never be called if routing is consistent)
        while True:
            frame = reader.read()
            if not frame:
                break
            if frame.frame_type == FrameType.REQ:
                response = Frame.end(frame.id, bytes([2]))
                response.routing_id = frame.routing_id
                writer.write(response)

    threading.Thread(target=slave1_thread, daemon=True).start()
    threading.Thread(target=slave2_thread, daemon=True).start()

    done1.wait(timeout=2)
    done2.wait(timeout=2)

    switch = RelaySwitch([
        SocketPair(id="test-master-12", read=engine_read1.makefile('rb'), write=engine_write1.makefile('wb')),
        SocketPair(id="test-master-13", read=engine_read2.makefile('rb'), write=engine_write2.makefile('wb')),
    ])

    # Send first request - should go to master 0 (first match)
    req1 = Frame.req(MessageId(1), same_cap, bytes(), "text/plain")
    switch.send_to_master(req1)

    resp1 = switch.read_from_masters()
    assert resp1.payload == bytes([1])  # From master 0

    # Send second request - should ALSO go to master 0 (consistent routing)
    req2 = Frame.req(MessageId(2), same_cap, bytes(), "text/plain")
    switch.send_to_master(req2)

    resp2 = switch.read_from_masters()
    assert resp2.payload == bytes([1])  # Also from master 0


# TEST431: Continuation frame routing (CHUNK, END follow REQ)
def test_431_continuation_frame_routing():
    """Verify continuation frames route to same master as REQ"""
    engine_read, slave_write = socket.socketpair()
    slave_read, engine_write = socket.socketpair()

    done = threading.Event()

    def slave_thread():
        reader = FrameReader(slave_read.makefile('rb'))
        writer = FrameWriter(slave_write.makefile('wb'))

        manifest = make_manifest('cap:in="media:void";test;out="media:void"')
        send_notify(writer, manifest, Limits.default())
        done.set()
        complete_identity_verification(reader, writer)

        # Read REQ
        req = reader.read()
        assert req.frame_type == FrameType.REQ

        # Read CHUNK continuation
        chunk = reader.read()
        assert chunk.frame_type == FrameType.CHUNK
        assert chunk.id.to_string() == req.id.to_string()

        # Read END continuation
        end = reader.read()
        assert end.frame_type == FrameType.END
        assert end.id.to_string() == req.id.to_string()

        # Send response
        response = Frame.end(req.id, bytes([42]))
        response.routing_id = req.routing_id
        writer.write(response)

    threading.Thread(target=slave_thread, daemon=True).start()

    done.wait(timeout=2)

    switch = RelaySwitch([SocketPair(id="test-master-14", read=engine_read.makefile('rb'), write=engine_write.makefile('wb'))])

    req_id = MessageId(1)

    # Send REQ
    req = Frame.req(req_id, 'cap:in="media:void";test;out="media:void"', bytes(), "text/plain")
    switch.send_to_master(req)

    # Send CHUNK continuation
    chunk_payload = bytes([1, 2, 3])
    chunk = Frame.chunk(req_id, "stream1", 0, chunk_payload, 0, compute_checksum(chunk_payload))
    switch.send_to_master(chunk)

    # Send END continuation
    end = Frame.end(req_id, None)
    switch.send_to_master(end)

    # Read response
    response = switch.read_from_masters()
    assert response.frame_type == FrameType.END
    assert response.payload == bytes([42])


# TEST432: Empty masters list creates empty switch, add_master works
def test_432_empty_masters_list_error():
    """Verify error when creating RelaySwitch with empty masters list"""
    with pytest.raises(ProtocolError) as exc_info:
        RelaySwitch([])
    assert "at least one master" in str(exc_info.value)


# TEST433: Capability aggregation deduplicates caps
def test_433_capability_aggregation_deduplicates():
    """Verify aggregate capabilities deduplicate overlapping caps"""
    # Create two masters with overlapping caps
    engine_read1, slave_write1 = socket.socketpair()
    slave_read1, engine_write1 = socket.socketpair()
    engine_read2, slave_write2 = socket.socketpair()
    slave_read2, engine_write2 = socket.socketpair()

    done1 = threading.Event()
    done2 = threading.Event()

    def slave1_thread():
        reader = FrameReader(slave_read1.makefile('rb'))
        writer = FrameWriter(slave_write1.makefile('wb'))
        manifest = make_manifest(
            CAP_GENERIC,
            'cap:in="media:void";double;out="media:void"',
        )
        send_notify(writer, manifest, Limits.default())
        done1.set()
        complete_identity_verification(reader, writer)

    def slave2_thread():
        reader = FrameReader(slave_read2.makefile('rb'))
        writer = FrameWriter(slave_write2.makefile('wb'))
        manifest = make_manifest(
            CAP_GENERIC,
            'cap:in="media:void";triple;out="media:void"',
        )
        send_notify(writer, manifest, Limits.default())
        done2.set()
        complete_identity_verification(reader, writer)

    threading.Thread(target=slave1_thread, daemon=True).start()
    threading.Thread(target=slave2_thread, daemon=True).start()

    done1.wait(timeout=2)
    done2.wait(timeout=2)

    switch = RelaySwitch([
        SocketPair(id="test-master-15", read=engine_read1.makefile('rb'), write=engine_write1.makefile('wb')),
        SocketPair(id="test-master-16", read=engine_read2.makefile('rb'), write=engine_write2.makefile('wb')),
    ])

    payload = json.loads(switch.capabilities())
    # Walk installed_cartridges → cap_groups → caps and dedup by URN.
    cap_set = set()
    for ic in payload.get("installed_cartridges", []):
        for group in ic.get("cap_groups", []):
            for cap in group.get("caps", []):
                cap_set.add(cap["urn"])
    cap_list = sorted(cap_set)

    # Both slaves declare the explicit identity cap, the shared legal
    # generic cap, and a unique double/triple cap. The generic cap
    # remains stable without collapsing to an illegal bare top form.
    # The unique caps are
    # `cap:double;in=media:void;out=media:void` and
    # `cap:triple;in=media:void;out=media:void` (alphabetical tag
    # order). Total: 4 unique URNs.
    assert len(cap_list) == 4
    assert CAP_GENERIC in cap_list
    assert CAP_IDENTITY in cap_list
    assert 'cap:double;in=media:void;out=media:void' in cap_list
    assert 'cap:in=media:void;out=media:void;triple' in cap_list


# TEST434: Limits negotiation takes minimum
def test_434_limits_negotiation_minimum():
    """Verify negotiated limits take minimum across all masters"""
    engine_read1, slave_write1 = socket.socketpair()
    slave_read1, engine_write1 = socket.socketpair()
    engine_read2, slave_write2 = socket.socketpair()
    slave_read2, engine_write2 = socket.socketpair()

    done1 = threading.Event()
    done2 = threading.Event()

    def slave1_thread():
        reader = FrameReader(slave_read1.makefile('rb'))
        writer = FrameWriter(slave_write1.makefile('wb'))
        manifest = make_manifest()
        limits1 = Limits(max_frame=1_000_000, max_chunk=100_000)
        send_notify(writer, manifest, limits1)
        done1.set()
        complete_identity_verification(reader, writer)

    def slave2_thread():
        reader = FrameReader(slave_read2.makefile('rb'))
        writer = FrameWriter(slave_write2.makefile('wb'))
        manifest = make_manifest()
        limits2 = Limits(max_frame=2_000_000, max_chunk=50_000)  # Larger frame, smaller chunk
        send_notify(writer, manifest, limits2)
        done2.set()
        complete_identity_verification(reader, writer)

    threading.Thread(target=slave1_thread, daemon=True).start()
    threading.Thread(target=slave2_thread, daemon=True).start()

    done1.wait(timeout=2)
    done2.wait(timeout=2)

    switch = RelaySwitch([
        SocketPair(id="test-master-17", read=engine_read1.makefile('rb'), write=engine_write1.makefile('wb')),
        SocketPair(id="test-master-18", read=engine_read2.makefile('rb'), write=engine_write2.makefile('wb')),
    ])

    # Should take minimum of each limit
    assert switch.limits().max_frame == 1_000_000  # min(1M, 2M)
    assert switch.limits().max_chunk == 50_000     # min(100K, 50K)


# TEST435: URN matching (exact vs accepts())
def test_435_urn_matching_exact_and_accepts():
    """Verify exact and is_dispatchable contravariant/covariant matching for cap routing"""
    engine_read, slave_write = socket.socketpair()
    slave_read, engine_write = socket.socketpair()

    done = threading.Event()

    # Master advertises a specific cap
    registered_cap = 'cap:in="media:text;utf8";process;out="media:text;utf8"'

    def slave_thread():
        reader = FrameReader(slave_read.makefile('rb'))
        writer = FrameWriter(slave_write.makefile('wb'))
        manifest = make_manifest(registered_cap)
        send_notify(writer, manifest, Limits.default())
        done.set()
        complete_identity_verification(reader, writer)

        # Respond to request
        while True:
            frame = reader.read()
            if not frame:
                break
            if frame.frame_type == FrameType.REQ:
                response = Frame.end(frame.id, bytes([42]))
                response.routing_id = frame.routing_id
                writer.write(response)

    threading.Thread(target=slave_thread, daemon=True).start()

    done.wait(timeout=2)

    switch = RelaySwitch([SocketPair(id="test-master-19", read=engine_read.makefile('rb'), write=engine_write.makefile('wb'))])

    # Exact match should work
    req1 = Frame.req(MessageId(1), registered_cap, bytes(), "text/plain")
    switch.send_to_master(req1)
    resp1 = switch.read_from_masters()
    assert resp1.payload == bytes([42])

    # More specific request SHOULD match under is_dispatchable semantics:
    # Input (contravariant): request's media:text;utf8;normalized conforms_to candidate's media:text;utf8
    # Output (covariant): candidate's media:text;utf8 conforms_to request's media:text
    req2 = Frame.req(
        MessageId(2),
        'cap:in="media:text;utf8;normalized";process;out="media:text"',
        bytes(),
        "text/plain"
    )
    switch.send_to_master(req2)
    resp2 = switch.read_from_masters()
    assert resp2.payload == bytes([42])


# TEST487: RelaySwitch construction verifies identity through relay chain
def test_487_relay_switch_identity_verification_succeeds():
    engine_read, slave_write = socket.socketpair()
    slave_read, engine_write = socket.socketpair()

    def slave_thread():
        reader = FrameReader(slave_read.makefile("rb"))
        writer = FrameWriter(slave_write.makefile("wb"))
        send_notify(writer, make_manifest('cap:in="media:void";test;out="media:void"'), Limits.default())
        complete_identity_verification(reader, writer)

    threading.Thread(target=slave_thread, daemon=True).start()

    switch = RelaySwitch([SocketPair(id="test-master-20", read=engine_read.makefile("rb"), write=engine_write.makefile("wb"))])
    assert switch._find_master_for_cap('cap:in="media:void";test;out="media:void"') == 0


# TEST488: RelaySwitch construction fails when master's identity verification fails
def test_488_relay_switch_identity_verification_fails():
    engine_read, slave_write = socket.socketpair()
    slave_read, engine_write = socket.socketpair()

    def slave_thread():
        reader = FrameReader(slave_read.makefile("rb"))
        writer = FrameWriter(slave_write.makefile("wb"))
        send_notify(writer, make_manifest('cap:in="media:void";test;out="media:void"'), Limits.default())
        req = reader.read()
        assert req is not None
        assert req.frame_type == FrameType.REQ
        assert req.cap == CAP_IDENTITY
        writer.write(Frame.err(req.id, "BROKEN", "identity verification broken"))

    threading.Thread(target=slave_thread, daemon=True).start()

    with pytest.raises(ProtocolError) as exc_info:
        RelaySwitch([SocketPair(id="test-master-21", read=engine_read.makefile("rb"), write=engine_write.makefile("wb"))])
    assert "identity verification failed" in str(exc_info.value)


# TEST666: Preferred cap routing - routes to exact equivalent when multiple masters match
def test_666_preferred_cap_routing():
    engine_read1, slave_write1 = socket.socketpair()
    slave_read1, engine_write1 = socket.socketpair()
    engine_read2, slave_write2 = socket.socketpair()
    slave_read2, engine_write2 = socket.socketpair()

    done1 = threading.Event()
    done2 = threading.Event()

    generic_cap = CAP_GENERIC
    specific_cap = 'cap:in="media:ext=pdf";out=media:'

    def slave1_thread():
        reader = FrameReader(slave_read1.makefile("rb"))
        writer = FrameWriter(slave_write1.makefile("wb"))
        send_notify(writer, make_manifest(generic_cap), Limits.default())
        done1.set()
        complete_identity_verification(reader, writer)

    def slave2_thread():
        reader = FrameReader(slave_read2.makefile("rb"))
        writer = FrameWriter(slave_write2.makefile("wb"))
        send_notify(writer, make_manifest(specific_cap), Limits.default())
        done2.set()
        complete_identity_verification(reader, writer)

    threading.Thread(target=slave1_thread, daemon=True).start()
    threading.Thread(target=slave2_thread, daemon=True).start()
    done1.wait(timeout=2)
    done2.wait(timeout=2)

    switch = RelaySwitch([
        SocketPair(id="test-master-22", read=engine_read1.makefile("rb"), write=engine_write1.makefile("wb")),
        SocketPair(id="test-master-23", read=engine_read2.makefile("rb"), write=engine_write2.makefile("wb")),
    ])

    request = 'cap:in="media:ext=pdf";out=media:'
    assert switch._find_master_for_cap(request) == 1
    assert switch._find_master_for_cap(request, preferred_cap=specific_cap) == 1
    assert switch._find_master_for_cap(request, preferred_cap=generic_cap) == 0


# ============================================================
# Reattach-by-id tests for the cardinality-stable slot model.
#
# When a master dies and the host reconnects, the new socket MUST
# attach to the same slot index — preserving routing entries
# keyed by index. Accumulating zombie slots on each reconnect was
# the bug class these tests guard against.


def test_133_reattach_by_id_preserves_slot_index():
    """After ``handle_master_death`` the slot stays in place, and a
    reconnect via ``add_master`` with the same id MUST land back in
    the same slot index — not append a new slot."""
    engine_read, slave_write = socket.socketpair()
    slave_read, engine_write = socket.socketpair()

    done1 = threading.Event()

    def slave1_thread():
        reader = FrameReader(slave_read.makefile("rb"))
        writer = FrameWriter(slave_write.makefile("wb"))
        send_notify(writer, make_manifest(CAP_GENERIC), Limits.default())
        done1.set()
        complete_identity_verification(reader, writer)

    threading.Thread(target=slave1_thread, daemon=True).start()
    done1.wait(timeout=2)

    switch = RelaySwitch([
        SocketPair(id="xpc-service", read=engine_read.makefile("rb"), write=engine_write.makefile("wb")),
    ])
    assert len(switch._masters) == 1
    assert switch._masters[0].id == "xpc-service"
    assert switch._masters[0].healthy is True

    # Simulate master death via the same code path the frame loop
    # uses on EOF. Bypassing the frame loop keeps the test focused
    # on the reattach contract itself.
    switch._handle_master_death(0)
    assert len(switch._masters) == 1, (
        "_handle_master_death must NOT remove the slot — reattach depends on it staying in place"
    )
    assert switch._masters[0].healthy is False

    # Reconnect: build a fresh slave + socket pair under the SAME id.
    engine_read2, slave_write2 = socket.socketpair()
    slave_read2, engine_write2 = socket.socketpair()

    done2 = threading.Event()

    def slave2_thread():
        reader = FrameReader(slave_read2.makefile("rb"))
        writer = FrameWriter(slave_write2.makefile("wb"))
        send_notify(writer, make_manifest(CAP_GENERIC), Limits.default())
        done2.set()
        complete_identity_verification(reader, writer)

    threading.Thread(target=slave2_thread, daemon=True).start()
    done2.wait(timeout=2)

    new_idx = switch.add_master(SocketPair(
        id="xpc-service",
        read=engine_read2.makefile("rb"),
        write=engine_write2.makefile("wb"),
    ))
    assert new_idx == 0, (
        "reattach MUST return the same slot index (0), not append a new slot"
    )
    assert len(switch._masters) == 1, (
        "reattach MUST NOT grow the slot count — that was the zombie-slot bug"
    )
    assert switch._masters[0].healthy is True
    assert switch._masters[0].id == "xpc-service", (
        "slot id MUST be preserved across reattach"
    )


# TEST134: Add master with duplicate healthy id errors
def test_134_add_master_with_duplicate_healthy_id_errors():
    """Adding a master with the id of an already-healthy slot is a
    wiring bug; surface as a hard ProtocolError."""
    engine_read, slave_write = socket.socketpair()
    slave_read, engine_write = socket.socketpair()

    done = threading.Event()

    def slave_thread():
        reader = FrameReader(slave_read.makefile("rb"))
        writer = FrameWriter(slave_write.makefile("wb"))
        send_notify(writer, make_manifest(CAP_GENERIC), Limits.default())
        done.set()
        complete_identity_verification(reader, writer)

    threading.Thread(target=slave_thread, daemon=True).start()
    done.wait(timeout=2)

    switch = RelaySwitch([
        SocketPair(id="xpc-service", read=engine_read.makefile("rb"), write=engine_write.makefile("wb")),
    ])
    assert switch._masters[0].healthy is True

    # Try to add a second master with the same id while healthy.
    # The duplicate-id check fires BEFORE any I/O on the dummy
    # socket, so the dummy never has to go through a handshake.
    dummy_a, dummy_b = socket.socketpair()
    with pytest.raises(ProtocolError) as exc_info:
        switch.add_master(SocketPair(
            id="xpc-service",
            read=dummy_a.makefile("rb"),
            write=dummy_b.makefile("wb"),
        ))
    assert "already attached to a healthy slot" in str(exc_info.value)
    assert len(switch._masters) == 1, (
        "no slot should be created when the duplicate-id check fires"
    )


# TEST6745: RelaySwitch::new rejects duplicate ids in its cardinality list.
def test_6745_relay_switch_init_rejects_duplicate_ids():
    """The constructor rejects duplicate ids before any I/O. Without
    this guard the first reconnect would reattach to whichever slot
    is found first by the linear scan, leaving the other stuck
    unhealthy forever."""
    a_read, a_other = socket.socketpair()
    b_read, b_other = socket.socketpair()

    with pytest.raises(ProtocolError) as exc_info:
        RelaySwitch([
            SocketPair(id="dup-id", read=a_read.makefile("rb"), write=a_other.makefile("wb")),
            SocketPair(id="dup-id", read=b_read.makefile("rb"), write=b_other.makefile("wb")),
        ])
    assert "duplicate master id 'dup-id'" in str(exc_info.value)


# TEST136: All masters ready false when expected count unset
def test_0136_all_masters_ready_false_when_expected_count_unset():
    """Even with a connected, fully-RelayNotify'd master, the predicate
    must return false until the engine explicitly declares its expected
    master count via set_expected_master_count. The default-zero policy
    is the safety net that makes 'engine boot forgot to declare its
    expected count' surface as a hung readiness gate rather than a
    false-positive ready signal."""
    engine_read, slave_write = socket.socketpair()
    slave_read, engine_write = socket.socketpair()

    done = threading.Event()

    def slave_thread():
        reader = FrameReader(slave_read.makefile("rb"))
        writer = FrameWriter(slave_write.makefile("wb"))
        send_notify(writer, make_manifest(CAP_GENERIC), Limits.default())
        done.set()
        complete_identity_verification(reader, writer)

    threading.Thread(target=slave_thread, daemon=True).start()
    done.wait(timeout=2)

    switch = RelaySwitch([
        SocketPair(id="xpc-service", read=engine_read.makefile("rb"), write=engine_write.makefile("wb")),
    ])
    assert switch._masters[0].healthy is True

    # Expected count never declared (default 0): not-yet-configured.
    assert switch.all_masters_ready() is False, (
        "all_masters_ready must return false when expected_master_count is 0"
    )

    # Once the expected count is met and the single master is healthy,
    # the predicate flips to true — proving the gate is the count, not
    # an unconditional false.
    switch.set_expected_master_count(1)
    assert switch.all_masters_ready() is True, (
        "all_masters_ready must return true when expected count is met and the master is healthy"
    )


# TEST137: All masters ready false when partially connected
def test_0137_all_masters_ready_false_when_partially_connected():
    """1 master connected, 2 expected. This is the live regression: the
    internal master had caps from t=0 but the external-cartridges master
    was still spawning cartridges. The host saw ready immediately and the
    bidi never started. The predicate must return false until
    len(masters) reaches expected_master_count."""
    switch = _build_switch_with_n_masters(1)
    assert switch._masters[0].healthy is True

    switch.set_expected_master_count(2)
    assert switch.all_masters_ready() is False, (
        "all_masters_ready must return false until masters.len() reaches expected_master_count"
    )


# TEST139: All masters ready true when masters connected but capless
def test_0139_all_masters_ready_true_when_masters_connected_but_capless():
    """Cartridges in discovered/inspecting/verifying contribute zero caps
    to their master's RelayNotify. The engine readiness gate must still
    fire so the splash screen can unblock — caps register incrementally as
    cartridges progress to Operational. A regression that re-coupled
    readiness to cap-set non-emptiness would make this fail (and hang the
    splash screen on every cold start with slow cartridges)."""
    switch = _build_switch_with_n_masters(2, capless=True)
    assert all(m.healthy for m in switch._masters)

    switch.set_expected_master_count(2)
    assert switch.all_masters_ready() is True, (
        "all_masters_ready must NOT require master.caps to be non-empty — "
        "caps register asynchronously as cartridges progress to Operational"
    )


# TEST140: All masters ready does not overshoot
def test_0140_all_masters_ready_does_not_overshoot():
    """2 masters connected, 1 expected. The predicate should still report
    ready — the engine got more masters than it declared, which is fine;
    'at least expected' is the semantic. A regression that used == instead
    of >= would make this case false and break edition setups where an
    extra master arrives later."""
    switch = _build_switch_with_n_masters(2)
    assert all(m.healthy for m in switch._masters)

    switch.set_expected_master_count(1)
    assert switch.all_masters_ready() is True, (
        "all_masters_ready uses >= not == against expected_master_count"
    )


# TEST132: add_master dynamically connects new host to running switch
def test_132_add_master_dynamic():
    from capdag.bifaci.in_process_host import (
        FrameHandler,
        InProcessCartridgeHost,
        InProcessHostIdentity,
    )
    from capdag.bifaci.relay import RelaySlave
    from capdag.cap.caller import CapArgumentValue
    from capdag.cap.definition import Cap
    from capdag.urn.cap_urn import CapUrn

    class ConstHandler(FrameHandler):
        """Handler that returns a constant byte string (ignores input)."""

        def __init__(self, value: str):
            self.value = value

        def handle_request(self, cap_urn, input_q, output, peer):
            while True:
                frame = input_q.get()
                if frame is None:
                    break
                if frame.frame_type == FrameType.END:
                    break
            output.emit_response("media:", self.value.encode("utf-8"))

    threads = []

    def wire_host(host):
        """Wire host -> slave -> switch; return the switch-side SocketPair plus
        the sockets to keep alive."""
        # host <-> slave-local
        host_sock_a, slave_local_a = socket.socketpair()
        # slave <-> switch
        slave_sock_a, switch_sock_a = socket.socketpair()

        host_read = host_sock_a.makefile("rb")
        host_write = host_sock_a.makefile("wb")

        def host_run():
            host.run(host_read, host_write)

        ht = threading.Thread(target=host_run, daemon=True)
        ht.start()
        threads.append(ht)

        slave_local_reader = FrameReader(slave_local_a.makefile("rb"))
        slave_local_writer = FrameWriter(slave_local_a.makefile("wb"))
        slave = RelaySlave(slave_local_reader, slave_local_writer)

        slave_socket_reader = FrameReader(slave_sock_a.makefile("rb"))
        slave_socket_writer = FrameWriter(slave_sock_a.makefile("wb"))

        def slave_run():
            slave.run(slave_socket_reader, slave_socket_writer, None)

        st = threading.Thread(target=slave_run, daemon=True)
        st.start()
        threads.append(st)

        switch_pair = SocketPair(
            id=None,  # filled by caller
            read=switch_sock_a.makefile("rb"),
            write=switch_sock_a.makefile("wb"),
        )
        return switch_pair

    def make_const_host(host_id: str, cap_urn: str, value: str):
        cap = Cap(CapUrn.from_string(cap_urn), value, "")
        return InProcessCartridgeHost(
            InProcessHostIdentity.for_test(host_id),
            [(value, [cap], ConstHandler(value))],
        )

    # Create initial switch with handler A.
    cap_a = 'cap:in="media:void";alpha;out="media:void"'
    host_a = make_const_host("alpha-host", cap_a, "alpha")
    pair_a = wire_host(host_a)
    pair_a = SocketPair(id="test-master-0", read=pair_a.read, write=pair_a.write)

    switch = RelaySwitch([pair_a])
    with switch._lock:
        assert len(switch._masters) == 1

    # Add handler B dynamically.
    cap_b = 'cap:in="media:void";beta;out="media:void"'
    host_b = make_const_host("beta-host", cap_b, "beta")
    pair_b = wire_host(host_b)
    pair_b = SocketPair(id="test-master-1", read=pair_b.read, write=pair_b.write)

    idx = switch.add_master(pair_b)
    assert idx == 1
    with switch._lock:
        assert len(switch._masters) == 2

    # Verify both caps are in aggregate capabilities.
    caps_payload = json.loads(switch.capabilities())
    advertised = [
        cap["urn"]
        for ic in caps_payload.get("installed_cartridges", [])
        for group in ic.get("cap_groups", [])
        for cap in group.get("caps", [])
    ]
    assert any("alpha" in c for c in advertised)
    assert any("beta" in c for c in advertised)

    # Execute against beta (dynamically added master).
    rid = MessageId.new_uuid()
    max_chunk = switch.limits().max_chunk
    frames = CapArgumentValue.build_request_frames(rid, cap_b, [], max_chunk)
    for frame in frames:
        switch.send_to_master(frame, None)

    response_data = bytearray()
    while True:
        frame = switch.read_from_masters()
        if frame is None:
            break
        if frame.id != rid:
            continue
        if frame.frame_type == FrameType.CHUNK:
            if frame.payload is not None:
                import cbor2
                value = cbor2.loads(frame.payload)
                assert isinstance(value, bytes), f"unexpected CBOR: {value!r}"
                response_data.extend(value)
        elif frame.frame_type == FrameType.END:
            break
        elif frame.frame_type == FrameType.ERR:
            raise AssertionError(f"ERR: {frame.error_message()}")

    assert bytes(response_data) == b"beta"


# ============================================================
# Deferred runtime identity-probe cluster (parity with the Rust
# RelaySwitch tests of the same numbers). A master that advertises
# EMPTY caps at connect skips the synchronous probe; a later
# RelayNotify that transitions empty→non-empty must be re-verified
# end-to-end before the new caps become routable.

# Canonical form of the post-init advertised non-identity cap. Routability
# is always checked via the dispatch path (_find_master_for_cap), never by
# string-comparing URNs.
DEFERRED_TEST_CAP = 'cap:in="media:void";test;out="media:void"'


def _deferred_identity_slave(slave_read, slave_write, caps, succeed: bool):
    """Mirror of the Rust ``slave_deferred_identity`` helper.

    Sends an EMPTY initial RelayNotify (so construction skips the synchronous
    probe and the master joins capless+healthy), then a populated RelayNotify
    carrying ``caps`` (the empty→non-empty transition the relay must
    re-verify). It then answers the runtime identity probe: if ``succeed`` it
    echoes the probe's nonce back on the same flow (probe passes → master
    flips healthy → caps routable); otherwise it replies ERR (probe fails →
    master stays unhealthy, caps held back).
    """
    reader = FrameReader(slave_read.makefile("rb"))
    writer = FrameWriter(slave_write.makefile("wb"))

    # 1. Empty initial RelayNotify — construction skips the probe.
    send_notify(writer, {"installed_cartridges": []}, Limits.default())

    # 2. Populated RelayNotify — the empty→non-empty transition.
    group_caps = [
        {"urn": urn, "title": "test", "aliases": ["test"], "args": []}
        for urn in caps
    ]
    populated = {
        "installed_cartridges": [
            {
                "registry_url": None,
                "channel": "release",
                "id": "test-cartridge",
                "version": "0.0.0",
                "sha256": "0" * 64,
                "cap_groups": [
                    {"name": "test", "caps": group_caps, "adapter_urns": []},
                ],
            }
        ]
    }
    send_notify(writer, populated, Limits.default())

    # 3. Answer the runtime identity probe.
    probe_rid = None
    probe_xid = None
    nonce = bytearray()
    while True:
        frame = reader.read()
        if frame is None:
            return
        if frame.frame_type == FrameType.REQ:
            probe_rid = frame.id
            probe_xid = frame.routing_id
            if not succeed:
                err = Frame.err(frame.id, "BROKEN", "test cartridge")
                err.routing_id = frame.routing_id
                writer.write(err)
                return
        elif frame.frame_type == FrameType.CHUNK:
            if frame.payload is not None:
                nonce.extend(frame.payload)
        elif frame.frame_type == FrameType.END:
            # Echo the nonce back on the probe's flow → probe passes.
            stream_id = "identity-echo"
            ss = Frame.stream_start(probe_rid, stream_id, "media:")
            ss.routing_id = probe_xid
            chunk = Frame.chunk(
                probe_rid, stream_id, 0, bytes(nonce), 0, compute_checksum(bytes(nonce))
            )
            chunk.routing_id = probe_xid
            se = Frame.stream_end(probe_rid, stream_id, 1)
            se.routing_id = probe_xid
            end = Frame.end(probe_rid, None)
            end.routing_id = probe_xid
            for fr in (ss, chunk, se, end):
                writer.write(fr)
            # Stay connected after a successful probe — a real host does not
            # disconnect right after identity verification. Closing here would
            # race an EOF-driven master death against the healthy-flip the
            # probe just performed. Block until the switch tears the socket
            # down (EOF), keeping the master healthy for the test's assertions.
            while reader.read() is not None:
                pass
            return


def _build_deferred_switch(succeed: bool):
    """Construct a single-master switch whose master defers identity to a
    runtime RelayNotify, and start the background pump so probe echoes route."""
    engine_read, slave_write = socket.socketpair()
    slave_read, engine_write = socket.socketpair()

    threading.Thread(
        target=_deferred_identity_slave,
        args=(slave_read, slave_write, [CAP_IDENTITY, DEFERRED_TEST_CAP], succeed),
        daemon=True,
    ).start()

    switch = RelaySwitch([SocketPair(
        id="deferred-master-0",
        read=engine_read.makefile("rb"),
        write=engine_write.makefile("wb"),
    )])
    switch.start_background_pump()
    return switch


# TEST0131: empty→non-empty transition must run a runtime identity probe;
# a master that fails it ends up unhealthy with last_error and its caps are
# excluded from routing.
def test_0131_runtime_identity_probe_required_on_empty_to_nonempty_transition():
    switch = _build_deferred_switch(succeed=False)

    deadline = time.monotonic() + 15
    master_unhealthy = False
    while time.monotonic() < deadline:
        with switch._lock:
            if switch._masters:
                m = switch._masters[0]
                if (not m.healthy) and m.last_error is not None:
                    master_unhealthy = True
                    break
        time.sleep(0.05)
    assert master_unhealthy, (
        "master must be marked unhealthy after the runtime identity probe fails"
    )

    # The unverified master's caps must NOT be routable — checked via the
    # dispatch path, never by string-comparing URNs.
    assert switch._find_master_for_cap(DEFERRED_TEST_CAP) is None, (
        "unverified master's caps must be excluded from routing"
    )


# TEST0135: the SUCCESS path — a master that advertises caps after connecting
# and then passes the probe flips healthy and its caps become routable.
def test_0135_runtime_identity_probe_success_makes_caps_routable():
    switch = _build_deferred_switch(succeed=True)

    deadline = time.monotonic() + 15
    routable = False
    while time.monotonic() < deadline:
        if switch._find_master_for_cap(DEFERRED_TEST_CAP) == 0:
            routable = True
            break
        time.sleep(0.05)
    assert routable, (
        "after a successful runtime identity probe the master's post-init "
        "advertised cap must become routable"
    )
    with switch._lock:
        assert switch._masters[0].healthy is True, (
            "master must be healthy after a successful runtime identity probe"
        )


# TEST1897: the installed-cartridge INVENTORY is NOT health-filtered. A
# master held unhealthy by a failed probe still has its cartridges visible in
# the inventory aggregate, even though its caps are excluded from routing.
def test_1897_unhealthy_master_inventory_retained_but_not_routable():
    switch = _build_deferred_switch(succeed=False)

    deadline = time.monotonic() + 15
    unhealthy = False
    while time.monotonic() < deadline:
        with switch._lock:
            if switch._masters:
                m = switch._masters[0]
                if (not m.healthy) and m.last_error is not None:
                    unhealthy = True
                    break
        time.sleep(0.05)
    assert unhealthy, "master must be unhealthy after the probe fails"

    # ROUTING: the unhealthy master's caps are excluded (dispatch path).
    assert switch._find_master_for_cap(DEFERRED_TEST_CAP) is None, (
        "an unhealthy master's caps must NOT be routable"
    )

    # INVENTORY: the cartridge is STILL visible — not health-filtered.
    inventory = switch.installed_cartridges()
    assert any(c.id == "test-cartridge" for c in inventory), (
        "an unhealthy master's installed cartridges must remain visible in "
        f"the inventory aggregate, got: {[c.id for c in inventory]}"
    )


# TEST1898: the routable-capability watch (subscribe_capabilities). A
# subscriber must receive the CURRENT routable cap set on subscribe even
# though it was rebuilt during construction — BEFORE any receiver existed
# (the watch must persist the value, i.e. send_replace, not a plain
# broadcast that drops it with zero receivers). The delivered set is the
# health-filtered routable cap URNs.
def test_1898_subscribe_capabilities_delivers_routable_set():
    engine_read, slave_write = socket.socketpair()
    slave_read, engine_write = socket.socketpair()
    done = threading.Event()

    def slave_thread():
        reader = FrameReader(slave_read.makefile("rb"))
        writer = FrameWriter(slave_write.makefile("wb"))
        send_notify(writer, make_manifest(DEFERRED_TEST_CAP), Limits.default())
        done.set()
        complete_identity_verification(reader, writer)

    threading.Thread(target=slave_thread, daemon=True).start()
    done.wait(timeout=2)

    # Capabilities are rebuilt inside __init__ — before we subscribe.
    switch = RelaySwitch([SocketPair(
        id="watch-master-0",
        read=engine_read.makefile("rb"),
        write=engine_write.makefile("wb"),
    )])

    rx = switch.subscribe_capabilities()
    watched = rx.borrow()

    # The watch must mirror the synchronous routable-set getter: identical
    # serialized snapshot from the same source (a snapshot-identity check,
    # NOT a URN comparison). This is also what catches the bug the test
    # guards: the snapshot is rebuilt before any subscriber exists, so the
    # watch must persist it (send_replace). A plain broadcast would leave the
    # watch holding the empty initial value while the getter returns the
    # populated set — making these two diverge.
    assert watched == switch.routable_capabilities(), (
        "the capability watch must deliver the same routable-set snapshot as "
        "routable_capabilities()"
    )

    # The watch must have persisted a NON-empty routable set (the populated
    # caps), proving send_replace semantics rather than the dropped-empty bug.
    assert json.loads(watched), (
        "the routable set must be non-empty after a healthy master verified"
    )

    # Prove the snapshot is the live ROUTABLE set the only correct way — via
    # dispatch conformance, not string comparison of URNs.
    assert switch._find_master_for_cap(DEFERRED_TEST_CAP) == 0, (
        "the routable set the watch delivers must make the master's "
        "advertised cap dispatchable"
    )


# Gap-5 lock: an add_master identity-probe FAILURE registers the master as
# UNHEALTHY (inventory visible) rather than RAISING — matching the reference
# add_master (and unlike the constructor, which raises; see test_488).
def test_1904_add_master_probe_failure_registers_unhealthy_not_raises():
    # First master: a healthy, fully-verified slot.
    g_engine_read, g_slave_write = socket.socketpair()
    g_slave_read, g_engine_write = socket.socketpair()
    g_done = threading.Event()

    def good_slave():
        reader = FrameReader(g_slave_read.makefile("rb"))
        writer = FrameWriter(g_slave_write.makefile("wb"))
        send_notify(writer, make_manifest(CAP_GENERIC), Limits.default())
        g_done.set()
        complete_identity_verification(reader, writer)

    threading.Thread(target=good_slave, daemon=True).start()
    g_done.wait(timeout=2)
    switch = RelaySwitch([SocketPair(
        id="good-master-0",
        read=g_engine_read.makefile("rb"),
        write=g_engine_write.makefile("wb"),
    )])

    # Second master: advertises non-empty caps but its identity handler is
    # broken (replies ERR). add_master must NOT raise.
    b_engine_read, b_slave_write = socket.socketpair()
    b_slave_read, b_engine_write = socket.socketpair()
    b_done = threading.Event()

    def broken_slave():
        reader = FrameReader(b_slave_read.makefile("rb"))
        writer = FrameWriter(b_slave_write.makefile("wb"))
        send_notify(writer, make_manifest(DEFERRED_TEST_CAP), Limits.default())
        b_done.set()
        req = reader.read()
        assert req is not None and req.frame_type == FrameType.REQ
        assert req.cap == CAP_IDENTITY
        writer.write(Frame.err(req.id, "BROKEN", "identity verification broken"))

    threading.Thread(target=broken_slave, daemon=True).start()
    b_done.wait(timeout=2)

    idx = switch.add_master(SocketPair(
        id="broken-master-1",
        read=b_engine_read.makefile("rb"),
        write=b_engine_write.makefile("wb"),
    ))
    assert idx == 1, "add_master must still register the slot (not raise)"

    with switch._lock:
        broken = switch._masters[1]
        assert broken.healthy is False, (
            "a master that fails its add-time identity probe must be unhealthy"
        )
        assert broken.last_error is not None, (
            "an identity-probe failure must populate last_error"
        )

    # The broken master's caps must not be routable (dispatch path).
    assert switch._find_master_for_cap(DEFERRED_TEST_CAP) is None, (
        "an unhealthy master's caps must not be routable"
    )
    # The healthy master is unaffected.
    assert switch._find_master_for_cap(CAP_GENERIC) == 0


# ============================================================
# Unified RequestTable / protocol_stats() cluster (protocol v3, L7/L8).
# Parity with the reference RelaySwitch tests of the same numbers: the
# unified request table replaces the smeared routing/peer/parent maps with
# one register()/terminate() per request, drop-counted no_route/channel_closed
# frames, cancel cascade via linked children, and a master-death sweep — all
# observable through protocol_stats().


def _state(dest: int, origin, channel=None, is_peer: bool = False) -> RequestState:
    return RequestState(
        routing=RoutingEntry(source_master_idx=origin, destination_master_idx=dest),
        origin=origin,
        external_channel=channel,
        is_peer=is_peer,
    )


# TEST7025: A flow frame for a request with no routing state is a counted
# no_route drop — not a protocol error and not a silent loss — observable in
# the protocol stats snapshot. (The reference builds a switch with ZERO
# masters; this mirror's constructor requires at least one — see TEST432 —
# so this uses a single connected, healthy master instead. The drop-counting
# behavior under test is unaffected by that setup difference.)
def test_7025_unroutable_flow_frame_is_counted_drop():
    switch = _build_switch_with_n_masters(1)

    # Response continuation (has XID) for a key that was never registered
    # (or already terminated): must be dropped + counted, never an error.
    orphan = Frame.progress(MessageId.new_uuid(), 0.5, "orphan")
    orphan.routing_id = MessageId(999)
    result = switch._handle_master_frame(0, orphan)
    assert result is None, "nothing to deliver"

    # Request continuation (no XID) for an unknown RID: same law.
    chunk = Frame.chunk(MessageId.new_uuid(), "s", 0, b"", 0, compute_checksum(b""))
    result = switch._handle_master_frame(0, chunk)
    assert result is None

    stats = switch.protocol_stats()
    assert stats.drops.by_reason.get("no_route") == 2, (
        f"both drops counted, exactly once each (L8): {stats.drops}"
    )
    assert stats.requests.active == []


# TEST7035: After END, the switch holds zero state for the request — entry,
# rid index, and response channel all released atomically, with the terminal
# delivered and a terminated summary recorded.
def test_7035_end_terminates_and_releases_all_state():
    switch = _build_switch_with_n_masters(1)

    xid = MessageId(11)
    rid = MessageId.new_uuid()
    key = (xid, rid)
    delivered = []
    switch._requests.register(key, _state(0, None, delivered.append))
    assert len(switch.protocol_stats().requests.active) == 1

    # Terminal END arrives from the master side.
    end = Frame.end_ok_with(rid, None, 1.0, None)
    end.routing_id = xid
    switch._handle_master_frame(0, end)

    # The terminal was DELIVERED to the waiting channel...
    assert len(delivered) == 1, "END must reach the response channel"
    assert delivered[0].frame_type == FrameType.END
    assert delivered[0].final_progress() == 1.0

    # ...and zero state remains (L7), with the lifecycle recorded.
    stats = switch.protocol_stats()
    assert stats.requests.active == [], "no live entry after END"
    assert stats.requests.terminated_by_kind.get("end") == 1
    summary = stats.requests.recent_terminated[-1]
    assert summary.rid == rid.to_string()
    assert summary.frames_in == 1, "ingress recording captured the terminal frame"

    # A follow-up frame for the released key is a counted no_route drop.
    late = Frame.progress(rid, 1.0, "late")
    late.routing_id = xid
    switch._handle_master_frame(0, late)
    assert switch.protocol_stats().drops.by_reason.get("no_route") == 1


# TEST7036: After ERR, the same total-cleanup invariant holds as after END,
# with kind err.
def test_7036_err_terminates_and_releases_all_state():
    switch = _build_switch_with_n_masters(1)

    xid = MessageId(21)
    rid = MessageId.new_uuid()
    delivered = []
    switch._requests.register((xid, rid), _state(0, None, delivered.append))

    err = Frame.err(rid, "HANDLER_ERROR", "boom")
    err.routing_id = xid
    switch._handle_master_frame(0, err)

    assert len(delivered) == 1, "ERR must reach the channel"
    assert delivered[0].frame_type == FrameType.ERR
    assert delivered[0].error_code() == "HANDLER_ERROR"

    stats = switch.protocol_stats()
    assert stats.requests.active == []
    assert stats.requests.terminated_by_kind.get("err") == 1


# TEST7037: Cancelling a request terminates it AND its recursively-linked
# peer children — Cancel frames reach the destination, waiting channels get
# ERR CANCELLED, and zero state remains for parent or child.
def test_7037_cancel_cascades_to_children_and_cleans_all_state():
    engine_read, slave_write = socket.socketpair()
    slave_read, engine_write = socket.socketpair()
    done = threading.Event()
    cancels = []
    collected = threading.Event()

    def slave_thread():
        reader = FrameReader(slave_read.makefile("rb"))
        writer = FrameWriter(slave_write.makefile("wb"))
        send_notify(writer, make_manifest(), Limits.default())
        done.set()
        complete_identity_verification(reader, writer)
        # Collect the Cancel frames the cascade sends us.
        while len(cancels) < 2:
            frame = reader.read()
            if frame is None:
                break
            if frame.frame_type == FrameType.CANCEL:
                cancels.append(frame.id)
        collected.set()

    threading.Thread(target=slave_thread, daemon=True).start()
    done.wait(timeout=2)

    switch = RelaySwitch([SocketPair(
        id="cancel-cascade-master-0",
        read=engine_read.makefile("rb"),
        write=engine_write.makefile("wb"),
    )])

    # Parent (engine-origin, has a waiting channel) + child peer call.
    parent_key = (MessageId(1), MessageId.new_uuid())
    child_key = (MessageId(2), MessageId.new_uuid())
    delivered = []
    switch._requests.register(parent_key, _state(0, None, delivered.append))
    switch._requests.register(child_key, _state(0, 0, None, is_peer=True))
    switch._requests.link_child(parent_key, child_key)

    switch.cancel_request(parent_key[1], False)

    # Parent's waiter observes ERR CANCELLED.
    assert len(delivered) == 1, "parent channel gets ERR"
    assert delivered[0].error_code() == "CANCELLED"

    # Both parent and child are fully released (L7), recorded cancelled.
    stats = switch.protocol_stats()
    assert stats.requests.active == [], (
        f"no state for parent or child remains: {stats.requests.active}"
    )
    assert stats.requests.terminated_by_kind.get("cancelled") == 2

    # The destination master received Cancel for BOTH rids.
    assert collected.wait(timeout=5), "slave must observe both Cancel frames"
    assert len(cancels) == 2, "parent + cascaded child Cancel frames"
    assert parent_key[1] in cancels
    assert child_key[1] in cancels


# TEST7038: Master death terminates every request routed to it with kind
# master_died, delivering synthetic MASTER_DIED ERRs to waiting channels and
# leaving zero state.
def test_7038_master_death_terminates_pending_requests():
    switch = _build_switch_with_n_masters(1)

    key = (MessageId(5), MessageId.new_uuid())
    delivered = []
    switch._requests.register(key, _state(0, None, delivered.append))

    switch._handle_master_death(0)

    assert len(delivered) == 1, "synthetic ERR must be delivered"
    assert delivered[0].error_code() == "MASTER_DIED"

    stats = switch.protocol_stats()
    assert stats.requests.active == [], "zero state remains (L7)"
    assert stats.requests.terminated_by_kind.get("master_died") == 1
    summary = stats.requests.recent_terminated[-1]
    assert summary.rid == key[1].to_string()


# TEST7093: A response frame for a LIVE request whose external consumer is
# gone (dropped/timed-out caller callback) is a counted channel_closed drop
# AND cancels the request upstream — the destination receives Cancel, the
# entry terminates as cancelled, and the cartridge stops producing for a dead
# channel instead of running to completion against it.
def test_7093_dead_consumer_cancels_upstream():
    engine_read, slave_write = socket.socketpair()
    slave_read, engine_write = socket.socketpair()
    done = threading.Event()
    cancel_seen = threading.Event()
    cap = 'cap:in="media:void";test;out="media:void"'

    def slave_thread():
        reader = FrameReader(slave_read.makefile("rb"))
        writer = FrameWriter(slave_write.makefile("wb"))
        send_notify(writer, make_manifest(cap), Limits.default())
        done.set()
        complete_identity_verification(reader, writer)

        # Serve one REQ: read it, then stream a response frame. The
        # engine-side consumer will already be gone — the switch must
        # answer with Cancel on this connection.
        req = None
        while req is None:
            frame = reader.read()
            if frame is None:
                return
            if frame.frame_type == FrameType.REQ:
                req = frame
        log = Frame.log(req.id, "info", "first result row")
        log.routing_id = req.routing_id
        writer.write(log)

        # The switch must now cancel this request (dead consumer).
        while True:
            frame = reader.read()
            if frame is None:
                return
            if frame.frame_type == FrameType.CANCEL:
                assert frame.id == req.id, "cancel targets the abandoned request"
                cancel_seen.set()
                return

    threading.Thread(target=slave_thread, daemon=True).start()
    done.wait(timeout=2)

    switch = RelaySwitch([SocketPair(
        id="dead-consumer-master-0",
        read=engine_read.makefile("rb"),
        write=engine_write.makefile("wb"),
    )])

    def raising_channel(frame):
        # The caller abandoned this request (dropped/timed-out future) —
        # calling its callback raises, exactly like a closed mpsc sender.
        raise RuntimeError("receiver gone")

    with switch._lock:
        dest_idx = switch._find_master_for_cap(cap)
        assert dest_idx == 0
        xid = switch._next_xid_locked()
        rid = MessageId.new_uuid()
        switch._requests.register(
            (xid, rid),
            _state(dest_idx, None, raising_channel),
        )
        req = Frame.req(rid, cap, b"", "application/cbor")
        req.routing_id = xid
        switch._masters[dest_idx].socket_writer.write(req)

    switch.start_background_pump()

    # The slave streams a frame into the dead channel; the switch must count
    # the drop and cancel upstream (the slave task asserts Cancel).
    assert cancel_seen.wait(timeout=5), "slave must observe Cancel before timeout"

    # Wait for the cascade (dispatched on a background thread) to finish
    # terminating the request before asserting the final snapshot.
    deadline = time.monotonic() + 5
    stats = switch.protocol_stats()
    while stats.requests.active and time.monotonic() < deadline:
        time.sleep(0.02)
        stats = switch.protocol_stats()

    assert stats.drops.by_reason.get("channel_closed") == 1, (
        "the abandoned frame is a counted channel_closed drop"
    )
    assert stats.requests.terminated_by_kind.get("cancelled") == 1, (
        "the abandoned request terminates as cancelled — it never lingers"
    )
    assert stats.requests.active == [], "no state remains for the abandoned request (L7)"


# TEST7085: The RelayNotify capabilities payload carries the host's protocol
# stats snapshot, surviving the wire round-trip. (Adapted: this mirror has no
# typed RelayNotifyCapabilitiesPayload — it builds/parses the manifest dict
# directly via `_parse_relay_notify_payload`.)
def test_7085_relay_notify_carries_host_protocol_stats():
    counters = DropCounters()
    counters.record(DropReason.NO_ROUTE)
    counters.record(DropReason.NO_ROUTE)

    manifest = {
        "installed_cartridges": [],
        "host_protocol_stats": {
            "drops": counters.snapshot().to_dict(),
            "outgoing_rids": 3,
            "incoming_rxids": 5,
            "incoming_to_peer_rids": 1,
            "outgoing_max_seq": 4,
            "routing_gc_runs_total": 2,
            "routing_gc_evicted_total": 7,
        },
    }
    _, _, host_stats = _parse_relay_notify_payload(json.dumps(manifest).encode("utf-8"))
    assert host_stats is not None, "host stats must survive the round trip"
    assert host_stats.drops.total == 2
    assert host_stats.drops.by_reason.get("no_route") == 2
    assert host_stats.incoming_rxids == 5
    assert host_stats.routing_gc_evicted_total == 7

    # A payload WITHOUT stats (initial capability advertisement) still
    # parses — the field is a per-republish refresh, not a requirement.
    bare = {"installed_cartridges": []}
    _, _, bare_stats = _parse_relay_notify_payload(json.dumps(bare).encode("utf-8"))
    assert bare_stats is None


# TEST7091: Host protocol stats carried by a master's RelayNotify are
# RETAINED by the switch (not parsed-and-discarded) and surface in
# `protocol_stats().hosts` keyed by master id; a master that has not yet
# advertised stats is absent from the map — never a zeroed placeholder.
def test_7091_switch_retains_host_protocol_stats_from_relay_notify():
    engine_read, slave_write = socket.socketpair()
    slave_read, engine_write = socket.socketpair()
    done = threading.Event()
    # Gates the second (stats-carrying) RelayNotify until AFTER the
    # "absent before any advertisement" assertion below has run — real OS
    # threads (unlike the reference's cooperative-scheduling test) would
    # otherwise race the reader thread against that assertion.
    send_stats = threading.Event()

    def slave_thread():
        reader = FrameReader(slave_read.makefile("rb"))
        writer = FrameWriter(slave_write.makefile("wb"))
        send_notify(writer, make_manifest(CAP_GENERIC), Limits.default())
        done.set()
        complete_identity_verification(reader, writer)

        send_stats.wait(timeout=5)

        # Republish the SAME inventory (no cap change → no re-verify), now
        # carrying host protocol stats — the periodic refresh path.
        manifest = make_manifest(CAP_GENERIC)
        manifest["host_protocol_stats"] = {
            "drops": {"total": 3, "by_reason": {"post_terminal": 2, "no_route": 1}},
            "outgoing_rids": 4,
            "incoming_rxids": 6,
            "incoming_to_peer_rids": 0,
            "outgoing_max_seq": 2,
            "routing_gc_runs_total": 1,
            "routing_gc_evicted_total": 9,
        }
        send_notify(writer, manifest, Limits.default())
        # Keep the connection open until the assertion side finishes.
        while reader.read() is not None:
            pass

    threading.Thread(target=slave_thread, daemon=True).start()
    done.wait(timeout=2)

    switch = RelaySwitch([SocketPair(
        id="host-stats-master-0",
        read=engine_read.makefile("rb"),
        write=engine_write.makefile("wb"),
    )])

    # The initial advertisement carried no host stats: absent, not zeroed.
    assert switch.protocol_stats().hosts == {}, "no host stats before a RelayNotify carries them"

    switch.start_background_pump()
    send_stats.set()

    deadline = time.monotonic() + 5
    host_stats = None
    while time.monotonic() < deadline:
        stats = switch.protocol_stats()
        if "host-stats-master-0" in stats.hosts:
            host_stats = stats.hosts["host-stats-master-0"]
            break
        time.sleep(0.02)
    assert host_stats is not None, (
        "host stats must surface in protocol_stats().hosts after RelayNotify"
    )
    assert host_stats.drops.total == 3
    assert host_stats.drops.by_reason.get("post_terminal") == 2
    assert host_stats.incoming_rxids == 6
    assert host_stats.routing_gc_evicted_total == 9
