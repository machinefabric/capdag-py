"""CBOR Integration Tests - Protocol validation tests ported from Go

These tests validate end-to-end protocol behavior including:
- Frame forwarding
- Thread spawning
- Bidirectional communication
- Handshake and limit negotiation
- Heartbeat handling

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
import socket
import threading
from capdag.bifaci.frame import (
    Frame,
    FrameType,
    MessageId,
    FlowKey,
    SeqAssigner,
    Limits,
    DEFAULT_MAX_FRAME,
    DEFAULT_MAX_CHUNK,
    compute_checksum,
)
from capdag.bifaci.io import (
    FrameReader,
    FrameWriter,
    handshake,
    handshake_accept,
)
from capdag.bifaci.host_runtime import CartridgeHost
from capdag.standard.caps import CAP_IDENTITY

# Test manifest JSON - cartridges MUST include manifest in HELLO response
TEST_MANIFEST = b'{"name":"TestCartridge","version":"1.0.0","channel":"release","description":"Test cartridge","cap_groups":[{"name":"default","caps":[{"urn":"cap:test","title":"Test","command":"test"}]}]}'
CAP_GENERIC = "cap:echo"


def create_socket_pair():
    """Create a Unix socket pair for bidirectional communication"""
    return socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)


def cartridge_handshake_worker(cartridge_read_sock, cartridge_write_sock, manifest):
    """Helper: do handshake on cartridge side in a thread"""
    reader = FrameReader(cartridge_read_sock.makefile("rb", buffering=0))
    writer = FrameWriter(cartridge_write_sock.makefile("wb", buffering=0))
    limits = handshake_accept(reader, writer, manifest)
    reader.set_limits(limits)
    writer.set_limits(limits)
    return reader, writer


# TEST284: Handshake exchanges HELLO frames, negotiates limits
def test_284_handshake_host_cartridge():
    """Test HELLO frame exchange and limit negotiation"""
    host_write_sock, cartridge_read_sock = create_socket_pair()
    cartridge_write_sock, host_read_sock = create_socket_pair()

    manifest_holder = []
    limits_holder = []

    def cartridge_thread():
        reader = FrameReader(cartridge_read_sock.makefile("rb", buffering=0))
        writer = FrameWriter(cartridge_write_sock.makefile("wb", buffering=0))
        limits = handshake_accept(reader, writer, TEST_MANIFEST)
        limits_holder.append(limits)
        assert limits.max_frame > 0
        assert limits.max_chunk > 0

    cartridge = threading.Thread(target=cartridge_thread, daemon=True)
    cartridge.start()

    reader = FrameReader(host_read_sock.makefile("rb", buffering=0))
    writer = FrameWriter(host_write_sock.makefile("wb", buffering=0))
    result = handshake(reader, writer)
    received_manifest = result.manifest
    host_limits = result.limits

    assert received_manifest == TEST_MANIFEST

    cartridge.join(timeout=5.0)

    cartridge_limits = limits_holder[0]
    assert host_limits.max_frame == cartridge_limits.max_frame
    assert host_limits.max_chunk == cartridge_limits.max_chunk


# TEST285: Simple request-response flow (REQ → END with payload)
def test_285_request_response_simple():
    """Test simple REQ → END with payload"""
    host_write_sock, cartridge_read_sock = create_socket_pair()
    cartridge_write_sock, host_read_sock = create_socket_pair()

    def cartridge_thread():
        reader = FrameReader(cartridge_read_sock.makefile("rb", buffering=0))
        writer = FrameWriter(cartridge_write_sock.makefile("wb", buffering=0))
        limits = handshake_accept(reader, writer, TEST_MANIFEST)
        reader.set_limits(limits)
        writer.set_limits(limits)

        frame = reader.read()
        assert frame is not None
        assert frame.frame_type == FrameType.REQ
        assert frame.cap == CAP_GENERIC
        assert frame.payload == b"hello"

        writer.write(Frame.end(frame.id, b"hello back"))

    cartridge = threading.Thread(target=cartridge_thread, daemon=True)
    cartridge.start()

    reader = FrameReader(host_read_sock.makefile("rb", buffering=0))
    writer = FrameWriter(host_write_sock.makefile("wb", buffering=0))
    result = handshake(reader, writer)
    # handshake already sets limits on reader/writer

    request_id = MessageId.new_uuid()
    writer.write(Frame.req(request_id, CAP_GENERIC, b"hello", "application/json"))

    response = reader.read()
    assert response is not None
    assert response.frame_type == FrameType.END
    assert response.payload == b"hello back"

    cartridge.join(timeout=5.0)


# TEST286: Streaming response with multiple CHUNK frames
def test_286_streaming_chunks():
    """Test streaming response with multiple CHUNK frames"""
    host_write_sock, cartridge_read_sock = create_socket_pair()
    cartridge_write_sock, host_read_sock = create_socket_pair()

    def cartridge_thread():
        reader = FrameReader(cartridge_read_sock.makefile("rb", buffering=0))
        writer = FrameWriter(cartridge_write_sock.makefile("wb", buffering=0))
        limits = handshake_accept(reader, writer, TEST_MANIFEST)
        reader.set_limits(limits)
        writer.set_limits(limits)

        frame = reader.read()
        request_id = frame.id

        sid = "response"
        writer.write(Frame.stream_start(request_id, sid, "media:"))
        for seq, data in enumerate([b"chunk1", b"chunk2", b"chunk3"]):
            writer.write(Frame.chunk(request_id, sid, seq, data, seq, compute_checksum(data)))
        writer.write(Frame.stream_end(request_id, sid, 3))
        writer.write(Frame.end(request_id, None))

    cartridge = threading.Thread(target=cartridge_thread, daemon=True)
    cartridge.start()

    reader = FrameReader(host_read_sock.makefile("rb", buffering=0))
    writer = FrameWriter(host_write_sock.makefile("wb", buffering=0))
    result = handshake(reader, writer)
    # handshake already sets limits on reader/writer

    request_id = MessageId.new_uuid()
    writer.write(Frame.req(request_id, "cap:stream", b"go", "application/json"))

    # Collect chunks
    chunks = []
    while True:
        frame = reader.read()
        assert frame is not None
        if frame.frame_type == FrameType.CHUNK:
            chunks.append(frame.payload or b"")
        if frame.frame_type == FrameType.END:
            break

    assert len(chunks) == 3
    assert chunks[0] == b"chunk1"
    assert chunks[1] == b"chunk2"
    assert chunks[2] == b"chunk3"

    cartridge.join(timeout=5.0)


# TEST287: Host-initiated heartbeat
def test_287_heartbeat_from_host():
    """Test host-initiated heartbeat"""
    host_write_sock, cartridge_read_sock = create_socket_pair()
    cartridge_write_sock, host_read_sock = create_socket_pair()

    def cartridge_thread():
        reader = FrameReader(cartridge_read_sock.makefile("rb", buffering=0))
        writer = FrameWriter(cartridge_write_sock.makefile("wb", buffering=0))
        limits = handshake_accept(reader, writer, TEST_MANIFEST)
        reader.set_limits(limits)
        writer.set_limits(limits)

        frame = reader.read()
        assert frame is not None
        assert frame.frame_type == FrameType.HEARTBEAT

        writer.write(Frame.heartbeat(frame.id))

    cartridge = threading.Thread(target=cartridge_thread, daemon=True)
    cartridge.start()

    reader = FrameReader(host_read_sock.makefile("rb", buffering=0))
    writer = FrameWriter(host_write_sock.makefile("wb", buffering=0))
    result = handshake(reader, writer)
    # handshake already sets limits on reader/writer

    heartbeat_id = MessageId.new_uuid()
    writer.write(Frame.heartbeat(heartbeat_id))

    response = reader.read()
    assert response is not None
    assert response.frame_type == FrameType.HEARTBEAT
    assert response.id == heartbeat_id

    cartridge.join(timeout=5.0)


# TEST290: Limit negotiation picks minimum
def test_290_limits_negotiation():
    """Test limit negotiation picks minimum of both sides"""
    host_write_sock, cartridge_read_sock = create_socket_pair()
    cartridge_write_sock, host_read_sock = create_socket_pair()

    limits_holder = []

    def cartridge_thread():
        reader = FrameReader(cartridge_read_sock.makefile("rb", buffering=0))
        writer = FrameWriter(cartridge_write_sock.makefile("wb", buffering=0))
        limits = handshake_accept(reader, writer, TEST_MANIFEST)
        limits_holder.append(limits)

    cartridge = threading.Thread(target=cartridge_thread, daemon=True)
    cartridge.start()

    reader = FrameReader(host_read_sock.makefile("rb", buffering=0))
    writer = FrameWriter(host_write_sock.makefile("wb", buffering=0))
    result = handshake(reader, writer)
    host_limits = result.limits

    cartridge.join(timeout=5.0)

    cartridge_limits = limits_holder[0]

    assert host_limits.max_frame == cartridge_limits.max_frame
    assert host_limits.max_chunk == cartridge_limits.max_chunk
    assert host_limits.max_frame > 0
    assert host_limits.max_chunk > 0


# TEST291: Binary payload roundtrip (all 256 byte values)
def test_291_binary_payload_roundtrip():
    """Test binary data integrity through all 256 byte values"""
    host_write_sock, cartridge_read_sock = create_socket_pair()
    cartridge_write_sock, host_read_sock = create_socket_pair()

    binary_data = bytes(range(256))

    def cartridge_thread():
        reader = FrameReader(cartridge_read_sock.makefile("rb", buffering=0))
        writer = FrameWriter(cartridge_write_sock.makefile("wb", buffering=0))
        limits = handshake_accept(reader, writer, TEST_MANIFEST)
        reader.set_limits(limits)
        writer.set_limits(limits)

        frame = reader.read()
        payload = frame.payload

        assert len(payload) == 256
        for i, byte in enumerate(payload):
            assert byte == i, f"Byte mismatch at position {i}"

        writer.write(Frame.end(frame.id, payload))

    cartridge = threading.Thread(target=cartridge_thread, daemon=True)
    cartridge.start()

    reader = FrameReader(host_read_sock.makefile("rb", buffering=0))
    writer = FrameWriter(host_write_sock.makefile("wb", buffering=0))
    result = handshake(reader, writer)
    # handshake already sets limits on reader/writer

    request_id = MessageId.new_uuid()
    writer.write(Frame.req(request_id, "cap:binary", binary_data, "application/octet-stream"))

    response = reader.read()
    result = response.payload

    assert len(result) == 256
    for i, byte in enumerate(result):
        assert byte == i, f"Response byte mismatch at position {i}"

    cartridge.join(timeout=5.0)


# TEST292: Sequential requests get distinct MessageIds
def test_292_message_id_uniqueness():
    """Test sequential requests produce unique MessageIds"""
    host_write_sock, cartridge_read_sock = create_socket_pair()
    cartridge_write_sock, host_read_sock = create_socket_pair()

    received_ids = []

    def cartridge_thread():
        reader = FrameReader(cartridge_read_sock.makefile("rb", buffering=0))
        writer = FrameWriter(cartridge_write_sock.makefile("wb", buffering=0))
        limits = handshake_accept(reader, writer, TEST_MANIFEST)
        reader.set_limits(limits)
        writer.set_limits(limits)

        for _ in range(3):
            frame = reader.read()
            received_ids.append(frame.id)
            writer.write(Frame.end(frame.id, b"ok"))

    cartridge = threading.Thread(target=cartridge_thread, daemon=True)
    cartridge.start()

    reader = FrameReader(host_read_sock.makefile("rb", buffering=0))
    writer = FrameWriter(host_write_sock.makefile("wb", buffering=0))
    result = handshake(reader, writer)
    # handshake already sets limits on reader/writer

    for _ in range(3):
        request_id = MessageId.new_uuid()
        writer.write(Frame.req(request_id, "cap:test", b"", "application/json"))
        reader.read()

    cartridge.join(timeout=5.0)

    assert len(received_ids) == 3
    for i in range(len(received_ids)):
        for j in range(i + 1, len(received_ids)):
            assert received_ids[i] != received_ids[j], "IDs should be unique"


# TEST299: Empty payload request/response roundtrip
def test_299_empty_payload_roundtrip():
    """Test empty payload roundtrip"""
    host_write_sock, cartridge_read_sock = create_socket_pair()
    cartridge_write_sock, host_read_sock = create_socket_pair()

    def cartridge_thread():
        reader = FrameReader(cartridge_read_sock.makefile("rb", buffering=0))
        writer = FrameWriter(cartridge_write_sock.makefile("wb", buffering=0))
        limits = handshake_accept(reader, writer, TEST_MANIFEST)
        reader.set_limits(limits)
        writer.set_limits(limits)

        frame = reader.read()
        assert frame.payload is None or frame.payload == b"", "empty payload must arrive empty"

        writer.write(Frame.end(frame.id, b""))

    cartridge = threading.Thread(target=cartridge_thread, daemon=True)
    cartridge.start()

    reader = FrameReader(host_read_sock.makefile("rb", buffering=0))
    writer = FrameWriter(host_write_sock.makefile("wb", buffering=0))
    result = handshake(reader, writer)
    # handshake already sets limits on reader/writer

    request_id = MessageId.new_uuid()
    writer.write(Frame.req(request_id, "cap:empty", b"", "application/json"))

    response = reader.read()
    assert response.payload is None or response.payload == b""

    cartridge.join(timeout=5.0)


# =============================================================================
# Full relay-path integration tests (engine → relay → host → cartridge → back)
# Ported from Rust src/bifaci/integration_tests.rs. The CartridgeHost is the
# Python mirror of Rust's CartridgeHostRuntime.
# =============================================================================


def _stream_pair():
    """Create a unidirectional byte stream returning (read_file, write_file).

    Backed by a Unix socket pair; the write end is the second socket so a
    reader on the first end sees what is written to the second.
    """
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    read_file = a.makefile("rb", buffering=0)
    write_file = b.makefile("wb", buffering=0)
    return read_file, write_file, a, b


def create_cartridge_pair():
    """Mirror Rust create_cartridge_pair: returns (c_read, c_write, c_from_rt, c_to_rt).

    - c_read:    host reads cartridge stdout
    - c_write:   host writes cartridge stdin
    - c_from_rt: cartridge reads from runtime (host's writes)
    - c_to_rt:   cartridge writes to runtime (host reads)
    """
    # cartridge -> runtime channel
    c_read, c_to_rt, _s0, _s1 = _stream_pair()
    # runtime -> cartridge channel
    c_from_rt, c_write, _s2, _s3 = _stream_pair()
    # keep socket refs alive on the returned files to prevent GC closing them
    c_read._keep = (_s0, _s1, _s2, _s3)
    return c_read, c_write, c_from_rt, c_to_rt


def create_relay_pair():
    """Mirror Rust create_relay_pair: returns (rt_relay_read, rt_relay_write, eng_write, eng_read).

    - rt_relay_read:  host reads from relay (engine's writes)
    - rt_relay_write: host writes to relay (engine reads)
    - eng_write:      engine writes to relay
    - eng_read:       engine reads from relay
    """
    rt_relay_read, eng_write, _s0, _s1 = _stream_pair()
    eng_read, rt_relay_write, _s2, _s3 = _stream_pair()
    rt_relay_read._keep = (_s0, _s1, _s2, _s3)
    return rt_relay_read, rt_relay_write, eng_write, eng_read


def cartridge_handshake_with_identity(c_from_rt, c_to_rt, manifest):
    """Do HELLO handshake on the cartridge side, then satisfy the host's
    CAP_IDENTITY verification round-trip by echoing the nonce chunks back.

    Mirrors Rust's cartridge_handshake_with_identity. Returns
    (reader, writer) positioned after identity verification.
    """
    reader = FrameReader(c_from_rt)
    writer = FrameWriter(c_to_rt)
    limits = handshake_accept(reader, writer, manifest)
    reader.set_limits(limits)
    writer.set_limits(limits)

    # Handle identity verification REQ
    req = reader.read()
    assert req is not None, "expected identity REQ after handshake"
    assert req.frame_type == FrameType.REQ, "first frame after handshake must be identity REQ"

    payload = bytearray()
    while True:
        f = reader.read()
        assert f is not None, "expected frame during identity verification"
        if f.frame_type == FrameType.STREAM_START:
            continue
        elif f.frame_type == FrameType.CHUNK:
            payload.extend(f.payload or b"")
        elif f.frame_type == FrameType.STREAM_END:
            continue
        elif f.frame_type == FrameType.END:
            break
        else:
            raise AssertionError(
                f"unexpected frame type during identity verification: {f.frame_type}"
            )

    # Echo the (CBOR-wrapped) nonce back verbatim, exactly as the host sent it.
    stream_id = "identity-echo"
    ss = Frame.stream_start(req.id, stream_id, "media:")
    writer.write(ss)
    checksum = compute_checksum(bytes(payload))
    chunk = Frame.chunk(req.id, stream_id, 0, bytes(payload), 0, checksum)
    writer.write(chunk)
    se = Frame.stream_end(req.id, stream_id, 1)
    writer.write(se)
    end = Frame.end(req.id, None)
    writer.write(end)

    return reader, writer


def _read_until_end_collect_chunks(reader):
    """Read frames until END, returning concatenated CHUNK payloads."""
    payload = bytearray()
    while True:
        f = reader.read()
        if f is None:
            break
        if f.frame_type == FrameType.CHUNK:
            payload.extend(f.payload or b"")
        if f.frame_type == FrameType.END:
            break
    return bytes(payload)


# TEST1122: Full path: engine REQ → runtime → cartridge → response back through relay
def test_1122_full_path_engine_req_to_cartridge_response():
    manifest = (
        b'{"name":"EchoCartridge","version":"1.0","channel":"release","registry_url":null,'
        b'"description":"Echo test cartridge","cap_groups":[{"name":"default","caps":'
        b'[{"urn":"cap:effect=none","title":"Test","command":"test","args":[]}]}]}'
    )

    c_read, c_write, c_from_rt, c_to_rt = create_cartridge_pair()
    rt_relay_read, rt_relay_write, eng_write, eng_read = create_relay_pair()

    def cartridge_thread():
        reader, writer = cartridge_handshake_with_identity(c_from_rt, c_to_rt, manifest)

        req = reader.read()
        assert req is not None, "Expected REQ"
        assert req.frame_type == FrameType.REQ
        assert req.cap == CAP_IDENTITY

        arg_data = bytearray()
        while True:
            f = reader.read()
            assert f is not None, "Expected frame"
            if f.frame_type == FrameType.CHUNK:
                arg_data.extend(f.payload or b"")
            elif f.frame_type == FrameType.END:
                break

        seq = SeqAssigner()
        sid = "resp"
        start = Frame.stream_start(req.id, sid, "media:")
        seq.assign(start)
        writer.write(start)
        checksum = compute_checksum(bytes(arg_data))
        chunk = Frame.chunk(req.id, sid, 0, bytes(arg_data), 0, checksum)
        seq.assign(chunk)
        writer.write(chunk)
        stream_end = Frame.stream_end(req.id, sid, 1)
        seq.assign(stream_end)
        writer.write(stream_end)
        end = Frame.end(req.id, None)
        seq.assign(end)
        writer.write(end)
        seq.remove(FlowKey.from_frame(end))

    cart = threading.Thread(target=cartridge_thread, daemon=True)
    cart.start()

    host = CartridgeHost()
    host.attach_cartridge(c_read, c_write)

    req_id = MessageId.new_uuid()
    response_holder = []

    def engine_thread():
        w = FrameWriter(eng_write)
        r = FrameReader(eng_read)

        seq = SeqAssigner()
        sid = MessageId.new_uuid().to_string()
        xid = MessageId(1)
        req_frame = Frame.req(req_id, CAP_IDENTITY, b"", "text/plain")
        req_frame.routing_id = xid
        seq.assign(req_frame)
        w.write(req_frame)
        stream_start = Frame.stream_start(req_id, sid, "media:")
        stream_start.routing_id = xid
        seq.assign(stream_start)
        w.write(stream_start)
        payload = b"hello world"
        checksum = compute_checksum(payload)
        chunk = Frame.chunk(req_id, sid, 0, payload, 0, checksum)
        chunk.routing_id = xid
        seq.assign(chunk)
        w.write(chunk)
        stream_end = Frame.stream_end(req_id, sid, 1)
        stream_end.routing_id = xid
        seq.assign(stream_end)
        w.write(stream_end)
        end = Frame.end(req_id, None)
        end.routing_id = xid
        seq.assign(end)
        w.write(end)
        seq.remove(FlowKey.from_frame(end))

        response_holder.append(_read_until_end_collect_chunks(r))

    eng = threading.Thread(target=engine_thread, daemon=True)
    eng.start()

    host_thread = threading.Thread(
        target=lambda: host.run(rt_relay_read, rt_relay_write, lambda: b""),
        daemon=True,
    )
    host_thread.start()

    eng.join(timeout=10.0)
    assert response_holder, "engine did not produce a response"
    assert response_holder[0] == b"hello world", "Cartridge should echo back the argument data"

    cart.join(timeout=5.0)


# TEST1123: Cartridge ERR frame flows back to engine through relay
def test_1123_cartridge_error_flows_to_engine():
    fail_cap = 'cap:in="media:void";fail;out="media:void"'
    manifest = (
        b'{"name":"ErrCartridge","version":"1.0","channel":"release","registry_url":null,'
        b'"description":"Error test cartridge","cap_groups":[{"name":"default","caps":'
        b'[{"urn":"cap:effect=none","title":"Identity","command":"identity","args":[]},'
        b'{"urn":"cap:in=\\"media:void\\";fail;out=\\"media:void\\"","title":"Test","command":"test","args":[]}]}]}'
    )

    c_read, c_write, c_from_rt, c_to_rt = create_cartridge_pair()
    rt_relay_read, rt_relay_write, eng_write, eng_read = create_relay_pair()

    def cartridge_thread():
        reader, writer = cartridge_handshake_with_identity(c_from_rt, c_to_rt, manifest)
        req = reader.read()
        assert req is not None, "Expected REQ"
        seq = SeqAssigner()
        err = Frame.err(req.id, "FAIL_CODE", "Something went wrong")
        seq.assign(err)
        writer.write(err)
        seq.remove(FlowKey.from_frame(err))

    cart = threading.Thread(target=cartridge_thread, daemon=True)
    cart.start()

    host = CartridgeHost()
    host.attach_cartridge(c_read, c_write)

    req_id = MessageId.new_uuid()
    result_holder = []

    def engine_thread():
        w = FrameWriter(eng_write)
        r = FrameReader(eng_read)

        seq = SeqAssigner()
        xid = MessageId(1)
        req = Frame.req(req_id, fail_cap, b"", "text/plain")
        req.routing_id = xid
        seq.assign(req)
        w.write(req)
        end = Frame.end(req_id, None)
        end.routing_id = xid
        seq.assign(end)
        w.write(end)
        seq.remove(FlowKey.from_frame(end))

        err_code = ""
        err_msg = ""
        while True:
            f = r.read()
            if f is None:
                break
            if f.frame_type == FrameType.ERR:
                err_code = f.error_code() or ""
                err_msg = f.error_message() or ""
                break
        result_holder.append((err_code, err_msg))

    eng = threading.Thread(target=engine_thread, daemon=True)
    eng.start()

    host_thread = threading.Thread(
        target=lambda: host.run(rt_relay_read, rt_relay_write, lambda: b""),
        daemon=True,
    )
    host_thread.start()

    eng.join(timeout=10.0)
    assert result_holder, "engine did not receive an ERR frame"
    code, msg = result_holder[0]
    assert code == "FAIL_CODE"
    assert msg == "Something went wrong"

    cart.join(timeout=5.0)


# TEST898: Binary data integrity through full relay path (256 byte values)
def test_898_binary_integrity_through_relay():
    bin_cap = 'cap:in="media:void";binary;out="media:void"'
    manifest = (
        b'{"name":"BinCartridge","version":"1.0","channel":"release","registry_url":null,'
        b'"description":"Binary test cartridge","cap_groups":[{"name":"default","caps":'
        b'[{"urn":"cap:effect=none","title":"Identity","command":"identity","args":[]},'
        b'{"urn":"cap:in=\\"media:void\\";binary;out=\\"media:void\\"","title":"Test","command":"test","args":[]}]}]}'
    )

    c_read, c_write, c_from_rt, c_to_rt = create_cartridge_pair()
    rt_relay_read, rt_relay_write, eng_write, eng_read = create_relay_pair()

    binary_data = bytes(range(256))

    def cartridge_thread():
        reader, writer = cartridge_handshake_with_identity(c_from_rt, c_to_rt, manifest)

        req = reader.read()
        assert req is not None, "Expected REQ"

        received = bytearray()
        while True:
            f = reader.read()
            assert f is not None, "frame"
            if f.frame_type == FrameType.CHUNK:
                received.extend(f.payload or b"")
            elif f.frame_type == FrameType.END:
                break

        assert len(received) == 256, "Must receive all 256 bytes"
        for i, b in enumerate(received):
            assert b == i, f"Byte mismatch at position {i}"

        seq = SeqAssigner()
        sid = "resp"
        start = Frame.stream_start(req.id, sid, "media:")
        seq.assign(start)
        writer.write(start)
        checksum = compute_checksum(bytes(received))
        chunk = Frame.chunk(req.id, sid, 0, bytes(received), 0, checksum)
        seq.assign(chunk)
        writer.write(chunk)
        stream_end = Frame.stream_end(req.id, sid, 1)
        seq.assign(stream_end)
        writer.write(stream_end)
        end = Frame.end(req.id, None)
        seq.assign(end)
        writer.write(end)
        seq.remove(FlowKey.from_frame(end))

    cart = threading.Thread(target=cartridge_thread, daemon=True)
    cart.start()

    host = CartridgeHost()
    host.attach_cartridge(c_read, c_write)

    req_id = MessageId.new_uuid()
    response_holder = []

    def engine_thread():
        w = FrameWriter(eng_write)
        r = FrameReader(eng_read)

        seq = SeqAssigner()
        xid = MessageId(1)
        sid = MessageId.new_uuid().to_string()
        req = Frame.req(req_id, bin_cap, b"", "application/octet-stream")
        req.routing_id = xid
        seq.assign(req)
        w.write(req)
        stream_start = Frame.stream_start(req_id, sid, "media:")
        stream_start.routing_id = xid
        seq.assign(stream_start)
        w.write(stream_start)
        checksum = compute_checksum(binary_data)
        chunk = Frame.chunk(req_id, sid, 0, binary_data, 0, checksum)
        chunk.routing_id = xid
        seq.assign(chunk)
        w.write(chunk)
        stream_end = Frame.stream_end(req_id, sid, 1)
        stream_end.routing_id = xid
        seq.assign(stream_end)
        w.write(stream_end)
        end = Frame.end(req_id, None)
        end.routing_id = xid
        seq.assign(end)
        w.write(end)
        seq.remove(FlowKey.from_frame(end))

        response_holder.append(_read_until_end_collect_chunks(r))

    eng = threading.Thread(target=engine_thread, daemon=True)
    eng.start()

    host_thread = threading.Thread(
        target=lambda: host.run(rt_relay_read, rt_relay_write, lambda: b""),
        daemon=True,
    )
    host_thread.start()

    eng.join(timeout=10.0)
    assert response_holder, "engine did not produce a response"
    response = response_holder[0]
    assert len(response) == 256
    for i, b in enumerate(response):
        assert b == i, f"Response byte mismatch at position {i}"

    cart.join(timeout=5.0)


# TEST899: Streaming chunks flow through relay without accumulation
def test_899_streaming_chunks_through_relay():
    stream_cap = 'cap:in="media:void";stream;out="media:void"'
    manifest = (
        b'{"name":"StreamCartridge","version":"1.0","channel":"release","registry_url":null,'
        b'"description":"Streaming test cartridge","cap_groups":[{"name":"default","caps":'
        b'[{"urn":"cap:effect=none","title":"Identity","command":"identity","args":[]},'
        b'{"urn":"cap:in=\\"media:void\\";stream;out=\\"media:void\\"","title":"Test","command":"test","args":[]}]}]}'
    )

    c_read, c_write, c_from_rt, c_to_rt = create_cartridge_pair()
    rt_relay_read, rt_relay_write, eng_write, eng_read = create_relay_pair()

    def cartridge_thread():
        reader, writer = cartridge_handshake_with_identity(c_from_rt, c_to_rt, manifest)

        req = reader.read()
        assert req is not None, "Expected REQ"

        while True:
            f = reader.read()
            assert f is not None, "frame"
            if f.frame_type == FrameType.END:
                break

        sid = "resp"
        seq = SeqAssigner()
        start = Frame.stream_start(req.id, sid, "media:")
        seq.assign(start)
        writer.write(start)
        for idx in range(5):
            data = f"chunk{idx}".encode()
            checksum = compute_checksum(data)
            chunk = Frame.chunk(req.id, sid, 0, data, idx, checksum)
            seq.assign(chunk)
            writer.write(chunk)
        stream_end = Frame.stream_end(req.id, sid, 5)
        seq.assign(stream_end)
        writer.write(stream_end)
        end = Frame.end(req.id, None)
        seq.assign(end)
        writer.write(end)

    cart = threading.Thread(target=cartridge_thread, daemon=True)
    cart.start()

    host = CartridgeHost()
    host.attach_cartridge(c_read, c_write)

    req_id = MessageId.new_uuid()
    chunks_holder = []

    def engine_thread():
        w = FrameWriter(eng_write)
        r = FrameReader(eng_read)

        seq = SeqAssigner()
        xid = MessageId(1)
        req = Frame.req(req_id, stream_cap, b"", "text/plain")
        req.routing_id = xid
        seq.assign(req)
        w.write(req)
        end = Frame.end(req_id, None)
        end.routing_id = xid
        seq.assign(end)
        w.write(end)
        seq.remove(FlowKey.from_frame(end))

        chunks = []
        while True:
            f = r.read()
            if f is None:
                break
            if f.frame_type == FrameType.CHUNK:
                chunks.append((f.seq, f.payload or b""))
            if f.frame_type == FrameType.END:
                break
        chunks_holder.append(chunks)

    eng = threading.Thread(target=engine_thread, daemon=True)
    eng.start()

    host_thread = threading.Thread(
        target=lambda: host.run(rt_relay_read, rt_relay_write, lambda: b""),
        daemon=True,
    )
    host_thread.start()

    eng.join(timeout=10.0)
    assert chunks_holder, "engine did not produce chunks"
    chunks = chunks_holder[0]
    assert len(chunks) == 5, "All 5 chunks must arrive"
    for i, (seq_val, data) in enumerate(chunks):
        assert seq_val == i + 1, "Chunk seq must be contiguous from 1 (StreamStart takes seq 0)"
        assert data == f"chunk{i}".encode(), "Chunk data must match"

    cart.join(timeout=5.0)


# TEST900: Two cartridges routed independently by cap_urn
def test_900_two_cartridges_routed_independently():
    alpha_cap = 'cap:in="media:void";alpha;out="media:void"'
    beta_cap = 'cap:in="media:void";beta;out="media:void"'
    manifest_a = (
        b'{"name":"CartridgeA","version":"1.0","channel":"release","registry_url":null,'
        b'"description":"Cartridge A","cap_groups":[{"name":"default","caps":'
        b'[{"urn":"cap:effect=none","title":"Identity","command":"identity","args":[]},'
        b'{"urn":"cap:in=\\"media:void\\";alpha;out=\\"media:void\\"","title":"Test","command":"test","args":[]}]}]}'
    )
    manifest_b = (
        b'{"name":"CartridgeB","version":"1.0","channel":"release","registry_url":null,'
        b'"description":"Cartridge B","cap_groups":[{"name":"default","caps":'
        b'[{"urn":"cap:effect=none","title":"Identity","command":"identity","args":[]},'
        b'{"urn":"cap:in=\\"media:void\\";beta;out=\\"media:void\\"","title":"Test","command":"test","args":[]}]}]}'
    )

    ca_read, ca_write, ca_from_rt, ca_to_rt = create_cartridge_pair()
    cb_read, cb_write, cb_from_rt, cb_to_rt = create_cartridge_pair()
    rt_relay_read, rt_relay_write, eng_write, eng_read = create_relay_pair()

    def cartridge_a_thread():
        reader, writer = cartridge_handshake_with_identity(ca_from_rt, ca_to_rt, manifest_a)
        req = reader.read()
        assert req is not None, "Expected REQ"
        assert req.cap == alpha_cap, "Cartridge A must receive alpha REQ"
        while True:
            f = reader.read()
            assert f is not None, "f"
            if f.frame_type == FrameType.END:
                break
        seq = SeqAssigner()
        sid = "a"
        start = Frame.stream_start(req.id, sid, "media:")
        seq.assign(start)
        writer.write(start)
        payload = b"from-alpha"
        checksum = compute_checksum(payload)
        chunk = Frame.chunk(req.id, sid, 0, payload, 0, checksum)
        seq.assign(chunk)
        writer.write(chunk)
        stream_end = Frame.stream_end(req.id, sid, 1)
        seq.assign(stream_end)
        writer.write(stream_end)
        end = Frame.end(req.id, None)
        seq.assign(end)
        writer.write(end)
        seq.remove(FlowKey.from_frame(end))

    def cartridge_b_thread():
        reader, writer = cartridge_handshake_with_identity(cb_from_rt, cb_to_rt, manifest_b)
        req = reader.read()
        assert req is not None, "Expected REQ"
        assert req.cap == beta_cap, "Cartridge B must receive beta REQ"
        while True:
            f = reader.read()
            assert f is not None, "f"
            if f.frame_type == FrameType.END:
                break
        seq = SeqAssigner()
        sid = "b"
        start = Frame.stream_start(req.id, sid, "media:")
        seq.assign(start)
        writer.write(start)
        payload = b"from-beta"
        checksum = compute_checksum(payload)
        chunk = Frame.chunk(req.id, sid, 0, payload, 0, checksum)
        seq.assign(chunk)
        writer.write(chunk)
        stream_end = Frame.stream_end(req.id, sid, 1)
        seq.assign(stream_end)
        writer.write(stream_end)
        end = Frame.end(req.id, None)
        seq.assign(end)
        writer.write(end)
        seq.remove(FlowKey.from_frame(end))

    cart_a = threading.Thread(target=cartridge_a_thread, daemon=True)
    cart_b = threading.Thread(target=cartridge_b_thread, daemon=True)
    cart_a.start()
    cart_b.start()

    host = CartridgeHost()
    host.attach_cartridge(ca_read, ca_write)
    host.attach_cartridge(cb_read, cb_write)

    alpha_id = MessageId.new_uuid()
    beta_id = MessageId.new_uuid()
    result_holder = []

    def engine_thread():
        w = FrameWriter(eng_write)
        r = FrameReader(eng_read)

        seq = SeqAssigner()
        xid_alpha = MessageId(1)
        xid_beta = MessageId(2)
        req_alpha = Frame.req(alpha_id, alpha_cap, b"", "text/plain")
        req_alpha.routing_id = xid_alpha
        seq.assign(req_alpha)
        w.write(req_alpha)
        end_alpha = Frame.end(alpha_id, None)
        end_alpha.routing_id = xid_alpha
        seq.assign(end_alpha)
        w.write(end_alpha)
        seq.remove(FlowKey.from_frame(end_alpha))
        req_beta = Frame.req(beta_id, beta_cap, b"", "text/plain")
        req_beta.routing_id = xid_beta
        seq.assign(req_beta)
        w.write(req_beta)
        end_beta = Frame.end(beta_id, None)
        end_beta.routing_id = xid_beta
        seq.assign(end_beta)
        w.write(end_beta)
        seq.remove(FlowKey.from_frame(end_beta))

        alpha_data = bytearray()
        beta_data = bytearray()
        ends_received = 0
        while True:
            f = r.read()
            if f is None:
                break
            if f.frame_type == FrameType.CHUNK:
                if f.id == alpha_id:
                    alpha_data.extend(f.payload or b"")
                elif f.id == beta_id:
                    beta_data.extend(f.payload or b"")
            if f.frame_type == FrameType.END:
                ends_received += 1
                if ends_received >= 2:
                    break
        result_holder.append((bytes(alpha_data), bytes(beta_data)))

    eng = threading.Thread(target=engine_thread, daemon=True)
    eng.start()

    host_thread = threading.Thread(
        target=lambda: host.run(rt_relay_read, rt_relay_write, lambda: b""),
        daemon=True,
    )
    host_thread.start()

    eng.join(timeout=10.0)
    assert result_holder, "engine did not produce responses"
    alpha_data, beta_data = result_holder[0]
    assert alpha_data == b"from-alpha", "Alpha response must come from Cartridge A"
    assert beta_data == b"from-beta", "Beta response must come from Cartridge B"

    cart_a.join(timeout=5.0)
    cart_b.join(timeout=5.0)


# TEST901: REQ for unknown cap returns ERR frame (not fatal)
def test_901_req_for_unknown_cap_returns_err_frame():
    known_cap = 'cap:in="media:void";known;out="media:void"'
    unknown_cap = 'cap:in="media:void";unknown;out="media:void"'
    manifest = (
        b'{"name":"OneCartridge","version":"1.0","channel":"release","registry_url":null,'
        b'"description":"Known cap cartridge","cap_groups":[{"name":"default","caps":'
        b'[{"urn":"cap:effect=none","title":"Identity","command":"identity","args":[]},'
        b'{"urn":"cap:in=\\"media:void\\";known;out=\\"media:void\\"","title":"Test","command":"test","args":[]}]}]}'
    )

    c_read, c_write, c_from_rt, c_to_rt = create_cartridge_pair()
    rt_relay_read, rt_relay_write, eng_write, eng_read = create_relay_pair()

    cartridge_error = []

    def cartridge_thread():
        reader, _writer = cartridge_handshake_with_identity(c_from_rt, c_to_rt, manifest)
        # Cartridge waits for EOF — no REQ should arrive since cap is unknown
        try:
            f = reader.read()
            if f is not None:
                cartridge_error.append(
                    f"Cartridge should not receive frames for unknown cap, got {f.frame_type}"
                )
        except Exception:
            pass  # treated as EOF

    cart = threading.Thread(target=cartridge_thread, daemon=True)
    cart.start()

    host = CartridgeHost()
    host.attach_cartridge(c_read, c_write)

    req_id = MessageId.new_uuid()

    def engine_send():
        w = FrameWriter(eng_write)
        seq = SeqAssigner()
        xid = MessageId(1)
        req = Frame.req(req_id, unknown_cap, b"", "text/plain")
        req.routing_id = xid
        seq.assign(req)
        w.write(req)
        end = Frame.end(req_id, None)
        end.routing_id = xid
        seq.assign(end)
        w.write(end)
        seq.remove(FlowKey.from_frame(end))

    recv_holder = []

    def engine_recv():
        r = FrameReader(eng_read)
        # Skip RelayNotify (initial capabilities notification)
        frame = r.read()
        assert frame is not None, "Expected first frame"
        if frame.frame_type == FrameType.RELAY_NOTIFY:
            frame = r.read()
            assert frame is not None, "Expected ERR frame after RelayNotify"
        assert frame.frame_type == FrameType.ERR, "Should get ERR for unknown cap"
        assert frame.id == req_id, "ERR should reference the original request ID"
        code = frame.error_code() or ""
        assert code == "NO_HANDLER", f"Error code should be NO_HANDLER, got: {code}"
        recv_holder.append(True)

    host_thread = threading.Thread(
        target=lambda: host.run(rt_relay_read, rt_relay_write, lambda: b""),
        daemon=True,
    )
    host_thread.start()

    send_t = threading.Thread(target=engine_send, daemon=True)
    recv_t = threading.Thread(target=engine_recv, daemon=True)
    recv_t.start()
    send_t.start()

    send_t.join(timeout=10.0)
    recv_t.join(timeout=10.0)

    assert not cartridge_error, cartridge_error[0] if cartridge_error else ""
    assert recv_holder, "engine_recv did not complete its assertions"
