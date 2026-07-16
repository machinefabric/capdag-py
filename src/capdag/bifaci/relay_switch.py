"""RelaySwitch — Cap-aware routing multiplexer for multiple RelayMasters.

RelaySwitch sits above multiple RelayMasters and provides deterministic
request routing based on cap URN matching. It plays the same role for RelayMasters
that CartridgeHost plays for cartridges.

## Architecture

```text
┌─────────────────────────────┐
│   Test Engine / API Client  │
└──────────────┬──────────────┘
               │
┌──────────────▼──────────────┐
│       RelaySwitch            │
│  • Aggregates capabilities   │
│  • Routes REQ by cap URN     │
│  • Routes frames by req_id   │
│  • Tracks peer requests      │
└─┬───┬───┬───┬───────────────┘
  │   │   │   │
  ▼   ▼   ▼   ▼
 RM  RM  RM  RM   (RelayMasters)
```

No fallbacks. No heuristics. No special cases. Just deterministic frame routing
based on URN matching and request ID tracking.
"""

import json
import threading
import queue
import time
from typing import Any, Callable, Optional, List, Tuple, Dict
from dataclasses import dataclass, field

from capdag.bifaci.frame import (
    FailureClass,
    Frame, FrameType, Limits, MessageId, compute_checksum, DropReason,
    DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK, DEFAULT_MAX_REORDER_BUFFER,
)
from capdag.bifaci.io import FrameReader, FrameWriter, CborError, verify_identity, identity_nonce
from capdag.bifaci.request_state import (
    FrameDirection,
    RequestState,
    RequestStateError,
    RequestTable,
    RequestTableSnapshot,
    RoutingEntry,
    TerminalKind,
    TerminatedSummary,
)
from capdag.bifaci.stats import DropCounters, DropSnapshot, HostProtocolStats
from capdag.standard.caps import CAP_IDENTITY
from capdag.urn.cap_urn import CapUrn

# =============================================================================
# ERROR TYPES
# =============================================================================

class RelaySwitchError(Exception):
    """Base error for RelaySwitch"""
    pass


class NoHandlerError(RelaySwitchError):
    """No master found for capability"""
    def __init__(self, cap_urn: str):
        super().__init__(f"No handler for cap: {cap_urn}")
        self.cap_urn = cap_urn


class UnknownRequestError(RelaySwitchError):
    """Unknown request ID"""
    def __init__(self, request_id: str):
        super().__init__(f"Unknown request ID: {request_id}")
        self.request_id = request_id


class ProtocolError(RelaySwitchError):
    """Protocol violation"""
    pass


class AllMastersUnhealthyError(RelaySwitchError):
    """All masters are unhealthy"""
    def __init__(self):
        super().__init__("All relay masters are unhealthy")


# =============================================================================
# CARTRIDGE ATTACHMENT ERRORS
# =============================================================================

from enum import Enum


class CartridgeAttachmentErrorKind(str, Enum):
    """Kinds of attachment failure for a cartridge. Matches the
    ``CartridgeAttachmentErrorKind`` enum defined in ``cartridge.proto``;
    this enum is the authoritative, language-neutral domain definition.
    The value is the snake_case wire form."""

    #: Manifest parsed but violates the cartridge schema (missing required
    #: CAP_IDENTITY, min_app_version not met, old-format cap_groups, ...).
    INCOMPATIBLE = "incompatible"
    #: cartridge.json or HELLO manifest failed to parse as JSON, or lacked
    #: required top-level fields.
    MANIFEST_INVALID = "manifest_invalid"
    #: HELLO handshake did not complete (timeout, bad frame sequence, I/O).
    HANDSHAKE_FAILED = "handshake_failed"
    #: CAP_IDENTITY echo protocol check failed.
    IDENTITY_REJECTED = "identity_rejected"
    #: Entry point binary missing or not executable.
    ENTRY_POINT_MISSING = "entry_point_missing"
    #: Cartridge repeatedly crashed the host during discovery; quarantined.
    QUARANTINED = "quarantined"
    #: On-disk install context disagrees with the cartridge.json the
    #: cartridge declares — slug folder mismatch, channel folder mismatch,
    #: or name/version directory mismatch. Structurally well-formed but
    #: cannot be trusted because its placement does not match what it
    #: claims to be. Distinct from QUARANTINED and MANIFEST_INVALID.
    BAD_INSTALLATION = "bad_installation"
    #: Operator explicitly disabled this cartridge through the host UI.
    DISABLED = "disabled"
    #: The cartridge declares a non-null registry_url but the host could
    #: not reach that registry to verify the cartridge is listed.
    REGISTRY_UNREACHABLE = "registry_unreachable"
    #: The cartridge was built against a different fabric registry manifest
    #: version than this engine is pinned to.
    FABRIC_MANIFEST_VERSION_MISMATCH = "fabric_manifest_version_mismatch"


@dataclass
class CartridgeAttachmentError:
    """Structured per-cartridge attachment failure."""

    kind: CartridgeAttachmentErrorKind
    message: str
    #: Unix timestamp seconds when the failure was first detected.
    detected_at_unix_seconds: int = 0


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class SocketPair:
    """Socket pair for master connection.

    ``id`` is the stable identity of the cardinality slot this socket
    fills. The relay's ``add_master`` reattach-by-id contract uses it
    on subsequent reconnects to find the slot to reattach to —
    preserving slot indices across the death-and-reconnect cycle.
    Re-adding the same id while the slot is still healthy is a
    wiring bug and is rejected.
    """
    id: str
    read: object  # file-like object for reading
    write: object  # file-like object for writing


class CartridgeLifecycle(str, Enum):
    """Positive lifecycle phase of an installed cartridge.

    Mutually exclusive with ``attachment_error``: when an attachment error
    is present this field is irrelevant. When there is no attachment error, a
    cartridge is dispatchable iff it has reached ``OPERATIONAL``. Mirrors the
    reference ``CartridgeLifecycle`` (snake_case wire values).
    """

    #: Found on disk; not yet inspected. Safe default — never dispatchable.
    DISCOVERED = "discovered"
    #: Manifest/identity being read.
    INSPECTING = "inspecting"
    #: Registry/verifier round-trip in progress.
    VERIFYING = "verifying"
    #: Fully verified and dispatchable.
    OPERATIONAL = "operational"

    @staticmethod
    def default() -> "CartridgeLifecycle":
        """The safe sentinel: a freshly-constructed identity is
        ``DISCOVERED``, never ``OPERATIONAL`` (which would falsely advertise
        a cartridge as dispatchable)."""
        return CartridgeLifecycle.DISCOVERED


@dataclass
class CartridgeRuntimeStats:
    """Live runtime statistics from the owning host. Mirrors the reference
    ``CartridgeRuntimeStats``. Absent (``None``) for cartridges that are not
    yet running (e.g. dir-registered, spawn-on-demand)."""

    running: bool = False
    pid: Optional[int] = None
    active_request_count: int = 0
    peer_request_count: int = 0
    memory_footprint_mb: int = 0
    memory_rss_mb: int = 0
    last_heartbeat_unix_seconds: Optional[int] = None
    restart_count: int = 0
    #: Cumulative protocol drop count self-reported by the cartridge as
    #: ``drops_total`` in heartbeat response meta (writer-gate post-terminal
    #: drops, closed-channel sends, …). ``None`` until the first heartbeat
    #: round-trip carries the counter — never a fabricated zero. Mirrors the
    #: reference ``CartridgeRuntimeStats.protocol_drops_total`` (L8).
    protocol_drops_total: Optional[int] = None


@dataclass
class InstalledCartridgeRecord:
    """Identity of an installed cartridge.

    `(registry_url, channel, id, version)` is the install's full
    identity. Each ``(registry, channel)`` is an independent
    namespace; installs of the same id+version from different
    registries × channels coexist on disk under different top-level
    slug folders.

    ``registry_url`` is ``Optional[str]``: ``None`` ⇔ dev install
    (cartridge built locally without ``MFR_CARTRIDGE_REGISTRY_URL``); non-None
    ⇔ verbatim URL the cartridge was published from. Compared
    byte-wise; never normalized.

    ``cap_groups`` carries the cartridge's manifest cap_groups so the
    engine can register content-inspection adapters per cartridge. The
    flat cap-urn snapshot is computed from these groups, never stored
    alongside them on the wire.

    ``attachment_error`` is present when the cartridge failed attachment
    (manifest, handshake, identity, …) and absent when attached and healthy.
    ``lifecycle`` is the positive phase, mutually exclusive with
    ``attachment_error``. ``runtime_stats`` carries live host-side stats.
    These three mirror the reference ``InstalledCartridgeRecord`` wire shape.
    """
    registry_url: Optional[str]
    id: str
    channel: str
    version: str
    sha256: str
    cap_groups: List[Any] = field(default_factory=list)
    attachment_error: Optional[CartridgeAttachmentError] = None
    runtime_stats: Optional[CartridgeRuntimeStats] = None
    #: Defaults to ``DISCOVERED`` (the safe sentinel) so a producer that
    #: forgets to set it never accidentally appears as ``OPERATIONAL``.
    lifecycle: CartridgeLifecycle = field(default_factory=CartridgeLifecycle.default)

    def effective_lifecycle(self) -> "CartridgeLifecycle":
        """The lifecycle phase, defaulting to ``DISCOVERED`` when unset.
        Callers SHOULD use this rather than reading ``lifecycle`` directly so
        an unset field cannot be mistaken for ``OPERATIONAL``. Mirrors the Go
        ``EffectiveLifecycle``."""
        return self.lifecycle or CartridgeLifecycle.DISCOVERED

    def registry_slug(self) -> str:
        """On-disk slug derived from ``registry_url``. ``None`` →
        ``DEV_SLUG``; non-None → first 16 hex chars of SHA-256 of
        the URL bytes."""
        from capdag.bifaci.cartridge_slug import slug_for
        return slug_for(self.registry_url)

    def cap_urns(self) -> List[str]:
        """Flat de-duplicated cap-URN view across this cartridge's
        groups, preserving first-seen order. Each URN is parsed and
        re-serialized so the returned strings are in canonical form
        regardless of how the cartridge authored them on the wire.
        Canonical form is what `find_master_for_cap` matches against
        — without this, two-equal-but-differently-spelled URNs route
        independently and dispatch silently misses the candidate."""
        seen = set()
        out: List[str] = []
        for group in self.cap_groups:
            caps = group.get("caps", []) if isinstance(group, dict) else []
            for cap in caps:
                raw = cap.get("urn", "") if isinstance(cap, dict) else ""
                if not raw:
                    continue
                # Canonicalize via parse + re-serialize. Failure here
                # means the cartridge advertised an invalid URN —
                # surface it loudly rather than silently passing the
                # raw string through.
                try:
                    canonical = CapUrn.from_string(raw).to_string()
                except Exception:
                    raise ProtocolError(
                        f"installed_cartridges entry advertises invalid cap URN: {raw!r}"
                    )
                if canonical in seen:
                    continue
                seen.add(canonical)
                out.append(canonical)
        return out


@dataclass
class MasterFrame:
    """Frame received from a master"""
    master_idx: int
    frame: Optional[Frame]
    error: Optional[Exception]


@dataclass
class RelaySwitchProtocolStats:
    """The switch's protocol observability snapshot (L8): live request state,
    recent terminations, and per-reason drop counters. Field names are the
    mirror contract. Mirrors the reference ``RelaySwitchProtocolStats``.

    ``hosts`` is per-master host protocol stats (drops, routing-table sizes,
    GC totals), keyed by master id, as reported in each host's latest
    RelayNotify. A master that has not yet advertised host stats is absent
    — never a zeroed placeholder.
    """
    requests: RequestTableSnapshot
    drops: DropSnapshot
    hosts: Dict[str, "HostProtocolStats"] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requests": self.requests.to_dict(),
            "drops": self.drops.to_dict(),
            "hosts": {k: v.to_dict() for k, v in self.hosts.items()},
        }


def _extract_parent_rid(meta: Optional[Dict[str, Any]]) -> Optional[MessageId]:
    """Extract the ``parent_rid`` cancel-cascade marker from a REQ's meta, if
    present. The value is CBOR-decoded already: 16-byte ``bytes``/``bytearray``
    for a UUID rid, or ``int`` for a Uint rid. Any other shape (or absence) is
    "no parent" — never an error, since most REQs are not peer calls."""
    if not meta:
        return None
    raw = meta.get("parent_rid")
    if isinstance(raw, (bytes, bytearray)) and len(raw) == 16:
        return MessageId(bytes(raw))
    if isinstance(raw, int):
        return MessageId(raw)
    return None


# =============================================================================
# RELAY SWITCH
# =============================================================================

class RelaySwitch:
    """Cap-aware routing multiplexer for multiple RelayMasters.

    Routes requests based on cap URN matching and tracks bidirectional request/response flows.
    """

    def __init__(self, sockets: List[SocketPair]):
        """Create a RelaySwitch from socket pairs.

        Each ``SocketPair`` carries an ``id`` that is the stable
        identity of its cardinality slot. ``add_master`` uses the id
        to reattach a reconnecting host to the same slot index —
        preserving the routing entries keyed by index. Duplicate
        ids in the constructor list are a wiring bug and surface as
        a hard ``ProtocolError`` (without this guard the first
        reconnect would reattach to whichever slot is found first
        by the linear scan, leaving the other stuck unhealthy
        forever — the exact bug class this contract closes).

        Args:
            sockets: List of socket pairs (one per master). Each
                pair's ``id`` must be unique within the list.

        Raises:
            RelaySwitchError: If construction fails (including
                duplicate ids).
        """
        if not sockets:
            raise ProtocolError("RelaySwitch requires at least one master")

        # Reject duplicate ids up front.
        seen_ids = set()
        for sp in sockets:
            if sp.id in seen_ids:
                raise ProtocolError(
                    f"RelaySwitch.__init__: duplicate master id {sp.id!r} in cardinality list — "
                    f"each slot must have a unique stable id"
                )
            seen_ids.add(sp.id)

        self._masters: List[_MasterConnection] = []
        self._cap_table: List[Tuple[str, int]] = []  # (cap_urn, master_idx)
        # Unified per-request state (L7): routing, origin, peer markers,
        # cancel-cascade children, external response channel, per-stream flow
        # stats, and the rid→xid index — one entry, one registration, one
        # termination. Replaces the smeared routing/peer/parent maps. Guarded
        # by `self._lock` (the table itself is unsynchronized, mirroring the
        # reference `RwLock<RequestTable>`).
        self._requests: RequestTable = RequestTable()
        # Dropped-frame accounting (L8): unroutable/post-terminal frames are
        # counted drops, never silent losses and never protocol errors.
        self._drops: DropCounters = DropCounters()
        self._aggregate_capabilities: bytes = b""
        self._aggregate_installed_cartridges: List[InstalledCartridgeRecord] = []
        self._negotiated_limits: Limits = Limits.default()
        self._lock = threading.Lock()
        # Serialises ``add_master`` calls so the master_idx reservation
        # for an append is race-free, and so the reattach branch sees a
        # stable ``self._masters`` snapshot across the I/O.
        self._add_master_lock = threading.Lock()
        # How many masters this engine intends to register at startup.
        # 0 means "not yet declared"; ``all_masters_ready`` returns
        # False in that state rather than guessing. Set once at boot via
        # ``set_expected_master_count``.
        self._expected_master_count = 0

        # Channel for reader threads to send frames
        self._frame_queue: queue.Queue = queue.Queue()

        # Routable-capability watch (health-filtered union of cap URNs). This
        # is the engine-readiness signal: a cap appears here only once its
        # master is healthy (identity-verified). Initialised to the empty
        # JSON array so a subscriber that arrives before the first rebuild
        # still gets a well-formed snapshot.
        self._routable_caps_bytes: bytes = json.dumps([]).encode("utf-8")
        self._capabilities_watch = _CapabilityWatch(self._routable_caps_bytes)

        # Deferred runtime identity-probe machinery. When a master transitions
        # from empty caps to non-empty caps via a RelayNotify update, its
        # index is queued here and the probe driver thread re-verifies its
        # identity end-to-end before the new caps become routable. Echo frames
        # route back through ``_external_response_channels`` keyed by the
        # probe's request id.
        self._external_response_channels: Dict[str, "queue.Queue[Frame]"] = {}
        self._pending_identity_probes: "queue.Queue[Optional[int]]" = queue.Queue()
        self._xid_counter: int = 0
        # Background-pump bookkeeping (the pump drains master frames and routes
        # probe echoes; started on demand via ``start_background_pump``).
        self._pump_started = False
        self._pump_stop = False
        # The probe driver runs for the switch's lifetime; it only does work
        # while frames are being drained (by the pump or ``read_from_masters``).
        self._probe_driver = threading.Thread(
            target=self._probe_driver_loop, daemon=True
        )
        self._probe_driver.start()

        # Connect to all masters
        for master_idx, sock_pair in enumerate(sockets):
            reader = FrameReader(sock_pair.read)
            writer = FrameWriter(sock_pair.write)

            # Perform handshake (read initial RelayNotify)
            frame = reader.read()
            if frame is None or frame.frame_type != FrameType.RELAY_NOTIFY:
                raise ProtocolError("Expected RelayNotify during handshake")

            manifest = frame.relay_notify_manifest()
            limits = frame.relay_notify_limits()

            if manifest is None or limits is None:
                raise ProtocolError("RelayNotify missing manifest or limits")

            caps, installed_cartridges, host_protocol_stats = _parse_relay_notify_payload(manifest)
            reader.set_limits(limits)
            writer.set_limits(limits)

            # End-to-end identity verification. The probe only makes sense
            # when the host advertises at least one cap — an empty cap list
            # means "no cartridges attached successfully" and there is no
            # handler chain to test. The master still joins (capless, healthy)
            # so its installed_cartridges attachment errors reach the engine,
            # and a later empty→non-empty RelayNotify triggers the deferred
            # runtime probe. Mirrors the reference ``new`` (which probes only
            # when caps are non-empty and propagates a probe failure as a
            # hard construction error).
            if caps:
                try:
                    verify_identity(reader, writer)
                except Exception as e:
                    raise ProtocolError(f"identity verification failed: {e}") from e

            # Build the reader thread but DO NOT start it until the master is
            # in ``self._masters``. A capless master's slave can send a
            # populated (empty→non-empty) RelayNotify immediately after the
            # handshake notify; if the reader thread ran before the append it
            # would observe ``len(self._masters) == 0`` and silently drop the
            # transition (the deferred identity probe would never fire).
            reader_thread = threading.Thread(
                target=self._reader_loop,
                args=(master_idx, reader),
                daemon=True
            )

            master_conn = _MasterConnection(
                id=sock_pair.id,
                socket_writer=writer,
                manifest=manifest,
                limits=limits,
                caps=caps,
                installed_cartridges=installed_cartridges,
                healthy=True,
                reader_handle=reader_thread,
                host_protocol_stats=host_protocol_stats,
            )
            self._masters.append(master_conn)
            reader_thread.start()

        # Build initial routing tables. Order matters:
        # `_rebuild_capabilities` reads `_aggregate_installed_cartridges`
        # so the aggregate must be rebuilt first.
        self._rebuild_cap_table()
        self._rebuild_installed_cartridges()
        self._rebuild_capabilities()
        self._rebuild_limits()

    def add_master(self, sock_pair: SocketPair) -> int:
        """Attach a (re)connecting host to a slot.

        ``sock_pair.id`` is the stable identity of the cardinality
        slot:

        - **Existing slot, currently UNHEALTHY** → reattach in place
          at the existing slot index. The dead master's reader
          thread has already exited on EOF; the new connection
          installs a fresh writer / reader thread and clears the
          unhealthy flag. ``request_routing`` and ``cap_table``
          entries keyed by ``master_idx`` stay coherent because the
          index does not change.

        - **Existing slot, currently HEALTHY** → caller bug
          (the same master must not be added twice). Surface as a
          ``ProtocolError`` so the wiring mistake is fixed
          instead of silently growing zombie slots.

        - **No existing slot with that id** → append a fresh slot
          at ``len(self._masters)``. The reader thread is spawned
          with that index baked in.

        Returns the slot index (stable across reattach).
        """
        with self._add_master_lock:
            # Existing-slot lookup under the lock so the linear scan
            # observes a stable ``self._masters``.
            existing_idx: Optional[int] = None
            with self._lock:
                for idx, master in enumerate(self._masters):
                    if master.id == sock_pair.id:
                        if master.healthy:
                            raise ProtocolError(
                                f"add_master: id {sock_pair.id!r} is already attached to a "
                                f"healthy slot at index {idx} — cardinality violation "
                                f"(each id may only be attached once at a time)"
                            )
                        existing_idx = idx
                        break

            # Reserve the slot index. For the append case this is
            # the current length under ``_add_master_lock``; for
            # reattach it is the existing slot index. The reader
            # thread captures this value so per-frame routing
            # always carries the right index.
            with self._lock:
                master_idx = existing_idx if existing_idx is not None else len(self._masters)

            # Handshake (read RelayNotify + verify identity).
            reader = FrameReader(sock_pair.read)
            writer = FrameWriter(sock_pair.write)
            frame = reader.read()
            if frame is None or frame.frame_type != FrameType.RELAY_NOTIFY:
                raise ProtocolError("Expected RelayNotify during handshake")
            manifest = frame.relay_notify_manifest()
            limits = frame.relay_notify_limits()
            if manifest is None or limits is None:
                raise ProtocolError("RelayNotify missing manifest or limits")
            caps, installed_cartridges, host_protocol_stats = _parse_relay_notify_payload(manifest)
            reader.set_limits(limits)
            writer.set_limits(limits)

            # End-to-end identity verification — probe only when the host
            # advertises caps. Unlike the constructor, a probe FAILURE here
            # does NOT abort registration: the master joins UNHEALTHY with
            # ``last_error`` populated, so its installed_cartridges remain
            # visible in the inventory aggregate while its caps are held back
            # from routing. Mirrors the reference ``add_master``.
            identity_failure: Optional[str] = None
            if caps:
                try:
                    verify_identity(reader, writer)
                except Exception as e:
                    identity_failure = f"identity verification failed: {e}"
            healthy_at_register = identity_failure is None

            # Build the reader thread bound to master_idx but DO NOT start it
            # until the slot is committed below — otherwise a capless master's
            # immediate empty→non-empty RelayNotify could be observed before
            # the slot exists and the deferred probe would never fire.
            reader_thread = threading.Thread(
                target=self._reader_loop,
                args=(master_idx, reader),
                daemon=True,
            )

            # Commit the connection state into the slot.
            with self._lock:
                if existing_idx is None:
                    # Append. The captured ``master_idx`` MUST equal
                    # the new length; if not, a concurrent appender
                    # bypassed ``_add_master_lock``, which is a
                    # protocol violation.
                    if len(self._masters) != master_idx:
                        raise ProtocolError(
                            f"add_master: append-index race for id {sock_pair.id!r}: "
                            f"reserved {master_idx} but len(masters) is now {len(self._masters)} "
                            f"(a concurrent caller bypassed _add_master_lock)"
                        )
                    self._masters.append(_MasterConnection(
                        id=sock_pair.id,
                        socket_writer=writer,
                        manifest=manifest,
                        limits=limits,
                        caps=caps,
                        installed_cartridges=installed_cartridges,
                        healthy=healthy_at_register,
                        reader_handle=reader_thread,
                        last_error=identity_failure,
                        host_protocol_stats=host_protocol_stats,
                    ))
                else:
                    slot = self._masters[master_idx]
                    if slot.id != sock_pair.id:
                        raise ProtocolError(
                            f"add_master: reattach-id mismatch at index {master_idx}: "
                            f"expected {sock_pair.id!r} but found {slot.id!r}"
                        )
                    # In-place mutation. The dead master's reader
                    # thread has already exited on EOF (Python
                    # threads can't be safely cancelled; we rely on
                    # the natural EOF exit). The new reader thread
                    # is wired in and the slot is marked healthy.
                    slot.socket_writer = writer
                    slot.manifest = manifest
                    slot.limits = limits
                    slot.caps = caps
                    slot.installed_cartridges = installed_cartridges
                    slot.healthy = healthy_at_register
                    slot.reader_handle = reader_thread
                    slot.last_error = identity_failure
                    slot.host_protocol_stats = host_protocol_stats

                self._rebuild_cap_table()
                self._rebuild_installed_cartridges()
                self._rebuild_capabilities()
                self._rebuild_limits()

            # Slot is committed — now it is safe to start reading.
            reader_thread.start()

            return master_idx

    def set_expected_master_count(self, expected: int) -> None:
        """Declare how many RelayMasters this engine intends to register
        at startup. ``all_masters_ready`` only returns True once
        ``len(masters) >= expected`` AND every connected master is
        healthy. Without this an engine that has only finished
        registering its internal master would falsely report ready
        before the external-cartridges master finished spawning + HELLO +
        cap-probing its cartridges. Set once at engine boot from the
        same call site that registers the cartridges."""
        with self._lock:
            self._expected_master_count = expected

    def all_masters_ready(self) -> bool:
        """True when (1) the number of connected masters is at least
        ``expected_master_count`` (declared via
        ``set_expected_master_count``), AND (2) every connected master
        is healthy.

        Cap-set non-emptiness is intentionally NOT required: a master
        can be healthy and connected with zero caps while its cartridges
        are still inspecting/verifying. Caps register incrementally as
        cartridges progress to Operational. When the expected count was
        never declared (0) this returns False — treat an undeclared
        count as not-yet-configured rather than guess (caller bug)."""
        with self._lock:
            expected = self._expected_master_count
            if expected == 0:
                return False
            if len(self._masters) < expected:
                return False
            for master in self._masters:
                if not master.healthy:
                    return False
            return True

    def _reader_loop(self, master_idx: int, reader: FrameReader):
        """Reader thread loop for a master"""
        while True:
            try:
                frame = reader.read()
                if frame is None:
                    # EOF
                    self._frame_queue.put(MasterFrame(master_idx, None, None))
                    return

                # Handle RelayNotify here (update cap tables) but ALSO forward
                # it to the engine for visibility — parity with the reference,
                # whose RelayNotify branch returns the frame through to the
                # engine after updating internal state.
                if frame.frame_type == FrameType.RELAY_NOTIFY:
                    manifest = frame.relay_notify_manifest()
                    limits = frame.relay_notify_limits()
                    if manifest is not None and limits is not None:
                        caps, installed_cartridges, host_protocol_stats = _parse_relay_notify_payload(manifest)
                        probe_required = False
                        with self._lock:
                            if 0 <= master_idx < len(self._masters):
                                master = self._masters[master_idx]
                                # Detect the empty → non-empty transition. The
                                # initial RelayNotify (during connect) skipped
                                # the identity probe when caps were empty; if
                                # the host now advertises a real handler chain
                                # we must probe it end-to-end before letting the
                                # new caps become routable. The master is held
                                # unhealthy until the probe driver confirms
                                # identity.
                                prior_caps_empty = len(master.caps) == 0
                                probe_required = prior_caps_empty and len(caps) > 0
                                master.manifest = manifest
                                master.limits = limits
                                master.caps = caps
                                master.installed_cartridges = installed_cartridges
                                master.host_protocol_stats = host_protocol_stats
                                if probe_required:
                                    master.healthy = False
                                    master.last_error = (
                                        "runtime identity probe pending — "
                                        "caps held back from routing"
                                    )
                                self._rebuild_cap_table()
                                self._rebuild_installed_cartridges()
                                self._rebuild_capabilities()
                                self._rebuild_limits()
                        if probe_required:
                            # Hand off to the probe driver. The queue is
                            # unbounded so this never blocks the reader.
                            self._pending_identity_probes.put(master_idx)
                    # Pass through to engine for visibility.
                    self._frame_queue.put(MasterFrame(master_idx, frame, None))
                    continue

                self._frame_queue.put(MasterFrame(master_idx, frame, None))
            except Exception as e:
                self._frame_queue.put(MasterFrame(master_idx, None, e))
                return

    def capabilities(self) -> bytes:
        """Get aggregate capabilities (union of all masters)"""
        with self._lock:
            return bytes(self._aggregate_capabilities)

    def subscribe_capabilities(self) -> "_CapabilityWatchReceiver":
        """Subscribe to changes in the *routable* capability set.

        The returned receiver yields the current routable-cap bytes (a JSON
        array of cap URNs) immediately on ``borrow()`` and a fresh snapshot
        every time the routable set changes — including when a deferred
        identity probe completes and a previously-unhealthy master's caps
        become routable. An engine-facing relay uses this to advertise
        readiness tied to master health, not mere inventory presence.

        The snapshot is health-filtered: a cap only appears once its master is
        identity-verified and healthy — unlike :meth:`installed_cartridges`,
        which is the inventory view and is deliberately NOT health-filtered.
        """
        return self._capabilities_watch.subscribe()

    def routable_capabilities(self) -> bytes:
        """Current health-filtered routable-cap bytes (JSON array of cap URNs).

        This is the synchronous counterpart to :meth:`subscribe_capabilities`
        and the snapshot the watch persists/delivers. Distinct from
        :meth:`capabilities`, which returns the (unfiltered) inventory manifest.
        """
        with self._lock:
            return bytes(self._routable_caps_bytes)

    def limits(self) -> Limits:
        """Get negotiated limits (minimum across all masters)"""
        with self._lock:
            return self._negotiated_limits

    def installed_cartridges(self) -> List[InstalledCartridgeRecord]:
        """Get aggregate installed cartridge identities of all healthy masters"""
        with self._lock:
            return list(self._aggregate_installed_cartridges)

    def set_terminate_observer(
        self, observer: Optional[Callable[[TerminatedSummary], None]]
    ) -> None:
        """Install a termination observer on the request table (L8): called
        with every termination's summary, under the table guard — must be
        cheap. Lets a caller accumulate complete per-run history without
        missing terminations between ``protocol_stats()`` polls (the ring
        evicts at 64). Installing replaces any previously-installed observer.
        Mirrors the reference ``RelaySwitch::set_terminate_observer``.
        """
        with self._lock:
            self._requests.set_terminate_observer(observer)

    def protocol_stats(self) -> RelaySwitchProtocolStats:
        """Protocol observability snapshot (L8): every live request's phase,
        age, per-stream flow counters, and children; the recently-terminated
        ring; and the per-reason drop totals. Poll this to understand the
        state of communications and the flow of requests through the switch.

        ``hosts`` is per-master host protocol stats, keyed by master id, as
        reported in each host's latest RelayNotify. A master that has not
        yet advertised host stats is absent — never a zeroed placeholder.
        """
        with self._lock:
            hosts: Dict[str, HostProtocolStats] = {}
            for master in self._masters:
                if master.host_protocol_stats is not None:
                    hosts[master.id] = master.host_protocol_stats
            return RelaySwitchProtocolStats(
                requests=self._requests.snapshot(),
                drops=self._drops.snapshot(),
                hosts=hosts,
            )

    def cancel_request(self, rid: MessageId, force_kill: bool) -> None:
        """Cancel a specific in-flight request by request ID.

        1. Looks up RID → XID → routing destination.
        2. Terminates the request (Cancelled) FIRST — one atomic removal
           yields the destination, the children for the cascade, and the
           external channel for the final ERR (L7). A concurrent terminal
           for the same key loses the race and is simply a no-op here.
        3. Sends a Cancel frame to the destination master.
        4. Recursively cancels the child peer calls recorded on the entry.
        5. Sends ERR "CANCELLED" to the external response channel if present.
        """
        with self._lock:
            self._cancel_request_locked(rid, force_kill)

    def _cancel_request_locked(self, rid: MessageId, force_kill: bool) -> None:
        """Cancel a request. Must be called with self._lock held."""
        xid = self._requests.xid_for_rid(rid)
        if xid is None:
            return

        key = (xid, rid)
        state = self._requests.terminate(key, TerminalKind.CANCELLED)
        if state is None:
            return

        # Send Cancel frame to destination
        cancel_frame = Frame.cancel(rid, force_kill)
        cancel_frame.routing_id = xid
        try:
            self._masters[state.routing.destination_master_idx].socket_writer.write(cancel_frame)
        except Exception:
            pass

        # Recursively cancel children
        for _child_xid, child_rid in state.children:
            self._cancel_request_locked(child_rid, force_kill)

        # Send ERR "CANCELLED" to the external response channel if present.
        # The send result is discarded, not drop-counted: only the primary
        # response-forwarding path in `_handle_master_frame` counts
        # channel_closed drops (mirrors the reference's `let _ = tx.send(...)`).
        if state.external_channel is not None:
            err_frame = Frame.err(rid, "CANCELLED", "Request cancelled")
            err_frame.routing_id = xid
            try:
                state.external_channel(err_frame)
            except Exception:
                pass

    def cancel_all_requests(self, force_kill: bool) -> List[MessageId]:
        """Cancel all external-origin (engine-initiated) in-flight requests.

        Returns the list of cancelled request IDs.
        """
        with self._lock:
            # Snapshot all external-origin (origin is None) rids before mutating
            rids = [rid for _xid, rid in self._requests.keys_where(lambda s: s.origin is None)]

            for rid in rids:
                self._cancel_request_locked(rid, force_kill)

            return rids

    def send_to_master(self, frame: Frame, preferred_cap: Optional[str] = None) -> None:
        """Send a frame to the appropriate master (engine → cartridge direction)

        Routes REQ by cap URN. Routes continuation frames by request ID.

        Args:
            frame: The frame to send
            preferred_cap: Optional capability URN for exact routing.
                          When provided, routes to the master whose registered cap
                          is equivalent to this URN. When None, uses standard
                          accepts + closest-specificity routing.

        Raises:
            NoHandlerError: No master found for cap
            UnknownRequestError: Unknown request ID for continuation frame
        """
        with self._lock:
            if frame.frame_type == FrameType.REQ:
                # Find master for this cap
                dest_idx = self._find_master_for_cap(frame.cap, preferred_cap)
                if dest_idx is None:
                    raise NoHandlerError(frame.cap)

                # Assign a fresh XID and register the request (origin=None:
                # external caller via send_to_master; no response channel —
                # responses return via read_from_masters). Duplicate
                # registration is a protocol violation and fails hard (L7).
                xid = self._next_xid_locked()
                frame.routing_id = xid
                key = (xid, frame.id)
                state = RequestState(
                    routing=RoutingEntry(source_master_idx=None, destination_master_idx=dest_idx),
                    origin=None,
                    external_channel=None,
                    is_peer=False,
                ).with_cap_urn(frame.cap)
                try:
                    self._requests.register(key, state)
                except RequestStateError as e:
                    raise ProtocolError(str(e)) from e

                self._masters[dest_idx].socket_writer.write(frame)

            elif frame.frame_type in (FrameType.STREAM_START, FrameType.CHUNK,
                                     FrameType.STREAM_END, FrameType.END, FrameType.ERR,
                                     FrameType.CANCEL, FrameType.CREDIT):
                # Continuation/control frames from the engine: look up XID
                # from RID if missing, then the destination — one table read.
                # Unknown RID is a hard error back to the caller: the engine
                # is a direct API client and must observe that the request no
                # longer exists (already terminated) so it stops sending.
                if frame.routing_id is not None:
                    xid = frame.routing_id
                else:
                    xid = self._requests.xid_for_rid(frame.id)
                    if xid is None:
                        raise UnknownRequestError(frame.id.to_string())
                    frame.routing_id = xid

                key = (xid, frame.id)
                entry = self._requests.get(key)
                if entry is None:
                    raise UnknownRequestError(frame.id.to_string())

                dest_idx = entry.routing.destination_master_idx
                self._masters[dest_idx].socket_writer.write(frame)

            else:
                # Other frame types pass through to first master (or error)
                if self._masters:
                    self._masters[0].socket_writer.write(frame)

    def read_from_masters(self) -> Optional[Frame]:
        """Read the next frame from any master (cartridge → engine direction).

        Blocks until a frame is available. Returns None when all masters have closed.
        Peer requests (cartridge → cartridge) are handled internally and not returned.
        """
        while True:
            # Block on queue - reader threads send frames here
            master_frame = self._frame_queue.get()

            if master_frame.error is not None:
                # Error reading from master
                self._handle_master_death(master_frame.master_idx)
                continue

            if master_frame.frame is None:
                # EOF from master
                self._handle_master_death(master_frame.master_idx)
                # Check if all masters are dead
                with self._lock:
                    if all(not m.healthy for m in self._masters):
                        return None
                continue

            # Handle the frame
            result_frame = self._handle_master_frame(master_frame.master_idx, master_frame.frame)
            if result_frame is not None:
                return result_frame
            # Peer request was handled internally, continue reading

    def start_background_pump(self) -> None:
        """Spawn the persistent background drain pump.

        ``_frame_queue`` accumulates inbound frames from every connected
        master (RelayNotify capability updates, peer invocations, deferred
        identity-probe echoes). Without a running drain, the queue fills and
        control frames — including the probe echoes the deferred-identity
        state machine awaits — never get routed. This pump runs for the
        switch's lifetime and feeds frames through ``_handle_master_frame``
        (the same dispatch path ``read_from_masters`` uses); pass-through
        frames returned by the handler are discarded because no single
        consumer owns them.

        Run EITHER this pump OR ``read_from_masters`` — not both — since they
        share the single ``_frame_queue`` consumer. Idempotent: a second call
        is a no-op. The deferred probe driver is started in ``__init__`` and
        only does work once a drain (this pump or ``read_from_masters``) is
        delivering echoes.
        """
        with self._lock:
            if self._pump_started:
                return
            self._pump_started = True
        t = threading.Thread(target=self._background_pump_loop, daemon=True)
        t.start()
        self._pump_thread = t

    def _background_pump_loop(self) -> None:
        while not self._pump_stop:
            master_frame = self._frame_queue.get()
            if master_frame.error is not None:
                self._handle_master_death(master_frame.master_idx)
                continue
            if master_frame.frame is None:
                self._handle_master_death(master_frame.master_idx)
                continue
            # Route the frame (probe echoes go to external channels, peer
            # frames are forwarded). Pass-through frames are discarded — the
            # pump has no engine consumer.
            self._handle_master_frame(master_frame.master_idx, master_frame.frame)

    def _next_xid_locked(self) -> MessageId:
        """Allocate a fresh routing id (xid). Caller MUST hold ``_lock``."""
        self._xid_counter += 1
        return MessageId(self._xid_counter)

    def _next_xid(self) -> MessageId:
        """Allocate a fresh routing id (xid). Caller must NOT hold ``_lock``."""
        with self._lock:
            return self._next_xid_locked()

    def _probe_driver_loop(self) -> None:
        """Serially probe each master that transitioned empty→non-empty caps.

        On success the master flips healthy and its caps become routable; on
        failure it stays unhealthy with ``last_error`` stamped. Mirrors the
        reference ``spawn_identity_probe_driver``.
        """
        while True:
            master_idx = self._pending_identity_probes.get()
            if master_idx is None:
                return  # shutdown sentinel
            detail = self._run_identity_probe_via_relay(master_idx)
            with self._lock:
                if 0 <= master_idx < len(self._masters):
                    master = self._masters[master_idx]
                    if detail is None:
                        # Probe passed — flip healthy; its caps become routable.
                        master.healthy = True
                        master.last_error = None
                    else:
                        # Probe failed — keep unhealthy and stamp last_error.
                        master.healthy = False
                        master.last_error = detail
                self._rebuild_cap_table()
                self._rebuild_capabilities()

    def _run_identity_probe_via_relay(self, master_idx: int) -> Optional[str]:
        """Run an end-to-end identity probe against a master via the relay.

        Sends CAP_IDENTITY REQ + STREAM_START + CHUNK(nonce) + STREAM_END +
        END on a fresh flow and awaits the echo, routed back through an
        external response channel keyed by the request id. Returns ``None`` on
        success, or a typed error string on failure (for ``last_error``).
        Mirrors the reference ``run_identity_probe_via_relay``.
        """
        RUNTIME_PROBE_TIMEOUT = 10.0

        rid = MessageId.new_uuid()
        rid_key = rid.to_string()
        nonce = identity_nonce()
        stream_id = "identity-verify-runtime"
        resp_q: "queue.Queue[Frame]" = queue.Queue()

        # Register the response channel and snapshot the writer under the lock.
        xid = self._next_xid()
        with self._lock:
            if not (0 <= master_idx < len(self._masters)):
                return "identity probe: master index out of range"
            self._external_response_channels[rid_key] = resp_q
            writer = self._masters[master_idx].socket_writer

        try:
            req = Frame.req(rid, CAP_IDENTITY, b"", "application/cbor")
            req.routing_id = xid
            ss = Frame.stream_start(rid, stream_id, "media:")
            ss.routing_id = xid
            chunk = Frame.chunk(rid, stream_id, 0, nonce, 0, compute_checksum(nonce))
            chunk.routing_id = xid
            se = Frame.stream_end(rid, stream_id, 1)
            se.routing_id = xid
            end = Frame.end(rid, None)
            end.routing_id = xid

            # Serialize the writes under the lock so the five probe frames
            # cannot interleave with an engine ``send_to_master`` writing to
            # the same master socket. The lock is released before the blocking
            # echo wait below.
            try:
                with self._lock:
                    for fr in (req, ss, chunk, se, end):
                        writer.write(fr)
            except Exception as e:
                return f"identity probe send failed: {e}"

            # Drain the echo: STREAM_START → CHUNK(nonce) → STREAM_END → END.
            deadline = time.monotonic() + RUNTIME_PROBE_TIMEOUT
            accumulated = bytearray()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return (
                        f"runtime identity probe timed out after "
                        f"{RUNTIME_PROBE_TIMEOUT}s"
                    )
                try:
                    frame = resp_q.get(timeout=remaining)
                except queue.Empty:
                    return (
                        f"runtime identity probe timed out after "
                        f"{RUNTIME_PROBE_TIMEOUT}s"
                    )
                if frame.frame_type == FrameType.STREAM_START:
                    continue
                if frame.frame_type == FrameType.CHUNK:
                    if frame.payload is not None:
                        accumulated.extend(frame.payload)
                    continue
                if frame.frame_type == FrameType.STREAM_END:
                    continue
                if frame.frame_type == FrameType.END:
                    if bytes(accumulated) != nonce:
                        return (
                            f"identity probe payload mismatch "
                            f"(expected {len(nonce)} bytes, got {len(accumulated)})"
                        )
                    return None
                if frame.frame_type == FrameType.ERR:
                    code = frame.error_code() or "UNKNOWN"
                    msg = frame.error_message() or "no message"
                    return f"identity probe failed: [{code}] {msg}"
                if frame.frame_type in (
                    FrameType.LOG,
                    FrameType.CREDIT,
                    FrameType.HEARTBEAT,
                ):
                    # Control/side-channel frames are legal ANYWHERE during
                    # the probe (spec 12.4: LOG interleaves without affecting
                    # data flow; CREDIT/HEARTBEAT are the control plane the
                    # writer gate itself exempts, L4). A v3 cartridge
                    # crediting its probe input as it consumes (L10) must
                    # not fail identity verification.
                    continue
                return f"identity probe: unexpected frame type {frame.frame_type}"
        finally:
            with self._lock:
                self._external_response_channels.pop(rid_key, None)

    def _find_master_for_cap(self, cap_urn: str, preferred_cap: Optional[str] = None) -> Optional[int]:
        """Find master index that can handle a capability.

        Args:
            cap_urn: The capability URN to find a handler for
            preferred_cap: Optional capability URN for exact routing.
                          When provided, uses comparable matching (broader) and prefers
                          masters whose registered cap is equivalent to this URN.
                          When None, uses standard accepts + closest-specificity routing.

        Returns:
            Master index, or None if no handler found
        """
        try:
            request_urn = CapUrn.from_string(cap_urn)
        except:
            return None

        request_specificity = request_urn.specificity()

        # Parse preferred cap URN if provided
        preferred_urn = None
        if preferred_cap:
            try:
                preferred_urn = CapUrn.from_string(preferred_cap)
            except:
                pass

        # Collect ALL matching masters with their specificity scores
        # When preferred_cap is set, use is_comparable (broader); otherwise accepts (standard)
        matches: List[Tuple[int, int, bool]] = []  # (master_idx, specificity, is_preferred)

        for registered_cap, master_idx in self._cap_table:
            try:
                registered_urn = CapUrn.from_string(registered_cap)
            except:
                continue

            # Use is_dispatchable: can this candidate handle this request?
            dispatchable = registered_urn.is_dispatchable(request_urn)

            if dispatchable:
                specificity = registered_urn.specificity()
                signed_distance = specificity - request_specificity
                # Preferred-cap routing must select the exact registered cap, not
                # any order-theoretically equivalent cap. Broad and specific caps
                # can be comparable/equivalent in the dispatch lattice while still
                # representing different concrete registrations.
                is_preferred = False
                if preferred_urn:
                    is_preferred = (
                        preferred_urn.in_urn == registered_urn.in_urn
                        and preferred_urn.out_urn == registered_urn.out_urn
                        and preferred_urn.tags == registered_urn.tags
                    )
                matches.append((master_idx, signed_distance, is_preferred))

        if not matches:
            return None

        # If any match is preferred, pick the first preferred match
        for idx, _, is_pref in matches:
            if is_pref:
                return idx

        # Rank: non-negative distance (refinement/exact) before negative (fallback),
        # then by smallest absolute distance. This prefers exact or more-specific candidates.
        matches.sort(key=lambda m: (0 if m[1] >= 0 else 1, abs(m[1])))
        return matches[0][0]

        return None

    def _handle_master_frame(self, source_idx: int, frame: Frame) -> Optional[Frame]:
        """Handle a frame from a master. Returns frame to return to engine, or None if handled internally."""
        with self._lock:
            if frame.frame_type == FrameType.REQ:
                # Peer request: cartridge → cartridge via switch (no preference)
                dest_idx = self._find_master_for_cap(frame.cap, None)
                if dest_idx is None:
                    raise NoHandlerError(frame.cap)

                # Assign the XID and register the peer request under the
                # unified table (L7): origin = the source master (so the
                # eventual response routes back here), is_peer marks the
                # special cleanup semantics.
                xid = self._next_xid_locked()
                frame.routing_id = xid
                rid = frame.id
                key = (xid, rid)
                state = RequestState(
                    routing=RoutingEntry(source_master_idx=source_idx, destination_master_idx=dest_idx),
                    origin=source_idx,
                    external_channel=None,
                    is_peer=True,
                ).with_cap_urn(frame.cap)
                try:
                    self._requests.register(key, state)
                except RequestStateError as e:
                    raise ProtocolError(str(e)) from e

                # Track parent→child for the cancel cascade.
                parent_rid = _extract_parent_rid(frame.meta)
                if parent_rid is not None:
                    parent_xid = self._requests.xid_for_rid(parent_rid)
                    if parent_xid is not None:
                        self._requests.link_child((parent_xid, parent_rid), key)

                self._masters[dest_idx].socket_writer.write(frame)

                # Do NOT return to engine (internal routing)
                return None

            elif frame.frame_type in (FrameType.STREAM_START, FrameType.CHUNK,
                                     FrameType.STREAM_END, FrameType.END,
                                     FrameType.ERR, FrameType.LOG, FrameType.CREDIT):
                rid_key = frame.id.to_string()

                # Deferred-identity-probe echo: route to the registered
                # external response channel keyed by the probe's request id.
                # The probe driver owns channel cleanup (it removes the entry
                # in its finally), so we only deliver here.
                ext_q = self._external_response_channels.get(rid_key)
                if ext_q is not None:
                    ext_q.put(frame)
                    return None

                if frame.routing_id is not None:
                    # ========================================
                    # HAS XID = RESPONSE (route back to origin)
                    # ========================================
                    xid = frame.routing_id
                    rid = frame.id
                    key = (xid, rid)
                    is_terminal = frame.frame_type in (FrameType.END, FrameType.ERR)

                    # Record flow stats, resolve the return path, and — on
                    # terminal — remove the whole entry atomically (L7). A
                    # frame for a released key is a counted no_route drop,
                    # never a protocol error and never silent (L8).
                    self._requests.record_frame(key, FrameDirection.INBOUND, frame)
                    if is_terminal:
                        kind = TerminalKind.END if frame.frame_type == FrameType.END else TerminalKind.ERR
                        state = self._requests.terminate(key, kind)
                        if state is None:
                            self._drops.record(DropReason.NO_ROUTE)
                            return None
                    else:
                        state = self._requests.get(key)
                        if state is None:
                            self._drops.record(DropReason.NO_ROUTE)
                            return None

                    if state.origin is None:
                        # External caller (via send_to_master, or a manually
                        # registered response channel — e.g. the identity probe).
                        channel = state.external_channel
                        if channel is not None:
                            try:
                                channel(frame)
                            except Exception:
                                self._drops.record(DropReason.CHANNEL_CLOSED)
                                # A dead consumer on a LIVE request means the
                                # caller abandoned it. Nobody can ever read this
                                # response — cancel upstream so the cartridge
                                # stops producing for a dead channel, instead of
                                # letting the request run to completion and
                                # counting a drop for every remaining frame.
                                # Terminal frames need no cancel: the entry is
                                # already terminated. Dispatched off-lock
                                # (`_handle_master_frame` holds `self._lock` for
                                # its whole body and `cancel_request` re-acquires
                                # it — `threading.Lock` is not reentrant).
                                if not is_terminal:
                                    threading.Thread(
                                        target=self.cancel_request,
                                        args=(rid, False),
                                        daemon=True,
                                    ).start()
                            return None
                        else:
                            # No response channel (sent via send_to_master, not
                            # a registered external caller). Strip XID and
                            # return to caller — final leg.
                            frame.routing_id = None
                            return frame
                    else:
                        # Route back to source master — KEEP XID.
                        self._masters[state.origin].socket_writer.write(frame)
                        return None
                else:
                    # ========================================
                    # NO XID = REQUEST CONTINUATION
                    # ========================================
                    # Frame has no XID, so it's a request continuation
                    # (peer-call argument streams / grants) flowing to the
                    # destination. An unknown RID means the request already
                    # terminated: counted drop (L6), not an error.
                    rid = frame.id
                    xid = self._requests.xid_for_rid(rid)
                    if xid is None:
                        self._drops.record(DropReason.NO_ROUTE)
                        return None
                    key = (xid, rid)
                    self._requests.record_frame(key, FrameDirection.INBOUND, frame)
                    state = self._requests.get(key)
                    if state is None:
                        self._drops.record(DropReason.NO_ROUTE)
                        return None
                    frame.routing_id = xid
                    self._masters[state.routing.destination_master_idx].socket_writer.write(frame)
                    return None

            elif frame.frame_type == FrameType.CANCEL:
                # Cancel from cartridge — route to destination like a
                # continuation frame. Cartridge is cancelling its own peer
                # call. Unknown RID means the request already completed: a
                # well-defined no-op (silently ignored, never an error).
                rid = frame.id
                if frame.routing_id is not None:
                    xid = frame.routing_id
                else:
                    xid = self._requests.xid_for_rid(rid)
                    if xid is None:
                        return None
                    frame.routing_id = xid
                key = (xid, rid)
                state = self._requests.get(key)
                if state is None:
                    return None
                self._masters[state.routing.destination_master_idx].socket_writer.write(frame)
                return None

            else:
                # Unknown frame type - return to engine
                return frame

    def _handle_master_death(self, master_idx: int):
        """Handle master death: ERR pending requests, mark unhealthy, rebuild caps"""
        with self._lock:
            if not self._masters[master_idx].healthy:
                return  # Already handled

            self._masters[master_idx].healthy = False

            # Find all pending requests routed to this master.
            dead_keys = self._requests.keys_where(
                lambda s: s.routing.destination_master_idx == master_idx
            )

            # Terminate each pending request (MasterDied) and deliver a
            # synthetic ERR to whoever was waiting on it. terminate()
            # atomically removes ALL state for the key (L7) and hands back
            # the origin + channel needed for delivery.
            for key in dead_keys:
                state = self._requests.terminate(key, TerminalKind.MASTER_DIED)
                if state is None:
                    continue  # raced another terminal — already fully cleaned

                xid, rid = key
                # A dead relay master is a runtime-environment failure —
                # Environment (docs/failure-taxonomy.md).
                err_frame = Frame.err_classified(rid, "MASTER_DIED", FailureClass.ENVIRONMENT, f"Relay master {master_idx} connection closed")
                err_frame.routing_id = xid

                if state.origin is None:
                    # Send result discarded, not drop-counted — matches
                    # `cancel_request` and the reference's `let _ = tx.send(...)`.
                    if state.external_channel is not None:
                        try:
                            state.external_channel(err_frame)
                        except Exception:
                            pass
                else:
                    src_idx = state.origin
                    if 0 <= src_idx < len(self._masters) and self._masters[src_idx].healthy:
                        try:
                            self._masters[src_idx].socket_writer.write(err_frame)
                        except Exception:
                            pass

            # Rebuild cap table without dead master.
            # `_rebuild_installed_cartridges` must run before
            # `_rebuild_capabilities` so the latter sees the
            # current aggregate.
            self._rebuild_cap_table()
            self._rebuild_installed_cartridges()
            self._rebuild_capabilities()
            self._rebuild_limits()

    def _rebuild_cap_table(self):
        """Rebuild capability routing table from all healthy masters"""
        self._cap_table.clear()
        for idx, master in enumerate(self._masters):
            if master.healthy:
                for cap in master.caps:
                    self._cap_table.append((cap, idx))

    def _rebuild_installed_cartridges(self):
        """Rebuild the aggregate installed-cartridge inventory.

        The inventory aggregate is the "what is physically installed and known
        to any master" view and is deliberately NOT health-filtered. Filtering
        by master health caused the "all cartridges disappeared" symptom on
        every transient master flap (reconnect, restart, RelayNotify race at
        startup). Reachability lives in
        ``InstalledCartridgeRecord.runtime_stats.running`` per cartridge, not
        in whether the parent master happens to be unhealthy this tick.

        Dedup is on the FULL identity tuple
        ``(registry_url, channel, id, version, sha256)``: two installs of the
        same id+version from different registries or channels are distinct
        cartridges with their own process and on-disk tree; collapsing them
        would make the second invisible to the engine.
        """
        records: List[InstalledCartridgeRecord] = []
        for master in self._masters:
            for ic in master.installed_cartridges:
                records.append(ic)
        # Sort by the identity tuple. ``registry_url`` is Optional; None sorts
        # before any Some (matching the reference ``Option<String>`` ordering).
        records.sort(key=lambda ic: (
            0 if ic.registry_url is None else 1,
            ic.registry_url or "",
            ic.channel,
            ic.id,
            ic.version,
            ic.sha256,
        ))
        result: List[InstalledCartridgeRecord] = []
        seen: set = set()
        for ic in records:
            key = (ic.registry_url, ic.channel, ic.id, ic.version, ic.sha256)
            if key in seen:
                continue
            seen.add(key)
            result.append(ic)
        self._aggregate_installed_cartridges = result

    def _rebuild_capabilities(self):
        """Rebuild aggregate capabilities manifest.

        The wire payload now carries caps inside
        ``installed_cartridges[*].cap_groups``; the relay republishes
        the union of every healthy master's installed cartridges so the
        engine sees one combined view and derives the flat cap-urn list
        itself.
        """
        installed = [_installed_cartridge_record_to_wire(ic)
                     for ic in self._aggregate_installed_cartridges]

        manifest = {"installed_cartridges": installed}
        self._aggregate_capabilities = json.dumps(manifest).encode("utf-8")

        # Routable-capability set: the health-filtered union of cap URNs (the
        # JSON array of *routable* caps — a cap only appears once its master is
        # healthy / identity-verified). This is the engine-readiness signal,
        # distinct from the unfiltered inventory manifest above. Fire the watch
        # only when the routable set actually CHANGES so a deferred probe
        # completing (which flips a master healthy and adds its caps) wakes the
        # engine, without a notify storm from unrelated rebuilds. ``send_replace``
        # persists the value across zero-subscriber windows.
        routable: List[str] = []
        seen_routable: set = set()
        for master in self._masters:
            if master.healthy:
                for cap in master.caps:
                    if cap not in seen_routable:
                        seen_routable.add(cap)
                        routable.append(cap)
        routable.sort()
        new_routable = json.dumps(routable).encode("utf-8")
        if new_routable != self._routable_caps_bytes:
            self._routable_caps_bytes = new_routable
            self._capabilities_watch.send_replace(new_routable)

    def _rebuild_limits(self):
        """Rebuild negotiated limits (minimum across all masters)"""
        min_frame = 2**63 - 1
        min_chunk = 2**63 - 1
        min_reorder = 2**63 - 1

        for master in self._masters:
            if master.healthy:
                if master.limits.max_frame < min_frame:
                    min_frame = master.limits.max_frame
                if master.limits.max_chunk < min_chunk:
                    min_chunk = master.limits.max_chunk
                if master.limits.max_reorder_buffer < min_reorder:
                    min_reorder = master.limits.max_reorder_buffer

        if min_frame == 2**63 - 1:
            min_frame = DEFAULT_MAX_FRAME
        if min_chunk == 2**63 - 1:
            min_chunk = DEFAULT_MAX_CHUNK
        if min_reorder == 2**63 - 1:
            min_reorder = DEFAULT_MAX_REORDER_BUFFER

        self._negotiated_limits = Limits(max_frame=min_frame, max_chunk=min_chunk, max_reorder_buffer=min_reorder)


# =============================================================================
# INTERNAL TYPES
# =============================================================================

class _CapabilityWatchReceiver:
    """A subscriber handle for :class:`_CapabilityWatch`.

    Mirrors the read side of a Rust ``tokio::sync::watch::Receiver`` closely
    enough for the routable-capability signal: ``borrow()`` returns the latest
    value seen so far (the current snapshot at subscribe time, then every
    replacement delivered since), and ``changed(timeout)`` blocks for the next
    replacement. The receiver is seeded with the watch's current value at
    subscribe time, so the snapshot persists across zero-subscriber windows —
    the ``send_replace`` semantics the engine-readiness signal depends on.
    """

    def __init__(self, initial: bytes):
        self._q: "queue.Queue[bytes]" = queue.Queue()
        self._latest = initial

    def borrow(self) -> bytes:
        """Return the most recent value, draining any pending replacements."""
        try:
            while True:
                self._latest = self._q.get_nowait()
        except queue.Empty:
            pass
        return self._latest

    def changed(self, timeout: Optional[float] = None) -> bytes:
        """Block until the next replacement arrives and return it.

        Raises ``queue.Empty`` if ``timeout`` elapses first.
        """
        value = self._q.get(timeout=timeout)
        self._latest = value
        return value

    def _offer(self, value: bytes) -> None:
        self._q.put(value)


class _CapabilityWatch:
    """A minimal ``tokio::sync::watch``-equivalent with ``send_replace``
    semantics.

    The watch always stores the latest value, so a subscriber that arrives
    AFTER a replacement still observes the current snapshot on its first
    ``borrow()`` — unlike a plain broadcast, which would have dropped the
    value when there were momentarily zero receivers. This is exactly the
    synchronous-construction case: capabilities are rebuilt inside
    ``__init__`` before any subscriber exists, and the routable set must not
    be silently lost.
    """

    def __init__(self, initial: bytes):
        self._lock = threading.Lock()
        self._value = initial
        self._receivers: List[_CapabilityWatchReceiver] = []

    def send_replace(self, value: bytes) -> None:
        with self._lock:
            self._value = value
            receivers = list(self._receivers)
        for r in receivers:
            r._offer(value)

    def subscribe(self) -> _CapabilityWatchReceiver:
        with self._lock:
            r = _CapabilityWatchReceiver(self._value)
            self._receivers.append(r)
            return r

    def current(self) -> bytes:
        with self._lock:
            return self._value


@dataclass
class _MasterConnection:
    """Connection to a single RelayMaster.

    ``id`` is the stable identity of this slot. Once set at slot
    creation it is never overwritten; reattach-by-id matches against
    it. Re-adding the same id while ``healthy`` is rejected at the
    add path.
    """
    id: str
    socket_writer: FrameWriter
    manifest: bytes
    limits: Limits
    caps: List[str]
    installed_cartridges: List[InstalledCartridgeRecord]
    healthy: bool
    reader_handle: threading.Thread
    #: Most recent attachment / identity-probe failure reason, or None when
    #: the slot is healthy. Mirrors the reference ``MasterConnection.last_error``.
    #: Populated when a connect-time / runtime identity probe fails so the
    #: inventory surface can show why a master is held back from routing.
    last_error: Optional[str] = None
    #: Latest per-host protocol stats (drops, routing-table sizes, GC totals)
    #: reported by this master's RelayNotify. ``None`` until the first
    #: advertisement that carries them — the field is a per-republish
    #: refresh, not a requirement on every RelayNotify. Retained (not
    #: parsed-and-discarded) so ``protocol_stats().hosts`` can name the host
    #: behind a drop. Mirrors the reference ``MasterConnection.host_protocol_stats``.
    host_protocol_stats: Optional[HostProtocolStats] = None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _installed_cartridge_record_to_wire(ic: InstalledCartridgeRecord) -> dict:
    """Serialize an ``InstalledCartridgeRecord`` to its wire dict.

    Field presence mirrors the reference ``skip_serializing_if`` rules: empty
    ``cap_groups``, absent ``attachment_error`` / ``runtime_stats``, and a
    default (``DISCOVERED``) ``lifecycle`` are omitted so the JSON is
    byte-identical to what the Rust/Go producers emit for the same record.
    """
    out: dict = {
        "registry_url": ic.registry_url,
        "id": ic.id,
        "channel": ic.channel,
        "version": ic.version,
        "sha256": ic.sha256,
    }
    if ic.cap_groups:
        out["cap_groups"] = ic.cap_groups
    if ic.attachment_error is not None:
        ae = ic.attachment_error
        out["attachment_error"] = {
            "kind": ae.kind.value if isinstance(ae.kind, Enum) else ae.kind,
            "message": ae.message,
            "detected_at_unix_seconds": ae.detected_at_unix_seconds,
        }
    if ic.runtime_stats is not None:
        rs = ic.runtime_stats
        out["runtime_stats"] = {
            "running": rs.running,
            "pid": rs.pid,
            "active_request_count": rs.active_request_count,
            "peer_request_count": rs.peer_request_count,
            "memory_footprint_mb": rs.memory_footprint_mb,
            "memory_rss_mb": rs.memory_rss_mb,
            "last_heartbeat_unix_seconds": rs.last_heartbeat_unix_seconds,
            "restart_count": rs.restart_count,
            "protocol_drops_total": rs.protocol_drops_total,
        }
    lifecycle = ic.effective_lifecycle()
    if lifecycle != CartridgeLifecycle.DISCOVERED:
        out["lifecycle"] = lifecycle.value
    return out


def _parse_relay_notify_payload(
    manifest: bytes,
) -> Tuple[List[str], List[InstalledCartridgeRecord], Optional[HostProtocolStats]]:
    """Parse installed cartridges (with cap_groups) from a RelayNotify manifest JSON.

    The payload carries ``installed_cartridges``, each with a ``cap_groups``
    array. The flat cap-urn list returned alongside is computed from those
    groups — it is no longer transmitted on the wire. The payload may also
    carry a ``host_protocol_stats`` object (L8): the host's protocol
    observability snapshot, refreshed with each stats republish.
    """
    try:
        parsed = json.loads(manifest.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise ProtocolError(f"Failed to parse manifest JSON: {e}")

    if "installed_cartridges" not in parsed:
        raise ProtocolError("manifest missing required installed_cartridges array")

    ic_raw = parsed["installed_cartridges"]
    if not isinstance(ic_raw, list):
        raise ProtocolError(f"installed_cartridges must be array, got {type(ic_raw)}")

    installed_cartridges: List[InstalledCartridgeRecord] = []
    for item in ic_raw:
        # (registry_url, channel) are both part of every
        # install's identity. Reject entries that omit either
        # — an upstream that ships an InstalledCartridgeRecord
        # without these fields is using an old schema.
        channel = item.get("channel")
        if channel not in ("release", "nightly"):
            raise ProtocolError(
                f"installed_cartridges entry missing or invalid 'channel' "
                f"(got {channel!r}); expected 'release' or 'nightly'"
            )
        if "registry_url" not in item:
            raise ProtocolError(
                "installed_cartridges entry missing required `registry_url` field. "
                "It must be present, with value null for dev installs or "
                "a URL string for registry installs."
            )
        registry_url_raw = item["registry_url"]
        if registry_url_raw is not None and not isinstance(registry_url_raw, str):
            raise ProtocolError(
                f"installed_cartridges entry `registry_url` must be null or string, "
                f"got {type(registry_url_raw)}"
            )
        cap_groups_raw = item.get("cap_groups", []) or []
        if not isinstance(cap_groups_raw, list):
            raise ProtocolError(
                f"installed_cartridges entry `cap_groups` must be array, "
                f"got {type(cap_groups_raw)}"
            )
        # Canonicalize every cap URN inside the cap_groups before
        # storing. The wire format permits authored aliases (e.g.
        # `cap:in=media:;out=media:` for the bare identity), but
        # the engine's downstream lookups are keyed on canonical
        # strings — leaving raw forms in place causes silent dispatch
        # misses where two-equal-but-differently-spelled URNs route
        # independently. Canonicalize at ingestion so the rest of
        # the engine never has to re-canonicalize.
        cap_groups_canonical: List[Any] = []
        for group in cap_groups_raw:
            if not isinstance(group, dict):
                cap_groups_canonical.append(group)
                continue
            new_group = dict(group)
            new_caps: List[Any] = []
            for cap in group.get("caps", []) or []:
                if not isinstance(cap, dict):
                    new_caps.append(cap)
                    continue
                raw_urn = cap.get("urn", "")
                if not raw_urn:
                    new_caps.append(cap)
                    continue
                try:
                    canonical = CapUrn.from_string(raw_urn).to_string()
                except Exception:
                    raise ProtocolError(
                        f"installed_cartridges entry advertises invalid cap URN: {raw_urn!r}"
                    )
                new_cap = dict(cap)
                new_cap["urn"] = canonical
                new_caps.append(new_cap)
            new_group["caps"] = new_caps
            cap_groups_canonical.append(new_group)
        # Optional attachment_error (present ⇔ the cartridge failed to attach).
        attachment_error = None
        ae_raw = item.get("attachment_error")
        if isinstance(ae_raw, dict):
            attachment_error = CartridgeAttachmentError(
                kind=CartridgeAttachmentErrorKind(ae_raw.get("kind")),
                message=str(ae_raw.get("message", "")),
                detected_at_unix_seconds=int(ae_raw.get("detected_at_unix_seconds", 0)),
            )

        # Optional runtime_stats.
        runtime_stats = None
        rs_raw = item.get("runtime_stats")
        if isinstance(rs_raw, dict):
            runtime_stats = CartridgeRuntimeStats(
                running=bool(rs_raw.get("running", False)),
                pid=rs_raw.get("pid"),
                active_request_count=int(rs_raw.get("active_request_count", 0)),
                peer_request_count=int(rs_raw.get("peer_request_count", 0)),
                memory_footprint_mb=int(rs_raw.get("memory_footprint_mb", 0)),
                memory_rss_mb=int(rs_raw.get("memory_rss_mb", 0)),
                last_heartbeat_unix_seconds=rs_raw.get("last_heartbeat_unix_seconds"),
                restart_count=int(rs_raw.get("restart_count", 0)),
                protocol_drops_total=rs_raw.get("protocol_drops_total"),
            )

        # Optional lifecycle — defaults to DISCOVERED (the safe sentinel) when
        # absent, so an unset field is never mistaken for OPERATIONAL.
        lifecycle_raw = item.get("lifecycle")
        if lifecycle_raw is None:
            lifecycle = CartridgeLifecycle.DISCOVERED
        else:
            lifecycle = CartridgeLifecycle(lifecycle_raw)

        installed_cartridges.append(InstalledCartridgeRecord(
            registry_url=registry_url_raw,
            id=str(item.get("id", "")),
            channel=str(channel),
            version=str(item.get("version", "")),
            sha256=str(item.get("sha256", "")),
            cap_groups=cap_groups_canonical,
            attachment_error=attachment_error,
            runtime_stats=runtime_stats,
            lifecycle=lifecycle,
        ))

    # Derive the flat cap-urn union from cap_groups across all installed
    # cartridges, preserving first-seen order.
    seen_caps: set = set()
    caps: List[str] = []
    for cart in installed_cartridges:
        for urn in cart.cap_urns():
            if urn in seen_caps:
                continue
            seen_caps.add(urn)
            caps.append(urn)

    # Host-level protocol observability (L8): drops, routing-table sizes, GC
    # totals. Absent on initial capability advertisements — a per-republish
    # refresh, not a requirement — so its absence is not an error.
    host_protocol_stats: Optional[HostProtocolStats] = None
    hps_raw = parsed.get("host_protocol_stats")
    if isinstance(hps_raw, dict):
        host_protocol_stats = HostProtocolStats.from_dict(hps_raw)

    return caps, installed_cartridges, host_protocol_stats
