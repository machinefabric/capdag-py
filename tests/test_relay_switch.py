"""Tests for RelaySwitch — TEST426-TEST435"""

import itertools
import json
import socket
import threading
from io import BytesIO

import pytest

from capdag.bifaci.frame import Frame, FrameType, Limits, MessageId, compute_checksum
from capdag.bifaci.io import FrameReader, FrameWriter
from capdag.bifaci.relay_switch import (
    RelaySwitch,
    SocketPair,
    NoHandlerError,
    ProtocolError,
)

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
        {"urn": urn, "title": "test", "command": "test", "args": []}
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

        # Read one REQ and send response
        frame = reader.read()
        if frame and frame.frame_type == FrameType.REQ:
            response = Frame.end(frame.id, bytes([42]))
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


# TEST437: find_master_for_cap with preferred_cap routes to generic handler With is_dispatchable semantics: - Generic provider (in=media:) CAN dispatch specific request (in="media:ext=pdf") because media: (wildcard) accepts any input type - Preference routes to preferred among dispatchable candidates
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
        preferred_cap='cap:in=\"media:ext=pdf\";out=media:ext=pdf',
    ) == 0


# TEST439: Generic provider CAN dispatch specific request (but only matches if no more specific provider exists) With is_dispatchable: generic provider (in=media:) CAN handle specific request (in="media:ext=pdf") because media: accepts any input type. With preference, can route to generic even when more specific exists.
def test_439_generic_provider_can_dispatch_specific_request():
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
    # Input (contravariant): request's media:text;utf8;normalized conforms_to provider's media:text;utf8
    # Output (covariant): provider's media:text;utf8 conforms_to request's media:text
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


def test_0133_reattach_by_id_preserves_slot_index():
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


# TEST0134: Add master with duplicate healthy id errors
def test_0134_add_master_with_duplicate_healthy_id_errors():
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


# TEST0081: Relay switch init rejects duplicate ids
def test_0081_relay_switch_init_rejects_duplicate_ids():
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


# TEST0136: All masters ready false when expected count unset
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


# TEST0137: All masters ready false when partially connected
def test_0137_all_masters_ready_false_when_partially_connected():
    """1 master connected, 2 expected. This is the live regression: the
    internal master had caps from t=0 but the external-providers master
    was still spawning cartridges. The host saw ready immediately and the
    bidi never started. The predicate must return false until
    len(masters) reaches expected_master_count."""
    switch = _build_switch_with_n_masters(1)
    assert switch._masters[0].healthy is True

    switch.set_expected_master_count(2)
    assert switch.all_masters_ready() is False, (
        "all_masters_ready must return false until masters.len() reaches expected_master_count"
    )


# TEST0139: All masters ready true when masters connected but capless
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


# TEST0140: All masters ready does not overshoot
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
