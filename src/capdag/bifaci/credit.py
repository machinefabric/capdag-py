"""Credit-based per-stream flow control (protocol v4).

One credit = permission to send one CHUNK frame. A sender starts each stream
with the negotiated ``initial_credit`` window and must wait when the window is
exhausted; the receiving endpoint replenishes it with CREDIT frames as it
consumes chunks (L9/L10 in the normative bifaci protocol documentation).

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
from typing import Dict, Optional, Tuple

from capdag import _formal
from capdag.bifaci.frame import Frame, FrameType, MessageId


def negotiate_initial_credit(ours: int, theirs: int) -> Optional[int]:
    """The credit window two ends start every stream with (L9): the smaller of
    the two proposals, decided by the proved model. ``None`` when the window
    would be zero — under a zero window no chunk could be sent and, with
    nothing consumed, none would ever be granted: every stream would stop at
    its first chunk, for good."""
    return _formal.negotiate(ours, theirs)


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

    What an acquire, a grant and a close do to the window is the proved
    model's decision (``formal/CapDAG/Bifaci/Credit.lean``); the gate keeps
    the window and wakes whoever waits on it.
    """

    def __init__(self, initial_credit: int):
        self._condition = threading.Condition()
        self._state = _formal.gate_opened(initial_credit)

    def _acquire_locked(self, n: int) -> bool:
        """Ask the model for `n` credits. Caller holds the condition."""
        answer = _formal.acquire(self._state, n)
        if isinstance(answer, _formal.AcquireAcquired):
            self._state = answer.gate
            return True
        if isinstance(answer, _formal.AcquireWait):
            return False
        if isinstance(answer, _formal.AcquireClosed):
            raise CreditClosed(answer.reason)
        raise RuntimeError(f"BUG: unknown answer to an acquire: {answer!r}")

    def acquire(self, n: int) -> None:
        """Acquire `n` credits, blocking if the window is exhausted.

        Raises:
            CreditClosed: If the gate closes before (or while) waiting.
        """
        with self._condition:
            while not self._acquire_locked(n):
                self._condition.wait()

    def try_acquire(self, n: int) -> bool:
        """Non-waiting acquire. Returns False when the window is exhausted.

        Raises:
            CreditClosed: If the gate is closed.
        """
        with self._condition:
            return self._acquire_locked(n)

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
            self._state = _formal.grant(self._state, n)
            self._condition.notify_all()

    def close(self, reason: str) -> None:
        """Close the gate: all current and future acquires fail with `CreditClosed`."""
        with self._condition:
            self._state = _formal.close(self._state, reason)
            self._condition.notify_all()

    def available(self) -> int:
        """Currently available credit (diagnostic/stats)."""
        with self._condition:
            return self._state.available

    def is_closed(self) -> bool:
        """Whether the gate has been closed."""
        with self._condition:
            return self._state.closed is not None


class CreditWindow:
    """The receiving end of one stream's credit window: what is left of what
    the sender was granted, and what this end has consumed and not yet granted
    back.

    - ``arrive()`` for each CHUNK: ``False`` is a CREDIT_VIOLATION — the
      sender sent past its window (L12).
    - ``consumed()`` once the chunk is consumed: the grant that is now due,
      ``0`` when the batch has not built up yet (L10: half the window, at
      least 1).
    - ``flush()`` when nothing more will be consumed for a while: whatever is
      pending is granted, so a sender never waits on a batch that will not
      fill.
    - ``continued()`` for a chunk that only continues an item: granted back at
      once, since nothing can consume it before the item is whole.

    Every decision is the proved model's
    (``formal/CapDAG/Bifaci/Credit.lean``).
    """

    def __init__(self, initial_credit: int):
        self._lock = threading.Lock()
        self._state = _formal.window_opened(initial_credit)

    def arrive(self) -> bool:
        """Account for one arriving CHUNK. ``False``: the chunk is beyond the
        granted window, and the window is unchanged."""
        with self._lock:
            arrival = _formal.window_arrive(self._state)
            if isinstance(arrival, _formal.CreditArrivalAccepted):
                self._state = arrival.window
                return True
            if isinstance(arrival, _formal.CreditArrivalViolation):
                return False
            raise RuntimeError(f"BUG: unknown answer to an arrival: {arrival!r}")

    def _granted(self, step) -> int:
        self._state = step.window
        return step.grant

    def consumed(self) -> int:
        """Account for one consumed chunk; the grant now due (0: none yet)."""
        with self._lock:
            return self._granted(_formal.consume(self._state))

    def flush(self) -> int:
        """The grant for everything consumed and not yet granted (0: nothing
        is pending)."""
        with self._lock:
            return self._granted(_formal.flush(self._state))

    def continued(self) -> int:
        """Account for a chunk that continues an item; the grant that gives it
        back at once."""
        with self._lock:
            return self._granted(_formal.continued(self._state))

    def remaining(self) -> int:
        """How many more chunks the sender may send before a grant."""
        with self._lock:
            return self._state.remaining

    def pending(self) -> int:
        """How many chunks were consumed and not yet granted back."""
        with self._lock:
            return self._state.pending


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
            # Which of the request's streams the grant is for is the model's
            # decision: the one it names, or — naming none — the only one
            # there is.
            streams = [sid for (rid, sid) in self._gates if rid == frame.id]
            target = _formal.grant_target(streams, frame.stream_id)
            if target is None:
                return False
            gate = self._gates[(frame.id, target.value)]
        gate.grant(credits)
        return True

    def __len__(self) -> int:
        """Number of registered gates (diagnostic/stats)."""
        with self._lock:
            return len(self._gates)

    def is_empty(self) -> bool:
        return len(self) == 0
