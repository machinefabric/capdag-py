"""Tests for CartridgeHost — multi-cartridge relay-based host.

Tests TEST413-TEST425 mirror the Go cartridge_host_multi_test.go tests.
Uses socket pairs and threads to simulate cartridges.

Socket lifecycle rules:
- Cartridge threads NEVER close host-side sockets (doing so discards unread data)
- For clean exit: cartridge handler returns, main thread closes all sockets after host.run
- For death simulation: cartridge closes only its own write end (cartridge_socks)
"""

import json
import socket
import threading
import time

import pytest

from capdag.bifaci.host_runtime import CartridgeHost
from capdag.bifaci.frame import Frame, FrameType, Limits, MessageId, compute_checksum
from capdag.bifaci.io import (
    FrameReader,
    FrameWriter,
    handshake_accept,
)


def make_conn():
    """Create a bidirectional connection using socket pairs.

    Returns (host_read, host_write, cartridge_read, cartridge_write, host_socks, cartridge_socks).
    - host_socks: [s1a, s2a] — close these to clean up from host side
    - cartridge_socks: [s1b, s2b] — close these to simulate cartridge death
    """
    # Channel 1: cartridge writes (s1b) → host reads (s1a)
    s1a, s1b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    # Channel 2: host writes (s2a) → cartridge reads (s2b)
    s2a, s2b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)

    host_read = s1a.makefile("rb")
    cartridge_write = s1b.makefile("wb")
    cartridge_read = s2b.makefile("rb")
    host_write = s2a.makefile("wb")

    return host_read, host_write, cartridge_read, cartridge_write, [s1a, s2a], [s1b, s2b]


def close_socks(socks):
    """Shutdown and close a list of sockets."""
    for s in socks:
        try:
            s.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            s.close()
        except Exception:
            pass


def cleanup(*sock_lists):
    """Close all socket lists."""
    for socks in sock_lists:
        close_socks(socks)


def simulate_cartridge(cartridge_read, cartridge_write, manifest_str, handler=None):
    """Run a simulated cartridge: handshake + optional handler."""
    reader = FrameReader(cartridge_read)
    writer = FrameWriter(cartridge_write)

    limits = handshake_accept(reader, writer, manifest_str.encode("utf-8"))
    reader.set_limits(limits)
    writer.set_limits(limits)

    if handler is not None:
        handler(reader, writer)


# TEST413: Register cartridge adds entries to cap_table
def test_413_register_cartridge_adds_cap_table():
    host = CartridgeHost()
    host.register_cartridge("/path/to/converter", ["cap:op=convert", "cap:op=analyze"])

    with host._lock:
        assert len(host._cap_table) == 2, "must have 2 cap table entries"
        assert host._cap_table[0].cap_urn == "cap:op=convert"
        assert host._cap_table[0].cartridge_idx == 0
        assert host._cap_table[1].cap_urn == "cap:op=analyze"
        assert host._cap_table[1].cartridge_idx == 0
        assert len(host._cartridges) == 1
        assert not host._cartridges[0].running, "registered cartridge must not be running"


# TEST414: capabilities() returns empty JSON initially (no running cartridges)
def test_414_capabilities_empty_initially():
    host = CartridgeHost()
    assert host.capabilities() is None, "no cartridges → None capabilities"
    host.register_cartridge("/path/to/cartridge", ["cap:op=test"])
    assert host.capabilities() is None, "registered but not running → None capabilities"


# TEST415: REQ for known cap triggers spawn attempt (verified by expected spawn error for non-existent binary)
def test_415_req_triggers_spawn():
    host = CartridgeHost()
    host.register_cartridge("/nonexistent/cartridge/binary", ["cap:op=test"])

    hr, hw, pr, pw, hs, ps = make_conn()
    err_frame = [None]

    def engine():
        w = FrameWriter(pw)
        r = FrameReader(pr)
        req_id = MessageId.new_uuid()
        w.write(Frame.req(req_id, "cap:op=test", b"hello", "text/plain"))
        frame = r.read()
        if frame is not None:
            err_frame[0] = frame
        close_socks(ps)

    t = threading.Thread(target=engine, daemon=True)
    t.start()

    host.run(hr, hw)
    cleanup(hs, ps)
    t.join(timeout=5)

    assert err_frame[0] is not None, "must receive ERR frame"
    assert err_frame[0].frame_type == FrameType.ERR
    assert err_frame[0].error_code() == "SPAWN_FAILED"


# TEST416: Attach cartridge performs HELLO handshake, extracts manifest, updates capabilities
def test_416_attach_cartridge_handshake():
    manifest = '{"name":"Test","version":"1.0","caps":[{"urn":"cap:in=media:;out=media:"}]}'
    hr, hw, pr, pw, hs, ps = make_conn()

    def cartridge():
        simulate_cartridge(pr, pw, manifest)
        # Don't close sockets — main thread handles cleanup

    t = threading.Thread(target=cartridge, daemon=True)
    t.start()

    host = CartridgeHost()
    idx = host.attach_cartridge(hr, hw)

    assert idx == 0
    with host._lock:
        assert host._cartridges[0].running
        assert host._cartridges[0].caps == ["cap:in=media:;out=media:"]

    caps = host.capabilities()
    assert caps is not None
    assert b"cap:in=media:;out=media:" in caps
    cleanup(hs, ps)
    t.join(timeout=5)


# TEST417: Route REQ to correct cartridge by cap_urn (with two attached cartridges)
def test_417_route_req_by_cap_urn():
    manifest_a = '{"name":"A","version":"1.0","caps":[{"urn":"cap:op=convert"}]}'
    manifest_b = '{"name":"B","version":"1.0","caps":[{"urn":"cap:op=analyze"}]}'

    hr_a, hw_a, pr_a, pw_a, hs_a, ps_a = make_conn()
    hr_b, hw_b, pr_b, pw_b, hs_b, ps_b = make_conn()

    def cartridge_a():
        def handler(r, w):
            frame = r.read()
            if frame is None:
                return
            req_id = frame.id
            while True:
                f = r.read()
                if f is None or f.frame_type == FrameType.END:
                    break
            w.write(Frame.end(req_id, b"converted"))
        simulate_cartridge(pr_a, pw_a, manifest_a, handler)

    def cartridge_b():
        def handler(r, w):
            r.read()  # waits for EOF
        simulate_cartridge(pr_b, pw_b, manifest_b, handler)

    t_a = threading.Thread(target=cartridge_a, daemon=True)
    t_b = threading.Thread(target=cartridge_b, daemon=True)
    t_a.start()
    t_b.start()

    host = CartridgeHost()
    host.attach_cartridge(hr_a, hw_a)
    host.attach_cartridge(hr_b, hw_b)

    r_hr, r_hw, r_pr, r_pw, r_hs, r_ps = make_conn()
    response_payload = [None]

    def engine():
        w = FrameWriter(r_pw)
        r = FrameReader(r_pr)
        req_id = MessageId.new_uuid()
        w.write(Frame.req(req_id, "cap:op=convert", b"", "text/plain"))
        w.write(Frame.end(req_id))
        frame = r.read()
        if frame is not None and frame.frame_type == FrameType.END:
            response_payload[0] = frame.payload
        close_socks(r_ps)

    t_eng = threading.Thread(target=engine, daemon=True)
    t_eng.start()

    host.run(r_hr, r_hw)
    cleanup(hs_a, ps_a, hs_b, ps_b, r_hs, r_ps)
    t_eng.join(timeout=5)
    t_a.join(timeout=5)
    t_b.join(timeout=5)

    assert response_payload[0] == b"converted"


# TEST418: Route STREAM_START/CHUNK/STREAM_END/END by req_id (not cap_urn) Verifies that after the initial REQ→cartridge routing, all subsequent continuation frames with the same req_id are routed to the same cartridge — even though no cap_urn is present on those frames.
def test_418_route_continuation_by_req_id():
    manifest = '{"name":"Test","version":"1.0","caps":[{"urn":"cap:op=cont"}]}'
    hr, hw, pr, pw, hs, ps = make_conn()

    def cartridge_thread():
        def handler(r, w):
            req = r.read()
            if req is None:
                return
            assert req.frame_type == FrameType.REQ
            req_id = req.id
            ss = r.read()
            assert ss.frame_type == FrameType.STREAM_START
            assert ss.id.to_string() == req_id.to_string()
            chunk = r.read()
            assert chunk.frame_type == FrameType.CHUNK
            assert chunk.payload == b"payload-data"
            se = r.read()
            assert se.frame_type == FrameType.STREAM_END
            end = r.read()
            assert end.frame_type == FrameType.END
            w.write(Frame.end(req_id, b"ok"))
        simulate_cartridge(pr, pw, manifest, handler)

    t_p = threading.Thread(target=cartridge_thread, daemon=True)
    t_p.start()

    host = CartridgeHost()
    host.attach_cartridge(hr, hw)

    r_hr, r_hw, r_pr, r_pw, r_hs, r_ps = make_conn()
    response = [None]

    def engine():
        w = FrameWriter(r_pw)
        r = FrameReader(r_pr)
        req_id = MessageId.new_uuid()
        w.write(Frame.req(req_id, "cap:op=cont", b"", "text/plain"))
        w.write(Frame.stream_start(req_id, "arg-0", "media:"))
        w.write(Frame.chunk(req_id, "arg-0", 0, b"payload-data", 0, compute_checksum(b"payload-data")))
        w.write(Frame.stream_end(req_id, "arg-0", 1))
        w.write(Frame.end(req_id))
        frame = r.read()
        if frame is not None and frame.frame_type == FrameType.END:
            response[0] = frame.payload
        close_socks(r_ps)

    t_eng = threading.Thread(target=engine, daemon=True)
    t_eng.start()

    host.run(r_hr, r_hw)
    cleanup(hs, ps, r_hs, r_ps)
    t_eng.join(timeout=5)
    t_p.join(timeout=5)

    assert response[0] == b"ok"


# TEST419: Cartridge HEARTBEAT handled locally (not forwarded to relay)
def test_419_heartbeat_local_handling():
    manifest = '{"name":"Test","version":"1.0","caps":[{"urn":"cap:op=hb"}]}'
    hr, hw, pr, pw, hs, ps = make_conn()

    cartridge_done = threading.Event()

    def cartridge_thread():
        def handler(r, w):
            hb_id = MessageId.new_uuid()
            w.write(Frame.heartbeat(hb_id))
            resp = r.read()
            assert resp is not None
            assert resp.frame_type == FrameType.HEARTBEAT
            assert resp.id.to_string() == hb_id.to_string()
            log_id = MessageId.new_uuid()
            w.write(Frame.log(log_id, "info", "heartbeat was answered"))
            cartridge_done.set()
        simulate_cartridge(pr, pw, manifest, handler)

    t_p = threading.Thread(target=cartridge_thread, daemon=True)
    t_p.start()

    host = CartridgeHost()
    host.attach_cartridge(hr, hw)

    r_hr, r_hw, r_pr, r_pw, r_hs, r_ps = make_conn()
    received_types = []

    def engine():
        r = FrameReader(r_pr)
        while True:
            frame = r.read()
            if frame is None:
                break
            received_types.append(frame.frame_type)
            if frame.frame_type == FrameType.LOG:
                break  # Got what we expected

    t_eng = threading.Thread(target=engine, daemon=True)
    t_eng.start()

    def close_relay():
        # Wait for cartridge to send LOG, then give host time to forward it
        cartridge_done.wait(timeout=5.0)
        time.sleep(0.1)  # Small delay for host to forward
        close_socks(r_ps)

    t_close = threading.Thread(target=close_relay, daemon=True)
    t_close.start()

    host.run(r_hr, r_hw)
    cleanup(hs, ps, r_hs, r_ps)
    t_eng.join(timeout=5)
    t_p.join(timeout=5)
    t_close.join(timeout=5)

    for ft in received_types:
        assert ft != FrameType.HEARTBEAT, "heartbeat must not be forwarded to relay"
    assert FrameType.LOG in received_types, "LOG must be forwarded to relay"


# TEST420: Cartridge non-HELLO/non-HB frames forwarded to relay (pass-through)
def test_420_cartridge_frames_forwarded_to_relay():
    manifest = '{"name":"Test","version":"1.0","caps":[{"urn":"cap:op=fwd"}]}'
    hr, hw, pr, pw, hs, ps = make_conn()

    def cartridge_thread():
        def handler(r, w):
            req = r.read()
            if req is None:
                return
            req_id = req.id
            r.read()  # END
            w.write(Frame.log(req_id, "info", "processing"))
            w.write(Frame.stream_start(req_id, "output", "media:"))
            w.write(Frame.chunk(req_id, "output", 0, b"data", 0, compute_checksum(b"data")))
            w.write(Frame.stream_end(req_id, "output", 1))
            w.write(Frame.end(req_id))
        simulate_cartridge(pr, pw, manifest, handler)

    t_p = threading.Thread(target=cartridge_thread, daemon=True)
    t_p.start()

    host = CartridgeHost()
    host.attach_cartridge(hr, hw)

    r_hr, r_hw, r_pr, r_pw, r_hs, r_ps = make_conn()
    received_types = []

    def engine():
        w = FrameWriter(r_pw)
        r = FrameReader(r_pr)
        req_id = MessageId.new_uuid()
        w.write(Frame.req(req_id, "cap:op=fwd", b"", "text/plain"))
        w.write(Frame.end(req_id))
        while True:
            frame = r.read()
            if frame is None:
                break
            received_types.append(frame.frame_type)
            if frame.frame_type == FrameType.END:
                break
        close_socks(r_ps)

    t_eng = threading.Thread(target=engine, daemon=True)
    t_eng.start()

    host.run(r_hr, r_hw)
    cleanup(hs, ps, r_hs, r_ps)
    t_eng.join(timeout=5)
    t_p.join(timeout=5)

    type_set = set(received_types)
    assert FrameType.LOG in type_set, "LOG must be forwarded"
    assert FrameType.STREAM_START in type_set, "STREAM_START must be forwarded"
    assert FrameType.CHUNK in type_set, "CHUNK must be forwarded"
    assert FrameType.END in type_set, "END must be forwarded"


# TEST421: Cartridge death updates capability list (caps removed)
def test_421_cartridge_death_updates_caps():
    manifest = '{"name":"Test","version":"1.0","caps":[{"urn":"cap:op=die"}]}'
    hr, hw, pr, pw, hs, ps = make_conn()

    def cartridge_thread():
        simulate_cartridge(pr, pw, manifest)
        # Die by closing cartridge-side sockets → host sees EOF
        close_socks(ps)

    t_p = threading.Thread(target=cartridge_thread, daemon=True)
    t_p.start()

    host = CartridgeHost()
    host.attach_cartridge(hr, hw)

    caps = host.capabilities()
    assert caps is not None
    assert b"cap:op=die" in caps

    r_hr, r_hw, r_pr, r_pw, r_hs, r_ps = make_conn()

    def close_relay():
        time.sleep(1.0)
        close_socks(r_ps)

    t_close = threading.Thread(target=close_relay, daemon=True)
    t_close.start()

    host.run(r_hr, r_hw)

    caps_after = host.capabilities()
    if caps_after is not None:
        parsed = json.loads(caps_after)
        assert len(parsed.get("caps", [])) == 0, "dead cartridge caps must be removed"

    cleanup(hs, ps, r_hs, r_ps)
    t_p.join(timeout=5)
    t_close.join(timeout=5)


# TEST422: Cartridge death sends ERR for all pending requests via relay
def test_422_cartridge_death_sends_err():
    manifest = '{"name":"Test","version":"1.0","caps":[{"urn":"cap:op=die"}]}'
    hr, hw, pr, pw, hs, ps = make_conn()

    def cartridge_thread():
        def handler(r, w):
            r.read()  # Read REQ
            # Die by closing cartridge-side sockets
            close_socks(ps)
        simulate_cartridge(pr, pw, manifest, handler)

    t_p = threading.Thread(target=cartridge_thread, daemon=True)
    t_p.start()

    host = CartridgeHost()
    host.attach_cartridge(hr, hw)

    r_hr, r_hw, r_pr, r_pw, r_hs, r_ps = make_conn()
    err_frame = [None]

    def engine():
        w = FrameWriter(r_pw)
        r = FrameReader(r_pr)
        req_id = MessageId.new_uuid()
        w.write(Frame.req(req_id, "cap:op=die", b"hello", "text/plain"))
        w.write(Frame.end(req_id))
        while True:
            frame = r.read()
            if frame is None:
                break
            if frame.frame_type == FrameType.ERR:
                err_frame[0] = frame
                break
        close_socks(r_ps)

    t_eng = threading.Thread(target=engine, daemon=True)
    t_eng.start()

    host.run(r_hr, r_hw)
    cleanup(hs, ps, r_hs, r_ps)
    t_eng.join(timeout=5)
    t_p.join(timeout=5)

    assert err_frame[0] is not None, "must receive ERR when cartridge dies with pending request"
    assert err_frame[0].error_code() == "CARTRIDGE_DIED"


# TEST423: Multiple cartridges registered with distinct caps route independently
def test_423_multi_cartridge_distinct_caps():
    manifest_a = '{"name":"A","version":"1.0","caps":[{"urn":"cap:op=alpha"}]}'
    manifest_b = '{"name":"B","version":"1.0","caps":[{"urn":"cap:op=beta"}]}'

    hr_a, hw_a, pr_a, pw_a, hs_a, ps_a = make_conn()
    hr_b, hw_b, pr_b, pw_b, hs_b, ps_b = make_conn()

    def cartridge_a():
        def handler(r, w):
            req = r.read()
            if req is None:
                return
            while True:
                f = r.read()
                if f is None or f.frame_type == FrameType.END:
                    break
            w.write(Frame.end(req.id, b"from-A"))
        simulate_cartridge(pr_a, pw_a, manifest_a, handler)

    def cartridge_b():
        def handler(r, w):
            req = r.read()
            if req is None:
                return
            while True:
                f = r.read()
                if f is None or f.frame_type == FrameType.END:
                    break
            w.write(Frame.end(req.id, b"from-B"))
        simulate_cartridge(pr_b, pw_b, manifest_b, handler)

    t_a = threading.Thread(target=cartridge_a, daemon=True)
    t_b = threading.Thread(target=cartridge_b, daemon=True)
    t_a.start()
    t_b.start()

    host = CartridgeHost()
    host.attach_cartridge(hr_a, hw_a)
    host.attach_cartridge(hr_b, hw_b)

    r_hr, r_hw, r_pr, r_pw, r_hs, r_ps = make_conn()
    responses = {}
    lock = threading.Lock()

    def engine():
        w = FrameWriter(r_pw)
        r = FrameReader(r_pr)
        alpha_id = MessageId.new_uuid()
        w.write(Frame.req(alpha_id, "cap:op=alpha", b"", "text/plain"))
        w.write(Frame.end(alpha_id))
        beta_id = MessageId.new_uuid()
        w.write(Frame.req(beta_id, "cap:op=beta", b"", "text/plain"))
        w.write(Frame.end(beta_id))
        for _ in range(2):
            frame = r.read()
            if frame is None:
                break
            if frame.frame_type == FrameType.END:
                id_str = frame.id.to_string()
                with lock:
                    if id_str == alpha_id.to_string():
                        responses["alpha"] = frame.payload
                    elif id_str == beta_id.to_string():
                        responses["beta"] = frame.payload
        close_socks(r_ps)

    t_eng = threading.Thread(target=engine, daemon=True)
    t_eng.start()

    host.run(r_hr, r_hw)
    cleanup(hs_a, ps_a, hs_b, ps_b, r_hs, r_ps)
    t_eng.join(timeout=5)
    t_a.join(timeout=5)
    t_b.join(timeout=5)

    with lock:
        assert responses.get("alpha") == b"from-A"
        assert responses.get("beta") == b"from-B"


# TEST424: Concurrent requests to the same cartridge are handled independently
def test_424_concurrent_requests_same_cartridge():
    manifest = '{"name":"Test","version":"1.0","caps":[{"urn":"cap:op=conc"}]}'
    hr, hw, pr, pw, hs, ps = make_conn()

    def cartridge_thread():
        def handler(r, w):
            req_ids = []
            req0 = r.read()
            if req0 is None:
                return
            req_ids.append(req0.id)
            r.read()  # END 0
            req1 = r.read()
            if req1 is None:
                return
            req_ids.append(req1.id)
            r.read()  # END 1
            w.write(Frame.end(req_ids[0], b"response-0"))
            w.write(Frame.end(req_ids[1], b"response-1"))
        simulate_cartridge(pr, pw, manifest, handler)

    t_p = threading.Thread(target=cartridge_thread, daemon=True)
    t_p.start()

    host = CartridgeHost()
    host.attach_cartridge(hr, hw)

    r_hr, r_hw, r_pr, r_pw, r_hs, r_ps = make_conn()
    responses = {}
    lock = threading.Lock()

    def engine():
        w = FrameWriter(r_pw)
        r = FrameReader(r_pr)
        id0 = MessageId.new_uuid()
        id1 = MessageId.new_uuid()
        w.write(Frame.req(id0, "cap:op=conc", b"", "text/plain"))
        w.write(Frame.end(id0))
        w.write(Frame.req(id1, "cap:op=conc", b"", "text/plain"))
        w.write(Frame.end(id1))
        for _ in range(2):
            frame = r.read()
            if frame is None:
                break
            if frame.frame_type == FrameType.END:
                id_str = frame.id.to_string()
                with lock:
                    if id_str == id0.to_string():
                        responses["0"] = frame.payload
                    elif id_str == id1.to_string():
                        responses["1"] = frame.payload
        close_socks(r_ps)

    t_eng = threading.Thread(target=engine, daemon=True)
    t_eng.start()

    host.run(r_hr, r_hw)
    cleanup(hs, ps, r_hs, r_ps)
    t_eng.join(timeout=5)
    t_p.join(timeout=5)

    with lock:
        assert responses.get("0") == b"response-0"
        assert responses.get("1") == b"response-1"


# TEST425: find_cartridge_for_cap returns None for unregistered cap
def test_425_find_cartridge_for_cap_unknown():
    host = CartridgeHost()
    host.register_cartridge("/path/to/cartridge", ["cap:op=known"])

    idx = host.find_cartridge_for_cap("cap:op=known")
    assert idx is not None, "known cap must be found"
    assert idx == 0

    idx2 = host.find_cartridge_for_cap("cap:op=unknown")
    assert idx2 is None, "unknown cap must not be found"
