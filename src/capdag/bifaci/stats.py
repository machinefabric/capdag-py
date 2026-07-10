"""Protocol observability primitives shared by every bifaci runtime.

`DropCounters` is the L8 substrate: every frame a runtime drops increments
exactly one `DropReason` counter — frames are never dropped silently. The
counters are lock-protected so they can be bumped from writer threads and
blocking contexts alike, and snapshot into serializable maps for the
protocol stats surfaces.

(matches Rust src/bifaci/stats.rs and the capdag-objc Stats.swift mirror)
"""

import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Dict

from capdag.bifaci.frame import DropReason, FlowKey


# =============================================================================
# DROP COUNTERS — Per-reason dropped-frame counters (L8)
# =============================================================================

class DropCounters:
    """Per-reason dropped-frame counters (L8). Cheap to bump, snapshot on demand."""

    def __init__(self):
        self._counters: Dict[DropReason, int] = {reason: 0 for reason in DropReason.all()}
        self._lock = threading.Lock()

    def record(self, reason: DropReason) -> int:
        """Record one dropped frame. Returns the new total for that reason."""
        with self._lock:
            count = self._counters[reason] + 1
            self._counters[reason] = count
            return count

    def get(self, reason: DropReason) -> int:
        """Current count for one reason."""
        with self._lock:
            return self._counters[reason]

    def total(self) -> int:
        """Total drops across all reasons."""
        with self._lock:
            return sum(self._counters.values())

    def snapshot(self) -> "DropSnapshot":
        """Serializable snapshot keyed by the stable snake_case reason names —
        the field-name contract mirrors replicate. Zero-count reasons omitted."""
        with self._lock:
            by_reason: Dict[str, int] = {}
            total = 0
            for reason in DropReason.all():
                count = self._counters[reason]
                total += count
                if count > 0:
                    by_reason[reason.as_str()] = count
            return DropSnapshot(total=total, by_reason=by_reason)


# =============================================================================
# DROP SNAPSHOT — Serializable view of the drop counters
# =============================================================================

@dataclass(eq=True)
class DropSnapshot:
    """Serializable view of the drop counters."""
    total: int = 0
    # reason name (snake_case) -> count; zero-count reasons omitted.
    by_reason: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """CBOR-encodable dict, matching the `total` / `by_reason` wire contract."""
        return {"total": self.total, "by_reason": dict(self.by_reason)}

    @classmethod
    def from_dict(cls, raw: dict) -> "DropSnapshot":
        return cls(
            total=raw.get("total", 0),
            by_reason=dict(raw.get("by_reason", {}) or {}),
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
    FlowKey is post-terminal: it is dropped and counted instead of written.
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
