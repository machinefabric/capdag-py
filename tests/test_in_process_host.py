"""Tests for InProcessCartridgeHost — direct dispatch to in-process FrameHandlers.

Mirrors the Rust ``bifaci::in_process_host`` test module 1:1. The host speaks
the Frame protocol over a socket pair: it emits an initial RelayNotify, then
routes REQ frames to registered FrameHandler objects (or the built-in identity
handler) and forwards continuation frames by request id.

The Python mirror is thread-based (blocking FrameReader/FrameWriter), so each
test runs the host in a daemon thread and drives it from the test thread.
"""

import json
import socket
import threading

import cbor2

from capdag.bifaci.in_process_host import (
    FrameHandler,
    InProcessCartridgeHost,
    InProcessHostIdentity,
    ResponseWriter,
    accumulate_input,
)
from capdag.bifaci.frame import Frame, FrameType, MessageId, compute_checksum
from capdag.bifaci.io import FrameReader, FrameWriter, identity_nonce
from capdag.bifaci import decode_chunk_payload
from capdag.cap.definition import Cap
from capdag.urn.cap_urn import CapUrn
from capdag.standard.caps import CAP_IDENTITY


def make_test_cap(urn_str: str) -> Cap:
    return Cap(CapUrn.from_string(urn_str), "test", "")


def cbor_bytes_payload(data: bytes) -> bytes:
    """Build a CBOR-encoded chunk payload from raw bytes (matching the wire format)."""
    return cbor2.dumps(data)


def make_host_conn():
    """Create a socket pair connecting the host to a test driver.

    Returns (host_read, host_write, test_reader, test_writer, host_socks, test_socks).
    The host reads what the test writes and vice versa.
    """
    # Channel 1: test writes -> host reads
    s1a, s1b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    # Channel 2: host writes -> test reads
    s2a, s2b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)

    host_read = s1a.makefile("rb")
    test_write = s1b.makefile("wb")
    host_write = s2a.makefile("wb")
    test_read = s2b.makefile("rb")

    return host_read, host_write, test_read, test_write, [s1a, s2a], [s1b, s2b]


def close_socks(socks):
    for s in socks:
        try:
            s.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            s.close()
        except Exception:
            pass


def _aggregate_cap_urns(payload: dict):
    out = []
    for ic in payload.get("installed_cartridges", []):
        for group in ic.get("cap_groups", []):
            for cap in group.get("caps", []):
                out.append(cap["urn"])
    return out


class EchoHandler(FrameHandler):
    """Echo handler: accumulates input, echoes raw bytes back."""

    def handle_request(self, cap_urn, input_q, output, peer):
        try:
            args, meta = accumulate_input(input_q)
        except ValueError as e:
            output.emit_error("ACCUMULATE_ERROR", str(e))
            return
        data = b"".join(a.value for a in args)
        output.emit_response("media:", data)


# TEST6748: InProcessCartridgeHost routes REQ to matching handler and returns response
def test_6748_routes_req_to_handler():
    cap_urn = 'cap:in="media:text";echo;out="media:text"'
    cap = make_test_cap(cap_urn)
    handlers = [("echo", [cap], EchoHandler())]

    host = InProcessCartridgeHost(
        InProcessHostIdentity.for_test("in-process-test"), handlers
    )

    host_read, host_write, test_read, test_write, host_socks, test_socks = make_host_conn()

    host_thread = threading.Thread(target=lambda: host.run(host_read, host_write), daemon=True)
    host_thread.start()

    reader = FrameReader(test_read)
    writer = FrameWriter(test_write)

    # First frame should be RelayNotify with manifest
    notify = reader.read()
    assert notify is not None and notify.frame_type == FrameType.RELAY_NOTIFY
    manifest = notify.relay_notify_manifest()
    payload = json.loads(manifest)
    caps = _aggregate_cap_urns(payload)
    assert len(caps) >= 2  # identity + echo cap
    assert caps[0] == CAP_IDENTITY
    assert len(payload["installed_cartridges"]) == 1
    assert payload["installed_cartridges"][0]["id"] == "in-process-test"

    # Send a REQ + STREAM_START + CHUNK (CBOR-encoded) + STREAM_END + END
    rid = MessageId.new_uuid()
    req = Frame.req(rid, cap_urn, b"", "application/cbor")
    req.routing_id = MessageId(1)
    writer.write(req)

    writer.write(Frame.stream_start(rid, "arg0", "media:text"))

    payload_bytes = cbor_bytes_payload(b"hello world")
    writer.write(Frame.chunk(rid, "arg0", 0, payload_bytes, 0, compute_checksum(payload_bytes)))
    writer.write(Frame.stream_end(rid, "arg0", 1))
    writer.write(Frame.end(rid, None))

    # Read response: STREAM_START + CHUNK (CBOR-encoded) + STREAM_END + END
    resp_ss = reader.read()
    assert resp_ss.frame_type == FrameType.STREAM_START
    assert resp_ss.id == rid
    assert resp_ss.stream_id == "result"

    resp_chunk = reader.read()
    assert resp_chunk.frame_type == FrameType.CHUNK
    resp_data = decode_chunk_payload(resp_chunk.payload)
    assert resp_data == b"hello world"

    resp_se = reader.read()
    assert resp_se.frame_type == FrameType.STREAM_END

    resp_end = reader.read()
    assert resp_end.frame_type == FrameType.END

    close_socks(test_socks)
    close_socks(host_socks)
    host_thread.join(timeout=2)


# TEST6749: InProcessCartridgeHost handles identity verification (echo nonce)
def test_6749_identity_verification():
    host = InProcessCartridgeHost(InProcessHostIdentity.for_test("in-process-test"), [])

    host_read, host_write, test_read, test_write, host_socks, test_socks = make_host_conn()
    host_thread = threading.Thread(target=lambda: host.run(host_read, host_write), daemon=True)
    host_thread.start()

    reader = FrameReader(test_read)
    writer = FrameWriter(test_write)

    # Skip RelayNotify
    _ = reader.read()

    # Send identity verification
    rid = MessageId.new_uuid()
    req = Frame.req(rid, CAP_IDENTITY, b"", "application/cbor")
    req.routing_id = MessageId(0)
    writer.write(req)

    # Send nonce via stream (already CBOR-encoded by identity_nonce)
    nonce = identity_nonce()
    writer.write(Frame.stream_start(rid, "identity-verify", "media:"))
    writer.write(Frame.chunk(rid, "identity-verify", 0, nonce, 0, compute_checksum(nonce)))
    writer.write(Frame.stream_end(rid, "identity-verify", 1))
    writer.write(Frame.end(rid, None))

    # Read echoed response — identity echoes raw bytes (no CBOR decode/encode)
    resp_ss = reader.read()
    assert resp_ss.frame_type == FrameType.STREAM_START

    resp_chunk = reader.read()
    assert resp_chunk.frame_type == FrameType.CHUNK
    assert resp_chunk.payload == nonce

    resp_se = reader.read()
    assert resp_se.frame_type == FrameType.STREAM_END

    resp_end = reader.read()
    assert resp_end.frame_type == FrameType.END

    close_socks(test_socks)
    close_socks(host_socks)
    host_thread.join(timeout=2)


# TEST6750: InProcessCartridgeHost returns NO_HANDLER for unregistered cap
def test_6750_no_handler_returns_err():
    host = InProcessCartridgeHost(InProcessHostIdentity.for_test("in-process-test"), [])

    host_read, host_write, test_read, test_write, host_socks, test_socks = make_host_conn()
    host_thread = threading.Thread(target=lambda: host.run(host_read, host_write), daemon=True)
    host_thread.start()

    reader = FrameReader(test_read)
    writer = FrameWriter(test_write)

    # Skip RelayNotify
    _ = reader.read()

    rid = MessageId.new_uuid()
    req = Frame.req(rid, 'cap:in="media:ext=pdf";unknown;out="media:text"', b"", "application/cbor")
    req.routing_id = MessageId(1)
    writer.write(req)

    # Should get ERR back
    err_frame = reader.read()
    assert err_frame.frame_type == FrameType.ERR
    assert err_frame.id == rid
    assert err_frame.error_code() == "NO_HANDLER"

    close_socks(test_socks)
    close_socks(host_socks)
    host_thread.join(timeout=2)


# TEST6751: InProcessCartridgeHost manifest includes identity cap and handler caps
def test_6751_manifest_includes_all_caps():
    cap_urn = 'cap:in="media:ext=pdf";thumbnail;out="media:ext=png;image"'
    cap = make_test_cap(cap_urn)
    host = InProcessCartridgeHost(
        InProcessHostIdentity.for_test("thumb-host"),
        [("thumb", [cap], EchoHandler())],
    )

    manifest = host.build_manifest()
    payload = json.loads(manifest)
    caps = _aggregate_cap_urns(payload)
    assert caps[0] == CAP_IDENTITY
    assert any("thumbnail" in u for u in caps)
    assert len(payload["installed_cartridges"]) == 1
    assert payload["installed_cartridges"][0]["id"] == "thumb-host"
    assert len(payload["installed_cartridges"][0]["cap_groups"]) == 1


# TEST658: InProcessCartridgeHost handles heartbeat by echoing same ID
def test_658_heartbeat_response():
    host = InProcessCartridgeHost(InProcessHostIdentity.for_test("in-process-test"), [])

    host_read, host_write, test_read, test_write, host_socks, test_socks = make_host_conn()
    host_thread = threading.Thread(target=lambda: host.run(host_read, host_write), daemon=True)
    host_thread.start()

    reader = FrameReader(test_read)
    writer = FrameWriter(test_write)

    # Skip RelayNotify
    _ = reader.read()

    hb_id = MessageId.new_uuid()
    writer.write(Frame.heartbeat(hb_id))

    resp = reader.read()
    assert resp.frame_type == FrameType.HEARTBEAT
    assert resp.id == hb_id

    close_socks(test_socks)
    close_socks(host_socks)
    host_thread.join(timeout=2)


# TEST659: InProcessCartridgeHost handler error returns ERR frame
def test_659_handler_error_returns_err_frame():
    class FailHandler(FrameHandler):
        """Handler that always fails."""

        def handle_request(self, cap_urn, input_q, output, peer):
            # Drain input
            while True:
                frame = input_q.get()
                if frame is None:
                    break
                if frame.frame_type == FrameType.END:
                    break
            output.emit_error("PROVIDER_ERROR", "provider crashed")

    cap_urn = 'cap:in="media:void";fail;out="media:void"'
    cap = make_test_cap(cap_urn)
    host = InProcessCartridgeHost(
        InProcessHostIdentity.for_test("fail-host"),
        [("fail", [cap], FailHandler())],
    )

    host_read, host_write, test_read, test_write, host_socks, test_socks = make_host_conn()
    host_thread = threading.Thread(target=lambda: host.run(host_read, host_write), daemon=True)
    host_thread.start()

    reader = FrameReader(test_read)
    writer = FrameWriter(test_write)

    # Skip RelayNotify
    _ = reader.read()

    # Send REQ + END (no streams, void input)
    rid = MessageId.new_uuid()
    req = Frame.req(rid, cap_urn, b"", "application/cbor")
    req.routing_id = MessageId(1)
    writer.write(req)
    writer.write(Frame.end(rid, None))

    # Should get ERR frame
    err_frame = reader.read()
    assert err_frame.frame_type == FrameType.ERR
    assert err_frame.id == rid
    assert err_frame.error_code() == "PROVIDER_ERROR"
    assert "provider crashed" in err_frame.error_message()

    close_socks(test_socks)
    close_socks(host_socks)
    host_thread.join(timeout=2)


# TEST660: InProcessCartridgeHost closest-specificity routing prefers specific over identity
def test_660_closest_specificity_routing():
    specific_urn = 'cap:in="media:ext=pdf";thumbnail;out="media:ext=png;image"'
    generic_urn = 'cap:in="media:image";thumbnail;out="media:ext=png;image"'

    specific_cap = make_test_cap(specific_urn)
    generic_cap = make_test_cap(generic_urn)

    class TaggedHandler(FrameHandler):
        """Handler that tags its output with its name."""

        def __init__(self, name):
            self.name = name

        def handle_request(self, cap_urn, input_q, output, peer):
            while True:
                frame = input_q.get()
                if frame is None:
                    break
                if frame.frame_type == FrameType.END:
                    break
            output.emit_response("media:text", self.name.encode("utf-8"))

    handlers = [
        ("generic", [generic_cap], TaggedHandler("generic")),
        ("specific", [specific_cap], TaggedHandler("specific")),
    ]

    host = InProcessCartridgeHost(InProcessHostIdentity.for_test("in-process-test"), handlers)
    cap_table = InProcessCartridgeHost.build_cap_table(host.handlers)

    # Request for pdf thumbnail should match specific (pdf, specificity 3) over
    # generic (image, specificity 2).
    result = InProcessCartridgeHost.find_handler_for_cap(
        cap_table, 'cap:in="media:ext=pdf";thumbnail;out="media:ext=png;image"'
    )
    assert result == 1  # specific handler
