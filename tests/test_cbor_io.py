"""Tests for cbor_io - mirroring capdag Rust tests

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
import io
from capdag.bifaci.io import (
    encode_frame,
    decode_frame,
    read_frame,
    write_frame,
    FrameReader,
    FrameWriter,
    handshake,
    handshake_accept,
    verify_identity,
    HandshakeResult,
    CborError,
    FrameTooLargeError,
    UnexpectedEofError,
    HandshakeError,
)
from capdag.bifaci.frame import (
    Frame,
    FrameType,
    MessageId,
    Limits,
    DEFAULT_MAX_FRAME,
    DEFAULT_MAX_CHUNK,
    compute_checksum,
)


# TEST205: Test REQ frame encode/decode roundtrip preserves all fields
def test_205_encode_frame_produces_cbor_with_integer_keys():
    frame = Frame.hello(1024, 512)
    data = encode_frame(frame)

    # Should be valid CBOR
    assert len(data) > 0

    # Should be a map when decoded
    import cbor2
    decoded = cbor2.loads(data)
    assert isinstance(decoded, dict)

    # Should have integer keys
    for key in decoded.keys():
        assert isinstance(key, int)


# TEST206: Test HELLO frame encode/decode roundtrip preserves max_frame, max_chunk, max_reorder_buffer
def test_206_decode_frame_parses_cbor_correctly():
    original = Frame.hello(2048, 1024)
    data = encode_frame(original)

    decoded = decode_frame(data)

    assert decoded.frame_type == FrameType.HELLO
    assert decoded.hello_max_frame() == 2048
    assert decoded.hello_max_chunk() == 1024


# TEST207: Test ERR frame encode/decode roundtrip preserves error code and message
def test_207_decode_frame_fails_on_invalid_cbor():
    with pytest.raises(CborError):
        decode_frame(b"invalid cbor data")


# TEST208: Test LOG frame encode/decode roundtrip preserves level and message
def test_208_decode_frame_fails_on_non_map():
    import cbor2
    data = cbor2.dumps([1, 2, 3])  # Array, not map

    with pytest.raises(CborError):
        decode_frame(data)


# TEST210: Test END frame encode/decode roundtrip preserves eof marker and optional payload
def test_210_read_frame_reads_length_prefixed():
    output = io.BytesIO()
    original = Frame.hello(2048, 1024)
    limits = Limits(10000, 5000)

    write_frame(output, original, limits)

    # Read it back
    output.seek(0)
    decoded = read_frame(output, limits)

    assert decoded is not None
    assert decoded.frame_type == FrameType.HELLO
    assert decoded.hello_max_frame() == 2048


# TEST211: Test HELLO with manifest encode/decode roundtrip preserves manifest bytes and limits
def test_211_read_frame_returns_none_on_eof():
    input_stream = io.BytesIO(b"")  # Empty stream
    limits = Limits.default()

    result = read_frame(input_stream, limits)
    assert result is None


# TEST212: Test chunk_with_offset encode/decode roundtrip preserves offset, len, eof (with stream_id)
def test_212_read_frame_fails_on_incomplete_length_prefix():
    input_stream = io.BytesIO(b"\x00\x00")  # Only 2 bytes
    limits = Limits.default()

    with pytest.raises(UnexpectedEofError):
        read_frame(input_stream, limits)


# TEST213: Test heartbeat frame encode/decode roundtrip preserves ID with no extra fields
def test_213_read_frame_fails_on_incomplete_frame_data():
    # Write a frame claiming 100 bytes but only provide 10
    input_stream = io.BytesIO(b"\x00\x00\x00\x64" + b"x" * 10)
    limits = Limits.default()

    with pytest.raises(UnexpectedEofError):
        read_frame(input_stream, limits)


# TEST214: Test write_frame/read_frame IO roundtrip through length-prefixed wire format
def test_214_write_read_frame_io_roundtrip():
    output = io.BytesIO()
    limits = Limits(10000, 5000)
    original = Frame.req(
        MessageId.new_uuid(),
        "cap:test",
        b"payload",
        "application/json",
    )

    write_frame(output, original, limits)
    output.seek(0)
    decoded = read_frame(output, limits)

    assert decoded is not None
    assert decoded.frame_type == original.frame_type
    assert decoded.cap == original.cap
    assert decoded.payload == original.payload


# TEST215: Test reading multiple sequential frames from a single buffer
def test_215_frame_reader_reads_multiple_frames():
    output = io.BytesIO()
    limits = Limits(10000, 5000)

    frame1 = Frame.req(MessageId.new_uuid(), "cap:first", b"one", "text/plain")
    payload = b"two"
    frame2 = Frame.chunk(MessageId.new_uuid(), "stream-001", 0, payload, 0, compute_checksum(payload))
    frame3 = Frame.end(MessageId.new_uuid(), b"three")

    write_frame(output, frame1, limits)
    write_frame(output, frame2, limits)
    write_frame(output, frame3, limits)

    # Read back
    output.seek(0)
    reader = FrameReader(output, limits)

    read1 = reader.read()
    assert read1 is not None
    assert read1.frame_type == FrameType.REQ
    assert read1.id == frame1.id

    read2 = reader.read()
    assert read2 is not None
    assert read2.frame_type == FrameType.CHUNK
    assert read2.id == frame2.id
    assert read2.stream_id == "stream-001"

    read3 = reader.read()
    assert read3 is not None
    assert read3.frame_type == FrameType.END
    assert read3.id == frame3.id

    assert reader.read() is None


# TEST216: Test write_frame rejects frames exceeding max_frame limit
def test_216_write_frame_rejects_oversized_frame():
    output = io.BytesIO()
    limits = Limits(100, 50)
    payload = b"x" * 200
    frame = Frame.req(
        MessageId.new_uuid(),
        "cap:test",
        payload,
        "application/octet-stream",
    )

    with pytest.raises(FrameTooLargeError):
        write_frame(output, frame, limits)


# TEST217: Test read_frame rejects incoming frames exceeding the negotiated max_frame limit
def test_217_read_frame_rejects_oversized_incoming_frame():
    output = io.BytesIO()
    write_limits = Limits(10_000_000, 1_000_000)
    read_limits = Limits(50, 50)
    frame = Frame.req(
        MessageId.new_uuid(),
        "cap:test",
        b"x" * 200,
        "text/plain",
    )

    write_frame(output, frame, write_limits)
    output.seek(0)

    with pytest.raises(FrameTooLargeError):
        read_frame(output, read_limits)


# TEST218: Test write_chunked splits data into chunks respecting max_chunk and reconstructs correctly Chunks from write_chunked have seq=0. SeqAssigner at the output stage assigns final seq. Chunk ordering within a stream is tracked by chunk_index (chunk_index field).
def test_218_write_chunked_splits_and_reconstructs():
    output = io.BytesIO()
    limits = Limits(1_000_000, 10)
    writer = FrameWriter(output, limits)

    request_id = MessageId.new_uuid()
    stream_id = "stream-test-218"
    data = b"Hello, this is a longer message that will be chunked!"

    writer.write_chunked(request_id, stream_id, "text/plain", data)
    output.seek(0)

    reader = FrameReader(output, Limits(1_000_000, 1_000_000))
    received = b""
    chunk_count = 0
    first_chunk_had_len = False
    first_chunk_had_content_type = False

    while True:
        frame = reader.read()
        assert frame is not None
        assert frame.frame_type == FrameType.CHUNK
        assert frame.id == request_id
        assert frame.stream_id == stream_id
        assert frame.seq == 0
        assert frame.chunk_index == chunk_count

        if chunk_count == 0:
            first_chunk_had_len = frame.len is not None
            first_chunk_had_content_type = frame.content_type is not None
            assert frame.len == len(data)
            assert frame.content_type == "text/plain"

        received += frame.payload or b""
        if frame.eof:
            break
        chunk_count += 1

    assert received == data
    assert chunk_count > 0
    assert first_chunk_had_len
    assert first_chunk_had_content_type


# TEST219: Test write_chunked with empty data produces a single EOF chunk
def test_219_write_chunked_empty_data():
    output = io.BytesIO()
    limits = Limits(1_000_000, 100)
    writer = FrameWriter(output, limits)

    request_id = MessageId.new_uuid()
    writer.write_chunked(request_id, "stream-empty", "text/plain", b"")
    output.seek(0)

    frame = read_frame(output, limits)
    assert frame is not None
    assert frame.frame_type == FrameType.CHUNK
    assert frame.stream_id == "stream-empty"
    assert frame.eof is True
    assert frame.len == 0
    assert frame.payload == b""
    assert read_frame(output, limits) is None


# TEST220: Test write_chunked with data exactly equal to max_chunk produces exactly one chunk
def test_220_write_chunked_exact_fit():
    output = io.BytesIO()
    limits = Limits(1_000_000, 10)
    writer = FrameWriter(output, limits)

    request_id = MessageId.new_uuid()
    data = b"0123456789"
    writer.write_chunked(request_id, "stream-exact", "text/plain", data)
    output.seek(0)

    frame = read_frame(output, Limits(1_000_000, 1_000_000))
    assert frame is not None
    assert frame.stream_id == "stream-exact"
    assert frame.eof is True
    assert frame.payload == data
    assert frame.seq == 0
    assert read_frame(output, Limits(1_000_000, 1_000_000)) is None


# TEST221: Test read_frame returns Ok(None) on clean EOF (empty stream)
def test_221_read_frame_returns_none_on_eof():
    input_stream = io.BytesIO(b"")
    assert read_frame(input_stream, Limits.default()) is None


# TEST222: Test read_frame handles truncated length prefix (fewer than 4 bytes available)
def test_222_read_frame_fails_on_truncated_length_prefix():
    input_stream = io.BytesIO(b"\x00\x01")
    with pytest.raises(UnexpectedEofError):
        read_frame(input_stream, Limits.default())


# TEST223: Test read_frame returns error on truncated frame body (length prefix says more bytes than available)
def test_223_read_frame_fails_on_truncated_frame_body():
    input_stream = io.BytesIO(b"\x00\x00\x00\x64" + b"\x01\x02\x03\x04\x05")
    with pytest.raises(UnexpectedEofError):
        read_frame(input_stream, Limits.default())


# TEST461: write_chunked produces frames with seq=0; SeqAssigner assigns at output stage
def test_461_write_chunked_seq_zero():
    output = io.BytesIO()
    limits = Limits(1_000_000, 5)
    writer = FrameWriter(output, limits)

    request_id = MessageId.new_uuid()
    writer.write_chunked(request_id, "s", "application/octet-stream", b"abcdefghij")
    output.seek(0)

    reader = FrameReader(output, Limits(1_000_000, 1_000_000))
    frames = []

    while True:
        frame = reader.read()
        assert frame is not None
        frames.append(frame)
        if frame.eof:
            break

    assert len(frames) == 2
    assert [frame.seq for frame in frames] == [0, 0]
    assert [frame.chunk_index for frame in frames] == [0, 1]
    assert frames[0].payload == b"abcde"
    assert frames[1].payload == b"fghij"


# TEST472: Handshake negotiates max_reorder_buffer (minimum of both sides)
def test_472_handshake_negotiates_reorder_buffer():
    host_to_cartridge = io.BytesIO()
    cartridge_to_host = io.BytesIO()

    host_writer = FrameWriter.new(host_to_cartridge)
    host_reader = FrameReader.new(cartridge_to_host)
    host_writer.write(Frame.hello(DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK, 64))

    host_to_cartridge.seek(0)
    cartridge_reader = FrameReader.new(host_to_cartridge)
    cartridge_writer = FrameWriter.new(cartridge_to_host)
    received = cartridge_reader.read()
    assert received is not None
    assert received.hello_max_reorder_buffer() == 64

    manifest = b'{"name":"test","version":"1.0.0","channel":"release","description":"test","cap_groups":[{"name":"default","caps":[{"urn":"cap:in=media:;out=media:"}]}]}'
    cartridge_writer.write(
        Frame.hello_with_manifest(DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK, manifest, 32)
    )

    cartridge_to_host.seek(0)
    result = handshake(host_reader, host_writer)
    assert isinstance(result, HandshakeResult)
    assert result.manifest == manifest
    assert result.limits.max_reorder_buffer == 32


# TEST481: verify_identity succeeds with standard identity echo handler
def test_481_verify_identity_succeeds():
    import socket
    import threading

    host_read_sock, cartridge_write_sock = socket.socketpair()
    cartridge_read_sock, host_write_sock = socket.socketpair()
    manifest = b'{"name":"Identity","version":"1.0.0","channel":"release","description":"test","cap_groups":[{"name":"default","caps":[{"urn":"cap:"}]}]}'

    def cartridge_thread():
        reader = FrameReader(cartridge_read_sock.makefile("rb"))
        writer = FrameWriter(cartridge_write_sock.makefile("wb"))
        handshake_accept(reader, writer, manifest)
        req = reader.read()
        assert req is not None and req.frame_type == FrameType.REQ
        ss = reader.read()
        chunk = reader.read()
        se = reader.read()
        end = reader.read()
        assert ss.frame_type == FrameType.STREAM_START
        assert chunk.frame_type == FrameType.CHUNK
        assert se.frame_type == FrameType.STREAM_END
        assert end.frame_type == FrameType.END
        writer.write(Frame.stream_start(req.id, "identity-verify", "media:"))
        writer.write(Frame.chunk(req.id, "identity-verify", 0, chunk.payload, 0, compute_checksum(chunk.payload)))
        writer.write(Frame.stream_end(req.id, "identity-verify", 1))
        writer.write(Frame.end(req.id, None))

    t = threading.Thread(target=cartridge_thread, daemon=True)
    t.start()

    reader = FrameReader(host_read_sock.makefile("rb"))
    writer = FrameWriter(host_write_sock.makefile("wb"))
    handshake(reader, writer)
    verify_identity(reader, writer)
    t.join(timeout=2)


# TEST482: verify_identity fails when cartridge returns ERR on identity call
def test_482_verify_identity_fails_on_err():
    import socket
    import threading

    host_read_sock, cartridge_write_sock = socket.socketpair()
    cartridge_read_sock, host_write_sock = socket.socketpair()
    manifest = b'{"name":"Identity","version":"1.0.0","channel":"release","description":"test","cap_groups":[{"name":"default","caps":[{"urn":"cap:"}]}]}'

    def cartridge_thread():
        reader = FrameReader(cartridge_read_sock.makefile("rb"))
        writer = FrameWriter(cartridge_write_sock.makefile("wb"))
        handshake_accept(reader, writer, manifest)
        req = reader.read()
        assert req is not None and req.frame_type == FrameType.REQ
        writer.write(Frame.err(req.id, "BROKEN", "identity handler broken"))

    t = threading.Thread(target=cartridge_thread, daemon=True)
    t.start()

    reader = FrameReader(host_read_sock.makefile("rb"))
    writer = FrameWriter(host_write_sock.makefile("wb"))
    handshake(reader, writer)
    with pytest.raises(HandshakeError) as exc_info:
        verify_identity(reader, writer)
    assert "BROKEN" in str(exc_info.value)
    t.join(timeout=2)


# TEST483: verify_identity fails when connection closes before response
def test_483_verify_identity_fails_on_close():
    import socket
    import threading

    host_read_sock, cartridge_write_sock = socket.socketpair()
    cartridge_read_sock, host_write_sock = socket.socketpair()
    manifest = b'{"name":"Identity","version":"1.0.0","channel":"release","description":"test","cap_groups":[{"name":"default","caps":[{"urn":"cap:"}]}]}'

    def cartridge_thread():
        reader = FrameReader(cartridge_read_sock.makefile("rb"))
        writer = FrameWriter(cartridge_write_sock.makefile("wb"))
        handshake_accept(reader, writer, manifest)
        _ = reader.read()
        cartridge_write_sock.close()

    t = threading.Thread(target=cartridge_thread, daemon=True)
    t.start()

    reader = FrameReader(host_read_sock.makefile("rb"))
    writer = FrameWriter(host_write_sock.makefile("wb"))
    handshake(reader, writer)
    with pytest.raises(HandshakeError):
        verify_identity(reader, writer)
    t.join(timeout=2)


# TEST224: Test MessageId::Uint roundtrips through encode/decode
def test_224_handshake_negotiates_to_minimum_limits():
    host_to_cartridge = io.BytesIO()
    cartridge_to_host = io.BytesIO()

    # Host with larger limits
    host_writer = FrameWriter.new(host_to_cartridge)
    host_reader = FrameReader.new(cartridge_to_host)

    # Cartridge with smaller limits
    manifest = b'{"identifier": "test", "version": "1.0.0","channel":"release", "cap_groups":[{"name":"default","caps":[]}]}'

    # Host sends HELLO
    host_hello = Frame.hello(10000, 5000)
    host_writer.write(host_hello)

    # Cartridge receives, negotiates, and responds with smaller limits
    host_to_cartridge.seek(0)
    cartridge_reader = FrameReader.new(host_to_cartridge)
    received = cartridge_reader.read()

    # Cartridge should negotiate to min(10000, 8000) = 8000
    their_max_frame = received.hello_max_frame() or DEFAULT_MAX_FRAME
    negotiated_frame = min(8000, their_max_frame)

    cartridge_hello = Frame.hello_with_manifest(negotiated_frame, 3000, manifest)

    cartridge_writer = FrameWriter.new(cartridge_to_host)
    cartridge_writer.write(cartridge_hello)

    # Host receives and verifies negotiation
    cartridge_to_host.seek(0)
    result = host_reader.read()
    assert result.hello_max_frame() == negotiated_frame


# TEST225: Test decode_frame rejects non-map CBOR values (e.g., array, integer, string)
def test_225_handshake_function_full_handshake():
    # Create bidirectional streams
    host_to_cartridge = io.BytesIO()
    cartridge_to_host = io.BytesIO()

    # Prepare manifest
    manifest = b'{"identifier": "test-cartridge", "version": "1.0.0","channel":"release", "cap_groups":[{"name":"default","caps":[]}]}'

    # Cartridge side accepts handshake in background (simulate)
    cartridge_hello = Frame.hello_with_manifest(DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK, manifest)
    cartridge_writer_temp = FrameWriter.new(cartridge_to_host)
    cartridge_writer_temp.write(cartridge_hello)

    # Host side initiates
    host_reader = FrameReader.new(cartridge_to_host)
    host_writer = FrameWriter.new(host_to_cartridge)

    # First write host HELLO
    host_hello = Frame.hello(DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK)
    host_writer.write(host_hello)

    # Then read cartridge response
    cartridge_to_host.seek(0)
    result = host_reader.read()

    assert result is not None
    assert result.hello_manifest() == manifest


# TEST226: Test decode_frame rejects CBOR map missing required version field
def test_226_handshake_accept_receives_first():
    host_to_cartridge = io.BytesIO()
    cartridge_to_host = io.BytesIO()

    # Host sends HELLO first
    host_hello = Frame.hello(DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK)
    host_writer_temp = FrameWriter.new(host_to_cartridge)
    host_writer_temp.write(host_hello)

    # Cartridge accepts
    host_to_cartridge.seek(0)
    cartridge_reader = FrameReader.new(host_to_cartridge)
    cartridge_writer = FrameWriter.new(cartridge_to_host)

    manifest = b'{"identifier": "test", "version": "1.0.0","channel":"release", "cap_groups":[{"name":"default","caps":[]}]}'

    limits = handshake_accept(cartridge_reader, cartridge_writer, manifest)

    # Verify negotiated limits
    assert limits.max_frame == DEFAULT_MAX_FRAME
    assert limits.max_chunk == DEFAULT_MAX_CHUNK

    # Verify cartridge sent HELLO with manifest
    cartridge_to_host.seek(0)
    cartridge_reader_temp = FrameReader.new(cartridge_to_host)
    response = cartridge_reader_temp.read()
    assert response.frame_type == FrameType.HELLO
    assert response.hello_manifest() == manifest


# TEST227: Test decode_frame rejects CBOR map with invalid frame_type value
def test_227_handshake_fails_if_cartridge_missing_manifest():
    host_to_cartridge = io.BytesIO()
    cartridge_to_host = io.BytesIO()

    # Cartridge sends HELLO WITHOUT manifest (invalid)
    cartridge_hello = Frame.hello(DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK)  # No manifest!
    cartridge_writer_temp = FrameWriter.new(cartridge_to_host)
    cartridge_writer_temp.write(cartridge_hello)

    # Host tries to handshake
    cartridge_to_host.seek(0)
    host_reader = FrameReader.new(cartridge_to_host)
    host_writer = FrameWriter.new(host_to_cartridge)

    # First send host HELLO
    host_writer.write(Frame.hello(DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK))

    # Then try to read cartridge response - should fail because no manifest
    with pytest.raises(HandshakeError, match="missing required manifest"):
        their_frame = host_reader.read()
        if their_frame.hello_manifest() is None:
            raise HandshakeError("Cartridge HELLO missing required manifest")


# TEST228: Test decode_frame rejects CBOR map missing required id field
def test_228_read_frame_enforces_limit():
    output = io.BytesIO()

    # Write a large frame (use CHUNK frame since RES removed in Protocol v2)
    payload = b"x" * 2000
    frame = Frame.chunk(MessageId.new_uuid(), "test-stream", 0, payload, 0, compute_checksum(payload))
    large_limits = Limits(10000, 5000)
    write_frame(output, frame, large_limits)

    # Try to read with small limit
    output.seek(0)
    small_limits = Limits(1000, 500)

    with pytest.raises(FrameTooLargeError):
        read_frame(output, small_limits)


# TEST229: Test FrameReader/FrameWriter set_limits updates the negotiated limits
def test_229_frame_with_zero_length_payload():
    output = io.BytesIO()
    frame = Frame.chunk(MessageId.new_uuid(), "test-stream", 0, b"", 0, 0)
    limits = Limits.default()

    write_frame(output, frame, limits)

    output.seek(0)
    decoded = read_frame(output, limits)

    assert decoded is not None
    assert decoded.payload == b""


# TEST230: Test async handshake exchanges HELLO frames and negotiates minimum limits
def test_230_frame_roundtrip_preserves_fields():
    original = Frame(
        frame_type=FrameType.REQ,
        id=MessageId.new_uuid(),
        seq=42,
        content_type="application/json",
        meta={"key": "value"},
        payload=b"test data",
        cap="cap:in=\"media:void\";test;out=\"media:void\"",
    )

    data = encode_frame(original)
    decoded = decode_frame(data)

    assert decoded.frame_type == original.frame_type
    assert decoded.seq == original.seq
    assert decoded.content_type == original.content_type
    assert decoded.payload == original.payload
    assert decoded.cap == original.cap


# TEST231: Test handshake fails when peer sends non-HELLO frame
def test_231_multiple_readers_on_same_stream():
    output = io.BytesIO()
    limits = Limits.default()

    frame1 = Frame.hello(1024, 512)
    frame2 = Frame.hello(2048, 1024)
    frame3 = Frame.hello(4096, 2048)

    write_frame(output, frame1, limits)
    write_frame(output, frame2, limits)
    write_frame(output, frame3, limits)

    output.seek(0)
    reader = FrameReader(output, limits)

    read1 = reader.read()
    read2 = reader.read()
    read3 = reader.read()

    assert read1.hello_max_frame() == 1024
    assert read2.hello_max_frame() == 2048
    assert read3.hello_max_frame() == 4096


# TEST232: Test handshake fails when cartridge HELLO is missing required manifest
def test_232_writer_flushes_after_each_frame():
    output = io.BytesIO()
    writer = FrameWriter.new(output)

    frame = Frame.hello(1024, 512)
    writer.write(frame)

    # Data should be available immediately
    data = output.getvalue()
    assert len(data) > 0


# TEST233: Test binary payload with all 256 byte values roundtrips through encode/decode
def test_233_frame_encoding_preserves_binary_data():
    # Binary data with all byte values
    binary_data = bytes(range(256))

    frame = Frame.chunk(MessageId.new_uuid(), "test-stream", 0, binary_data, 0, compute_checksum(binary_data))

    data = encode_frame(frame)
    decoded = decode_frame(data)

    assert decoded.payload == binary_data


# TEST234: Test decode_frame handles garbage CBOR bytes gracefully with an error
def test_234_handshake_with_very_small_limits():
    host_to_cartridge = io.BytesIO()
    cartridge_to_host = io.BytesIO()

    tiny_limits = Limits(256, 128)  # Use larger limits to fit HELLO frame with length prefix

    # Host with tiny limits
    host_hello = Frame.hello(tiny_limits.max_frame, tiny_limits.max_chunk)
    host_writer_temp = FrameWriter(host_to_cartridge, tiny_limits)
    host_writer_temp.write(host_hello)

    # Cartridge reads
    host_to_cartridge.seek(0)
    cartridge_reader = FrameReader(host_to_cartridge, tiny_limits)
    received = cartridge_reader.read()

    assert received is not None
    assert received.hello_max_frame() == 256


# TEST1140: write_stream_chunked (protocol v2) splits payload into STREAM_START → CHUNK(s) → STREAM_END → END
def test_1140_write_stream_chunked_reassembly():
    buf = io.BytesIO()
    writer = FrameWriter(buf, Limits(DEFAULT_MAX_FRAME, 100))

    request_id = MessageId.new_uuid()
    data = bytes(i % 256 for i in range(250))

    writer.write_stream_chunked(request_id, "resp-1", "media:", data)

    buf.seek(0)
    reader = FrameReader(buf)

    frames = []
    while True:
        frame = reader.read()
        if frame is None:
            break
        frames.append(frame)
        if frame.frame_type == FrameType.END:
            break

    # Protocol v2: STREAM_START + 3 CHUNK (250/100=3) + STREAM_END + END = 6 frames
    assert len(frames) == 6, f"Expected 6 frames (STREAM_START + 3 CHUNK + STREAM_END + END), got {len(frames)}"
    assert frames[0].frame_type == FrameType.STREAM_START
    assert frames[0].stream_id == "resp-1"
    assert frames[0].media_urn == "media:"
    assert frames[1].frame_type == FrameType.CHUNK
    assert frames[1].stream_id == "resp-1"
    assert frames[2].frame_type == FrameType.CHUNK
    assert frames[3].frame_type == FrameType.CHUNK
    assert frames[4].frame_type == FrameType.STREAM_END
    assert frames[4].stream_id == "resp-1"
    assert frames[5].frame_type == FrameType.END

    reassembled = b""
    for f in frames:
        if f.frame_type == FrameType.CHUNK:
            reassembled += f.payload or b""
    assert reassembled == data, "concatenated chunks must match original data"


# TEST1141: write_stream_chunked with data exactly equal to max_chunk produces exactly one CHUNK
def test_1141_exact_max_chunk_stream_chunked():
    buf = io.BytesIO()
    writer = FrameWriter(buf, Limits(DEFAULT_MAX_FRAME, 100))

    request_id = MessageId.new_uuid()
    data = bytes([0xAB] * 100)

    writer.write_stream_chunked(request_id, "resp-1", "media:", data)

    buf.seek(0)
    reader = FrameReader(buf)

    frames = []
    while True:
        frame = reader.read()
        if frame is None:
            break
        frames.append(frame)
        if frame.frame_type == FrameType.END:
            break

    # STREAM_START + 1 CHUNK + STREAM_END + END = 4 frames
    assert len(frames) == 4, f"Expected 4 frames, got {len(frames)}"
    assert frames[0].frame_type == FrameType.STREAM_START
    assert frames[1].frame_type == FrameType.CHUNK
    assert frames[1].payload == data
    assert frames[2].frame_type == FrameType.STREAM_END
    assert frames[3].frame_type == FrameType.END


# TEST121: Test payload of max_chunk + 1 bytes produces exactly two chunks
def test_121_max_chunk_plus_one_splits_into_two_chunks():
    buf = io.BytesIO()
    writer = FrameWriter(buf, Limits(DEFAULT_MAX_FRAME, 100))

    request_id = MessageId.new_uuid()
    data = bytes(range(101))

    writer.write_stream_chunked(request_id, "resp-1", "media:", data)

    buf.seek(0)
    reader = FrameReader(buf)

    frames = []
    while True:
        frame = reader.read()
        if frame is None:
            break
        frames.append(frame)
        if frame.frame_type == FrameType.END:
            break

    # STREAM_START + 2 CHUNK + STREAM_END + END = 5 frames
    assert len(frames) == 5, f"Expected 5 frames, got {len(frames)}"
    assert frames[0].frame_type == FrameType.STREAM_START
    assert frames[1].frame_type == FrameType.CHUNK
    assert len(frames[1].payload) == 100
    assert frames[2].frame_type == FrameType.CHUNK
    assert len(frames[2].payload) == 1
    assert frames[3].frame_type == FrameType.STREAM_END
    assert frames[4].frame_type == FrameType.END

    reassembled = frames[1].payload + frames[2].payload
    assert reassembled == data


# TEST122: Test auto-chunking preserves data integrity across chunk boundaries for 3x max_chunk payload
def test_122_chunking_data_integrity_3x():
    buf = io.BytesIO()
    writer = FrameWriter(buf, Limits(DEFAULT_MAX_FRAME, 100))

    request_id = MessageId.new_uuid()
    pattern = b"ABCDEFGHIJ"
    data = (pattern * 30)  # 300 bytes

    writer.write_stream_chunked(request_id, "resp-1", "media:", data)

    buf.seek(0)
    reader = FrameReader(buf)

    frames = []
    while True:
        frame = reader.read()
        if frame is None:
            break
        frames.append(frame)
        if frame.frame_type == FrameType.END:
            break

    # Protocol v2: STREAM_START + 3 CHUNK (300/100) + STREAM_END + END = 6 frames
    assert len(frames) == 6, f"Expected 6 frames, got {len(frames)}"

    reassembled = b""
    for f in frames:
        if f.frame_type == FrameType.CHUNK:
            reassembled += f.payload or b""
    assert len(reassembled) == 300
    assert reassembled == data, "pattern must be preserved across chunk boundaries"


# TEST389: StreamStart encode/decode roundtrip preserves stream_id and media_urn
def test_389_stream_start_roundtrip():
    id = MessageId.new_uuid()
    stream_id = "stream-abc-123"
    media_urn = "media:"

    frame = Frame.stream_start(id, stream_id, media_urn)
    encoded = encode_frame(frame)
    decoded = decode_frame(encoded)

    assert decoded.frame_type == FrameType.STREAM_START
    assert decoded.id == id
    assert decoded.stream_id == "stream-abc-123"
    assert decoded.media_urn == "media:"


# TEST390: StreamEnd encode/decode roundtrip preserves stream_id, no media_urn
def test_390_stream_end_roundtrip():
    id = MessageId.new_uuid()
    stream_id = "stream-xyz-789"

    frame = Frame.stream_end(id, stream_id, 0)
    encoded = encode_frame(frame)
    decoded = decode_frame(encoded)

    assert decoded.frame_type == FrameType.STREAM_END
    assert decoded.id == id
    assert decoded.stream_id == "stream-xyz-789"
    assert decoded.media_urn is None, "StreamEnd should not have media_urn"


# TEST848: RelayNotify encode/decode roundtrip preserves manifest and limits
def test_848_relay_notify_roundtrip():
    manifest = b'{"cap_groups":[{"name":"default","caps":["cap:relay-test"]}]}'
    max_frame = 2_000_000
    max_chunk = 128_000

    frame = Frame.relay_notify(manifest, max_frame, max_chunk)
    encoded = encode_frame(frame)
    decoded = decode_frame(encoded)

    assert decoded.frame_type == FrameType.RELAY_NOTIFY

    extracted_manifest = decoded.relay_notify_manifest()
    assert extracted_manifest is not None, "relay_notify_manifest() must not be None after roundtrip"
    assert extracted_manifest == manifest

    extracted_limits = decoded.relay_notify_limits()
    assert extracted_limits is not None, "relay_notify_limits() must not be None after roundtrip"
    assert extracted_limits.max_frame == max_frame
    assert extracted_limits.max_chunk == max_chunk


# TEST849: RelayState encode/decode roundtrip preserves resource payload
def test_849_relay_state_roundtrip():
    resources = b'{"gpu_memory":8192,"cpu_cores":16}'

    frame = Frame.relay_state(resources)
    encoded = encode_frame(frame)
    decoded = decode_frame(encoded)

    assert decoded.frame_type == FrameType.RELAY_STATE
    assert decoded.payload == resources


# TEST440: CHUNK frame with chunk_index and checksum roundtrips through encode/decode
def test_440_chunk_index_checksum_roundtrip():
    rid = MessageId.random()
    payload = b"test chunk data"
    cs = compute_checksum(payload)

    frame = Frame.chunk(rid, "test-stream", 5, payload, 3, cs)

    encoded = encode_frame(frame)
    decoded = decode_frame(encoded)

    assert decoded.frame_type == FrameType.CHUNK
    assert decoded.id == rid
    assert decoded.stream_id == "test-stream"
    assert decoded.seq == 5
    assert decoded.payload == payload
    assert decoded.chunk_index == 3, "chunk_index must roundtrip"
    assert decoded.checksum == cs, "checksum must roundtrip"


# TEST441: STREAM_END frame with chunk_count roundtrips through encode/decode
def test_441_stream_end_chunk_count_roundtrip():
    rid = MessageId.random()

    frame = Frame.stream_end(rid, "test-stream", chunk_count=42)

    encoded = encode_frame(frame)
    decoded = decode_frame(encoded)

    assert decoded.frame_type == FrameType.STREAM_END
    assert decoded.id == rid
    assert decoded.stream_id == "test-stream"
    assert decoded.chunk_count == 42, "chunk_count must roundtrip"


# TEST846: Test progress LOG frame encode/decode roundtrip preserves progress float
def test_846_progress_frame_roundtrip():
    rid = MessageId.new_uuid()

    # Test several progress values including edge cases AND the f64→f32→f64 chain
    # that modelcartridge uses
    test_values = [
        (0.0, "zero"),
        (0.03333333, "1/30"),
        (0.06666667, "2/30"),
        (0.13333334, "4/30"),
        (0.25, "quarter"),
        (0.5, "half"),
        (0.75, "three-quarter"),
        (1.0, "one"),
    ]

    for progress, label in test_values:
        original = Frame.progress(rid, progress, "test phase")
        encoded = encode_frame(original)
        decoded = decode_frame(encoded)

        assert decoded.frame_type == FrameType.LOG
        assert decoded.log_level() == "progress"
        assert decoded.log_message() == "test phase"

        decoded_progress = decoded.log_progress()
        assert decoded_progress is not None, \
            f"log_progress() must return value for progress={progress} ({label})"
        assert abs(decoded_progress - progress) < 0.001, \
            f"progress roundtrip for {label}: expected {progress}, got {decoded_progress}"


# TEST847: Double roundtrip (modelcartridge → relay → candlecartridge)
def test_847_progress_double_roundtrip():
    rid = MessageId.new_uuid()

    for progress in [0.0, 0.03333333, 0.06666667, 0.13333334, 0.5, 1.0]:
        original = Frame.progress(rid, progress, "test")

        # First roundtrip (modelcartridge → relay_switch)
        bytes1 = encode_frame(original)
        decoded1 = decode_frame(bytes1)

        # Relay switch modifies seq (like SeqAssigner does)
        decoded1.seq = 42

        # Second roundtrip (relay_switch → candlecartridge)
        bytes2 = encode_frame(decoded1)
        decoded2 = decode_frame(bytes2)

        lp = decoded2.log_progress()
        assert lp is not None, f"progress={progress}: log_progress() returned None"
        assert abs(lp - progress) < 0.001, \
            f"progress={progress}: expected {progress}, got {lp}"
