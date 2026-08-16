"""Unified per-request state for routing runtimes (protocol v4, L7/L8).

One `RequestState` per in-flight request replaces the parallel routing maps
(routing entry, origin, peer markers, parent->child links, response channel,
rid->xid index) that previously had to be mutated consistently by hand.
Registration and termination are single operations: a request is registered
once and terminated once (End | Err | Cancelled | MasterDied); after
`terminate` returns, zero state for the key remains (L7).

The table is also the observability substrate: per-stream flow counters,
phase tracking, and a bounded ring of recently-terminated summaries feed the
protocol stats snapshots (L8) without retaining routing state.

Mirrors capdag/src/bifaci/request_state.rs (and the capdag-objc
RequestState.swift mirror). Snapshot types expose ``to_dict()`` producing the
same snake_case field-name contract as Rust's serde output (TEST7087) —
matching this mirror's existing snapshot idiom (see `stats.DropSnapshot`).

`RequestTable` is NOT internally synchronized — the owning runtime guards it
with its own lock (threading.Lock/RLock), mirroring Rust's
`RwLock<RequestTable>` and the capdag-objc mirror's un-synchronized class.
"""

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Dict, List, Optional, Tuple

from capdag.bifaci.frame import Frame, FrameType, MessageId


class RequestStateError(Exception):
    """Protocol violation raised by the unified request table (duplicate
    registration, rid re-indexing). Mirrors Rust's `Result<(), String>`."""
    pass


# (XID, RID) — the unique key of a routed request.
RequestKey = Tuple[MessageId, MessageId]


@dataclass
class RoutingEntry:
    """Where a request came from and where it is going, as master indices."""
    # Master the request arrived from (None = external caller / engine).
    source_master_idx: Optional[int]
    # Master the request was dispatched to.
    destination_master_idx: int


class TerminalKind(str, Enum):
    """How a request's lifecycle ended."""
    END = "end"
    ERR = "err"
    CANCELLED = "cancelled"
    MASTER_DIED = "master_died"

    def as_str(self) -> str:
        return self.value


class RequestPhase(str, Enum):
    """Live phase of a request. `Terminated` never appears in the active
    table — termination removes the entry (L7) and leaves a
    `TerminatedSummary` in the recent ring instead."""
    # Registered; no flow frames observed yet.
    CREATED = "created"
    # At least one flow frame has moved through the runtime.
    STREAMING = "streaming"


class FrameDirection(Enum):
    """Direction of a recorded frame relative to this runtime."""
    INBOUND = "inbound"
    OUTBOUND = "outbound"


@dataclass
class StreamFlowStats:
    """Per-stream flow accounting. Keyed by stream_id (None = frames not tied
    to a specific stream: REQ, END, ERR, LOG)."""
    frames_in: int = 0
    frames_out: int = 0
    bytes_in: int = 0
    bytes_out: int = 0
    chunks_in: int = 0
    chunks_out: int = 0
    # The stream's REMAINING credit window as observed by this runtime: the
    # negotiated initial window, plus credits granted through this runtime,
    # minus chunks that consumed them (in either direction — a stream's
    # chunks flow one way and its grants the other). Non-negative in healthy
    # operation; a negative value means the producer overran its window.
    # Diagnostic — the endpoints hold the authoritative windows.
    credit_outstanding: int = 0
    # Stream announced with unbounded=true (no length promise).
    unbounded: bool = False
    # STREAM_END observed.
    ended: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "frames_in": self.frames_in,
            "frames_out": self.frames_out,
            "bytes_in": self.bytes_in,
            "bytes_out": self.bytes_out,
            "chunks_in": self.chunks_in,
            "chunks_out": self.chunks_out,
            "credit_outstanding": self.credit_outstanding,
            "unbounded": self.unbounded,
            "ended": self.ended,
        }


class RequestState:
    """Everything a routing runtime knows about one in-flight request."""

    def __init__(
        self,
        routing: RoutingEntry,
        origin: Optional[int],
        external_channel: Optional[Callable[[Frame], None]],
        is_peer: bool,
        initial_credit: int,
    ) -> None:
        """Create request state.

        Args:
            routing: Source/destination master indices.
            origin: Master index the response must return to (None = external caller).
            external_channel: Response delivery callback for externally-registered requests.
            is_peer: Whether this is a cartridge-initiated peer invocation.
            initial_credit: The NEGOTIATED initial credit window of this
                request's destination — the ledger seed for every stream
                (see ``StreamFlowStats.credit_outstanding``).
        """
        now = time.monotonic()
        self.routing = routing
        self.origin = origin
        self.external_channel = external_channel
        self.is_peer = is_peer
        self.initial_credit = initial_credit
        # Cap URN of the originating REQ, when known at registration — the
        # request's nameable identity on the L8 surface. Without it a stats
        # snapshot shows only anonymous rids, making background chatter
        # indistinguishable from run traffic.
        self.cap_urn: Optional[str] = None
        # The process slot this request owns, released exactly once when the
        # request terminates. ``None`` for requests that took no permit (peer
        # calls and relay-internal probes).
        self.admission_permit: Optional["AdmissionPermit"] = None
        # Child peer calls spawned under this request (cancel cascade).
        self.children: List[RequestKey] = []
        self.phase: RequestPhase = RequestPhase.CREATED
        # Per-stream flow stats (None key = non-stream frames).
        self.streams: Dict[Optional[str], StreamFlowStats] = {}
        self.created_at: float = now
        self.last_activity: float = now

    def with_cap_urn(self, cap_urn: Optional[str]) -> "RequestState":
        """Attach the originating REQ's cap URN — the request's nameable
        identity in observability surfaces. Returns self for chaining
        (mirrors Rust's consuming builder)."""
        self.cap_urn = cap_urn
        return self

    def record(self, direction: FrameDirection, frame: Frame) -> None:
        """Record a frame's effect on this request's flow stats and phase."""
        self.last_activity = time.monotonic()
        if frame.is_flow_frame():
            self.phase = RequestPhase.STREAMING
        stats = self.streams.get(frame.stream_id)
        if stats is None:
            # A fresh stream starts with the NEGOTIATED initial window (L10):
            # the producer may send that many chunks before any CREDIT frame
            # arrives, so a ledger that starts at zero reads every healthy
            # stream as negative by exactly the initial window.
            stats = StreamFlowStats(credit_outstanding=self.initial_credit)
            self.streams[frame.stream_id] = stats
        num_bytes = len(frame.payload) if frame.payload is not None else 0
        if direction == FrameDirection.INBOUND:
            stats.frames_in += 1
            stats.bytes_in += num_bytes
            if frame.frame_type == FrameType.CHUNK:
                stats.chunks_in += 1
        else:
            stats.frames_out += 1
            stats.bytes_out += num_bytes
            if frame.frame_type == FrameType.CHUNK:
                stats.chunks_out += 1
        # A chunk consumes one credit from ITS stream's window regardless of
        # which way it flows past this runtime — a stream's chunks all flow
        # one direction, and its grants flow the other.
        if frame.frame_type == FrameType.CHUNK:
            stats.credit_outstanding -= 1
        if frame.frame_type == FrameType.STREAM_START and frame.is_unbounded():
            stats.unbounded = True
        elif frame.frame_type == FrameType.STREAM_END:
            stats.ended = True
        elif frame.frame_type == FrameType.CREDIT:
            credit_count = frame.credit_count()
            stats.credit_outstanding += credit_count if credit_count is not None else 0


@dataclass
class TerminatedSummary:
    """Summary of a finished request, retained in a bounded ring for stats."""
    xid: str
    rid: str
    kind: TerminalKind
    is_peer: bool
    cap_urn: Optional[str]
    lifetime_ms: int
    frames_in: int
    frames_out: int
    bytes_in: int
    bytes_out: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "xid": self.xid,
            "rid": self.rid,
            "kind": self.kind.value,
            "is_peer": self.is_peer,
            "cap_urn": self.cap_urn,
            "lifetime_ms": self.lifetime_ms,
            "frames_in": self.frames_in,
            "frames_out": self.frames_out,
            "bytes_in": self.bytes_in,
            "bytes_out": self.bytes_out,
        }


# How many terminated-request summaries the ring retains.
RECENT_TERMINATED_CAP = 64


@dataclass
class StreamSnapshot:
    """One stream's stats in a snapshot."""
    stream_id: Optional[str]
    stats: StreamFlowStats

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"stream_id": self.stream_id}
        out.update(self.stats.to_dict())
        return out


@dataclass
class RequestSnapshot:
    """One live request in a snapshot."""
    xid: str
    rid: str
    phase: RequestPhase
    is_peer: bool
    cap_urn: Optional[str]
    origin_master: Optional[int]
    destination_master: int
    age_ms: int
    idle_ms: int
    children: int
    streams: List[StreamSnapshot] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "xid": self.xid,
            "rid": self.rid,
            "phase": self.phase.value,
            "is_peer": self.is_peer,
            "cap_urn": self.cap_urn,
            "origin_master": self.origin_master,
            "destination_master": self.destination_master,
            "age_ms": self.age_ms,
            "idle_ms": self.idle_ms,
            "children": self.children,
            "streams": [s.to_dict() for s in self.streams],
        }


@dataclass
class RequestTableSnapshot:
    """Full table snapshot: the L8 observability surface for request state."""
    active: List[RequestSnapshot]
    recent_terminated: List[TerminatedSummary]
    total_registered: int
    terminated_by_kind: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "active": [r.to_dict() for r in self.active],
            "recent_terminated": [t.to_dict() for t in self.recent_terminated],
            "total_registered": self.total_registered,
            "terminated_by_kind": dict(self.terminated_by_kind),
        }


class RequestTable:
    """The unified request table (L7): one entry per in-flight request, one
    registration, one termination, plus the rid->xid secondary index and the
    recently-terminated ring.

    NOT internally synchronized — the owning runtime guards it with its own
    lock, mirroring Rust's `RwLock<RequestTable>`.
    """

    def __init__(self) -> None:
        self._entries: Dict[RequestKey, RequestState] = {}
        self._rid_index: Dict[MessageId, MessageId] = {}
        self._recent_terminated: Deque[TerminatedSummary] = deque()
        self._total_registered: int = 0
        self._terminated_by_kind: Dict[str, int] = {}
        # Called with every termination's summary, synchronously under the
        # table guard — observers must be cheap and non-blocking (an engine
        # aggregating per-run history, a test recorder). The bounded ring
        # serves polling; this hook serves accumulation that must not miss
        # terminations between polls (the ring evicts at RECENT_TERMINATED_CAP).
        self._terminate_observer: Optional[Callable[[TerminatedSummary], None]] = None

    def __repr__(self) -> str:
        return (
            f"RequestTable(entries={len(self._entries)}, "
            f"recent_terminated={len(self._recent_terminated)}, "
            f"total_registered={self._total_registered})"
        )

    def register(self, key: RequestKey, state: RequestState) -> None:
        """Register a request. A request is registered exactly once (L7):
        re-registering a live key, or a RID already indexed to a different
        XID, is a protocol violation and is rejected.

        Raises:
            RequestStateError: On duplicate registration or rid re-indexing.
        """
        xid, rid = key
        if key in self._entries:
            raise RequestStateError(
                f"request ({xid}, {rid}) already registered — a request is "
                "registered exactly once (L7)"
            )
        existing_xid = self._rid_index.get(rid)
        if existing_xid is not None and existing_xid != xid:
            raise RequestStateError(
                f"rid {rid} already indexed to xid {existing_xid} — cannot "
                f"re-index to xid {xid} (L7)"
            )
        self._rid_index[rid] = xid
        self._entries[key] = state
        self._total_registered += 1

    def get(self, key: RequestKey) -> Optional[RequestState]:
        return self._entries.get(key)

    def contains(self, key: RequestKey) -> bool:
        return key in self._entries

    def xid_for_rid(self, rid: MessageId) -> Optional[MessageId]:
        """Look up the XID a bare RID belongs to (continuation frames
        arriving without routing IDs)."""
        return self._rid_index.get(rid)

    def terminate(self, key: RequestKey, kind: TerminalKind) -> Optional[RequestState]:
        """Terminate a request: remove the entry and its rid index
        atomically, record a summary, and return the removed state (children
        for cancel cascades, the external channel for final delivery). After
        this returns, zero state for the key remains (L7). Returns None if
        the key is not live (already terminated — termination happens
        exactly once)."""
        state = self._entries.pop(key, None)
        if state is None:
            return None
        # Terminal state reached: give the cartridge its slot back. Exactly
        # once — the entry is removed above, so no other path can double-release.
        if state.admission_permit is not None:
            state.admission_permit.release()
        xid, rid = key
        # Only remove the rid index if it points at THIS xid — a re-used RID
        # under another XID (never valid per register, but defensive against
        # the impossible) must not lose its index.
        if self._rid_index.get(rid) == xid:
            del self._rid_index[rid]

        frames_in = sum(s.frames_in for s in state.streams.values())
        frames_out = sum(s.frames_out for s in state.streams.values())
        bytes_in = sum(s.bytes_in for s in state.streams.values())
        bytes_out = sum(s.bytes_out for s in state.streams.values())

        if len(self._recent_terminated) == RECENT_TERMINATED_CAP:
            self._recent_terminated.popleft()

        lifetime_ms = int((time.monotonic() - state.created_at) * 1000)
        summary = TerminatedSummary(
            xid=xid.to_string(),
            rid=rid.to_string(),
            kind=kind,
            is_peer=state.is_peer,
            cap_urn=state.cap_urn,
            lifetime_ms=lifetime_ms,
            frames_in=frames_in,
            frames_out=frames_out,
            bytes_in=bytes_in,
            bytes_out=bytes_out,
        )
        self._recent_terminated.append(summary)
        self._terminated_by_kind[kind.as_str()] = (
            self._terminated_by_kind.get(kind.as_str(), 0) + 1
        )
        if self._terminate_observer is not None:
            self._terminate_observer(summary)
        return state

    def set_terminate_observer(
        self, observer: Optional[Callable[[TerminatedSummary], None]]
    ) -> None:
        """Install the termination observer (see field docs). One observer;
        installing replaces any previous one."""
        self._terminate_observer = observer

    def recently_terminated_rid(self, rid: MessageId) -> bool:
        """Whether this RID belongs to a recently terminated request (the
        bounded ``_recent_terminated`` ring).

        This is the discriminator between the two ways a frame can arrive
        with no routing state. A hit here means the frame CROSSED its
        request's terminal in flight — the ordinary teardown race of
        credit-based flow control (a grant or straggler emitted before the
        sender observed END/ERR) — which receivers count as a BENIGN
        post-terminal straggler (nothing went wrong; never a drop).
        A miss means the table has never known the RID within the ring's
        horizon: a genuine ``no_route`` anomaly worth alarming on. The ring
        holds the last ``RECENT_TERMINATED_CAP`` terminations; the race
        window is milliseconds, so eviction cannot misclassify a real race,
        only age a pathologically late frame back into ``no_route`` — where
        something that stale belongs.
        """
        rid_str = str(rid)
        return any(t.rid == rid_str for t in self._recent_terminated)

    def record_frame(self, key: RequestKey, direction: FrameDirection, frame: Frame) -> None:
        """Record a frame moving through the runtime for this request.
        Unknown keys are ignored — the caller decides whether that is a
        counted drop (it is, at the routing layer) — recording is
        accounting, not routing."""
        state = self._entries.get(key)
        if state is not None:
            state.record(direction, frame)

    def link_child(self, parent: RequestKey, child: RequestKey) -> None:
        """Register a child peer call under its parent (cancel cascade)."""
        state = self._entries.get(parent)
        if state is not None:
            state.children.append(child)

    def keys(self) -> List[RequestKey]:
        """Keys of all live requests (for sweeps). Copied so the caller can
        mutate the table while iterating."""
        return list(self._entries.keys())

    def keys_where(self, pred: Callable[[RequestState], bool]) -> List[RequestKey]:
        """Keys of live requests matching a predicate on their state."""
        return [k for k, s in self._entries.items() if pred(s)]

    def __len__(self) -> int:
        return len(self._entries)

    def is_empty(self) -> bool:
        return len(self._entries) == 0

    def snapshot(self) -> RequestTableSnapshot:
        """Serializable snapshot of the table: live requests + recent
        terminations + lifetime totals. Field names are the mirror
        contract."""
        now = time.monotonic()
        active: List[RequestSnapshot] = []
        for key, s in self._entries.items():
            xid, rid = key
            streams = [
                StreamSnapshot(stream_id=stream_id, stats=stats)
                for stream_id, stats in s.streams.items()
            ]
            active.append(
                RequestSnapshot(
                    xid=xid.to_string(),
                    rid=rid.to_string(),
                    phase=s.phase,
                    is_peer=s.is_peer,
                    cap_urn=s.cap_urn,
                    origin_master=s.origin,
                    destination_master=s.routing.destination_master_idx,
                    age_ms=int((now - s.created_at) * 1000),
                    idle_ms=int((now - s.last_activity) * 1000),
                    children=len(s.children),
                    streams=streams,
                )
            )
        active.sort(key=lambda r: r.rid)
        return RequestTableSnapshot(
            active=active,
            recent_terminated=list(self._recent_terminated),
            total_registered=self._total_registered,
            terminated_by_kind=dict(sorted(self._terminated_by_kind.items())),
        )


# =============================================================================
# Admission control (mirrors Rust src/bifaci/request_state.rs).
#
# Pool-chain admission per cartridge install identity behind one relay master
# (see ``bifaci.pools``). The cartridge-side pool-chain gate
# (cartridge_runtime.py) bounds what one process runs at a time; THIS gate
# bounds what the switch dispatches to it, so work queues in the switch
# instead of piling up unacknowledged on the wire.
# =============================================================================

#: How long a queued request waits for an admission target that has gone
#: unavailable before it is failed.
#:
#: A cartridge disappearing from its host's inventory is not, by itself, a
#: reason to fail work that has not started: the process may be respawning, the
#: host may be re-publishing its roster, or a transient registry outage may have
#: briefly retired and then restored the install. 17.2 requires that queued
#: bodies are NOT assigned terminal failure from another body's process loss and
#: that "once a replacement instance advertises capacity, subsequent queued work
#: is admitted to that live instance" — this window is how long the queue is held
#: open for that replacement to appear.
#:
#: It is a bound, not a retry: when it expires the wait fails hard and the
#: failure is classified ``environment``, so a target that is genuinely gone
#: surfaces promptly instead of hanging the run.
ADMISSION_UNAVAILABLE_GRACE_SECONDS = 60.0


class AdmissionError(Exception):
    """A request could not take an admission slot. Carries the operator-facing
    reason; the switch maps it to a cartridge-unavailable routing error."""


@dataclass(frozen=True)
class AdmissionKey:
    """Stable admission identity for one cartridge behind one relay master."""

    master_idx: int
    registry_url: Optional[str]
    channel: str
    id: str
    version: str
    sha256: str


@dataclass(frozen=True)
class PoolKey:
    """One admission domain: a pool on one install. (matches Rust
    request_state::PoolKey)"""

    install: AdmissionKey
    pool: str


class _PoolSlot:
    """One pool's admission state: EFFECTIVE capacity (0 = unlimited),
    active count, and — for singleton pools only, the head of every chain —
    the FIFO ticket queue. (matches Rust PoolSlot)"""

    def __init__(self) -> None:
        self.capacity: int = 0
        self.active: int = 0
        self.queue: Deque[int] = deque()

    def has_room(self) -> bool:
        return self.capacity == 0 or self.active < self.capacity


class _InstallState:
    """One install's availability. Outages are an INSTALL-level fact — a
    process disappears whole, never one pool at a time. (matches Rust
    InstallState)"""

    def __init__(self) -> None:
        # ``None`` while the target is available; the monotonic instant it went
        # unavailable otherwise. Kept as an instant rather than a bool so the
        # grace window measures the OUTAGE, not the arrival time of each waiter
        # — a request that queues late into an outage does not get a fresh
        # window.
        self.unavailable_since: Optional[float] = None

    @property
    def available(self) -> bool:
        return self.unavailable_since is None

    def mark_unavailable(self, now: float) -> None:
        """Mark unavailable, preserving the start of an outage already in
        progress."""
        if self.unavailable_since is None:
            self.unavailable_since = now

    def grace_remaining(self, now: float, grace: float) -> Optional[float]:
        """Remaining grace for an outage, or ``None`` when available. ``0.0``
        means the window has expired."""
        if self.unavailable_since is None:
            return None
        return max(0.0, grace - (now - self.unavailable_since))


class AdmissionPermit:
    """A set of actively owned pool slots — a dispatch's whole chain.
    Released exactly once."""

    def __init__(self, controller: "AdmissionController", chain: List[PoolKey]) -> None:
        self._controller = controller
        self._chain = chain
        self._released = False

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._controller._release(self._chain)


class AdmissionController:
    """The engine-side pool admission gate (see ``bifaci.pools``): one slot
    per (install, pool), one availability state per install. A dispatch
    acquires its cap's whole pool CHAIN atomically."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._slots: Dict[PoolKey, _PoolSlot] = {}
        self._installs: Dict[AdmissionKey, _InstallState] = {}
        self._tickets = 0
        # ``ADMISSION_UNAVAILABLE_GRACE_SECONDS`` in production. Tests shorten
        # it to drive the expiry path without sleeping through a real minute.
        self.grace = ADMISSION_UNAVAILABLE_GRACE_SECONDS

    def configure_pools(self, install: AdmissionKey, pools: Dict[str, int]) -> None:
        """Advertise one install's full pool map: EFFECTIVE capacity per
        pool. A configure is the target advertising itself: it ENDS any
        outage, which is what releases waiters queued through a respawn or a
        roster round-trip. (matches Rust configure_pools)"""
        with self._condition:
            state = self._installs.get(install)
            if state is None:
                state = _InstallState()
                self._installs[install] = state
            state.unavailable_since = None
            for pool, capacity in pools.items():
                key = PoolKey(install=install, pool=pool)
                slot = self._slots.get(key)
                if slot is None:
                    slot = _PoolSlot()
                    self._slots[key] = slot
                slot.capacity = capacity
            self._condition.notify_all()

    def reconcile_master(self, master_idx: int, available: set) -> None:
        """Mark every install of this master absent from the advertised set
        unavailable."""
        now = time.monotonic()
        with self._condition:
            for install, state in self._installs.items():
                if install.master_idx == master_idx and install not in available:
                    state.mark_unavailable(now)
            self._condition.notify_all()

    def disable_master(self, master_idx: int) -> None:
        """Mark every install of this master unavailable (master died)."""
        now = time.monotonic()
        with self._condition:
            for install, state in self._installs.items():
                if install.master_idx == master_idx:
                    state.mark_unavailable(now)
            self._condition.notify_all()

    def acquire(
        self, chain: List[PoolKey], cancel: Optional[threading.Event] = None
    ) -> AdmissionPermit:
        """Take a FIFO admission slot across a cap's whole pool CHAIN,
        waiting for capacity. The chain's FIRST key is the cap's singleton
        pool — the queue the ticket waits in; admission requires EVERY chain
        pool to have room, decided in one critical section (no
        half-admission).

        An UNAVAILABLE target (an install-level fact) does not fail the
        caller immediately. The request stays queued for
        :data:`ADMISSION_UNAVAILABLE_GRACE_SECONDS` measured from the start
        of the outage, so a cartridge that is respawning — or that a
        transient registry outage briefly retired — resumes serving its
        queue instead of terminally failing every body waiting on it (17.2:
        one body's process loss must not terminate unrelated queued bodies).
        Only when the window expires does the wait fail, and it fails hard.

        ``cancel``, when set, abandons the wait (the caller gave up); the
        ticket is removed so it cannot strand the queue behind a dead head.
        (matches Rust acquire)
        """
        if not chain:
            raise AdmissionError(
                "admission chain is empty — a dispatch always has at least its cap's own pool"
            )
        head = chain[0]
        install = head.install
        with self._condition:
            for key in chain:
                if key not in self._slots:
                    raise AdmissionError(
                        f"cartridge '{key.install.id}' has no configured admission pool '{key.pool}'"
                    )
            ticket = self._tickets
            self._tickets += 1
            # Queue even while unavailable: the loop below owns the grace
            # window, so a request arriving mid-outage gets the same treatment
            # as one that was already waiting when the outage began.
            self._slots[head].queue.append(ticket)

            while True:
                if cancel is not None and cancel.is_set():
                    self._remove_ticket_locked(head, ticket)
                    raise AdmissionError(
                        f"admission wait for '{install.id}' was cancelled"
                    )
                head_slot = self._slots.get(head)
                if head_slot is None:
                    raise AdmissionError(
                        f"admission pool for '{install.id}' disappeared while queued"
                    )
                state = self._installs.get(install)
                if state is None:
                    raise AdmissionError(
                        f"cartridge '{install.id}' has admission pools but no install "
                        "state — configure_pools was bypassed"
                    )
                chain_has_room = all(self._slots[key].has_room() for key in chain)
                if state.available and chain_has_room and head_slot.queue and head_slot.queue[0] == ticket:
                    head_slot.queue.popleft()
                    for key in chain:
                        self._slots[key].active += 1
                    self._condition.notify_all()
                    return AdmissionPermit(self, list(chain))

                remaining = state.grace_remaining(time.monotonic(), self.grace)
                if remaining is not None and remaining <= 0.0:
                    # Outage outlived the window — the target is gone, not slow.
                    self._remove_ticket_locked(head, ticket)
                    raise AdmissionError(
                        f"cartridge '{install.id}' was unavailable for longer than "
                        f"{int(self.grace)}s while this request waited for capacity"
                    )
                # Available: wait for capacity. Mid-outage: wait no longer than
                # what is left of the window — a timeout there is not an error,
                # the next iteration re-reads the slot and decides. A cancellable
                # wait polls, because ``Condition`` cannot select on an Event.
                if cancel is not None:
                    poll = 0.02 if remaining is None else min(0.02, remaining)
                    self._condition.wait(poll)
                else:
                    self._condition.wait(remaining)

    def _remove_ticket_locked(self, key: PoolKey, ticket: int) -> None:
        """Drop a ticket from its singleton queue so an abandoned waiter
        cannot strand the queue behind it. Caller must hold the condition."""
        slot = self._slots.get(key)
        if slot is None:
            return
        try:
            slot.queue.remove(ticket)
        except ValueError:
            pass
        self._condition.notify_all()

    def _release(self, chain: List[PoolKey]) -> None:
        with self._condition:
            for key in chain:
                slot = self._slots.get(key)
                if slot is not None and slot.active > 0:
                    slot.active -= 1
            self._condition.notify_all()
