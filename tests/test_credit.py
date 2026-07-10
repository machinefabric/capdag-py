"""Tests for bifaci credit - mirroring capdag Rust tests (src/bifaci/credit.rs)

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
The Rust reference drives CreditGate from tokio tasks; the Python mirror has no
asyncio in the hot path, so these tests drive it from real OS threads instead —
same observable contract (acquire blocks until grant/close, close releases all
waiters with CreditClosed, grants after close are no-ops).
"""

import threading
import time

import pytest

from capdag.bifaci.frame import Frame, MessageId, CreditDirection
from capdag.bifaci.credit import CreditGate, CreditRouter, CreditClosed


# TEST7015: CreditGate acquire succeeds immediately within the initial window and waits when exhausted until a grant arrives.
def test_7015_credit_gate_acquire_and_grant():
    gate = CreditGate(2)
    gate.acquire(1)
    gate.acquire(1)
    assert gate.available() == 0

    result = {}

    def waiter():
        try:
            gate.acquire(1)
            result["ok"] = True
        except BaseException as e:  # pragma: no cover - failure path only
            result["error"] = e

    t = threading.Thread(target=waiter, daemon=True)
    t.start()
    time.sleep(0.05)
    assert t.is_alive(), "acquire must wait at zero credit"

    gate.grant(1)
    t.join(timeout=1.0)
    assert not t.is_alive(), "waiter must wake on grant"
    assert result.get("ok") is True
    assert "error" not in result


# TEST7016: CreditGate close releases blocked waiters with CreditClosed and fails all future acquires.
def test_7016_credit_gate_close_releases_waiters():
    gate = CreditGate(0)
    result = {}

    def waiter():
        try:
            gate.acquire(1)
            result["ok"] = True
        except CreditClosed as e:
            result["error"] = e

    t = threading.Thread(target=waiter, daemon=True)
    t.start()
    time.sleep(0.05)

    gate.close("CANCELLED")
    t.join(timeout=1.0)
    assert not t.is_alive(), "waiter must wake on close"
    err = result.get("error")
    assert isinstance(err, CreditClosed)
    assert err.reason == "CANCELLED"

    with pytest.raises(CreditClosed):
        gate.acquire(1)  # closed gate rejects acquire

    gate.grant(5)  # no-op after close
    with pytest.raises(CreditClosed):
        gate.acquire(1)


# TEST7017: CreditRouter routes grants by (rid, stream_id), falls back to a request's sole gate for stream-less grants, and reports unmatched grants.
def test_7017_credit_router_routing():
    router = CreditRouter()
    rid = MessageId.new_uuid()
    gate = CreditGate(0)
    router.register(rid, "s1", gate)

    # Exact (rid, stream) match
    f = Frame.credit(rid, "s1", 3, CreditDirection.RESPONSE)
    assert router.grant(f) is True
    assert gate.available() == 3

    # Stream-less grant matches the sole gate
    f = Frame.credit(rid, None, 2, CreditDirection.RESPONSE)
    assert router.grant(f) is True
    assert gate.available() == 5

    # Second gate makes a stream-less grant ambiguous -> unmatched
    gate2 = CreditGate(0)
    router.register(rid, "s2", gate2)
    f = Frame.credit(rid, None, 1, CreditDirection.RESPONSE)
    assert router.grant(f) is False

    # Unknown request -> unmatched no-op
    f = Frame.credit(MessageId.new_uuid(), None, 1, CreditDirection.RESPONSE)
    assert router.grant(f) is False


# TEST7018: CreditRouter close_request closes and removes every gate of the request, releasing their waiters.
def test_7018_credit_router_close_request():
    router = CreditRouter()
    rid = MessageId.new_uuid()
    g1 = CreditGate(0)
    g2 = CreditGate(0)
    router.register(rid, "a", g1)
    router.register(rid, "b", g2)

    result = {}

    def waiter():
        try:
            g1.acquire(1)
            result["ok"] = True
        except CreditClosed as e:
            result["error"] = e

    t = threading.Thread(target=waiter, daemon=True)
    t.start()
    time.sleep(0.05)

    router.close_request(rid, "END")
    assert router.is_empty()
    assert g2.is_closed()

    t.join(timeout=1.0)
    assert not t.is_alive()
    err = result.get("error")
    assert isinstance(err, CreditClosed)
    assert err.reason == "END"
