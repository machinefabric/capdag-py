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
from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass

from capdag.bifaci.frame import Frame, FrameType, Limits, MessageId, DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK, DEFAULT_MAX_REORDER_BUFFER
from capdag.bifaci.io import FrameReader, FrameWriter, CborError
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
# DATA STRUCTURES
# =============================================================================

@dataclass
class SocketPair:
    """Socket pair for master connection"""
    read: object  # file-like object for reading
    write: object  # file-like object for writing


@dataclass
class InstalledCartridgeIdentity:
    """Identity of an installed cartridge"""
    id: str
    version: str
    sha256: str


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

        Args:
            sockets: List of socket pairs (one per master)

        Raises:
            RelaySwitchError: If construction fails
        """
        if not sockets:
            raise ProtocolError("RelaySwitch requires at least one master")

        self._masters: List[_MasterConnection] = []
        self._cap_table: List[Tuple[str, int]] = []  # (cap_urn, master_idx)
        self._request_routing: Dict[str, RoutingEntry] = {}
        self._peer_requests: set = set()  # Request IDs for peer-initiated requests
        self._peer_call_parents: Dict[str, List[str]] = {}  # parent key → list of child peer-call keys
        self._aggregate_capabilities: bytes = b""
        self._aggregate_installed_cartridges: List[InstalledCartridgeIdentity] = []
        self._negotiated_limits: Limits = Limits.default()
        self._lock = threading.Lock()

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

            # Spawn reader thread for this master
            reader_thread = threading.Thread(
                target=self._reader_loop,
                args=(master_idx, reader),
                daemon=True
            )
            reader_thread.start()

            master_conn = _MasterConnection(
                socket_writer=writer,
                manifest=manifest,
                limits=limits,
                caps=caps,
                installed_cartridges=installed_cartridges,
                healthy=True,
                reader_handle=reader_thread
            )
            self._masters.append(master_conn)

        # Build initial routing tables
        self._rebuild_cap_table()
        self._rebuild_capabilities()
        self._rebuild_installed_cartridges()
        self._rebuild_limits()

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
                            self._rebuild_capabilities()
                            self._rebuild_installed_cartridges()
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

    def installed_cartridges(self) -> List[InstalledCartridgeIdentity]:
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
                # Check if this registered cap is equivalent to the preferred cap
                is_preferred = False
                if preferred_urn:
                    is_preferred = preferred_urn.is_equivalent(registered_urn)
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

            # Rebuild cap table without dead master
            self._rebuild_cap_table()
            self._rebuild_capabilities()
            self._rebuild_installed_cartridges()
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
        result: List[InstalledCartridgeIdentity] = []
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
        """Rebuild aggregate capabilities manifest (union with deduplication)"""
        all_caps = set()
        for master in self._masters:
            if master.healthy:
                all_caps.update(master.caps)

        manifest = {
            "capabilities": sorted(list(all_caps))
        }
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
    """Connection to a single RelayMaster"""
    socket_writer: FrameWriter
    manifest: bytes
    limits: Limits
    caps: List[str]
    installed_cartridges: List[InstalledCartridgeIdentity]
    healthy: bool
    reader_handle: threading.Thread


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _parse_relay_notify_payload(manifest: bytes) -> Tuple[List[str], List[InstalledCartridgeIdentity]]:
    """Parse capability URNs and installed cartridges from RelayNotify manifest JSON.

    Tries "caps" first (new format), falls back to "capabilities" (old format).
    Returns (caps, installed_cartridges).
    """
    try:
        parsed = json.loads(manifest.decode("utf-8"))
    except json.JSONDecodeError as e:
        raise ProtocolError(f"Failed to parse manifest JSON: {e}")

    # Try "caps" first (new format), fall back to "capabilities" (old format)
    if "caps" in parsed:
        caps_value = parsed["caps"]
    elif "capabilities" in parsed:
        caps_value = parsed["capabilities"]
    else:
        raise ProtocolError("manifest missing caps/capabilities array")

    if not isinstance(caps_value, list):
        raise ProtocolError(f"Manifest capabilities must be array, got {type(caps_value)}")
    caps = [str(cap) for cap in caps_value]

    installed_cartridges = []
    if "installed_cartridges" in parsed:
        ic_raw = parsed["installed_cartridges"]
        if not isinstance(ic_raw, list):
            raise ProtocolError(f"installed_cartridges must be array, got {type(ic_raw)}")
        for item in ic_raw:
            installed_cartridges.append(InstalledCartridgeIdentity(
                id=str(item.get("id", "")),
                version=str(item.get("version", "")),
                sha256=str(item.get("sha256", "")),
            ))

    return caps, installed_cartridges
