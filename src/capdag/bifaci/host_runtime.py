"""Multi-Cartridge Host — Manages N cartridge binaries with cap-based routing.

The CartridgeHost is the host-side runtime that manages all communication with
cartridge processes. It handles:

- Cartridge registration for on-demand spawning
- Cartridge attachment for pre-connected cartridges
- HELLO handshake and limit negotiation
- Cap-based request routing (REQ → correct cartridge)
- Request continuation routing (STREAM_START/CHUNK/STREAM_END/END → by req_id)
- Heartbeat handling (local, not forwarded)
- Cartridge death detection with pending request ERR
- Aggregate capability advertisement

This matches the Rust CartridgeHostRuntime and Go CartridgeHost architectures exactly.

Usage:
```python
from capdag.cartridge_host_runtime import CartridgeHost

host = CartridgeHost()
host.register_cartridge("/path/to/cartridge", ["cap:convert"])
host.run(relay_reader, relay_writer, resource_fn=lambda: b"")
```
"""

import hashlib
import json
import subprocess
import threading
import queue
import time
from pathlib import Path
from typing import Any, Optional, List, Callable
from dataclasses import dataclass

from capdag.bifaci.frame import (
    FailureClass,
    Frame,
    FrameType,
    Limits,
    DropReason,
    CreditDirection,
    DEFAULT_MAX_FRAME,
    DEFAULT_MAX_CHUNK,
    DEFAULT_MAX_REORDER_BUFFER,
)
from capdag.bifaci.io import (
    FrameReader,
    FrameWriter,
    handshake,
    verify_identity,
    CborError,
)
from capdag.bifaci.relay_switch import (
    InstalledCartridgeRecord,
    CartridgeLifecycle,
    CartridgeAttachmentError,
    CartridgeAttachmentErrorKind,
    CartridgeRuntimeStats,
    _installed_cartridge_record_to_wire,
)
from capdag.bifaci.cartridge_repo import CartridgeChannel
from capdag.bifaci.cartridge_json import hash_cartridge_directory
from capdag.bifaci.stats import DropCounters, HostProtocolStats
from capdag.urn.cap_urn import CapUrn, CapUrnError


# =========================================================================
# Error types
# =========================================================================

class AsyncHostError(Exception):
    """Base error for cartridge host"""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class CborErrorWrapper(AsyncHostError):
    """CBOR error wrapper"""
    pass


class IoError(AsyncHostError):
    """I/O error"""
    pass


class CartridgeError(AsyncHostError):
    """Cartridge returned error"""

    def __init__(self, code: str, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.error_message = message


class UnexpectedFrameType(AsyncHostError):
    """Unexpected frame type"""

    def __init__(self, frame_type: FrameType):
        super().__init__(f"Unexpected frame type: {frame_type}")
        self.frame_type = frame_type


class ProcessExited(AsyncHostError):
    """Cartridge process exited unexpectedly"""

    def __init__(self):
        super().__init__("Cartridge process exited unexpectedly")


class Handshake(AsyncHostError):
    """Handshake failed"""
    pass


class Closed(AsyncHostError):
    """Host is closed"""

    def __init__(self):
        super().__init__("Host is closed")


class SendError(AsyncHostError):
    """Send error: channel closed"""

    def __init__(self):
        super().__init__("Send error: channel closed")


class RecvError(AsyncHostError):
    """Receive error: channel closed"""

    def __init__(self):
        super().__init__("Receive error: channel closed")


class Protocol(AsyncHostError):
    """Generic protocol violation"""
    pass


class PeerInvokeNotSupported(AsyncHostError):
    """Peer invoke not supported for this cap URN"""

    def __init__(self, cap_urn: str):
        super().__init__(f"Peer invoke not supported: {cap_urn}")
        self.cap_urn = cap_urn


# =========================================================================
# Response types (used by test harnesses and interop)
# =========================================================================

@dataclass
class ResponseChunk:
    """A response chunk from a cartridge"""
    payload: bytes
    seq: int
    offset: Optional[int]
    len: Optional[int]
    is_eof: bool


class CartridgeResponse:
    """A complete response from a cartridge, which may be single or streaming"""

    def __init__(self, chunks: List[ResponseChunk]):
        """Create from list of chunks"""
        self.chunks = chunks

    @staticmethod
    def single(data: bytes) -> "CartridgeResponse":
        """Create single response"""
        chunk = ResponseChunk(payload=data, seq=0, offset=None, len=None, is_eof=True)
        return CartridgeResponse([chunk])

    @staticmethod
    def streaming(chunks: List[ResponseChunk]) -> "CartridgeResponse":
        """Create streaming response"""
        return CartridgeResponse(chunks)

    def is_single(self) -> bool:
        """Check if this is a single response"""
        return len(self.chunks) == 1 and self.chunks[0].seq == 0

    def is_streaming(self) -> bool:
        """Check if this is a streaming response"""
        return not self.is_single()

    def final_payload(self) -> Optional[bytes]:
        """Get the final chunk's payload (last chunk of streaming, or single payload)"""
        if not self.chunks:
            return None
        return self.chunks[-1].payload

    def concatenated(self) -> bytes:
        """Concatenate all payloads into a single buffer"""
        if self.is_single():
            return self.chunks[0].payload

        result = bytearray()
        for chunk in self.chunks:
            result.extend(chunk.payload)
        return bytes(result)


def cbor_decode_response(response: CartridgeResponse) -> CartridgeResponse:
    """CBOR-decode the raw payload from a CartridgeResponse.

    Cartridge emitters CBOR-encode each emission as a CBOR byte string.
    This function decodes the concatenated CBOR values and returns a new
    CartridgeResponse with decoded payloads.

    Raises on malformed CBOR — no silent fallbacks.
    """
    import io
    import cbor2

    raw = response.concatenated()
    if not raw:
        return CartridgeResponse.single(b"")

    decoded_chunks = []
    stream = io.BytesIO(raw)
    seq = 0
    while stream.tell() < len(raw):
        value = cbor2.CBORDecoder(stream).decode()
        if isinstance(value, bytes):
            payload = value
        elif isinstance(value, str):
            payload = value.encode("utf-8")
        elif isinstance(value, (int, float, bool, list, dict)):
            payload = json.dumps(value).encode("utf-8")
        elif value is None:
            payload = b"null"
        else:
            raise ValueError(
                f"Cannot decode CBOR value of type {type(value).__name__} to bytes"
            )
        decoded_chunks.append(ResponseChunk(
            payload=payload, seq=seq, offset=None, len=None, is_eof=False
        ))
        seq += 1

    if not decoded_chunks:
        raise ValueError("No CBOR values found in response payload")

    decoded_chunks[-1].is_eof = True

    if len(decoded_chunks) == 1:
        return CartridgeResponse.single(decoded_chunks[0].payload)
    return CartridgeResponse.streaming(decoded_chunks)


# =========================================================================
# Internal types
# =========================================================================

@dataclass
class _CartridgeEvent:
    """Internal event from a cartridge reader thread."""
    cartridge_idx: int
    frame: Optional[Frame]  # None = death
    is_death: bool


@dataclass
class _CapTableEntry:
    """Maps a cap URN to a cartridge index."""
    cap_urn: str
    cartridge_idx: int


@dataclass
class _RoutingEntry:
    """Tracks a routed request with its original MessageId."""
    cartridge_idx: int
    msg_id: object  # MessageId


@dataclass
class RegisteredDirSpec:
    """A directory-registered cartridge in a roster sync. Mirrors the
    parameters of ``CartridgeHost.register_cartridge_dir`` so a caller can
    describe the full desired registered-dir set without reaching into
    runtime internals."""
    entry_point: str
    version_dir: str
    id: str
    channel: CartridgeChannel
    registry_url: Optional[str]
    version: str
    cap_groups: List[Any]


class CartridgeProcessHandle:
    """Thread-safe handle for sending commands to a running
    ``CartridgeHost``. Obtained via ``process_handle()`` before calling
    ``run()``. Commands are delivered through a queue the run loop drains
    on each iteration."""

    def __init__(self, command_queue: "queue.Queue"):
        self._command_queue = command_queue

    def sync_roster(self, cartridges: List[RegisteredDirSpec]) -> None:
        """Replace the live registered-dir roster (see SyncRoster). The
        run loop adds newly-desired specs, retires dir-registered
        cartridges no longer present, and re-publishes RelayNotify."""
        self._command_queue.put(("sync_roster", list(cartridges)))

    def kill_cartridge(self, pid: int) -> None:
        """Request that the host kill a specific cartridge process by PID."""
        self._command_queue.put(("kill_cartridge", pid))


class _ManagedCartridge:
    """A cartridge managed by the CartridgeHost."""

    def __init__(self, path: str = "", cap_groups: Optional[List[Any]] = None):
        self.path = path
        # Version directory for directory-based cartridges. When set,
        # identity hashing uses the full directory tree and the cartridge
        # is part of a registered-dir roster sync. None for attached /
        # probe-based registrations.
        self.cartridge_dir: Optional[str] = None
        self.process: Optional[subprocess.Popen] = None
        self.writer: Optional[FrameWriter] = None
        self.writer_queue: Optional[queue.Queue] = None
        self.manifest: bytes = b""
        self.limits: Limits = Limits.default()
        # Cartridge's cap_groups: the single source of truth for what
        # caps this cartridge claims — populated at registration
        # time (probe HELLO at discovery) and refreshed on each
        # spawn/HELLO. The flat cap-URN list is derived from these on
        # demand via ``cap_urns()``; we don't carry a parallel
        # ``known_caps`` field that could drift. Mirrors the Rust
        # ``ManagedCartridge.cap_groups`` design.
        self.cap_groups: List[Any] = list(cap_groups) if cap_groups else []
        # Resolved installed-cartridge identity (registry_url, id,
        # channel, version, sha256). None for attached/probe-based
        # registrations that carry no on-disk anchor. Gates whether the
        # cartridge is advertised in the RelayNotify aggregate.
        self.installed_identity: Optional["InstalledCartridgeRecord"] = None
        self.running: bool = False
        self.hello_failed: bool = False
        # Retired by a roster sync (the install was removed/replaced on
        # disk). A removed cartridge disappears from the inventory entirely
        # — unlike ``hello_failed``, which stays visible carrying an
        # attachment error. Mirrors the reference ``ManagedCartridge.removed``
        # (Swift ``isRemoved``).
        self.removed: bool = False
        # Cumulative protocol drop count self-reported by the cartridge as
        # ``drops_total`` in heartbeat response meta. ``None`` until the
        # first heartbeat round-trip carries the counter. Survives across
        # readings (each heartbeat carries the cartridge's running total).
        self.protocol_drops_total: Optional[int] = None
        # Pending host-initiated heartbeat probes sent to this cartridge
        # (MessageId -> monotonic sent time). A heartbeat frame whose id
        # matches an entry here is a RESPONSE to our own probe (ingest
        # self-reported meta); anything else is a cartridge-initiated
        # heartbeat request (echo immediately). Mirrors the reference
        # ``ManagedCartridge.pending_heartbeats``.
        self.pending_heartbeats: dict = {}
        # Most recent death/failure message (handshake failure, spawn
        # failure, process death), surfaced verbatim on the inventory
        # attachment error when the cartridge has permanently failed HELLO.
        self.last_death_message: Optional[str] = None

    def installed_cartridge_record(self) -> Optional["InstalledCartridgeRecord"]:
        """The cartridge's resolvable install identity, or None for an
        attached/probe-based registration with no on-disk anchor."""
        return self.installed_identity

    def is_registered_dir(self) -> bool:
        """True for a cartridge registered from a version directory (the
        lazily-spawned, dir-backed kind). Distinguishes roster-managed
        installs from attached/internal providers during a SyncRoster."""
        return self.cartridge_dir is not None

    def cap_urns(self) -> List[str]:
        """Flat de-duped view of this cartridge's caps, derived from cap_groups."""
        seen = set()
        out: List[str] = []
        for group in self.cap_groups:
            for cap in group.get("caps", []):
                urn = cap.get("urn", "") if isinstance(cap, dict) else getattr(cap, "urn", "")
                if urn and urn not in seen:
                    seen.add(urn)
                    out.append(urn)
        return out


# =========================================================================
# CartridgeHost — multi-cartridge relay-based host
# =========================================================================

class CartridgeHost:
    """Manages N cartridge binaries with cap-based routing.

    Cartridges are either registered (for on-demand spawning) or attached
    (pre-connected). REQ frames from the relay are routed to the correct
    cartridge by cap URN. Continuation frames (STREAM_START, CHUNK,
    STREAM_END, END) are routed by request ID.

    Matches the Rust CartridgeHostRuntime and Go CartridgeHost architectures.
    """

    def __init__(self):
        self._cartridges: List[_ManagedCartridge] = []
        self._cap_table: List[_CapTableEntry] = []
        self._request_routing: dict = {}  # req_id_str → _RoutingEntry
        self._peer_requests: dict = {}  # req_id_str → True (cartridge-initiated)
        self._capabilities: Optional[bytes] = None
        self._event_queue: queue.Queue = queue.Queue(maxsize=256)
        self._lock = threading.Lock()
        # External commands (SyncRoster / KillCartridge) delivered via
        # ``process_handle()``; drained each run-loop iteration.
        self._command_queue: queue.Queue = queue.Queue()
        # Relay writer captured during ``run()`` so command handlers can
        # re-publish RelayNotify to the engine. None outside ``run()``.
        self._relay_writer: Optional[FrameWriter] = None
        # Inventory records this host does NOT manage as processes —
        # discovery outcomes like incompatible installs (verdict-rejected,
        # wrong manifest version, quarantined). Merged into EVERY
        # capabilities advertisement so a host-originated RelayNotify can
        # never erase them from the engine's inventory. Mirrors the
        # reference ``static_inventory_records``.
        self._static_inventory_records: List["InstalledCartridgeRecord"] = []

    def process_handle(self) -> CartridgeProcessHandle:
        """Return a thread-safe handle for sending commands (SyncRoster /
        KillCartridge) to this host. Must be obtained before ``run()``;
        the handle stays valid for the lifetime of ``run()``."""
        return CartridgeProcessHandle(self._command_queue)

    def set_static_inventory_records(self, records: List["InstalledCartridgeRecord"]) -> None:
        """Provide inventory records for cartridges this host does NOT
        manage as processes — discovery outcomes such as incompatible
        installs, carrying their ``attachment_error``. They are merged into
        every capabilities advertisement (initial and republished), so the
        engine's inventory — and therefore the UI — always shows every
        on-disk cartridge with its status. Mirrors the reference
        ``set_static_inventory_records``."""
        with self._lock:
            self._static_inventory_records = list(records)

    def register_cartridge(
        self,
        path: str,
        name: str,
        version: str,
        channel: CartridgeChannel,
        registry_url: Optional[str],
        cap_groups: List[Any],
    ) -> None:
        """Register a cartridge binary for on-demand spawning.

        ``cap_groups`` is the single source of truth for what caps this
        cartridge handles — populated at registration time (probe HELLO at
        discovery) and refreshed on each spawn/HELLO. The install identity
        is stamped from the binary: ``(name, version, channel, registry_url)``
        come from the cartridge's own manifest (the binary path has no bearing
        on them), and the sha256 is taken over the binary bytes. This mirrors
        the reference ``CartridgeHostRuntime::register_cartridge`` /
        ``new_registered_binary`` — advertisement is identity-gated, so a
        cartridge with no resolvable identity is dropped from every
        RelayNotify, never silently advertised under a synthetic id.

        Args:
            path: Path to the cartridge binary
            name: Cartridge id from its manifest
            version: Cartridge version from its manifest
            channel: Distribution channel from its manifest
            registry_url: Registry URL from its manifest (None ⇔ dev)
            cap_groups: Cap groups this cartridge handles.
        """
        with self._lock:
            cartridge_idx = len(self._cartridges)
            cartridge = _ManagedCartridge(path=path, cap_groups=cap_groups)
            cartridge.installed_identity = _installed_cartridge_record_from_binary(
                path, name, version, channel, registry_url
            )
            self._cartridges.append(cartridge)

            for urn in cartridge.cap_urns():
                self._cap_table.append(_CapTableEntry(cap_urn=urn, cartridge_idx=cartridge_idx))

    def register_cartridge_dir(
        self,
        entry_point: str,
        version_dir: str,
        cartridge_id: str,
        channel: CartridgeChannel,
        registry_url: Optional[str],
        version: str,
        cap_groups: List[Any],
    ) -> None:
        """Register a directory-based cartridge for on-demand spawning.

        The ``version_dir`` must contain a valid ``cartridge.json`` with
        an entry point. Identity is computed from the directory tree hash.
        ``channel`` and ``registry_url`` come from ``cartridge.json`` (the
        host has already validated the three-place rule); they propagate
        through ``InstalledCartridgeRecord`` to the engine's RelayNotify
        so consumers preserve the (registry, channel) provenance
        end-to-end. A directory that is unhashable at registration time is
        recorded as ``hello_failed`` so it drops out of the aggregate
        rather than being silently dropped. Mirrors the Rust
        ``register_cartridge_dir`` / ``new_registered_dir``.
        """
        with self._lock:
            cartridge_idx = len(self._cartridges)
            cartridge = _ManagedCartridge(path=entry_point, cap_groups=cap_groups)
            cartridge.cartridge_dir = version_dir
            try:
                sha256 = hash_cartridge_directory(Path(version_dir))
                cartridge.installed_identity = InstalledCartridgeRecord(
                    registry_url=registry_url,
                    id=cartridge_id,
                    channel=channel.value,
                    version=version,
                    sha256=sha256,
                    cap_groups=list(cap_groups),
                    # Engine-spawned external providers are operational by
                    # construction: discovery validated the install context and
                    # probed the cartridge before this registration.
                    lifecycle=CartridgeLifecycle.OPERATIONAL,
                )
            except Exception as e:
                # Unhashable directory: record an identity carrying the
                # attachment error and mark the cartridge permanently failed so
                # it is excluded from the cap table and RelayNotify aggregate
                # (never hosted), but still surfaces the real reason. Mirrors
                # the reference new_registered_dir error path.
                import time
                cartridge.installed_identity = InstalledCartridgeRecord(
                    registry_url=registry_url,
                    id=cartridge_id,
                    channel=channel.value,
                    version=version,
                    sha256="",
                    cap_groups=list(cap_groups),
                    attachment_error=CartridgeAttachmentError(
                        kind=CartridgeAttachmentErrorKind.ENTRY_POINT_MISSING,
                        message=f"Cartridge directory not hashable at '{version_dir}': {e}",
                        detected_at_unix_seconds=int(time.time()),
                    ),
                    # attachment_error is set ⇒ lifecycle is irrelevant per the
                    # mutual-exclusivity contract; default to DISCOVERED (the
                    # safe sentinel) rather than asserting OPERATIONAL.
                    lifecycle=CartridgeLifecycle.DISCOVERED,
                )
                cartridge.hello_failed = True
            self._cartridges.append(cartridge)
            if not cartridge.hello_failed:
                for urn in cartridge.cap_urns():
                    self._cap_table.append(_CapTableEntry(cap_urn=urn, cartridge_idx=cartridge_idx))

    def attach_cartridge(self, cartridge_stdout, cartridge_stdin) -> int:
        """Attach a pre-connected cartridge (already running).

        Performs HELLO handshake immediately and returns the cartridge index.

        Args:
            cartridge_stdout: Cartridge's stdout stream (host reads from this)
            cartridge_stdin: Cartridge's stdin stream (host writes to this)

        Returns:
            Cartridge index

        Raises:
            AsyncHostError: If handshake fails
        """
        reader = FrameReader(cartridge_stdout)
        writer = FrameWriter(cartridge_stdin)

        try:
            result = handshake(reader, writer)
            verify_identity(reader, writer)
        except Exception as e:
            raise Handshake(f"handshake failed: {e}")

        cap_groups = _parse_cap_groups_from_manifest(result.manifest)

        with self._lock:
            cartridge_idx = len(self._cartridges)

            writer_q = queue.Queue(maxsize=64)
            cartridge = _ManagedCartridge()
            cartridge.writer = writer
            cartridge.writer_queue = writer_q
            cartridge.manifest = result.manifest
            cartridge.limits = result.limits
            cartridge.cap_groups = cap_groups
            cartridge.running = True
            # Derive the install identity from the HELLO manifest. Advertisement
            # is identity-gated, so without this the attached cartridge is
            # silently excluded from every RelayNotify and the engine can never
            # route to it (the dev/interop relay path).
            cartridge.installed_identity = _installed_cartridge_record_from_manifest(
                result.manifest
            )

            self._cartridges.append(cartridge)

            for urn in cartridge.cap_urns():
                self._cap_table.append(_CapTableEntry(cap_urn=urn, cartridge_idx=cartridge_idx))
            self._rebuild_capabilities()

        # Start reader and writer threads
        threading.Thread(
            target=self._writer_loop, args=(writer, writer_q),
            daemon=True
        ).start()
        threading.Thread(
            target=self._reader_loop, args=(cartridge_idx, reader),
            daemon=True
        ).start()

        return cartridge_idx

    def capabilities(self) -> Optional[bytes]:
        """Return the aggregate capabilities of all running cartridges as JSON."""
        with self._lock:
            return self._capabilities

    def find_cartridge_for_cap(self, cap_urn: str) -> Optional[int]:
        """Find the cartridge index that can handle a given cap URN.

        Returns cartridge index if found, None if not.
        """
        with self._lock:
            return self._find_cartridge_for_cap_locked(cap_urn)

    def _find_cartridge_for_cap_locked(self, cap_urn: str) -> Optional[int]:
        """Find cartridge for cap (caller must hold lock)."""
        # Exact string match first
        for entry in self._cap_table:
            if entry.cap_urn == cap_urn:
                return entry.cartridge_idx

        # URN-level matching: use is_dispatchable (provider can handle request)
        try:
            request_urn = CapUrn.from_string(cap_urn)
        except CapUrnError:
            return None

        request_specificity = request_urn.specificity()
        matches = []  # (cartridge_idx, signed_distance)

        for entry in self._cap_table:
            try:
                registered_urn = CapUrn.from_string(entry.cap_urn)
            except CapUrnError:
                continue
            if registered_urn.is_dispatchable(request_urn):
                specificity = registered_urn.specificity()
                signed_distance = specificity - request_specificity
                matches.append((entry.cartridge_idx, signed_distance))

        if not matches:
            return None

        # Rank: non-negative distance (refinement/exact) before negative (fallback),
        # then by smallest absolute distance
        matches.sort(key=lambda m: (0 if m[1] >= 0 else 1, abs(m[1])))
        return matches[0][0]

    def run(self, relay_read, relay_write, resource_fn: Optional[Callable] = None) -> None:
        """Run the main event loop, reading from relay and cartridges.

        Blocks until relay closes or a fatal error occurs.

        Args:
            relay_read: Relay stdout stream (host reads from this)
            relay_write: Relay stdin stream (host writes to this)
            resource_fn: Optional function returning resource state bytes
        """
        relay_reader = FrameReader(relay_read)
        relay_writer = FrameWriter(relay_write)
        # Bind the relay writer so command handlers (SyncRoster) and
        # cartridge HELLO/death can re-publish RelayNotify to the engine.
        self._relay_writer = relay_writer

        # Send the initial RelayNotify so the engine learns about
        # pre-registered cartridges (possibly an empty roster) without
        # waiting for the first cap change.
        with self._lock:
            self._rebuild_capabilities(emit=True)

        relay_queue = queue.Queue(maxsize=64)
        relay_done = threading.Event()
        relay_error = [None]

        def relay_reader_thread():
            try:
                while True:
                    frame = relay_reader.read()
                    if frame is None:
                        relay_done.set()
                        return
                    relay_queue.put(frame)
            except Exception as e:
                relay_error[0] = e
                relay_done.set()

        threading.Thread(target=relay_reader_thread, daemon=True).start()

        # Periodic runtime-stats refresh cadence. The reference republishes
        # RelayNotify on a ~2s stats interval so the engine sees current
        # request counts / memory / heartbeat ages even when no cap change
        # has fired. Only republished when at least one cartridge is running,
        # keeping idle hosts quiet.
        STATS_INTERVAL_SECONDS = 2.0
        last_stats_publish = time.monotonic()

        while True:
            # Periodic runtime-stats republish — mirrors the reference
            # ``stats_interval`` tick.
            now = time.monotonic()
            if now - last_stats_publish >= STATS_INTERVAL_SECONDS:
                last_stats_publish = now
                with self._lock:
                    any_running = any(c.running for c in self._cartridges)
                    if any_running:
                        self._rebuild_capabilities(emit=True)

            # Drain external commands (SyncRoster / KillCartridge) first so
            # roster changes are reflected before processing relay traffic.
            try:
                while True:
                    cmd = self._command_queue.get_nowait()
                    self._handle_command(cmd, relay_writer)
            except queue.Empty:
                pass

            # Check relay done
            if relay_done.is_set() and relay_queue.empty():
                self._relay_writer = None
                self._kill_all_cartridges()
                if relay_error[0] is not None:
                    raise IoError(str(relay_error[0]))
                return

            # Try to get a relay frame or cartridge event (non-blocking check both)
            try:
                frame = relay_queue.get(timeout=0.01)
                self._handle_relay_frame(frame, relay_writer)
                continue
            except queue.Empty:
                pass

            try:
                event = self._event_queue.get_nowait()
                if event.is_death:
                    self._handle_cartridge_death(event.cartridge_idx, relay_writer)
                elif event.frame is not None:
                    self._handle_cartridge_frame(event.cartridge_idx, event.frame, relay_writer)
            except queue.Empty:
                pass

    def _handle_relay_frame(self, frame: Frame, relay_writer: FrameWriter) -> None:
        """Route an incoming frame from the relay to the correct cartridge."""
        with self._lock:
            id_key = frame.id.to_string() if hasattr(frame.id, 'to_string') else str(frame.id)

            if frame.frame_type == FrameType.REQ:
                cap_urn = frame.cap or ""

                cartridge_idx = self._find_cartridge_for_cap_locked(cap_urn)
                if cartridge_idx is None:
                    # No dispatchable cartridge for a planned cap is a
                    # deployment/manifest mismatch — Environment.
                    err_frame = Frame.err_classified(frame.id, "NO_HANDLER", FailureClass.ENVIRONMENT, f"no cartridge handles cap: {cap_urn}")
                    relay_writer.write(err_frame)
                    return

                cartridge = self._cartridges[cartridge_idx]
                if not cartridge.running:
                    if cartridge.hello_failed:
                        err_frame = Frame.err_classified(frame.id, "SPAWN_FAILED", FailureClass.ENVIRONMENT, "cartridge previously failed to start")
                        relay_writer.write(err_frame)
                        return
                    err = self._spawn_cartridge_locked(cartridge_idx)
                    if err is not None:
                        err_frame = Frame.err_classified(frame.id, "SPAWN_FAILED", FailureClass.ENVIRONMENT, str(err))
                        relay_writer.write(err_frame)
                        return

                self._request_routing[id_key] = _RoutingEntry(cartridge_idx=cartridge_idx, msg_id=frame.id)
                self._send_to_cartridge(cartridge_idx, frame)

            elif frame.frame_type in (
                FrameType.STREAM_START,
                FrameType.CHUNK,
                FrameType.STREAM_END,
                FrameType.CREDIT,
            ):
                # CREDIT rides the same continuation route as data frames
                # (reference PATH C adds ``FrameType::Credit`` to this arm): an
                # engine→cartridge grant targets the handler that is sending the
                # credited output stream, routed by its request id. Dropping it
                # here silently would starve the cartridge's credit gate and
                # deadlock any response larger than the initial window.
                entry = self._request_routing.get(id_key)
                if entry is not None:
                    self._send_to_cartridge(entry.cartridge_idx, frame)

            elif frame.frame_type in (FrameType.END, FrameType.ERR):
                entry = self._request_routing.get(id_key)
                if entry is not None:
                    self._send_to_cartridge(entry.cartridge_idx, frame)
                    is_terminal = True
                    # Only remove routing on terminal frames if this is a PEER response
                    # (engine responding to a cartridge's peer invoke). For engine-initiated
                    # requests, the relay END is just the end of the request body — the
                    # cartridge still needs to respond, so routing must survive.
                    if is_terminal and id_key in self._peer_requests:
                        self._request_routing.pop(id_key, None)
                        self._peer_requests.pop(id_key, None)

            elif frame.frame_type == FrameType.HEARTBEAT:
                # Engine-level heartbeat — not forwarded to cartridges
                return

            elif frame.frame_type == FrameType.HELLO:
                raise Protocol("unexpected HELLO from relay")

            elif frame.frame_type in (FrameType.RELAY_NOTIFY, FrameType.RELAY_STATE):
                raise Protocol(f"relay frame {frame.frame_type} reached cartridge host")

    def _handle_cartridge_frame(self, cartridge_idx: int, frame: Frame, relay_writer: FrameWriter) -> None:
        """Process a frame from a cartridge."""
        with self._lock:
            id_key = frame.id.to_string() if hasattr(frame.id, 'to_string') else str(frame.id)

            if frame.frame_type == FrameType.HEARTBEAT:
                cartridge = self._cartridges[cartridge_idx]
                sent_at = cartridge.pending_heartbeats.pop(frame.id, None)
                if sent_at is not None:
                    # A response to our own probe: ingest the cartridge's
                    # self-reported meta. The cumulative protocol drop
                    # counter (L8) is the cartridge's running total — stored
                    # as-is, never merged or maxed. Mirrors the reference
                    # heartbeat-response handling.
                    if frame.meta:
                        drops_total = frame.meta.get("drops_total")
                        if isinstance(drops_total, int):
                            cartridge.protocol_drops_total = drops_total
                else:
                    # Cartridge-initiated heartbeat request — respond locally,
                    # don't forward.
                    response = Frame.heartbeat(frame.id)
                    self._send_to_cartridge(cartridge_idx, response)

            elif frame.frame_type == FrameType.HELLO:
                # HELLO post-handshake — protocol violation, ignore
                return

            elif frame.frame_type == FrameType.REQ:
                # Cartridge is invoking a peer cap (sending request to engine)
                self._request_routing[id_key] = _RoutingEntry(cartridge_idx=cartridge_idx, msg_id=frame.id)
                self._peer_requests[id_key] = True
                relay_writer.write(frame)

            elif frame.frame_type == FrameType.LOG:
                relay_writer.write(frame)

            elif frame.frame_type in (
                FrameType.STREAM_START,
                FrameType.CHUNK,
                FrameType.STREAM_END,
                FrameType.CREDIT,
            ):
                # A cartridge-originated CREDIT grant (crediting the engine's
                # request-body / peer-response streams) forwards outbound like
                # any other continuation frame — the reference forwards every
                # non-REQ cartridge frame to the relay. Silently dropping it
                # would stall flow control in the cartridge→engine direction.
                relay_writer.write(frame)

            elif frame.frame_type == FrameType.END:
                relay_writer.write(frame)
                if id_key not in self._peer_requests:
                    self._request_routing.pop(id_key, None)

            elif frame.frame_type == FrameType.ERR:
                relay_writer.write(frame)
                self._request_routing.pop(id_key, None)
                self._peer_requests.pop(id_key, None)

    def _handle_cartridge_death(self, cartridge_idx: int, relay_writer: FrameWriter) -> None:
        """Process a cartridge death event."""
        with self._lock:
            cartridge = self._cartridges[cartridge_idx]
            cartridge.running = False

            if cartridge.writer_queue is not None:
                # Signal writer to stop
                cartridge.writer_queue.put(None)
                cartridge.writer_queue = None

            if cartridge.process is not None:
                try:
                    cartridge.process.kill()
                except Exception:
                    pass
                cartridge.process = None

            # Send ERR for all pending requests routed to this cartridge
            failed_keys = []
            failed_entries = []
            for req_id, entry in self._request_routing.items():
                if entry.cartridge_idx == cartridge_idx:
                    failed_keys.append(req_id)
                    failed_entries.append(entry)

            for i, key in enumerate(failed_keys):
                # A dead cartridge process is a runtime-environment
                # failure — Environment (docs/failure-taxonomy.md).
                err_frame = Frame.err_classified(
                    failed_entries[i].msg_id,
                    "CARTRIDGE_DIED",
                    FailureClass.ENVIRONMENT,
                    f"cartridge {cartridge_idx} died"
                )
                try:
                    relay_writer.write(err_frame)
                except Exception:
                    pass  # Relay might already be gone
                del self._request_routing[key]
                self._peer_requests.pop(key, None)

            self._update_cap_table()
            self._rebuild_capabilities()

    def _send_to_cartridge(self, cartridge_idx: int, frame: Frame) -> None:
        """Send a frame to a cartridge via its writer queue."""
        cartridge = self._cartridges[cartridge_idx]
        if cartridge.writer_queue is not None:
            try:
                cartridge.writer_queue.put_nowait(frame)
            except queue.Full:
                pass  # Cartridge probably dead, frame dropped

    def _writer_loop(self, writer: FrameWriter, q: queue.Queue) -> None:
        """Writer thread — reads frames from queue and writes to cartridge."""
        while True:
            frame = q.get()
            if frame is None:  # Shutdown sentinel
                return
            try:
                writer.write(frame)
            except Exception:
                return

    def _reader_loop(self, cartridge_idx: int, reader: FrameReader) -> None:
        """Reader thread — reads frames from cartridge and sends events."""
        while True:
            try:
                frame = reader.read()
                if frame is None:
                    self._event_queue.put(_CartridgeEvent(
                        cartridge_idx=cartridge_idx, frame=None, is_death=True
                    ))
                    return
                self._event_queue.put(_CartridgeEvent(
                    cartridge_idx=cartridge_idx, frame=frame, is_death=False
                ))
            except Exception:
                self._event_queue.put(_CartridgeEvent(
                    cartridge_idx=cartridge_idx, frame=None, is_death=True
                ))
                return

    def _spawn_cartridge_locked(self, cartridge_idx: int) -> Optional[str]:
        """Spawn a registered cartridge process (caller must hold lock).

        Returns None on success, error message string on failure.
        """
        cartridge = self._cartridges[cartridge_idx]

        if not cartridge.path:
            cartridge.hello_failed = True
            cartridge.last_death_message = "cartridge has no path"
            return "cartridge has no path"

        try:
            proc = subprocess.Popen(
                [cartridge.path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            cartridge.hello_failed = True
            cartridge.last_death_message = f"failed to start cartridge: {e}"
            return f"failed to start cartridge: {e}"

        cartridge.process = proc

        reader = FrameReader(proc.stdout)
        writer = FrameWriter(proc.stdin)

        try:
            result = handshake(reader, writer)
            verify_identity(reader, writer)
        except Exception as e:
            cartridge.hello_failed = True
            cartridge.last_death_message = f"handshake failed: {e}"
            try:
                proc.kill()
            except Exception:
                pass
            return f"handshake failed: {e}"

        try:
            cap_groups = _parse_cap_groups_from_manifest(result.manifest)
        except Exception as e:
            cartridge.hello_failed = True
            cartridge.last_death_message = f"failed to parse manifest: {e}"
            try:
                proc.kill()
            except Exception:
                pass
            return f"failed to parse manifest: {e}"

        cartridge.manifest = result.manifest
        cartridge.limits = result.limits
        cartridge.cap_groups = cap_groups
        cartridge.running = True
        cartridge.writer = writer

        writer_q = queue.Queue(maxsize=64)
        cartridge.writer_queue = writer_q

        self._update_cap_table()
        self._rebuild_capabilities()

        threading.Thread(
            target=self._writer_loop, args=(writer, writer_q),
            daemon=True
        ).start()
        threading.Thread(
            target=self._reader_loop, args=(cartridge_idx, reader),
            daemon=True
        ).start()

        return None

    def _update_cap_table(self) -> None:
        """Rebuild the cap table from all cartridges.

        ``cap_groups`` is the single source of truth for what each
        cartridge handles. Mirrors Rust's ``update_cap_table``.
        """
        self._cap_table = []
        for idx, cartridge in enumerate(self._cartridges):
            if cartridge.hello_failed:
                continue
            for urn in cartridge.cap_urns():
                self._cap_table.append(_CapTableEntry(cap_urn=urn, cartridge_idx=idx))

    def _build_installed_cartridge_identities(self) -> List[dict]:
        """Build the ``installed_cartridges`` list for a RelayNotify
        payload.

        Identity gates advertisement: a cartridge with no resolvable
        ``installed_identity`` is NOT part of the inventory the engine can
        route to and is dropped. (Attached cartridges get a manifest-derived
        identity at attach time, so a missing identity here means a
        genuinely anchorless cartridge; we expose that by dropping it rather
        than fabricating a synthetic ``cartridge-N`` record that would hide
        the gap.)

        Retirement (``removed``) is NOT a failure — a roster-retired
        cartridge disappears from the inventory entirely, there is nothing
        to report. A cartridge whose HELLO permanently failed
        (``hello_failed``, e.g. a pre-v3 binary hard-rejected by the version
        check) STAYS in the inventory carrying a ``handshake_failed``
        attachment error and no cap_groups — never silently absent; failure
        is named, not hidden. Static inventory records (discovery outcomes
        this host doesn't manage as processes) are merged in on every call
        so a host-originated RelayNotify can never erase them from the
        engine's inventory. Mirrors the reference
        ``build_installed_cartridge_identities``."""
        import dataclasses

        installed: List[dict] = []
        for cartridge in self._cartridges:
            if cartridge.removed:
                continue
            rec = cartridge.installed_cartridge_record()
            if rec is None:
                continue
            pid = None
            if cartridge.process is not None:
                pid = cartridge.process.pid
            stats = CartridgeRuntimeStats(
                running=cartridge.running,
                pid=pid,
                protocol_drops_total=cartridge.protocol_drops_total,
            )
            if cartridge.hello_failed:
                error = CartridgeAttachmentError(
                    kind=CartridgeAttachmentErrorKind.HANDSHAKE_FAILED,
                    message=cartridge.last_death_message or (
                        "HELLO handshake failed (protocol version mismatch or "
                        "malformed manifest) — rebuild the cartridge against the "
                        "current protocol"
                    ),
                    detected_at_unix_seconds=int(time.time()),
                )
                out = dataclasses.replace(
                    rec,
                    cap_groups=[],
                    attachment_error=error,
                    runtime_stats=stats,
                )
                installed.append(_installed_cartridge_record_to_wire(out))
                continue
            out = dataclasses.replace(
                rec,
                cap_groups=cartridge.cap_groups,
                runtime_stats=stats,
            )
            installed.append(_installed_cartridge_record_to_wire(out))
        # Discovery outcomes the host doesn't manage (incompatible installs)
        # ride every advertisement so no republish can erase them.
        for rec in self._static_inventory_records:
            installed.append(_installed_cartridge_record_to_wire(rec))
        return installed

    def _rebuild_capabilities(self, emit: bool = False) -> None:
        """Rebuild the aggregate capabilities JSON.

        The wire payload lives entirely inside
        ``installed_cartridges[*].cap_groups``. ``cap_groups`` is the
        single source of truth. When ``emit`` is True and a relay writer
        is bound (i.e. running in relay mode), a RelayNotify frame with
        the updated inventory is pushed to the engine so it sees
        added/removed cartridges without reconnecting. Mirrors the Rust
        ``rebuild_capabilities``.
        """
        installed = self._build_installed_cartridge_identities()

        if not installed:
            self._capabilities = None
        else:
            self._capabilities = json.dumps({"installed_cartridges": installed}).encode("utf-8")

        if emit and self._relay_writer is not None:
            payload = json.dumps({"installed_cartridges": installed}).encode("utf-8")
            # Advertise the host's REAL aggregate limits — the element-wise
            # minimum over every running cartridge's negotiated handshake
            # limits. The switch overwrites the master's limits on each
            # RelayNotify, so sending defaults here would clobber genuine
            # negotiations (and misreport initial_credit end-to-end).
            # Mirrors the reference ``aggregate_limits``.
            limits = self._aggregate_limits()
            notify = Frame.relay_notify(
                payload,
                limits.max_frame,
                limits.max_chunk,
                limits.max_reorder_buffer,
                limits.initial_credit,
            )
            try:
                self._relay_writer.write(notify)
            except Exception:
                # Relay closed — ignore, mirrors Rust's best-effort send.
                pass

    def _aggregate_limits(self) -> Limits:
        """Element-wise minimum over the negotiated limits of every running
        cartridge; defaults when none are running. This is what the host is
        actually able to honor across its fleet. Caller MUST hold
        ``self._lock``. Mirrors the reference ``aggregate_limits``."""
        limits = Limits.default()
        for cartridge in self._cartridges:
            if not cartridge.running:
                continue
            limits.max_frame = min(limits.max_frame, cartridge.limits.max_frame)
            limits.max_chunk = min(limits.max_chunk, cartridge.limits.max_chunk)
            limits.max_reorder_buffer = min(
                limits.max_reorder_buffer, cartridge.limits.max_reorder_buffer
            )
            limits.initial_credit = min(limits.initial_credit, cartridge.limits.initial_credit)
        return limits

    def _kill_all_cartridges(self) -> None:
        """Stop all managed cartridges."""
        with self._lock:
            for cartridge in self._cartridges:
                if cartridge.writer_queue is not None:
                    cartridge.writer_queue.put(None)
                    cartridge.writer_queue = None
                if cartridge.process is not None:
                    try:
                        cartridge.process.kill()
                    except Exception:
                        pass
                cartridge.running = False

    def _handle_command(self, cmd, relay_writer: FrameWriter) -> None:
        """Dispatch an external command delivered via the process handle."""
        kind = cmd[0]
        if kind == "sync_roster":
            self._sync_registered_roster(cmd[1])
        elif kind == "kill_cartridge":
            self._kill_cartridge_by_pid(cmd[1])

    def _kill_cartridge_by_pid(self, pid: int) -> None:
        with self._lock:
            for cartridge in self._cartridges:
                if cartridge.process is not None and cartridge.process.pid == pid:
                    try:
                        cartridge.process.kill()
                    except Exception:
                        pass

    def _sync_registered_roster(self, desired: List[RegisteredDirSpec]) -> None:
        """Replace the live registered-dir roster with a freshly-discovered
        set and re-publish RelayNotify, so the engine sees added/removed
        cartridges without reconnecting — the parity path the daemon uses
        after a rescan (e.g. a registry verdict flipped a held cartridge to
        Listed).

        Running cartridges no longer in the set are killed and dropped from
        the inventory; survivors keep their live process and stats. Only
        dir-registered cartridges participate — attached/internal providers
        are left untouched. Mirrors the Rust ``sync_registered_roster``.
        """
        def identity_of(rec: "InstalledCartridgeRecord"):
            return (rec.registry_url, rec.channel, rec.id, rec.version)

        desired_keys = {
            (s.registry_url, s.channel.value, s.id, s.version) for s in desired
        }

        new_specs: List[RegisteredDirSpec] = []
        with self._lock:
            # Retire registered-dir cartridges no longer desired. Only
            # already-``removed`` cartridges are skipped here — a cartridge
            # that failed HELLO but was never retired is still reconsidered
            # (it may match a desired spec again after a rebuild). Mirrors
            # the reference ``sync_registered_roster``.
            for cartridge in self._cartridges:
                if cartridge.removed:
                    continue
                rec = cartridge.installed_cartridge_record()
                if rec is None:
                    continue  # no resolvable identity (internal provider) — leave it
                if not cartridge.is_registered_dir():
                    continue  # attached/internal — not part of a dir roster sync
                if identity_of(rec) in desired_keys:
                    continue  # still desired — keep, preserving any live process
                if cartridge.running:
                    if cartridge.writer_queue is not None:
                        cartridge.writer_queue.put(None)
                        cartridge.writer_queue = None
                    if cartridge.process is not None:
                        try:
                            cartridge.process.kill()
                        except Exception:
                            pass
                        cartridge.process = None
                    cartridge.running = False
                # Retire: drop from the inventory entirely (not a failure —
                # nothing to report). ``hello_failed`` also keeps it out of
                # the cap table / dispatch / spawn paths. Mirrors the
                # reference ``removed`` + ``hello_failed`` pair.
                cartridge.removed = True
                cartridge.hello_failed = True

            # Compute which desired specs are not already registered.
            present_keys = set()
            for cartridge in self._cartridges:
                if cartridge.hello_failed:
                    continue
                rec = cartridge.installed_cartridge_record()
                if rec is not None:
                    present_keys.add(identity_of(rec))
            for spec in desired:
                key = (spec.registry_url, spec.channel.value, spec.id, spec.version)
                if key in present_keys:
                    continue
                new_specs.append(spec)

        # Register the new specs OUTSIDE the lock — register_cartridge_dir
        # takes the lock itself (and hashes the directory, which may be
        # slow). Re-entrant locking is avoided by deferring to it here.
        for spec in new_specs:
            self.register_cartridge_dir(
                spec.entry_point,
                spec.version_dir,
                spec.id,
                spec.channel,
                spec.registry_url,
                spec.version,
                spec.cap_groups,
            )

        with self._lock:
            self._update_cap_table()
            self._rebuild_capabilities(emit=True)


# =========================================================================
# Helpers
# =========================================================================

def _installed_cartridge_record_from_binary(
    path: str,
    name: str,
    version: str,
    channel: CartridgeChannel,
    registry_url: Optional[str],
) -> Optional["InstalledCartridgeRecord"]:
    """Build the install identity for a cartridge registered by binary path
    (on-demand spawn). The identity tuple ``(registry_url, channel, id,
    version)`` comes from the cartridge's manifest (supplied by the caller —
    the binary path has no bearing on them); the sha256 is taken over the
    binary bytes. Mirrors the reference
    ``installed_cartridge_record_from_binary``. Returns ``None`` if the binary
    is unreadable (the cartridge is then dropped from advertisement rather
    than advertised without a resolvable identity)."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    sha256 = hashlib.sha256(data).hexdigest()
    return InstalledCartridgeRecord(
        registry_url=registry_url,
        id=name,
        channel=channel.value,
        version=version,
        sha256=sha256,
        # On-demand binary: not yet probed/verified at registration time.
        lifecycle=CartridgeLifecycle.DISCOVERED,
    )


def _installed_cartridge_record_from_manifest(
    manifest: bytes,
) -> Optional["InstalledCartridgeRecord"]:
    """Build the install identity for a cartridge attached over raw streams
    (no on-disk anchor: the dev/host-embedded/interop path).

    Advertisement is identity-gated — a cartridge with no identity is
    silently dropped from every RelayNotify (see
    ``_build_installed_cartridge_identities``), so an attached cartridge MUST
    carry a resolvable identity or the host advertises an empty inventory and
    the engine can never route to it. An attached cartridge has already
    completed HELLO + identity verification by the time this is called, so it
    is operational by construction; its identity is sourced from the manifest
    it sent during HELLO (the same ``(registry_url, channel, id, version)``
    tuple a registered install carries), with the sha256 taken over the
    manifest bytes (the only stable artefact available without a file on
    disk). Mirrors the reference ``installed_cartridge_record_from_manifest``.
    Returns ``None`` if the manifest does not parse (the caller still
    attaches; the record is honestly absent).
    """
    if not manifest:
        return None
    try:
        parsed = json.loads(manifest)
    except (ValueError, TypeError):
        return None
    name = parsed.get("name")
    version = parsed.get("version")
    channel = parsed.get("channel")
    if not isinstance(name, str) or not isinstance(version, str) or not isinstance(channel, str):
        return None
    sha256 = hashlib.sha256(manifest).hexdigest()
    return InstalledCartridgeRecord(
        registry_url=parsed.get("registry_url"),
        id=name,
        channel=channel,
        version=version,
        sha256=sha256,
        # Attached ⇒ HELLO + identity verification already succeeded.
        lifecycle=CartridgeLifecycle.OPERATIONAL,
    )


def _parse_cap_groups_from_manifest(manifest: bytes) -> List[Any]:
    """Parse the cartridge's cap_groups from a JSON manifest.

    Returns the list of ``cap_groups`` dicts as declared in the
    manifest. The flat cap-urn list is computed from these groups
    elsewhere — the engine reads ``installed_cartridges[*].cap_groups``
    and derives its own.
    """
    from capdag.standard.caps import CAP_IDENTITY

    if not manifest:
        return []

    parsed = json.loads(manifest)
    cap_groups = parsed.get("cap_groups")
    if not cap_groups:
        raise ValueError("Manifest missing required cap_groups array")

    has_identity = False
    for group in cap_groups:
        for cap in group.get("caps", []):
            if cap.get("urn", "") == CAP_IDENTITY:
                has_identity = True
                break
        if has_identity:
            break

    if not has_identity:
        raise ValueError(f"Manifest missing required CAP_IDENTITY ({CAP_IDENTITY})")

    return cap_groups


# =========================================================================
# Cartridge host runtime — bounded routing tables with age-based GC
# =========================================================================
#
# This is the engine-side per-host runtime that routes frames between a
# relay connection and a single managed cartridge. The Python mirror does
# not yet host the full async run loop (that lives in CartridgeHost above
# for the relay-host path); what is ported here is the bounded routing-table
# subsystem, its garbage collector, and the protocol-v3 routing/terminal-
# bookkeeping algorithm that decides how a continuation frame is routed and
# when a routing entry is released — exercised in isolation by the
# routing-GC and routing-selection tests. It mirrors Rust
# ``CartridgeHostRuntime`` exactly: four routing maps each with a parallel
# ``*_touched`` clock map, a monotonic ``routing_touch_seq`` stamp, a GC
# that evicts the least-recently-touched entries when a table crosses the
# soft watermark (with a secondary hard-cap pass for extreme runaway), the
# v3 ``incoming_body_done`` / ``incoming_response_done`` terminal-drain
# markers, a per-reason drop counter, and the ``protocol_stats()``
# observability snapshot.


class CartridgeHostRuntime:
    """Engine-side runtime owning bounded routing tables for one host.

    Mirrors the Rust ``CartridgeHostRuntime`` routing-table discipline.
    Protocol v3 (L6/L8/L11): the ``incoming_rxids`` entry for a request
    lives from REQ until the request's RESPONSE terminal, not the
    request-body END — the body END only sets a body-done marker
    (``incoming_body_done``) so self-loop peer-response data frames fall
    through to ``outgoing_rids`` routing; the handler's response terminal
    passing outbound (plus body-done) is what releases the entry. A
    response terminating BEFORE the body END arrives (response-first race)
    is remembered in ``incoming_response_done`` so the body END releases the
    entry immediately. Keeping the entry alive through the response phase is
    what routes engine→cartridge CREDIT grants for the handler's output
    streams — without it, any response larger than the initial window
    deadlocks. A cartridge that creates many distinct request IDs without
    dying would still accumulate entries forever, so the GC evicts the
    oldest entries by touch-sequence once a table crosses its soft
    watermark.
    """

    # Generous cap on the per-host routing tables. ~14x headroom over a
    # long-session steady state (~568 entries) so the GC runs ahead of
    # bursts while still catching a runaway producer.
    ROUTING_TABLE_HARD_CAP: int = 8192
    # Soft watermark — when a table reaches this size, the GC fires and
    # evicts the oldest 25% by touch sequence. ~80% of the hard cap so the
    # GC runs ahead of the cap rather than spinning right at it.
    ROUTING_TABLE_SOFT_WATERMARK: int = 6553
    # Fraction of entries to drop in one GC pass.
    ROUTING_TABLE_GC_EVICTION_FRACTION: float = 0.25

    def __init__(self) -> None:
        # List 1: OUTGOING_RIDS — peer requests sent by cartridges
        # (RID -> cartridge_idx) plus its parallel touched clock.
        self.outgoing_rids: dict = {}
        self.outgoing_rids_touched: dict = {}
        # List 2: INCOMING_RXIDS — incoming requests from relay
        # ((XID, RID) -> cartridge_idx). Continuations route by this table.
        self.incoming_rxids: dict = {}
        self.incoming_rxids_touched: dict = {}
        # Which incoming request spawned which outgoing peer RIDs
        # (parent (XID, RID) -> list of child peer RIDs) for cancel cascade.
        self.incoming_to_peer_rids: dict = {}
        self.incoming_to_peer_rids_touched: dict = {}
        # Max-seen seq per flow for cartridge-originated frames (FlowKey -> seq).
        self.outgoing_max_seq: dict = {}
        self.outgoing_max_seq_touched: dict = {}
        # Monotonic stamp source — a strict ordering, not wall-clock.
        self.routing_touch_seq: int = 0
        # Observability counters.
        self.routing_gc_runs_total: int = 0
        self.routing_gc_evicted_total: int = 0
        # Protocol v3 (L6): keys in ``incoming_rxids`` whose REQUEST BODY has
        # terminated (END/ERR delivered to the handler) while the entry
        # stays alive for the response phase. Data/terminal frames for a
        # body-done key are self-loop peer responses and route via
        # ``outgoing_rids``. Cleared with the entry.
        self.incoming_body_done: set = set()
        # Keys whose handler RESPONSE has terminated before the request
        # body END arrived (response-first race). When the body END then
        # arrives, the entry is released immediately. Cleared with the
        # entry.
        self.incoming_response_done: set = set()
        # Dropped-frame accounting (L8): unroutable continuations and
        # frames for dead cartridges are counted drops, never silent
        # losses.
        self.drops: DropCounters = DropCounters()
        # Inventory records this host does NOT manage as processes —
        # discovery outcomes like incompatible installs. Merged into every
        # capabilities advertisement so a host-originated RelayNotify can
        # never erase them from the engine's inventory. Mirrors the
        # reference ``static_inventory_records``.
        self.static_inventory_records: List[Any] = []

    def set_static_inventory_records(self, records: List[Any]) -> None:
        """Provide inventory records for cartridges this host does NOT
        manage as processes — discovery outcomes such as incompatible
        installs, carrying their ``attachment_error``. Mirrors the
        reference ``set_static_inventory_records``."""
        self.static_inventory_records = list(records)

    def protocol_stats(self) -> HostProtocolStats:
        """Protocol observability snapshot (L8): drop counters,
        routing-table sizes, and GC totals for this host. Mirrors the
        reference ``protocol_stats``."""
        return HostProtocolStats(
            drops=self.drops.snapshot(),
            outgoing_rids=len(self.outgoing_rids),
            incoming_rxids=len(self.incoming_rxids),
            incoming_to_peer_rids=len(self.incoming_to_peer_rids),
            outgoing_max_seq=len(self.outgoing_max_seq),
            routing_gc_runs_total=self.routing_gc_runs_total,
            routing_gc_evicted_total=self.routing_gc_evicted_total,
        )

    # --- touch helpers (called on insert and on every read that hits) ---

    def touch_incoming_rxid(self, key) -> None:
        self.routing_touch_seq += 1
        self.incoming_rxids_touched[key] = self.routing_touch_seq

    def touch_outgoing_rid(self, rid) -> None:
        self.routing_touch_seq += 1
        self.outgoing_rids_touched[rid] = self.routing_touch_seq

    def touch_incoming_to_peer_rids(self, key) -> None:
        self.routing_touch_seq += 1
        self.incoming_to_peer_rids_touched[key] = self.routing_touch_seq

    def touch_outgoing_max_seq(self, key) -> None:
        self.routing_touch_seq += 1
        self.outgoing_max_seq_touched[key] = self.routing_touch_seq

    # --- v3 continuation-frame routing (PATH C) + terminal drain ---
    #
    # These implement the reference ``handle_relay_frame`` PATH C route
    # selection and terminal bookkeeping, and the ``handle_cartridge_frame``
    # response-terminal bookkeeping, as pure operations on the routing
    # tables — the counterpart of the full frame-I/O loop this class does
    # not yet host (see the module note above).

    def route_continuation_frame(
        self,
        xid,
        rid,
        frame_type: FrameType,
        credit_direction: Optional[CreditDirection] = None,
    ):
        """Resolve the cartridge index a continuation frame
        (STREAM_START/CHUNK/STREAM_END/END/ERR/CREDIT) from the relay
        routes to, and apply the v3 terminal bookkeeping.

        Route selection:
        - CREDIT routes by its mandatory direction (L11): a ``response``
          grant credits the HANDLER's output → incoming side; a ``request``
          grant credits the REQUESTER's argument streams → outgoing side.
          The (xid, rid) key alone cannot disambiguate this for self-loop
          peer calls. A CREDIT frame with no direction is a counted
          ``no_route`` drop (v3 requires ``credit_dir``).
        - Data/terminal frames prefer the incoming side while the request
          body is still flowing; after body END they are self-loop peer
          responses and fall through to the outgoing side.

        On a terminal frame (END/ERR): if routed via ``incoming_rxids``, the
        entry STAYS (the handler's response is still flowing and its output
        CREDIT grants route through it) unless the response already
        terminated first (response-first race), in which case it is
        released immediately. If routed via ``outgoing_rids``, a peer
        response completed — clean up.

        Returns ``(cartridge_idx, routed_via_incoming)``, or ``None`` when
        there is no routing entry for this key (already cleaned up) or a
        CREDIT frame carries no direction — both are counted ``no_route``
        drops, never silent losses.

        Mirrors the reference PATH C in ``handle_relay_frame``.
        """
        key = (xid, rid)

        if frame_type == FrameType.CREDIT:
            if credit_direction == CreditDirection.RESPONSE:
                prefer_incoming = True
            elif credit_direction == CreditDirection.REQUEST:
                prefer_incoming = False
            else:
                self.drops.record(DropReason.NO_ROUTE)
                return None
        else:
            prefer_incoming = key not in self.incoming_body_done

        cartridge_idx = None
        routed_via_incoming = False
        if prefer_incoming and key in self.incoming_rxids:
            self.touch_incoming_rxid(key)
            cartridge_idx = self.incoming_rxids[key]
            routed_via_incoming = True
        elif rid in self.outgoing_rids:
            self.touch_outgoing_rid(rid)
            cartridge_idx = self.outgoing_rids[rid]
        elif key in self.incoming_rxids:
            # Fallback: no outgoing entry, so this cannot be a self-loop
            # peer response — route to the handler even post-body-END
            # (defensive; normal requests only ever see CREDIT here,
            # handled above).
            self.touch_incoming_rxid(key)
            cartridge_idx = self.incoming_rxids[key]
            routed_via_incoming = True

        if cartridge_idx is None:
            self.drops.record(DropReason.NO_ROUTE)
            return None

        is_terminal = frame_type in (FrameType.END, FrameType.ERR)
        if is_terminal:
            if routed_via_incoming:
                if key in self.incoming_response_done:
                    # Response already terminated (response-first race): the
                    # request is fully over — release.
                    self.incoming_response_done.discard(key)
                    self.incoming_rxids.pop(key, None)
                    self.incoming_rxids_touched.pop(key, None)
                else:
                    self.incoming_body_done.add(key)
            else:
                # Peer response completed — clean up outgoing_rids.
                self.outgoing_rids.pop(rid, None)
                self.outgoing_rids_touched.pop(rid, None)

        return (cartridge_idx, routed_via_incoming)

    def record_response_terminal(self, xid, rid) -> None:
        """Record that the handler's RESPONSE terminal (END/ERR) has passed
        outbound to the relay for request ``(xid, rid)``.

        The handler's RESPONSE terminal is the request's true end at this
        host (v3): once the body has completed too, release the incoming
        routing entry and its body-done marker. If the response terminates
        BEFORE the body END arrives (response-first race), remember it so
        the body END releases the entry immediately.

        Mirrors the reference response-terminal bookkeeping in
        ``handle_cartridge_frame``.
        """
        key = (xid, rid)
        if key in self.incoming_body_done:
            self.incoming_body_done.discard(key)
            self.incoming_rxids.pop(key, None)
            self.incoming_rxids_touched.pop(key, None)
        elif key in self.incoming_rxids:
            self.incoming_response_done.add(key)

    def remove_incoming_rxid(self, key) -> None:
        """Fully release an ``incoming_rxids`` entry and its v3 terminal
        markers (cartridge death / cancellation cleanup). Mirrors the
        reference cleanup sweep that clears ``incoming_body_done`` /
        ``incoming_response_done`` alongside ``incoming_rxids`` wherever the
        entry is removed."""
        self.incoming_rxids.pop(key, None)
        self.incoming_rxids_touched.pop(key, None)
        self.incoming_body_done.discard(key)
        self.incoming_response_done.discard(key)

    # --- garbage collector ---

    def gc_routing_tables_if_needed(self) -> None:
        """Run the GC on any table that has crossed its soft watermark.

        Each table is GC'd independently (their key sets don't overlap so
        there's no benefit to ganging them).
        """
        if len(self.incoming_rxids) >= self.ROUTING_TABLE_SOFT_WATERMARK:
            self._gc_routing_table(self.incoming_rxids, self.incoming_rxids_touched)
        if len(self.outgoing_rids) >= self.ROUTING_TABLE_SOFT_WATERMARK:
            self._gc_routing_table(self.outgoing_rids, self.outgoing_rids_touched)
        if len(self.incoming_to_peer_rids) >= self.ROUTING_TABLE_SOFT_WATERMARK:
            self._gc_routing_table(
                self.incoming_to_peer_rids, self.incoming_to_peer_rids_touched
            )
        if len(self.outgoing_max_seq) >= self.ROUTING_TABLE_SOFT_WATERMARK:
            self._gc_routing_table(self.outgoing_max_seq, self.outgoing_max_seq_touched)

    def _gc_routing_table(self, primary: dict, touched: dict) -> None:
        """Drop the oldest ``GC_EVICTION_FRACTION`` of ``primary`` (and its
        matching ``touched`` entries) by touch-sequence ascending.

        Keys missing from ``touched`` are treated as oldest (sequence 0) —
        evicting them is safer than letting them linger.
        """
        before_count = len(primary)
        evict_count = max(
            1, int(before_count * self.ROUTING_TABLE_GC_EVICTION_FRACTION)
        )

        # Pick the oldest N by touched-at (ascending).
        candidates = sorted(
            primary.keys(), key=lambda k: touched.get(k, 0)
        )
        for key in candidates[:evict_count]:
            primary.pop(key, None)
            touched.pop(key, None)

        self.routing_gc_runs_total += 1
        self.routing_gc_evicted_total += evict_count

        # Secondary "hard cap" pass: if still at or above the hard cap
        # (extreme runaway), evict more aggressively until back under the
        # soft watermark. Bounded loop — a couple of iterations at most.
        while len(primary) >= self.ROUTING_TABLE_HARD_CAP:
            extra_evict = max(
                1, len(primary) - self.ROUTING_TABLE_SOFT_WATERMARK
            )
            extras = sorted(primary.keys(), key=lambda k: touched.get(k, 0))
            for key in extras[:extra_evict]:
                primary.pop(key, None)
                touched.pop(key, None)
            self.routing_gc_evicted_total += extra_evict


