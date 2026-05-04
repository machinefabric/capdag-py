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
host.register_cartridge("/path/to/cartridge", ["cap:op=convert"])
host.run(relay_reader, relay_writer, resource_fn=lambda: b"")
```
"""

import json
import subprocess
import threading
import queue
from typing import Any, Optional, List, Callable
from dataclasses import dataclass

from capdag.bifaci.frame import Frame, FrameType, Limits
from capdag.bifaci.io import (
    FrameReader,
    FrameWriter,
    handshake,
    verify_identity,
    CborError,
)
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


class _ManagedCartridge:
    """A cartridge managed by the CartridgeHost."""

    def __init__(self, path: str = "", known_caps: Optional[List[str]] = None):
        self.path = path
        self.process: Optional[subprocess.Popen] = None
        self.writer: Optional[FrameWriter] = None
        self.writer_queue: Optional[queue.Queue] = None
        self.manifest: bytes = b""
        self.limits: Limits = Limits.default()
        # Flat cap-urn list (derived from cap_groups; kept alongside it
        # so cap-table rebuilds don't have to walk groups every time).
        self.caps: List[str] = []
        # Cartridge's manifest cap_groups, parsed at HELLO time. The
        # source of truth on the wire; the engine reads
        # `installed_cartridges[*].cap_groups` and derives the flat list.
        self.cap_groups: List[Any] = []
        self.known_caps: List[str] = known_caps or []
        self.running: bool = False
        self.hello_failed: bool = False


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

    def register_cartridge(self, path: str, known_caps: List[str]) -> None:
        """Register a cartridge binary for on-demand spawning.

        The cartridge is not spawned until a REQ arrives for one of its known caps.

        Args:
            path: Path to the cartridge binary
            known_caps: List of cap URNs this cartridge is expected to handle
        """
        with self._lock:
            cartridge_idx = len(self._cartridges)
            self._cartridges.append(_ManagedCartridge(path=path, known_caps=known_caps))

            for cap in known_caps:
                self._cap_table.append(_CapTableEntry(cap_urn=cap, cartridge_idx=cartridge_idx))

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
        caps = _flatten_cap_urns(cap_groups)

        with self._lock:
            cartridge_idx = len(self._cartridges)

            writer_q = queue.Queue(maxsize=64)
            cartridge = _ManagedCartridge()
            cartridge.writer = writer
            cartridge.writer_queue = writer_q
            cartridge.manifest = result.manifest
            cartridge.limits = result.limits
            cartridge.cap_groups = cap_groups
            cartridge.caps = caps
            cartridge.running = True

            self._cartridges.append(cartridge)

            for cap in caps:
                self._cap_table.append(_CapTableEntry(cap_urn=cap, cartridge_idx=cartridge_idx))
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

        while True:
            # Check relay done
            if relay_done.is_set() and relay_queue.empty():
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
                    err_frame = Frame.err(frame.id, "NO_HANDLER", f"no cartridge handles cap: {cap_urn}")
                    relay_writer.write(err_frame)
                    return

                cartridge = self._cartridges[cartridge_idx]
                if not cartridge.running:
                    if cartridge.hello_failed:
                        err_frame = Frame.err(frame.id, "SPAWN_FAILED", "cartridge previously failed to start")
                        relay_writer.write(err_frame)
                        return
                    err = self._spawn_cartridge_locked(cartridge_idx)
                    if err is not None:
                        err_frame = Frame.err(frame.id, "SPAWN_FAILED", str(err))
                        relay_writer.write(err_frame)
                        return

                self._request_routing[id_key] = _RoutingEntry(cartridge_idx=cartridge_idx, msg_id=frame.id)
                self._send_to_cartridge(cartridge_idx, frame)

            elif frame.frame_type in (FrameType.STREAM_START, FrameType.CHUNK, FrameType.STREAM_END):
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
                # Respond to cartridge heartbeat locally — don't forward
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

            elif frame.frame_type in (FrameType.STREAM_START, FrameType.CHUNK, FrameType.STREAM_END):
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
                err_frame = Frame.err(
                    failed_entries[i].msg_id,
                    "CARTRIDGE_DIED",
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
            return f"failed to start cartridge: {e}"

        cartridge.process = proc

        reader = FrameReader(proc.stdout)
        writer = FrameWriter(proc.stdin)

        try:
            result = handshake(reader, writer)
            verify_identity(reader, writer)
        except Exception as e:
            cartridge.hello_failed = True
            try:
                proc.kill()
            except Exception:
                pass
            return f"handshake failed: {e}"

        try:
            cap_groups = _parse_cap_groups_from_manifest(result.manifest)
        except Exception as e:
            cartridge.hello_failed = True
            try:
                proc.kill()
            except Exception:
                pass
            return f"failed to parse manifest: {e}"

        cartridge.manifest = result.manifest
        cartridge.limits = result.limits
        cartridge.cap_groups = cap_groups
        cartridge.caps = _flatten_cap_urns(cap_groups)
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
        """Rebuild the cap table from all cartridges."""
        self._cap_table = []
        for idx, cartridge in enumerate(self._cartridges):
            if cartridge.hello_failed:
                continue
            caps = cartridge.known_caps
            if cartridge.running and len(cartridge.caps) > 0:
                caps = cartridge.caps
            for cap in caps:
                self._cap_table.append(_CapTableEntry(cap_urn=cap, cartridge_idx=idx))

    def _rebuild_capabilities(self) -> None:
        """Rebuild the aggregate capabilities JSON.

        The wire payload now lives entirely inside
        ``installed_cartridges[*].cap_groups``. The Python host
        synthesises one ``installed_cartridges`` entry per running
        cartridge, attaching the parsed ``cap_groups`` so the engine
        can register adapter URNs.
        """
        installed: List[dict] = []
        for idx, cartridge in enumerate(self._cartridges):
            if cartridge.hello_failed or not cartridge.running:
                continue
            installed.append({
                "registry_url": None,
                "channel": "release",
                "id": f"cartridge-{idx}",
                "version": "0.0.0",
                "sha256": "",
                "cap_groups": cartridge.cap_groups,
            })

        if not installed:
            self._capabilities = None
            return

        self._capabilities = json.dumps({"installed_cartridges": installed}).encode("utf-8")

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


# =========================================================================
# Helpers
# =========================================================================

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


def _flatten_cap_urns(cap_groups: List[Any]) -> List[str]:
    """Walk a list of cap_groups dicts and return the flat list of cap
    URN strings, preserving order.
    """
    caps: List[str] = []
    for group in cap_groups:
        for cap in group.get("caps", []):
            urn = cap.get("urn", "")
            if urn:
                caps.append(urn)
    return caps


