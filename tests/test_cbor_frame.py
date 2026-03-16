"""Tests for cbor_frame - mirroring capdag Rust tests

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
from capdag.bifaci.frame import (
    FrameType,
    MessageId,
    Limits,
    Frame,
    Keys,
    FlowKey,
    SeqAssigner,
    ReorderBuffer,
    PROTOCOL_VERSION,
    DEFAULT_MAX_FRAME,
    DEFAULT_MAX_CHUNK,
    DEFAULT_MAX_REORDER_BUFFER,
    compute_checksum,
    verify_chunk_checksum,
)
from capdag.bifaci.io import ProtocolError


# TEST171: Test all FrameType discriminants roundtrip through u8 conversion preserving identity
def test_171_frame_type_roundtrip():
    """Test all frame types roundtrip through u8 conversion"""
    for t in [
        FrameType.HELLO,
        FrameType.REQ,
        # RES (2) removed in Protocol v2
        FrameType.CHUNK,
        FrameType.END,
        FrameType.LOG,
        FrameType.ERR,
        FrameType.HEARTBEAT,
        FrameType.STREAM_START,
        FrameType.STREAM_END,
    ]:
        v = int(t)
        recovered = FrameType.from_u8(v)
        assert recovered is not None, f"should recover frame type {t}"
        assert t == recovered


# TEST172: Test FrameType::from_u8 returns None for values outside the valid discriminant range
def test_172_invalid_frame_type():
    """Test invalid frame type values return None"""
    assert FrameType.from_u8(10) == FrameType.RELAY_NOTIFY
    assert FrameType.from_u8(11) == FrameType.RELAY_STATE
    assert FrameType.from_u8(12) is None, "value 12 is one past RelayState"
    assert FrameType.from_u8(100) is None
    assert FrameType.from_u8(255) is None


# TEST173: Test FrameType discriminant values match the wire protocol specification exactly
def test_173_frame_type_discriminant_values():
    """Test frame type values match protocol specification"""
    assert FrameType.HELLO == 0
    assert FrameType.REQ == 1
    # RES (2) removed in Protocol v2
    assert FrameType.CHUNK == 3
    assert FrameType.END == 4
    assert FrameType.LOG == 5
    assert FrameType.ERR == 6
    assert FrameType.HEARTBEAT == 7
    assert FrameType.STREAM_START == 8
    assert FrameType.STREAM_END == 9


# TEST174: Test MessageId::new_uuid generates valid UUID that roundtrips through string conversion
def test_174_message_id_uuid():
    """Test MessageId UUID generation and string roundtrip"""
    id = MessageId.new_uuid()
    s = id.to_uuid_string()
    assert s is not None, "should be uuid"
    recovered = MessageId.from_uuid_str(s)
    assert recovered is not None, "should parse"
    assert id == recovered


# TEST175: Test two MessageId::new_uuid calls produce distinct IDs (no collisions)
def test_175_message_id_uuid_uniqueness():
    """Test UUID uniqueness"""
    id1 = MessageId.new_uuid()
    id2 = MessageId.new_uuid()
    assert id1 != id2, "two UUIDs must be distinct"


# TEST176: Test MessageId::Uint does not produce a UUID string, to_uuid_string returns None
def test_176_message_id_uint_has_no_uuid_string():
    """Test Uint IDs have no UUID string representation"""
    id = MessageId(42)
    assert id.to_uuid_string() is None, "Uint IDs have no UUID representation"


# TEST177: Test MessageId::from_uuid_str rejects invalid UUID strings
def test_177_message_id_from_invalid_uuid_str():
    """Test invalid UUID strings are rejected"""
    assert MessageId.from_uuid_str("not-a-uuid") is None
    assert MessageId.from_uuid_str("") is None
    assert MessageId.from_uuid_str("12345678") is None


# TEST178: Test MessageId::as_bytes produces correct byte representations for Uuid and Uint variants
def test_178_message_id_as_bytes():
    """Test MessageId as_bytes for both variants"""
    uuid_id = MessageId.new_uuid()
    uuid_bytes = uuid_id.as_bytes()
    assert len(uuid_bytes) == 16, "UUID must be 16 bytes"

    uint_id = MessageId(0x0102030405060708)
    uint_bytes = uint_id.as_bytes()
    assert len(uint_bytes) == 8, "Uint ID must be 8 bytes big-endian"
    assert uint_bytes == bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])


# TEST179: Test MessageId::default creates a UUID variant (not Uint)
def test_179_message_id_default_is_uuid():
    """Test default MessageId is UUID"""
    id = MessageId.default()
    assert id.to_uuid_string() is not None, "default MessageId must be UUID"


# TEST180: Test Frame::hello without manifest produces correct HELLO frame for host side
def test_180_hello_frame():
    """Test HELLO frame creation (host side)"""
    frame = Frame.hello(1_000_000, 100_000)
    assert frame.frame_type == FrameType.HELLO
    assert frame.version == PROTOCOL_VERSION
    assert frame.hello_max_frame() == 1_000_000
    assert frame.hello_max_chunk() == 100_000
    assert frame.hello_manifest() is None, "Host HELLO must not include manifest"
    assert frame.payload is None, "HELLO has no payload"
    # ID should be Uint(0) for HELLO
    assert frame.id == MessageId(0)


# TEST181: Test Frame::hello_with_manifest produces HELLO with manifest bytes for plugin side
def test_181_hello_frame_with_manifest():
    """Test HELLO frame with manifest (plugin side)"""
    manifest_json = b'{"name":"TestPlugin","version":"1.0.0","description":"Test","caps":[]}'
    frame = Frame.hello_with_manifest(1_000_000, 100_000, manifest_json)
    assert frame.frame_type == FrameType.HELLO
    assert frame.hello_max_frame() == 1_000_000
    assert frame.hello_max_chunk() == 100_000
    manifest = frame.hello_manifest()
    assert manifest is not None, "Plugin HELLO must include manifest"
    assert manifest == manifest_json


# TEST182: Test Frame::req stores cap URN, payload, and content_type correctly
def test_182_req_frame():
    """Test REQ frame creation"""
    id = MessageId.new_uuid()
    frame = Frame.req(id, "cap:op=test", b"payload", "application/json")
    assert frame.frame_type == FrameType.REQ
    assert frame.id == id
    assert frame.cap == "cap:op=test"
    assert frame.payload == b"payload"
    assert frame.content_type == "application/json"
    assert frame.version == PROTOCOL_VERSION


# TEST183: RES frame removed in Protocol v2 — replaced by STREAM_START/CHUNK/STREAM_END/END


# TEST184: Test Frame::chunk stores stream_id, seq and payload for streaming
def test_184_chunk_frame():
    """Test CHUNK frame creation with stream_id (Protocol v2)"""
    id = MessageId.new_uuid()
    payload = b"data"
    frame = Frame.chunk(id, "stream-1", 3, payload, 0, compute_checksum(payload))
    assert frame.frame_type == FrameType.CHUNK
    assert frame.id == id
    assert frame.stream_id == "stream-1"
    assert frame.seq == 3
    assert frame.payload == payload
    assert frame.chunk_index == 0
    assert frame.checksum == compute_checksum(payload)
    assert not frame.is_eof(), "plain chunk should not be EOF"


# TEST185: Test Frame::err stores error code and message in metadata
def test_185_err_frame():
    """Test ERR frame creation"""
    id = MessageId.new_uuid()
    frame = Frame.err(id, "NOT_FOUND", "Cap not found")
    assert frame.frame_type == FrameType.ERR
    assert frame.error_code() == "NOT_FOUND"
    assert frame.error_message() == "Cap not found"


# TEST186: Test Frame::log stores level and message in metadata
def test_186_log_frame():
    """Test LOG frame creation"""
    id = MessageId.new_uuid()
    frame = Frame.log(id, "info", "Processing started")
    assert frame.frame_type == FrameType.LOG
    assert frame.id == id
    assert frame.log_level() == "info"
    assert frame.log_message() == "Processing started"


# TEST187: Test Frame::end with payload sets eof and optional final payload
def test_187_end_frame_with_payload():
    """Test END frame with payload"""
    id = MessageId.new_uuid()
    frame = Frame.end(id, b"final")
    assert frame.frame_type == FrameType.END
    assert frame.is_eof()
    assert frame.payload == b"final"


# TEST188: Test Frame::end without payload still sets eof marker
def test_188_end_frame_without_payload():
    """Test END frame without payload"""
    id = MessageId.new_uuid()
    frame = Frame.end(id, None)
    assert frame.frame_type == FrameType.END
    assert frame.is_eof()
    assert frame.payload is None


# TEST189: Test chunk_with_offset sets offset on all chunks but len only on seq=0
def test_189_chunk_with_offset():
    """Test CHUNK frame with offset information"""
    id = MessageId.new_uuid()

    # First chunk carries total len (Protocol v2: stream_id required)
    first = Frame.chunk_with_offset(id, "stream-1", 0, b"data", 0, 1000, False)
    assert first.seq == 0
    assert first.offset == 0
    assert first.stream_id == "stream-1"
    assert first.len == 1000, "first chunk must carry total len"
    assert not first.is_eof()

    # Middle chunk doesn't carry len
    mid = Frame.chunk_with_offset(id, "stream-1", 3, b"mid", 500, 9999, False)
    assert mid.len is None, "non-first chunk must not carry len, seq != 0"
    assert mid.offset == 500

    # Last chunk sets EOF
    last = Frame.chunk_with_offset(id, "stream-1", 5, b"last", 900, None, True)
    assert last.is_eof()
    assert last.len is None


# TEST190: Test Frame::heartbeat creates minimal frame with no payload or metadata
def test_190_heartbeat_frame():
    """Test HEARTBEAT frame creation"""
    id = MessageId.new_uuid()
    frame = Frame.heartbeat(id)
    assert frame.frame_type == FrameType.HEARTBEAT
    assert frame.id == id
    assert frame.payload is None
    assert frame.meta is None
    assert frame.seq == 0


# TEST191: Test error_code and error_message return None for non-Err frame types
def test_191_error_accessors_on_non_err_frame():
    """Test error accessors return None for non-ERR frames"""
    req = Frame.req(MessageId.new_uuid(), "cap:op=test", b"", "text/plain")
    assert req.error_code() is None, "REQ must have no error_code"
    assert req.error_message() is None, "REQ must have no error_message"

    hello = Frame.hello(1000, 500)
    assert hello.error_code() is None


# TEST192: Test log_level and log_message return None for non-Log frame types
def test_192_log_accessors_on_non_log_frame():
    """Test log accessors return None for non-LOG frames"""
    req = Frame.req(MessageId.new_uuid(), "cap:op=test", b"", "text/plain")
    assert req.log_level() is None, "REQ must have no log_level"
    assert req.log_message() is None, "REQ must have no log_message"


# TEST193: Test hello_max_frame and hello_max_chunk return None for non-Hello frame types
def test_193_hello_accessors_on_non_hello_frame():
    """Test hello accessors return None for non-HELLO frames"""
    err = Frame.err(MessageId.new_uuid(), "E", "m")
    assert err.hello_max_frame() is None
    assert err.hello_max_chunk() is None
    assert err.hello_manifest() is None


# TEST194: Test Frame::new sets version and defaults correctly, optional fields are None
def test_194_frame_new_defaults():
    """Test Frame.new sets correct defaults"""
    id = MessageId.new_uuid()
    frame = Frame.new(FrameType.CHUNK, id)
    assert frame.version == PROTOCOL_VERSION
    assert frame.frame_type == FrameType.CHUNK
    assert frame.id == id
    assert frame.seq == 0
    assert frame.content_type is None
    assert frame.meta is None
    assert frame.payload is None
    assert frame.len is None
    assert frame.offset is None
    assert frame.eof is None
    assert frame.cap is None


# TEST195: Test Frame::default creates a Req frame (the documented default)
def test_195_frame_default():
    """Test Frame.default creates REQ frame"""
    frame = Frame.default()
    assert frame.frame_type == FrameType.REQ
    assert frame.version == PROTOCOL_VERSION


# TEST196: Test is_eof returns false when eof field is None (unset)
def test_196_is_eof_when_none():
    """Test is_eof with None"""
    frame = Frame.new(FrameType.CHUNK, MessageId(0))
    assert not frame.is_eof(), "eof=None must mean not EOF"


# TEST197: Test is_eof returns false when eof field is explicitly Some(false)
def test_197_is_eof_when_false():
    """Test is_eof with explicit False"""
    frame = Frame.new(FrameType.CHUNK, MessageId(0))
    frame.eof = False
    assert not frame.is_eof()


# TEST198: Test Limits::default provides the documented default values
def test_198_limits_default():
    """Test Limits.default values"""
    limits = Limits.default()
    assert limits.max_frame == DEFAULT_MAX_FRAME
    assert limits.max_chunk == DEFAULT_MAX_CHUNK
    assert limits.max_frame == 3_670_016, "default max_frame = 3.5 MB"
    assert limits.max_chunk == 262_144, "default max_chunk = 256 KB"


# TEST199: Test PROTOCOL_VERSION is 2
def test_199_protocol_version_constant():
    """Test PROTOCOL_VERSION constant"""
    assert PROTOCOL_VERSION == 2


# TEST200: Test integer key constants match the protocol specification
def test_200_key_constants():
    """Test Keys constants match specification"""
    assert Keys.VERSION == 0
    assert Keys.FRAME_TYPE == 1
    assert Keys.ID == 2
    assert Keys.SEQ == 3
    assert Keys.CONTENT_TYPE == 4
    assert Keys.META == 5
    assert Keys.PAYLOAD == 6
    assert Keys.LEN == 7
    assert Keys.OFFSET == 8
    assert Keys.EOF == 9
    assert Keys.CAP == 10


# TEST201: Test hello_with_manifest preserves binary manifest data (not just JSON text)
def test_201_hello_manifest_binary_data():
    """Test manifest preserves binary data"""
    binary_manifest = bytes([0x00, 0x01, 0xFF, 0xFE, 0x80])
    frame = Frame.hello_with_manifest(1000, 500, binary_manifest)
    assert frame.hello_manifest() == binary_manifest


# TEST202: Test MessageId Eq/Hash semantics: equal UUIDs are equal, different ones are not
def test_202_message_id_equality_and_hash():
    """Test MessageId equality and hashing"""
    id1 = MessageId(bytes([1] * 16))
    id2 = MessageId(bytes([1] * 16))
    id3 = MessageId(bytes([2] * 16))

    assert id1 == id2
    assert id1 != id3

    # Test hashing
    id_set = {id1}
    assert id2 in id_set, "equal IDs must hash the same"
    assert id3 not in id_set

    uint1 = MessageId(42)
    uint2 = MessageId(42)
    uint3 = MessageId(43)

    assert uint1 == uint2
    assert uint1 != uint3


# TEST203: Test Uuid and Uint variants of MessageId are never equal even for coincidental byte values
def test_203_message_id_cross_variant_inequality():
    """Test UUID and Uint variants are never equal"""
    uuid_id = MessageId(bytes([0] * 16))
    uint_id = MessageId(0)
    assert uuid_id != uint_id, "different variants must not be equal"


# TEST204: Test Frame::req with empty payload stores Some(empty vec) not None
def test_204_req_frame_empty_payload():
    """Test REQ frame with empty payload"""
    frame = Frame.req(MessageId.new_uuid(), "cap:op=test", b"", "text/plain")
    assert frame.payload == b"", "empty payload is still bytes, not None"


# TEST365: Frame::stream_start stores req_id, stream_id, media_urn
def test_365_stream_start_frame():
    """Test STREAM_START frame stores all fields"""
    req_id = MessageId.new_uuid()
    stream_id = "stream-abc-123"
    media_urn = "media:"

    frame = Frame.stream_start(req_id, stream_id, media_urn)

    assert frame.frame_type == FrameType.STREAM_START
    assert frame.stream_id == stream_id
    assert frame.media_urn == media_urn
    assert frame.id == req_id


# TEST366: Frame::stream_end stores req_id, stream_id, chunk_count
def test_366_stream_end_frame():
    """Test STREAM_END frame stores req_id and stream_id"""
    req_id = MessageId.new_uuid()
    stream_id = "stream-xyz-456"
    chunk_count = 5

    frame = Frame.stream_end(req_id, stream_id, chunk_count)

    assert frame.frame_type == FrameType.STREAM_END
    assert frame.stream_id == stream_id
    assert frame.chunk_count == chunk_count
    assert frame.media_urn is None, "STREAM_END should not have media_urn"
    assert frame.id == req_id


# TEST367: Frame::stream_start with empty stream_id still constructs
def test_367_stream_start_with_empty_stream_id():
    """Test STREAM_START with empty stream_id"""
    req_id = MessageId.new_uuid()
    frame = Frame.stream_start(req_id, "", "media:json")

    assert frame.frame_type == FrameType.STREAM_START
    assert frame.stream_id == ""
    assert frame.media_urn == "media:json"


# TEST368: Frame::stream_start with empty media_urn still constructs
def test_368_stream_start_with_empty_media_urn():
    """Test STREAM_START with empty media_urn"""
    req_id = MessageId.new_uuid()
    frame = Frame.stream_start(req_id, "stream-test", "")

    assert frame.frame_type == FrameType.STREAM_START
    assert frame.stream_id == "stream-test"
    assert frame.media_urn == ""


# TEST399: RelayNotify discriminant roundtrips through u8 conversion (value 10)
def test_399_relay_notify_discriminant_roundtrip():
    """Test RelayNotify discriminant value is 10 and roundtrips"""
    ft = FrameType.RELAY_NOTIFY
    assert int(ft) == 10
    recovered = FrameType.from_u8(10)
    assert recovered == FrameType.RELAY_NOTIFY


# TEST400: RelayState discriminant roundtrips through u8 conversion (value 11)
def test_400_relay_state_discriminant_roundtrip():
    """Test RelayState discriminant value is 11 and roundtrips"""
    ft = FrameType.RELAY_STATE
    assert int(ft) == 11
    recovered = FrameType.from_u8(11)
    assert recovered == FrameType.RELAY_STATE


# TEST401: relay_notify factory stores manifest and limits, accessors extract them correctly
def test_401_relay_notify_factory_and_accessors():
    """Test relay_notify factory and accessor methods"""
    manifest = b'{"caps":["cap:op=test"]}'
    max_frame = 2_000_000
    max_chunk = 128_000

    frame = Frame.relay_notify(manifest, max_frame, max_chunk)

    assert frame.frame_type == FrameType.RELAY_NOTIFY

    # Test manifest accessor
    extracted_manifest = frame.relay_notify_manifest()
    assert extracted_manifest is not None, "relay_notify_manifest() must not be None"
    assert extracted_manifest == manifest

    # Test limits accessor
    extracted_limits = frame.relay_notify_limits()
    assert extracted_limits is not None, "relay_notify_limits() must not be None"
    assert extracted_limits.max_frame == max_frame
    assert extracted_limits.max_chunk == max_chunk

    # Test accessors on wrong frame type return None
    req = Frame.req(MessageId.new_uuid(), "cap:op=test", b"", "text/plain")
    assert req.relay_notify_manifest() is None
    assert req.relay_notify_limits() is None


# TEST402: relay_state factory stores resource payload in payload field
def test_402_relay_state_factory_and_payload():
    """Test relay_state factory stores resources in payload"""
    resources = b'{"gpu_memory":8192}'

    frame = Frame.relay_state(resources)

    assert frame.frame_type == FrameType.RELAY_STATE
    assert frame.payload == resources


# TEST403: FrameType::from_u8(12) returns None (one past RelayState)
def test_403_frame_type_one_past_relay_state():
    """Test that value 12 is invalid (one past RelayState)"""
    assert FrameType.from_u8(12) is None, "value 12 is one past RelayState"


# TEST667: verify_chunk_checksum detects corrupted payload
def test_667_verify_chunk_checksum_detects_corruption():
    """Test that verify_chunk_checksum detects corrupted payloads"""
    id = MessageId.new_uuid()
    stream_id = "stream-test"
    payload = b"original payload data"
    checksum = compute_checksum(payload)

    # Create valid chunk frame
    frame = Frame.chunk(id, stream_id, 0, payload, 0, checksum)

    # Valid frame should pass verification
    verify_chunk_checksum(frame)  # Should not raise

    # Corrupt the payload (simulate transmission error)
    frame.payload = b"corrupted payload!!"

    # Corrupted frame should fail verification
    with pytest.raises(ValueError) as exc_info:
        verify_chunk_checksum(frame)
    assert "checksum mismatch" in str(exc_info.value)

    # Missing checksum should fail
    frame.checksum = None
    with pytest.raises(ValueError) as exc_info:
        verify_chunk_checksum(frame)
    assert "missing" in str(exc_info.value)


# TEST436: compute_checksum determinism and sensitivity
def test_436_compute_checksum():
    data_a = b"hello world"
    data_b = b"hello world"
    data_c = b"different data"

    checksum_a = compute_checksum(data_a)
    checksum_b = compute_checksum(data_b)
    checksum_c = compute_checksum(data_c)

    # Same data produces same checksum
    assert checksum_a == checksum_b, "Identical data must produce identical checksum"

    # Different data produces different checksum
    assert checksum_a != checksum_c, "Different data must produce different checksum"

    # Non-empty data has non-zero checksum
    assert checksum_a != 0, "Non-empty data should have non-zero checksum"


# TEST442: SeqAssigner assigns monotonically increasing seq for same RID
def test_442_seq_assigner_monotonic_same_rid():
    assigner = SeqAssigner()
    rid = MessageId.random()

    f0 = Frame.req(rid, b"cap:op=test", b"")
    f1 = Frame.stream_start(rid, b"media:text")
    f2 = Frame.chunk(rid, b"payload")
    f3 = Frame.end(rid)

    assigner.assign(f0)
    assigner.assign(f1)
    assigner.assign(f2)
    assigner.assign(f3)

    assert f0.seq == 0
    assert f1.seq == 1
    assert f2.seq == 2
    assert f3.seq == 3


# TEST443: SeqAssigner maintains independent per-RID counters
def test_443_seq_assigner_independent_rids():
    assigner = SeqAssigner()
    rid_a = MessageId.random()
    rid_b = MessageId.random()

    a0 = Frame.req(rid_a, b"cap:op=a", b"")
    a1 = Frame.stream_start(rid_a, b"media:text")
    a2 = Frame.chunk(rid_a, b"payload")
    b0 = Frame.req(rid_b, b"cap:op=b", b"")
    b1 = Frame.stream_start(rid_b, b"media:text")

    assigner.assign(a0)
    assigner.assign(a1)
    assigner.assign(a2)
    assigner.assign(b0)
    assigner.assign(b1)

    assert a0.seq == 0
    assert a1.seq == 1
    assert a2.seq == 2
    assert b0.seq == 0
    assert b1.seq == 1


# TEST444: SeqAssigner skips non-flow frames
def test_444_seq_assigner_skips_non_flow():
    assigner = SeqAssigner()

    hello = Frame.hello(DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK)
    heartbeat = Frame.heartbeat()

    assigner.assign(hello)
    assigner.assign(heartbeat)

    assert hello.seq == 0, "Hello seq should remain 0"
    assert heartbeat.seq == 0, "Heartbeat seq should remain 0"


# TEST445: SeqAssigner remove resets only the matching flow counter
def test_445_seq_assigner_remove_by_flow_key():
    assigner = SeqAssigner()
    rid = MessageId.random()
    xid = MessageId.random()

    # Flow 1: (rid, no xid) — seq 0, 1
    f0 = Frame.req(rid, b"cap:op=test", b"")
    f1 = Frame.stream_start(rid, b"media:text")
    assigner.assign(f0)
    assigner.assign(f1)
    assert f0.seq == 0
    assert f1.seq == 1

    # Flow 2: (rid, xid) — seq 0, 1
    f2 = Frame.req(rid, b"cap:op=test", b"")
    f2.routing_id = xid
    f3 = Frame.stream_start(rid, b"media:text")
    f3.routing_id = xid
    assigner.assign(f2)
    assigner.assign(f3)
    assert f2.seq == 0
    assert f3.seq == 1

    # Remove flow 1 only
    key1 = FlowKey(rid.to_string(), "")
    assigner.remove(key1)

    # Flow 1 restarts at 0
    f4 = Frame.chunk(rid, b"payload")
    assigner.assign(f4)
    assert f4.seq == 0

    # Flow 2 continues at 2
    f5 = Frame.chunk(rid, b"payload")
    f5.routing_id = xid
    assigner.assign(f5)
    assert f5.seq == 2


# TEST445a: SeqAssigner same RID different XIDs are independent
def test_445a_seq_assigner_same_rid_different_xids_independent():
    assigner = SeqAssigner()
    rid = MessageId.random()
    xid_a = MessageId.random()
    xid_b = MessageId.random()

    # Flow (rid, xid_a): 0, 1
    fa0 = Frame.req(rid, b"cap:op=a", b"")
    fa0.routing_id = xid_a
    fa1 = Frame.stream_start(rid, b"media:text")
    fa1.routing_id = xid_a
    assigner.assign(fa0)
    assigner.assign(fa1)
    assert fa0.seq == 0
    assert fa1.seq == 1

    # Flow (rid, xid_b): 0
    fb0 = Frame.req(rid, b"cap:op=b", b"")
    fb0.routing_id = xid_b
    assigner.assign(fb0)
    assert fb0.seq == 0

    # Flow (rid, None): 0
    fn0 = Frame.req(rid, b"cap:op=n", b"")
    assigner.assign(fn0)
    assert fn0.seq == 0


# TEST446: SeqAssigner counts across mixed flow frame types
def test_446_seq_assigner_mixed_types():
    assigner = SeqAssigner()
    rid = MessageId.random()

    f_req = Frame.req(rid, b"cap:op=test", b"")
    f_log = Frame.log(rid, b"log message")
    f_chunk = Frame.chunk(rid, b"payload")
    f_end = Frame.end(rid)

    assigner.assign(f_req)
    assigner.assign(f_log)
    assigner.assign(f_chunk)
    assigner.assign(f_end)

    assert f_req.seq == 0
    assert f_log.seq == 1
    assert f_chunk.seq == 2
    assert f_end.seq == 3


# TEST447: FlowKey from frame with routing_id extracts (rid, xid)
def test_447_flow_key_with_xid():
    rid = MessageId.random()
    xid = MessageId.random()

    frame = Frame.req(rid, b"cap:op=test", b"")
    frame.routing_id = xid

    key = FlowKey.from_frame(frame)
    assert key._rid == rid.to_string()
    assert key._xid == xid.to_string()


# TEST448: FlowKey from frame without routing_id extracts (rid, "")
def test_448_flow_key_without_xid():
    rid = MessageId.random()

    frame = Frame.req(rid, b"cap:op=test", b"")
    key = FlowKey.from_frame(frame)
    assert key._rid == rid.to_string()
    assert key._xid == ""


# TEST449: FlowKey equality semantics
def test_449_flow_key_equality():
    rid = MessageId.random()
    xid = MessageId.random()

    key1 = FlowKey(rid.to_string(), xid.to_string())
    key2 = FlowKey(rid.to_string(), xid.to_string())
    key3 = FlowKey(rid.to_string(), "")

    assert key1 == key2, "Same rid+xid should be equal"
    assert key1 != key3, "Different xid should not be equal"


# TEST450: FlowKey hash allows HashMap lookup
def test_450_flow_key_hash_lookup():
    rid = MessageId.random()
    xid = MessageId.random()

    key1 = FlowKey(rid.to_string(), xid.to_string())
    key2 = FlowKey(rid.to_string(), xid.to_string())

    d = {key1: "value"}
    assert d[key2] == "value", "Identical keys should hash to same bucket"


# =============================================================================
# REORDER BUFFER TESTS
# =============================================================================


# Helper: create a flow frame with given type, rid, and seq
def _flow_frame(frame_type, rid, seq):
    f = Frame.new(frame_type, rid)
    f.seq = seq
    return f


# TEST451: ReorderBuffer delivers frames immediately when in order
def test_451_reorder_buffer_in_order():
    rb = ReorderBuffer(max_buffer_per_flow=10)
    rid = MessageId.random()

    r0 = rb.accept(_flow_frame(FrameType.REQ, rid, 0))
    assert len(r0) == 1

    r1 = rb.accept(_flow_frame(FrameType.CHUNK, rid, 1))
    assert len(r1) == 1

    r2 = rb.accept(_flow_frame(FrameType.END, rid, 2))
    assert len(r2) == 1


# TEST452: ReorderBuffer holds out-of-order, releases when gap filled
def test_452_reorder_buffer_out_of_order():
    rb = ReorderBuffer(max_buffer_per_flow=10)
    rid = MessageId.random()

    # Submit seq=1 before seq=0
    r1 = rb.accept(_flow_frame(FrameType.CHUNK, rid, 1))
    assert len(r1) == 0, "seq=1 before seq=0 should be buffered"

    # Submit seq=0 — should release both
    r0 = rb.accept(_flow_frame(FrameType.REQ, rid, 0))
    assert len(r0) == 2, "seq=0 should release seq=0 and seq=1"
    assert r0[0].seq == 0
    assert r0[1].seq == 1


# TEST453: ReorderBuffer gap fill with arrival order 0, 2, 1
def test_453_reorder_buffer_gap_fill():
    rb = ReorderBuffer(max_buffer_per_flow=10)
    rid = MessageId.random()

    r0 = rb.accept(_flow_frame(FrameType.REQ, rid, 0))
    assert len(r0) == 1, "seq=0 delivers immediately"

    r2 = rb.accept(_flow_frame(FrameType.END, rid, 2))
    assert len(r2) == 0, "seq=2 buffered (gap at seq=1)"

    r1 = rb.accept(_flow_frame(FrameType.CHUNK, rid, 1))
    assert len(r1) == 2, "seq=1 fills gap, releases seq=1 and seq=2"
    assert r1[0].seq == 1
    assert r1[1].seq == 2


# TEST454: ReorderBuffer rejects stale/duplicate seq
def test_454_reorder_buffer_stale_seq():
    rb = ReorderBuffer(max_buffer_per_flow=10)
    rid = MessageId.random()

    rb.accept(_flow_frame(FrameType.REQ, rid, 0))
    rb.accept(_flow_frame(FrameType.CHUNK, rid, 1))

    # Submit stale seq=0 again
    with pytest.raises(ProtocolError, match="stale"):
        rb.accept(_flow_frame(FrameType.CHUNK, rid, 0))


# TEST455: ReorderBuffer overflow
def test_455_reorder_buffer_overflow():
    rb = ReorderBuffer(max_buffer_per_flow=3)
    rid = MessageId.random()

    # Submit seq 1,2,3,4 (never seq 0) — 4th should overflow
    for i in range(1, 4):
        rb.accept(_flow_frame(FrameType.CHUNK, rid, i))

    with pytest.raises(ProtocolError, match="overflow"):
        rb.accept(_flow_frame(FrameType.CHUNK, rid, 4))


# TEST456: ReorderBuffer independent flows
def test_456_reorder_buffer_independent_flows():
    rb = ReorderBuffer(max_buffer_per_flow=10)
    rid_a = MessageId.random()
    rid_b = MessageId.random()

    # Flow A: submit seq=1 (out of order)
    ra1 = rb.accept(_flow_frame(FrameType.CHUNK, rid_a, 1))
    assert len(ra1) == 0, "A seq=1 buffered"

    # Flow B: submit seq=0 (in order) — independent of A
    rb0 = rb.accept(_flow_frame(FrameType.REQ, rid_b, 0))
    assert len(rb0) == 1, "B seq=0 delivers immediately regardless of A's gap"

    # Flow A: submit seq=0 — releases both A frames
    ra0 = rb.accept(_flow_frame(FrameType.REQ, rid_a, 0))
    assert len(ra0) == 2, "A seq=0 releases seq=0 and seq=1"


# TEST457: ReorderBuffer cleanup_flow resets state
def test_457_reorder_buffer_cleanup():
    rb = ReorderBuffer(max_buffer_per_flow=10)
    rid = MessageId.random()

    f0 = _flow_frame(FrameType.REQ, rid, 0)
    rb.accept(f0)
    rb.accept(_flow_frame(FrameType.CHUNK, rid, 1))

    # Cleanup the flow
    key = FlowKey.from_frame(f0)
    rb.cleanup_flow(key)

    # Same RID can start over at seq=0 without stale error
    r = rb.accept(_flow_frame(FrameType.REQ, rid, 0))
    assert len(r) == 1


# TEST458: ReorderBuffer non-flow frames bypass reordering
def test_458_reorder_buffer_non_flow_bypass():
    rb = ReorderBuffer(max_buffer_per_flow=10)

    hello = Frame.hello(DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK, DEFAULT_MAX_REORDER_BUFFER)
    hb = Frame.heartbeat(MessageId.random())
    rn = Frame.relay_notify(b"", DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK, DEFAULT_MAX_REORDER_BUFFER)
    rs = Frame.relay_state(b"")

    for frame in [hello, hb, rn, rs]:
        r = rb.accept(frame)
        assert len(r) == 1, f"Non-flow frame {frame.frame_type} should bypass reorder buffer"


# TEST459: ReorderBuffer handles END frame correctly
def test_459_reorder_buffer_end_frame():
    rb = ReorderBuffer(max_buffer_per_flow=10)
    rid = MessageId.random()

    rb.accept(_flow_frame(FrameType.REQ, rid, 0))

    end = _flow_frame(FrameType.END, rid, 1)
    r = rb.accept(end)
    assert len(r) == 1
    assert r[0].frame_type == FrameType.END
    assert r[0].seq == 1


# TEST460: ReorderBuffer handles ERR frame correctly
def test_460_reorder_buffer_err_frame():
    rb = ReorderBuffer(max_buffer_per_flow=10)
    rid = MessageId.random()

    rb.accept(_flow_frame(FrameType.REQ, rid, 0))

    err = _flow_frame(FrameType.ERR, rid, 1)
    r = rb.accept(err)
    assert len(r) == 1
    assert r[0].frame_type == FrameType.ERR
    assert r[0].seq == 1
    assert r[0].seq == 1


# =========================================================================
# Tests 491-528, 902-904, 907 — checksum, chunk_index, chunk_count, CBOR roundtrips
# =========================================================================

from capdag.bifaci.io import encode_frame, decode_frame, InvalidFrameError


# TEST491: CHUNK frame requires chunk_index and checksum
def test_491_chunk_requires_chunk_index_and_checksum():
    req_id = MessageId.random()
    payload = b"test data"
    checksum = compute_checksum(payload)

    frame = Frame.chunk(req_id, "stream-1", 0, payload, 5, checksum)

    assert frame.frame_type == FrameType.CHUNK
    assert frame.chunk_index == 5, "chunk_index must be set"
    assert frame.checksum == checksum, "checksum must be set"
    assert frame.payload == payload


# TEST492: STREAM_END frame requires and sets chunk_count
def test_492_stream_end_requires_chunk_count():
    req_id = MessageId.random()
    frame = Frame.stream_end(req_id, "stream-1", 42)

    assert frame.frame_type == FrameType.STREAM_END
    assert frame.chunk_count == 42, "chunk_count must be set"
    assert frame.stream_id == "stream-1"


# TEST493: compute_checksum produces correct FNV-1a hash for known test vectors
def test_493_compute_checksum_fnv1a_test_vectors():
    assert compute_checksum(b"") == 0xcbf29ce484222325, "empty string hash"
    assert compute_checksum(b"a") == 0xaf63dc4c8601ec8c, "single byte 'a'"
    assert compute_checksum(b"foobar") == 0x85944171f73967e8, "foobar string"


# TEST494: compute_checksum is deterministic
def test_494_compute_checksum_deterministic():
    data = b"test data for hashing"
    hash1 = compute_checksum(data)
    hash2 = compute_checksum(data)
    hash3 = compute_checksum(data)
    assert hash1 == hash2
    assert hash2 == hash3


# TEST495: CBOR decode REJECTS CHUNK frame missing chunk_index field
def test_495_cbor_rejects_chunk_without_chunk_index():
    req_id = MessageId.random()
    payload = b"data"
    checksum = compute_checksum(payload)

    # Create frame without chunk_index to simulate corruption
    frame = Frame.new(FrameType.CHUNK, req_id)
    frame.stream_id = "s1"
    frame.payload = payload
    frame.checksum = checksum
    # chunk_index deliberately missing (None)

    encoded = encode_frame(frame)

    with pytest.raises(InvalidFrameError, match="chunk_index"):
        decode_frame(encoded)


# TEST496: CBOR decode REJECTS CHUNK frame missing checksum field
def test_496_cbor_rejects_chunk_without_checksum():
    req_id = MessageId.random()
    payload = b"data"

    frame = Frame.new(FrameType.CHUNK, req_id)
    frame.stream_id = "s1"
    frame.payload = payload
    frame.chunk_index = 0
    # checksum deliberately missing (None)

    encoded = encode_frame(frame)

    with pytest.raises(InvalidFrameError, match="checksum"):
        decode_frame(encoded)


# TEST497: chunk corrupted payload is detected by checksum mismatch
def test_497_chunk_corrupted_payload_rejected():
    req_id = MessageId.random()
    payload = b"original data"
    checksum = compute_checksum(payload)

    frame = Frame.chunk(req_id, "s1", 0, payload, 0, checksum)

    # Verify valid frame
    assert verify_chunk_checksum(frame) is True

    # Corrupt the payload
    frame.payload = b"corrupted!"
    assert verify_chunk_checksum(frame) is False


# TEST498: routing_id field roundtrips through CBOR encoding
def test_498_routing_id_cbor_roundtrip():
    req_id = MessageId.random()
    routing_id = MessageId.random()

    frame = Frame.req(req_id, 'cap:in="media:void";op=test;out="media:void"', b"", "text/plain")
    frame.routing_id = routing_id

    encoded = encode_frame(frame)
    decoded = decode_frame(encoded)

    assert decoded.routing_id == routing_id, "routing_id must roundtrip"
    assert decoded.id == req_id


# TEST499: chunk_index and checksum roundtrip through CBOR encoding
def test_499_chunk_index_checksum_cbor_roundtrip():
    req_id = MessageId.random()
    payload = b"test payload"
    checksum = compute_checksum(payload)

    frame = Frame.chunk(req_id, "s1", 0, payload, 7, checksum)

    encoded = encode_frame(frame)
    decoded = decode_frame(encoded)

    assert decoded.chunk_index == 7, "chunk_index must roundtrip"
    assert decoded.checksum == checksum, "checksum must roundtrip"
    assert decoded.payload == payload


# TEST500: chunk_count roundtrips through CBOR encoding
def test_500_chunk_count_cbor_roundtrip():
    req_id = MessageId.random()

    frame = Frame.stream_end(req_id, "s1", 42)

    encoded = encode_frame(frame)
    decoded = decode_frame(encoded)

    assert decoded.chunk_count == 42, "chunk_count must roundtrip"
    assert decoded.stream_id == "s1"


# TEST501: Frame.new initializes new fields to None
def test_501_frame_new_initializes_optional_fields_none():
    frame = Frame.new(FrameType.REQ, MessageId.random())

    assert frame.routing_id is None
    assert frame.chunk_index is None
    assert frame.chunk_count is None
    assert frame.checksum is None


# TEST502: Keys module has constants for new fields
def test_502_keys_module_new_field_constants():
    assert Keys.ROUTING_ID == 13
    assert Keys.INDEX == 14
    assert Keys.CHUNK_COUNT == 15
    assert Keys.CHECKSUM == 16


# TEST503: compute_checksum handles empty data correctly
def test_503_compute_checksum_empty_data():
    h = compute_checksum(b"")
    assert h == 0xcbf29ce484222325, "empty data should produce FNV offset basis"


# TEST504: compute_checksum handles large payloads without overflow
def test_504_compute_checksum_large_payload():
    large_data = bytes([0xAA] * 1_000_000)
    h = compute_checksum(large_data)
    assert h != 0, "large payload should produce non-zero hash"

    h2 = compute_checksum(large_data)
    assert h == h2, "large payload hash must be deterministic"


# TEST505: chunk_with_offset sets chunk_index correctly
def test_505_chunk_with_offset_sets_chunk_index():
    req_id = MessageId.random()
    payload = b"data"
    checksum = compute_checksum(payload)

    frame = Frame.chunk_with_offset(
        req_id=req_id,
        stream_id="s1",
        seq=0,
        payload=payload,
        offset=1024,
        total_len=10000,
        is_last=False,
        chunk_index=5,
        checksum=checksum,
    )

    assert frame.chunk_index == 5, "chunk_index must be set"
    assert frame.checksum == checksum, "checksum must be set"
    assert frame.offset == 1024


# TEST506: Different data produces different checksums
def test_506_compute_checksum_different_data_different_hash():
    data1 = b"hello"
    data2 = b"world"

    hash1 = compute_checksum(data1)
    hash2 = compute_checksum(data2)

    assert hash1 != hash2, "different data must produce different hashes"


# TEST507: ReorderBuffer isolates flows by XID (routing_id)
def test_507_reorder_buffer_xid_isolation():
    buf = ReorderBuffer(max_buffer_per_flow=64)
    rid = MessageId.random()
    xid_a = MessageId.random()
    xid_b = MessageId.random()

    def make_xid_frame(rid, xid, seq):
        f = Frame.new(FrameType.CHUNK, rid)
        f.seq = seq
        f.routing_id = xid
        return f

    # Flow A: receive seq 1 first
    ready_a1 = buf.accept(make_xid_frame(rid, xid_a, 1))
    assert len(ready_a1) == 0, "xid_a seq 1 buffered"

    # Flow B: receive seq 0 (different flow, should deliver immediately)
    ready_b0 = buf.accept(make_xid_frame(rid, xid_b, 0))
    assert len(ready_b0) == 1, "xid_b seq 0 delivers immediately"

    # Flow A: receive seq 0, should deliver 0+1
    ready_a0 = buf.accept(make_xid_frame(rid, xid_a, 0))
    assert len(ready_a0) == 2, "xid_a delivers 0 and buffered 1"
    assert ready_a0[0].seq == 0
    assert ready_a0[1].seq == 1


# TEST508: ReorderBuffer rejects duplicate seq already in buffer
def test_508_reorder_buffer_duplicate_buffered_seq():
    buf = ReorderBuffer(max_buffer_per_flow=64)
    rid = MessageId.random()

    # Buffer seq 1 (waiting for seq 0)
    buf.accept(_flow_frame(FrameType.CHUNK, rid, 1))

    # Try to buffer seq 1 again - this is a duplicate
    with pytest.raises(Exception, match="stale|duplicate"):
        buf.accept(_flow_frame(FrameType.CHUNK, rid, 1))


# TEST509: ReorderBuffer handles large seq gaps without DOS
def test_509_reorder_buffer_large_gap_rejected():
    buf = ReorderBuffer(max_buffer_per_flow=64)
    rid = MessageId.random()

    buf.accept(_flow_frame(FrameType.REQ, rid, 0))

    # Buffer frames until we hit the limit
    for seq in range(2, 66):
        buf.accept(_flow_frame(FrameType.CHUNK, rid, seq))

    # This should overflow the buffer
    with pytest.raises(Exception, match="overflow"):
        buf.accept(_flow_frame(FrameType.CHUNK, rid, 66))


# TEST510: ReorderBuffer with multiple interleaved gaps fills correctly
def test_510_reorder_buffer_multiple_gaps():
    buf = ReorderBuffer(max_buffer_per_flow=64)
    rid = MessageId.random()

    # Send: 0, 3, 5, then fill the gaps
    ready0 = buf.accept(_flow_frame(FrameType.REQ, rid, 0))
    assert len(ready0) == 1

    ready3 = buf.accept(_flow_frame(FrameType.CHUNK, rid, 3))
    assert len(ready3) == 0, "seq 3 buffered"

    ready5 = buf.accept(_flow_frame(FrameType.CHUNK, rid, 5))
    assert len(ready5) == 0, "seq 5 buffered"

    # Fill gap with seq 1
    ready1 = buf.accept(_flow_frame(FrameType.CHUNK, rid, 1))
    assert len(ready1) == 1, "only seq 1 delivered, still missing 2"

    # Fill gap with seq 2 - should deliver 2, 3
    ready2 = buf.accept(_flow_frame(FrameType.CHUNK, rid, 2))
    assert len(ready2) == 2, "delivers 2 and 3"
    assert ready2[0].seq == 2
    assert ready2[1].seq == 3

    # Fill final gap with seq 4 - should deliver 4, 5
    ready4 = buf.accept(_flow_frame(FrameType.CHUNK, rid, 4))
    assert len(ready4) == 2, "delivers 4 and 5"
    assert ready4[0].seq == 4
    assert ready4[1].seq == 5


# TEST511: ReorderBuffer cleanup with buffered frames discards them
def test_511_reorder_buffer_cleanup_with_buffered_frames():
    buf = ReorderBuffer(max_buffer_per_flow=64)
    rid = MessageId.random()

    buf.accept(_flow_frame(FrameType.REQ, rid, 0))
    buf.accept(_flow_frame(FrameType.CHUNK, rid, 2))  # buffered
    buf.accept(_flow_frame(FrameType.CHUNK, rid, 3))  # buffered

    key = FlowKey(rid=rid, xid=None)
    buf.cleanup_flow(key)

    # After cleanup, seq 0 should work again (flow reset)
    ready = buf.accept(_flow_frame(FrameType.REQ, rid, 0))
    assert len(ready) == 1
    assert ready[0].seq == 0


# TEST512: ReorderBuffer delivers burst of consecutive buffered frames
def test_512_reorder_buffer_burst_delivery():
    buf = ReorderBuffer(max_buffer_per_flow=64)
    rid = MessageId.random()

    # Buffer seq 1-10 (all waiting for seq 0)
    for seq in range(1, 11):
        ready = buf.accept(_flow_frame(FrameType.CHUNK, rid, seq))
        assert len(ready) == 0, f"seq {seq} buffered"

    # Now send seq 0 - should deliver all 11 frames at once
    ready = buf.accept(_flow_frame(FrameType.REQ, rid, 0))
    assert len(ready) == 11, "delivers seq 0 plus 10 buffered frames"
    for i, frame in enumerate(ready):
        assert frame.seq == i, f"frame {i} has correct seq"


# TEST513: ReorderBuffer different frame types in same flow maintain order
def test_513_reorder_buffer_mixed_types_same_flow():
    buf = ReorderBuffer(max_buffer_per_flow=64)
    rid = MessageId.random()

    req = Frame.new(FrameType.REQ, rid)
    req.seq = 1
    log = Frame.new(FrameType.LOG, rid)
    log.seq = 2
    chunk = Frame.new(FrameType.CHUNK, rid)
    chunk.seq = 0

    # Send out of order: REQ(1), LOG(2), then CHUNK(0)
    buf.accept(req)  # buffered
    buf.accept(log)  # buffered

    ready = buf.accept(chunk)
    assert len(ready) == 3, "all three frames delivered in order"
    assert ready[0].frame_type == FrameType.CHUNK
    assert ready[1].frame_type == FrameType.REQ
    assert ready[2].frame_type == FrameType.LOG


# TEST514: ReorderBuffer with XID cleanup doesn't affect different XID
def test_514_reorder_buffer_xid_cleanup_isolation():
    buf = ReorderBuffer(max_buffer_per_flow=64)
    rid = MessageId.random()
    xid_a = MessageId.random()
    xid_b = MessageId.random()

    def make_xid_frame(rid, xid, seq):
        f = Frame.new(FrameType.CHUNK, rid)
        f.seq = seq
        f.routing_id = xid
        return f

    buf.accept(make_xid_frame(rid, xid_a, 0))
    buf.accept(make_xid_frame(rid, xid_b, 0))

    # Cleanup flow A
    key_a = FlowKey(rid=rid, xid=xid_a)
    buf.cleanup_flow(key_a)

    # Flow B should still expect seq 1
    ready = buf.accept(make_xid_frame(rid, xid_b, 1))
    assert len(ready) == 1
    assert ready[0].seq == 1

    # Flow A was reset, seq 0 works again
    ready_a = buf.accept(make_xid_frame(rid, xid_a, 0))
    assert len(ready_a) == 1


# TEST515: ReorderBuffer overflow error includes diagnostic information
def test_515_reorder_buffer_overflow_error_details():
    max_buffer = 3
    buf = ReorderBuffer(max_buffer_per_flow=max_buffer)
    rid = MessageId.random()

    # Fill buffer to capacity
    for seq in range(1, 4):
        buf.accept(_flow_frame(FrameType.CHUNK, rid, seq))

    # Overflow
    with pytest.raises(Exception, match="overflow") as exc_info:
        buf.accept(_flow_frame(FrameType.CHUNK, rid, 4))

    err = str(exc_info.value)
    assert "overflow" in err.lower()


# TEST516: ReorderBuffer stale error includes diagnostic information
def test_516_reorder_buffer_stale_error_details():
    buf = ReorderBuffer(max_buffer_per_flow=64)
    rid = MessageId.random()

    buf.accept(_flow_frame(FrameType.REQ, rid, 0))
    buf.accept(_flow_frame(FrameType.CHUNK, rid, 1))
    buf.accept(_flow_frame(FrameType.CHUNK, rid, 2))

    # Send stale seq 1
    with pytest.raises(Exception, match="stale|duplicate"):
        buf.accept(_flow_frame(FrameType.CHUNK, rid, 1))


# TEST517: FlowKey with None XID differs from Some(xid)
def test_517_flow_key_none_vs_some_xid():
    rid = MessageId.random()
    xid = MessageId.random()

    key_none = FlowKey(rid=rid, xid=None)
    key_some = FlowKey(rid=rid, xid=xid)

    assert key_none != key_some, "None XID must differ from Some(xid)"
    assert hash(key_none) != hash(key_some), "different XID states must hash differently"


# TEST518: ReorderBuffer handles zero-length ready vec correctly
def test_518_reorder_buffer_empty_ready_vec():
    buf = ReorderBuffer(max_buffer_per_flow=64)
    rid = MessageId.random()

    # Send seq 1 first - should return empty list (buffered)
    ready = buf.accept(_flow_frame(FrameType.CHUNK, rid, 1))
    assert len(ready) == 0, "buffered frame returns empty list"


# TEST519: ReorderBuffer state persists across accept calls
def test_519_reorder_buffer_state_persistence():
    buf = ReorderBuffer(max_buffer_per_flow=64)
    rid = MessageId.random()

    # First call: buffer seq 2
    buf.accept(_flow_frame(FrameType.CHUNK, rid, 2))

    # Second call: send seq 1, should still be buffered (missing 0)
    ready = buf.accept(_flow_frame(FrameType.CHUNK, rid, 1))
    assert len(ready) == 0, "seq 1 buffered, still waiting for seq 0"

    # Third call: send seq 0, should deliver 0, 1, 2
    ready = buf.accept(_flow_frame(FrameType.REQ, rid, 0))
    assert len(ready) == 3, "state persisted correctly"


# TEST520: ReorderBuffer max_buffer_per_flow is per-flow not global
def test_520_reorder_buffer_per_flow_limit():
    buf = ReorderBuffer(max_buffer_per_flow=2)
    rid_a = MessageId.random()
    rid_b = MessageId.random()

    # Flow A: buffer 2 frames (at limit)
    buf.accept(_flow_frame(FrameType.CHUNK, rid_a, 1))
    buf.accept(_flow_frame(FrameType.CHUNK, rid_a, 2))

    # Flow B: can still buffer 2 frames (separate limit)
    buf.accept(_flow_frame(FrameType.CHUNK, rid_b, 1))
    buf.accept(_flow_frame(FrameType.CHUNK, rid_b, 2))

    # Flow A: overflow
    with pytest.raises(Exception, match="overflow"):
        buf.accept(_flow_frame(FrameType.CHUNK, rid_a, 3))

    # Flow B: also overflow
    with pytest.raises(Exception, match="overflow"):
        buf.accept(_flow_frame(FrameType.CHUNK, rid_b, 3))


# TEST521: RelayNotify CBOR roundtrip preserves manifest and limits
def test_521_relay_notify_cbor_roundtrip():
    manifest = b'{"caps":["cap:in=\\"media:void\\";op=convert;out=\\"media:image\\""}'
    frame = Frame.relay_notify(manifest, 3_000_000, 256_000, 128)

    encoded = encode_frame(frame)
    decoded = decode_frame(encoded)

    assert decoded.frame_type == FrameType.RELAY_NOTIFY
    assert decoded.relay_notify_manifest() == manifest, "manifest must roundtrip"

    decoded_limits = decoded.relay_notify_limits()
    assert decoded_limits is not None, "limits must be present"
    assert decoded_limits.max_frame == 3_000_000, "max_frame must roundtrip"
    assert decoded_limits.max_chunk == 256_000, "max_chunk must roundtrip"
    assert decoded_limits.max_reorder_buffer == 128, "max_reorder_buffer must roundtrip"


# TEST522: RelayState CBOR roundtrip preserves payload
def test_522_relay_state_cbor_roundtrip():
    state_data = b'{"memory_mb":8192,"cpu_cores":16,"active_flows":42}'
    frame = Frame.relay_state(state_data)

    encoded = encode_frame(frame)
    decoded = decode_frame(encoded)

    assert decoded.frame_type == FrameType.RELAY_STATE
    assert decoded.payload == state_data, "state payload must roundtrip exactly"
    assert decoded.id == MessageId(0)


# TEST523: is_flow_frame returns false for RelayNotify
def test_523_relay_notify_not_flow_frame():
    frame = Frame.relay_notify(b"test", DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK)
    assert not frame.is_flow_frame(), "RelayNotify must not be a flow frame"


# TEST524: is_flow_frame returns false for RelayState
def test_524_relay_state_not_flow_frame():
    frame = Frame.relay_state(b"test")
    assert not frame.is_flow_frame(), "RelayState must not be a flow frame"


# TEST525: RelayNotify with empty manifest is valid
def test_525_relay_notify_empty_manifest():
    frame = Frame.relay_notify(b"", DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK)
    assert frame.frame_type == FrameType.RELAY_NOTIFY
    assert frame.relay_notify_manifest() == b""


# TEST526: RelayState with empty payload is valid
def test_526_relay_state_empty_payload():
    frame = Frame.relay_state(b"")
    assert frame.frame_type == FrameType.RELAY_STATE
    assert frame.payload == b""


# TEST527: RelayNotify with large manifest roundtrips correctly
def test_527_relay_notify_large_manifest():
    parts = [f'"cap:in=\\"media:void\\";op=op{i};out=\\"media:void\\""' for i in range(100)]
    large_manifest = ('{"caps":[' + ",".join(parts) + "]}").encode()

    frame = Frame.relay_notify(large_manifest, DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK)

    encoded = encode_frame(frame)
    decoded = decode_frame(encoded)

    assert decoded.relay_notify_manifest() == large_manifest


# TEST528: RelayNotify and RelayState use MessageId(0)
def test_528_relay_frames_use_uint_zero_id():
    notify = Frame.relay_notify(b"test", DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK)
    state = Frame.relay_state(b"test")

    assert notify.id == MessageId(0), "RelayNotify must use Uint(0) as sentinel ID"
    assert state.id == MessageId(0), "RelayState must use Uint(0) as sentinel ID"


# TEST902: Verify FNV-1a checksum handles empty data
def test_902_compute_checksum_empty():
    checksum = compute_checksum(b"")
    assert checksum == 0xcbf29ce484222325, "empty data produces FNV offset basis"


# TEST903: Verify CHUNK frame can store chunk_index and checksum fields
def test_903_chunk_with_chunk_index_and_checksum():
    rid = MessageId.random()
    payload = b"chunk data"
    checksum = compute_checksum(payload)

    frame = Frame.chunk(rid, "test-stream", 5, payload, 3, checksum)

    assert frame.frame_type == FrameType.CHUNK
    assert frame.id == rid
    assert frame.stream_id == "test-stream"
    assert frame.seq == 5
    assert frame.chunk_index == 3, "chunk_index should be set"
    assert frame.checksum == checksum, "checksum should be set"


# TEST904: Verify STREAM_END frame can store chunk_count field
def test_904_stream_end_with_chunk_count():
    rid = MessageId.random()
    frame = Frame.stream_end(rid, "test-stream", 42)

    assert frame.frame_type == FrameType.STREAM_END
    assert frame.id == rid
    assert frame.stream_id == "test-stream"
    assert frame.chunk_count == 42, "chunk_count should be set"


# TEST907: CBOR decode REJECTS STREAM_END frame missing chunk_count field
def test_907_cbor_rejects_stream_end_without_chunk_count():
    req_id = MessageId.random()

    # Create STREAM_END without chunk_count
    frame = Frame.new(FrameType.STREAM_END, req_id)
    frame.stream_id = "s1"
    # chunk_count deliberately missing (None)

    encoded = encode_frame(frame)

    with pytest.raises(InvalidFrameError, match="chunk_count"):
        decode_frame(encoded)
