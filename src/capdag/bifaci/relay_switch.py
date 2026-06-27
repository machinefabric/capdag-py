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
from typing import Any, Optional, List, Tuple, Dict
from dataclasses import dataclass, field

from capdag.bifaci.frame import Frame, FrameType, Limits, MessageId, DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK, DEFAULT_MAX_REORDER_BUFFER
from capdag.bifaci.io import FrameReader, FrameWriter, CborError, verify_identity
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
        independently and dispatch silently misses the provider."""
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
class RoutingEntry:
    """Routing entry for request tracking"""
    source_master_idx: int  # Index of source master (ENGINE_SOURCE for engine-initiated)
    destination_master_idx: int  # Index of destination master
    request_id: MessageId  # original MessageId for cancel frames


@dataclass
class MasterFrame:
    """Frame received from a master"""
    master_idx: int
    frame: Optional[Frame]
    error: Optional[Exception]


# Sentinel value for engine-initiated requests
ENGINE_SOURCE = 2**63 - 1


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
        self._request_routing: Dict[str, RoutingEntry] = {}
        self._peer_requests: set = set()  # Request IDs for peer-initiated requests
        self._peer_call_parents: Dict[str, List[str]] = {}  # parent key → list of child peer-call keys
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

            caps, installed_cartridges = _parse_relay_notify_payload(manifest)
            reader.set_limits(limits)
            writer.set_limits(limits)

            try:
                verify_identity(reader, writer)
            except Exception as e:
                raise ProtocolError(f"identity verification failed: {e}") from e

            # Spawn reader thread for this master
            reader_thread = threading.Thread(
                target=self._reader_loop,
                args=(master_idx, reader),
                daemon=True
            )
            reader_thread.start()

            master_conn = _MasterConnection(
                id=sock_pair.id,
                socket_writer=writer,
                manifest=manifest,
                limits=limits,
                caps=caps,
                installed_cartridges=installed_cartridges,
                healthy=True,
                reader_handle=reader_thread
            )
            self._masters.append(master_conn)

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
            caps, installed_cartridges = _parse_relay_notify_payload(manifest)
            reader.set_limits(limits)
            writer.set_limits(limits)
            try:
                verify_identity(reader, writer)
            except Exception as e:
                raise ProtocolError(f"identity verification failed: {e}") from e

            # Spawn reader thread bound to master_idx.
            reader_thread = threading.Thread(
                target=self._reader_loop,
                args=(master_idx, reader),
                daemon=True,
            )
            reader_thread.start()

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
                        healthy=True,
                        reader_handle=reader_thread,
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
                    slot.healthy = True
                    slot.reader_handle = reader_thread

                self._rebuild_cap_table()
                self._rebuild_installed_cartridges()
                self._rebuild_capabilities()
                self._rebuild_limits()

            return master_idx

    def set_expected_master_count(self, expected: int) -> None:
        """Declare how many RelayMasters this engine intends to register
        at startup. ``all_masters_ready`` only returns True once
        ``len(masters) >= expected`` AND every connected master is
        healthy. Without this an engine that has only finished
        registering its internal master would falsely report ready
        before the external-providers master finished spawning + HELLO +
        cap-probing its cartridges. Set once at engine boot from the
        same call site that registers the providers."""
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

                # Handle RelayNotify here (intercept before sending to queue)
                if frame.frame_type == FrameType.RELAY_NOTIFY:
                    with self._lock:
                        manifest = frame.relay_notify_manifest()
                        limits = frame.relay_notify_limits()
                        if manifest is not None and limits is not None:
                            caps, installed_cartridges = _parse_relay_notify_payload(manifest)
                            self._masters[master_idx].manifest = manifest
                            self._masters[master_idx].limits = limits
                            self._masters[master_idx].caps = caps
                            self._masters[master_idx].installed_cartridges = installed_cartridges
                            self._rebuild_cap_table()
                            self._rebuild_installed_cartridges()
                            self._rebuild_capabilities()
                            self._rebuild_limits()
                    continue

                self._frame_queue.put(MasterFrame(master_idx, frame, None))
            except Exception as e:
                self._frame_queue.put(MasterFrame(master_idx, None, e))
                return

    def capabilities(self) -> bytes:
        """Get aggregate capabilities (union of all masters)"""
        with self._lock:
            return bytes(self._aggregate_capabilities)

    def limits(self) -> Limits:
        """Get negotiated limits (minimum across all masters)"""
        with self._lock:
            return self._negotiated_limits

    def installed_cartridges(self) -> List[InstalledCartridgeRecord]:
        """Get aggregate installed cartridge identities of all healthy masters"""
        with self._lock:
            return list(self._aggregate_installed_cartridges)

    def cancel_request(self, rid: MessageId, force_kill: bool) -> None:
        """Cancel a specific in-flight request by request ID.

        Sends Cancel frame to the destination master, cascades to child peer calls,
        and cleans up all routing maps.
        """
        with self._lock:
            self._cancel_request_locked(rid.to_string(), force_kill)

    def _cancel_request_locked(self, rid_key: str, force_kill: bool) -> None:
        """Cancel a request. Must be called with self._lock held."""
        entry = self._request_routing.get(rid_key)
        if entry is None:
            return

        dest_idx = entry.destination_master_idx
        rid = entry.request_id

        # Build and send cancel frame to destination
        cancel_frame = Frame.cancel(rid, force_kill)
        try:
            self._masters[dest_idx].socket_writer.write(cancel_frame)
        except Exception:
            pass

        # Collect child peer calls for recursive cancel
        children = self._peer_call_parents.pop(rid_key, [])

        # Recursively cancel children
        for child_key in children:
            self._cancel_request_locked(child_key, force_kill)

        # Cleanup routing maps
        self._request_routing.pop(rid_key, None)
        self._peer_requests.discard(rid_key)

    def cancel_all_requests(self, force_kill: bool) -> List[MessageId]:
        """Cancel all external-origin (engine-initiated) in-flight requests.

        Returns the list of cancelled request IDs.
        """
        with self._lock:
            # Snapshot all engine-origin entries before mutating
            engine_entries = [
                (key, entry)
                for key, entry in self._request_routing.items()
                if entry.source_master_idx == ENGINE_SOURCE
            ]

            for key, entry in engine_entries:
                self._cancel_request_locked(key, force_kill)

            return [entry.request_id for _, entry in engine_entries]

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

                # Register routing (source = engine)
                self._request_routing[frame.id.to_string()] = RoutingEntry(
                    source_master_idx=ENGINE_SOURCE,
                    destination_master_idx=dest_idx,
                    request_id=frame.id,
                )

                self._masters[dest_idx].socket_writer.write(frame)

            elif frame.frame_type in (FrameType.STREAM_START, FrameType.CHUNK,
                                     FrameType.STREAM_END, FrameType.END, FrameType.ERR):
                # Continuation frames route by request ID
                entry = self._request_routing.get(frame.id.to_string())
                if entry is None:
                    raise UnknownRequestError(frame.id.to_string())

                dest_idx = entry.destination_master_idx
                self._masters[dest_idx].socket_writer.write(frame)

                # Cleanup on terminal frames for peer responses
                is_terminal = frame.frame_type in (FrameType.END, FrameType.ERR)
                if is_terminal and frame.id.to_string() in self._peer_requests:
                    del self._request_routing[frame.id.to_string()]
                    self._peer_requests.discard(frame.id.to_string())

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

            # Use is_dispatchable: can this provider handle this request?
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
        # then by smallest absolute distance. This prefers exact or more-specific providers.
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

                # Register routing (source = cartridge's master)
                self._request_routing[frame.id.to_string()] = RoutingEntry(
                    source_master_idx=source_idx,
                    destination_master_idx=dest_idx,
                    request_id=frame.id,
                )
                self._peer_requests.add(frame.id.to_string())

                self._masters[dest_idx].socket_writer.write(frame)

                # Do NOT return to engine (internal routing)
                return None

            elif frame.frame_type in (FrameType.STREAM_START, FrameType.CHUNK,
                                     FrameType.STREAM_END, FrameType.END,
                                     FrameType.ERR, FrameType.LOG):
                entry = self._request_routing.get(frame.id.to_string())
                if entry is not None and entry.source_master_idx != ENGINE_SOURCE:
                    # Response to peer request
                    dest_idx = entry.source_master_idx
                    is_terminal = frame.frame_type in (FrameType.END, FrameType.ERR)

                    self._masters[dest_idx].socket_writer.write(frame)

                    if is_terminal and frame.id.to_string() not in self._peer_requests:
                        del self._request_routing[frame.id.to_string()]

                    return None

                # Response to engine request
                is_terminal = frame.frame_type in (FrameType.END, FrameType.ERR)
                if is_terminal and frame.id.to_string() not in self._peer_requests:
                    del self._request_routing[frame.id.to_string()]

                return frame

            else:
                # Unknown frame type - return to engine
                return frame

    def _handle_master_death(self, master_idx: int):
        """Handle master death: ERR pending requests, mark unhealthy, rebuild caps"""
        with self._lock:
            if not self._masters[master_idx].healthy:
                return  # Already handled

            self._masters[master_idx].healthy = False

            # Cleanup routing for all requests destined to this master
            to_remove = []
            for req_id, entry in self._request_routing.items():
                if entry.destination_master_idx == master_idx:
                    to_remove.append(req_id)

            for req_id in to_remove:
                del self._request_routing[req_id]
                self._peer_requests.discard(req_id)
                self._peer_call_parents.pop(req_id, None)

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
        """Rebuild aggregate installed cartridges (union with deduplication, sorted)"""
        seen: Dict[str, bool] = {}
        result: List[InstalledCartridgeRecord] = []
        for master in self._masters:
            if master.healthy:
                for ic in master.installed_cartridges:
                    key = ic.id + "@" + ic.version
                    if key not in seen:
                        seen[key] = True
                        result.append(ic)
        result.sort(key=lambda ic: (ic.id, ic.version))
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
        }
    lifecycle = ic.effective_lifecycle()
    if lifecycle != CartridgeLifecycle.DISCOVERED:
        out["lifecycle"] = lifecycle.value
    return out


def _parse_relay_notify_payload(manifest: bytes) -> Tuple[List[str], List[InstalledCartridgeRecord]]:
    """Parse installed cartridges (with cap_groups) from a RelayNotify manifest JSON.

    The payload carries ``installed_cartridges``, each with a ``cap_groups``
    array. The flat cap-urn list returned alongside is computed from those
    groups — it is no longer transmitted on the wire.
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

    return caps, installed_cartridges
