"""Credit-based per-stream flow control (protocol v3).

One credit = permission to send one CHUNK frame. A sender starts each stream
with the negotiated ``initial_credit`` window and must wait when the window is
exhausted; the receiving endpoint replenishes it with CREDIT frames as it
consumes chunks (L9/L10 in ``docs/capdag-improvement/03-protocol-v3-design.md``).

``CreditGate`` is built on a ``threading.Condition`` guarding a plain integer
counter — the Python-native analogue of the Rust reference's mutex + notify
pair (and the Swift mirror's lock + continuation queue). Python's
``Condition.wait()`` already solves the missed-wakeup race that Rust's
``tokio::Notify`` needs an explicit ``enable()`` dance to avoid: the
check-or-wait happens atomically under the condition's lock, so a grant or
close that lands between the window check and the wait call can never be
lost. This module follows the Python mirror's threads + ``Condition`` idiom
throughout (no asyncio in the hot path); ``blocking_acquire`` is a thin alias
for ``acquire`` since Python's threading model has no separate
cheap-suspend/hard-block distinction the way async Rust does.

The observable contract is identical to every other mirror: ``acquire`` waits
until credit is available or the gate closes; ``close`` releases all waiters
with an error; grants never block.
"""

import threading
from typing import Dict, List, Optional, Tuple

from capdag.bifaci.frame import Frame, FrameType, MessageId


class CreditClosed(Exception):
    """Raised to a credit waiter when its gate closes (request terminal,
    cancellation, or connection death) — the waiter must stop sending."""

    def __init__(self, reason: str):
        super().__init__(f"credit gate closed: {reason}")
        self.reason = reason

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CreditClosed):
            return NotImplemented
        return self.reason == other.reason

    def __hash__(self) -> int:
        return hash(("CreditClosed", self.reason))

    def __repr__(self) -> str:
        return f"CreditClosed(reason={self.reason!r})"


class CreditGate:
    """A replenishable per-stream credit window for one sender.

    - ``acquire(1)`` before each CHUNK: returns immediately while the window
      is open, blocks when it is exhausted.
    - ``grant(n)`` when a CREDIT frame arrives: wakes waiters.
    - ``close(reason)`` on request terminal/cancel: releases all waiters with
      ``CreditClosed`` (L13 — a credit-blocked sender must never hang).
    """

    def __init__(self, initial_credit: int):
        self._condition = threading.Condition()
        # Chunks the sender may still emit before waiting.
        self._available = initial_credit
        # Set when the gate is closed; all current and future acquires fail.
        self._closed_reason: Optional[str] = None

    def acquire(self, n: int) -> None:
        """Acquire `n` credits, blocking if the window is exhausted.

        Raises:
            CreditClosed: If the gate closes before (or while) waiting.
        """
        with self._condition:
            while self._closed_reason is None and self._available < n:
                self._condition.wait()
            if self._closed_reason is not None:
                raise CreditClosed(self._closed_reason)
            self._available -= n

    def try_acquire(self, n: int) -> bool:
        """Non-waiting acquire. Returns False when the window is exhausted.

        Raises:
            CreditClosed: If the gate is closed.
        """
        with self._condition:
            if self._closed_reason is not None:
                raise CreditClosed(self._closed_reason)
            if self._available >= n:
                self._available -= n
                return True
            return False

    def blocking_acquire(self, n: int) -> None:
        """Blocking acquire for non-async/FFI-adjacent call sites.

        In the Rust reference this spins on ``try_acquire`` with a short park
        because the async ``acquire`` cannot be driven from a plain OS
        thread. The Python mirror has no separate async runtime in the hot
        path — every call site is already a plain thread — so this is simply
        an alias for :meth:`acquire`, which already blocks via
        ``Condition.wait()`` (no spinning, no wasted CPU).
        """
        self.acquire(n)

    def grant(self, n: int) -> None:
        """Replenish the window by `n` chunks and wake all waiters.
        Grants after close are no-ops."""
        with self._condition:
            if self._closed_reason is not None:
                return  # grants after close are no-ops
            self._available += n
            self._condition.notify_all()

    def close(self, reason: str) -> None:
        """Close the gate: all current and future acquires fail with `CreditClosed`."""
        with self._condition:
            if self._closed_reason is None:
                self._closed_reason = reason
            self._condition.notify_all()

    def available(self) -> int:
        """Currently available credit (diagnostic/stats)."""
        with self._condition:
            return self._available

    def is_closed(self) -> bool:
        """Whether the gate has been closed."""
        with self._condition:
            return self._closed_reason is not None


class CreditRouter:
    """Routes inbound CREDIT frames to the gates of the streams they credit.

    Keyed by (rid, stream_id). A CREDIT frame with no stream_id credits the
    request's sole/default stream: it matches the request's single registered
    gate when exactly one exists.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._gates: Dict[Tuple[MessageId, Optional[str]], CreditGate] = {}

    def register(self, rid: MessageId, stream_id: Optional[str], gate: CreditGate) -> None:
        """Register a gate for a stream a local sender is about to write."""
        with self._lock:
            self._gates[(rid, stream_id)] = gate

    def close_request(self, rid: MessageId, reason: str) -> None:
        """Remove and close every gate belonging to a request (terminal/cancel).
        Waiters blocked on those gates are released with `CreditClosed` (L13)."""
        with self._lock:
            keys = [k for k in self._gates.keys() if k[0] == rid]
            for key in keys:
                gate = self._gates.pop(key, None)
                if gate is not None:
                    gate.close(reason)

    def grant(self, frame: Frame) -> bool:
        """Deliver a CREDIT frame's grant to the matching gate.

        Returns False when no gate matches (request finished or the sender is
        not credit-registered) — a correct no-op, since grants only unblock.
        """
        if frame.frame_type != FrameType.CREDIT:
            return False
        credits = frame.credit_count()
        if credits is None:
            return False
        with self._lock:
            exact = self._gates.get((frame.id, frame.stream_id))
            if exact is not None:
                exact.grant(credits)
                return True
            if frame.stream_id is None:
                # No stream_id on the grant: match the request's sole gate if exactly one.
                matches: List[CreditGate] = [
                    g for (r, _sid), g in self._gates.items() if r == frame.id
                ]
                if len(matches) == 1:
                    matches[0].grant(credits)
                    return True
            return False

    def __len__(self) -> int:
        """Number of registered gates (diagnostic/stats)."""
        with self._lock:
            return len(self._gates)

    def is_empty(self) -> bool:
        return len(self) == 0
