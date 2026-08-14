"""Protocol observability primitives shared by every bifaci runtime.

Two counter families, deliberately distinct because they mean opposite
things:

- ``DropCounters`` is the L8 substrate for frames lost to something going
  WRONG: every dropped frame increments exactly one ``DropReason`` ×
  ``FrameType`` counter — frames are never dropped silently, and a
  non-zero drop total is always worth investigating.
- ``StragglerCounters`` counts the benign teardown crossing: flow frames
  that arrive after their request's terminal, which the protocol expects
  (in-flight frames legally race END/ERR). Stragglers are moot by
  protocol — nothing went wrong, no data was lost — and every stats
  surface indicates them as benign, never as drops or failures.

The counters are lock-protected so they can be bumped from writer threads
and blocking contexts alike, and snapshot into serializable maps for the
protocol stats surfaces.

(matches Rust src/bifaci/stats.rs and the capdag-objc Stats.swift mirror)
"""

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Dict

from capdag.bifaci.frame import DropReason, FlowKey, FrameType


# =============================================================================
# DROP COUNTERS — Per-reason dropped-frame counters (L8)
# =============================================================================

class DropCounters:
    """Per-reason × per-frame-type dropped-frame counters (L8). Cheap to
    bump, snapshot on demand. Drops mean something went wrong — the benign
    post-terminal case is NOT recorded here (see ``StragglerCounters``)."""

    def __init__(self):
        self._counters: Dict[DropReason, Dict[FrameType, int]] = {
            reason: {frame_type: 0 for frame_type in FrameType.all()}
            for reason in DropReason.all()
        }
        self._lock = threading.Lock()

    def record(self, reason: DropReason, frame_type: FrameType) -> int:
        """Record one dropped frame of the given type. Returns the new
        total for that reason (across frame types)."""
        with self._lock:
            self._counters[reason][frame_type] += 1
            return sum(self._counters[reason].values())

    def get(self, reason: DropReason) -> int:
        """Current count for one reason, summed across frame types."""
        with self._lock:
            return sum(self._counters[reason].values())

    def get_frame(self, reason: DropReason, frame_type: FrameType) -> int:
        """Current count for one (reason, frame type) cell."""
        with self._lock:
            return self._counters[reason][frame_type]

    def total(self) -> int:
        """Total drops across all reasons."""
        with self._lock:
            return sum(sum(row.values()) for row in self._counters.values())

    def snapshot(self) -> "DropSnapshot":
        """Serializable snapshot keyed by the stable snake_case reason names —
        the field-name contract mirrors replicate. ``by_reason`` carries
        per-reason totals; ``by_reason_frame_type`` breaks each reason down
        by the dropped frame's type. Zero-count entries omitted from both."""
        with self._lock:
            by_reason: Dict[str, int] = {}
            by_reason_frame_type: Dict[str, Dict[str, int]] = {}
            total = 0
            for reason in DropReason.all():
                count = sum(self._counters[reason].values())
                total += count
                if count > 0:
                    by_reason[reason.as_str()] = count
                    by_reason_frame_type[reason.as_str()] = {
                        frame_type.as_str(): cell
                        for frame_type, cell in self._counters[reason].items()
                        if cell > 0
                    }
            return DropSnapshot(
                total=total,
                by_reason=by_reason,
                by_reason_frame_type=by_reason_frame_type,
            )


# =============================================================================
# DROP SNAPSHOT — Serializable view of the drop counters
# =============================================================================

@dataclass(eq=True)
class DropSnapshot:
    """Serializable view of the drop counters."""
    total: int = 0
    # reason name (snake_case) -> count; zero-count reasons omitted.
    by_reason: Dict[str, int] = field(default_factory=dict)
    # reason name -> (frame type name -> count); zero cells omitted.
    by_reason_frame_type: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """CBOR-encodable dict, matching the `total` / `by_reason` /
        `by_reason_frame_type` wire contract."""
        return {
            "total": self.total,
            "by_reason": dict(self.by_reason),
            "by_reason_frame_type": {k: dict(v) for k, v in self.by_reason_frame_type.items()},
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "DropSnapshot":
        return cls(
            total=raw.get("total", 0),
            by_reason=dict(raw.get("by_reason", {}) or {}),
            by_reason_frame_type={
                k: dict(v) for k, v in (raw.get("by_reason_frame_type", {}) or {}).items()
            },
        )


# =============================================================================
# STRAGGLER COUNTERS — Benign post-terminal frames (never drops)
# =============================================================================

class StragglerCounters:
    """Per-frame-type counters for BENIGN post-terminal stragglers.

    A straggler is a flow frame that arrives after its request's terminal
    (END/ERR) — the ordinary, protocol-legal teardown crossing (L13): a
    callee may END before draining its input, a final CREDIT grant may
    cross the terminal in flight. Nothing went wrong and no data was lost;
    the frame is simply moot. Counted per frame type so surfaces can say
    exactly what crossed ("late credit" vs "late chunk") — and always
    indicated as benign, never as a drop or failure.
    (matches Rust StragglerCounters)"""

    def __init__(self):
        self._counters: Dict[FrameType, int] = {
            frame_type: 0 for frame_type in FrameType.all()
        }
        self._lock = threading.Lock()

    def record(self, frame_type: FrameType) -> int:
        """Record one benign post-terminal straggler. Returns the new total."""
        with self._lock:
            self._counters[frame_type] += 1
            return sum(self._counters.values())

    def get(self, frame_type: FrameType) -> int:
        """Current count for one frame type."""
        with self._lock:
            return self._counters[frame_type]

    def total(self) -> int:
        """Total stragglers across all frame types."""
        with self._lock:
            return sum(self._counters.values())

    def snapshot(self) -> "StragglerSnapshot":
        """Serializable snapshot keyed by the stable snake_case frame-type
        names; zero-count types omitted."""
        with self._lock:
            by_frame_type = {
                frame_type.as_str(): count
                for frame_type, count in self._counters.items()
                if count > 0
            }
            return StragglerSnapshot(
                total=sum(self._counters.values()),
                by_frame_type=by_frame_type,
            )


@dataclass(eq=True)
class StragglerSnapshot:
    """Serializable view of the straggler counters — benign by definition."""
    total: int = 0
    # frame type name (snake_case) -> count; zero-count types omitted.
    by_frame_type: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """CBOR-encodable dict, matching the `total` / `by_frame_type` wire contract."""
        return {"total": self.total, "by_frame_type": dict(self.by_frame_type)}

    @classmethod
    def from_dict(cls, raw: dict) -> "StragglerSnapshot":
        return cls(
            total=raw.get("total", 0),
            by_frame_type=dict(raw.get("by_frame_type", {}) or {}),
        )


# =============================================================================
# HOST PROTOCOL STATS — Per-host protocol observability snapshot (L8)
# =============================================================================

@dataclass(eq=True)
class HostProtocolStats:
    """A host runtime's protocol observability snapshot (L8): per-reason
    drop counters, routing-table sizes, and GC totals. Serializable; field
    names are the mirror contract (mirrors Rust ``HostProtocolStats``
    wire-for-wire over RelayNotify JSON, and the capdag-objc
    ``HostProtocolStats`` Codable mirror)."""

    drops: DropSnapshot
    # Benign post-terminal stragglers — the expected teardown crossing,
    # counted per frame type. Separate from drops: nothing went wrong.
    stragglers: "StragglerSnapshot" = field(default_factory=lambda: StragglerSnapshot())
    outgoing_rids: int = 0
    incoming_rxids: int = 0
    incoming_to_peer_rids: int = 0
    outgoing_max_seq: int = 0
    routing_gc_runs_total: int = 0
    routing_gc_evicted_total: int = 0

    def to_dict(self) -> dict:
        """CBOR/JSON-encodable dict matching the reference field-name contract."""
        return {
            "drops": self.drops.to_dict(),
            "stragglers": self.stragglers.to_dict(),
            "outgoing_rids": self.outgoing_rids,
            "incoming_rxids": self.incoming_rxids,
            "incoming_to_peer_rids": self.incoming_to_peer_rids,
            "outgoing_max_seq": self.outgoing_max_seq,
            "routing_gc_runs_total": self.routing_gc_runs_total,
            "routing_gc_evicted_total": self.routing_gc_evicted_total,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "HostProtocolStats":
        return cls(
            drops=DropSnapshot.from_dict(raw.get("drops", {}) or {}),
            stragglers=StragglerSnapshot.from_dict(raw.get("stragglers", {}) or {}),
            outgoing_rids=raw.get("outgoing_rids", 0),
            incoming_rxids=raw.get("incoming_rxids", 0),
            incoming_to_peer_rids=raw.get("incoming_to_peer_rids", 0),
            outgoing_max_seq=raw.get("outgoing_max_seq", 0),
            routing_gc_runs_total=raw.get("routing_gc_runs_total", 0),
            routing_gc_evicted_total=raw.get("routing_gc_evicted_total", 0),
        )


# =============================================================================
# TERMINATED FLOWS — Writer-side terminal gate set (L4)
# =============================================================================

class TerminatedFlows:
    """Terminated-flow set for the writer-side terminal gate (L4).

    After a flow's END/ERR is written, any later flow frame for the same
    FlowKey is a benign post-terminal straggler: it is suppressed and
    counted as such (never a drop) instead of written.
    The set is capacity-bounded FIFO — with seq state already removed at the
    terminal, an evicted entry can only readmit a straggler that the
    receiving side's reorder/routing layers then reject; the cap bounds
    memory on long-lived cartridges, it does not change protocol
    correctness.
    """

    def __init__(self, cap: int):
        if cap <= 0:
            raise ValueError("TerminatedFlows cap must be positive")
        self._order: deque = deque()
        self._set: set = set()
        self._cap = cap
        self._lock = threading.Lock()

    def insert(self, key: FlowKey) -> None:
        """Mark a flow terminated. Evicts the oldest entry at capacity."""
        with self._lock:
            if key in self._set:
                return
            if len(self._order) == self._cap:
                oldest = self._order.popleft()
                self._set.discard(oldest)
            self._order.append(key)
            self._set.add(key)

    def contains(self, key: FlowKey) -> bool:
        """Whether this flow has already seen its terminal frame."""
        with self._lock:
            return key in self._set

    def len(self) -> int:
        with self._lock:
            return len(self._set)

    def is_empty(self) -> bool:
        return self.len() == 0
