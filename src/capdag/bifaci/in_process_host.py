"""In-Process Cartridge Host — Direct dispatch to FrameHandler objects.

Sits where the cartridge host runtime sits (connected to a RelaySlave via a
local socket pair), but routes requests to in-process ``FrameHandler`` objects
instead of cartridge binaries.

Architecture::

    RelaySlave <-> InProcessCartridgeHost <-> Handler A (streaming frames)
                                         <-> Handler B (streaming frames)
                                         <-> Handler C (streaming frames)

The host does NOT accumulate data. On REQ, it spawns a handler (a thread) with
queues for frame I/O. All continuation frames (STREAM_START, CHUNK, STREAM_END,
END) are forwarded to the handler. The handler processes frames natively —
streaming or accumulating as it sees fit.

This is a faithful port of Rust ``bifaci::in_process_host``. The Python mirror
uses threads + blocking ``FrameReader``/``FrameWriter`` to match the existing
synchronous cartridge-host style, rather than tokio tasks.
"""

import json
import queue
import threading
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

import cbor2

from capdag.bifaci.frame import (
    Frame,
    FrameType,
    FlowKey,
    Limits,
    MessageId,
    SeqAssigner,
    compute_checksum,
    DEFAULT_MAX_CHUNK,
    DEFAULT_MAX_FRAME,
)
from capdag.bifaci.io import FrameReader, FrameWriter, identity_nonce
from capdag.bifaci.cartridge_repo import CartridgeChannel
from capdag.cap.caller import CapArgumentValue
from capdag.cap.definition import Cap
from capdag.urn.cap_urn import CapUrn, CapUrnError
from capdag.standard.caps import CAP_IDENTITY, identity_cap


# =============================================================================
# FRAME HANDLER
# =============================================================================


class FrameHandler(ABC):
    """Handler for streaming frame-based requests.

    Handlers receive input frames (STREAM_START, CHUNK, STREAM_END, END) via a
    queue and send response frames via a ResponseWriter. The host never
    accumulates — handlers decide how to process input (stream or accumulate).
    """

    @abstractmethod
    def handle_request(
        self,
        cap_urn: str,
        input_q: "queue.Queue",
        output: "ResponseWriter",
        peer: "PeerInvoker",
    ) -> None:
        """Handle a streaming request.

        The REQ frame has already been consumed by the host. ``input_q`` yields:
        STREAM_START, CHUNK, STREAM_END (per argument stream), then END, then a
        sentinel ``None``. The handler MUST send a complete response: either
        response frames (STREAM_START + CHUNK(s) + STREAM_END + END) or an error
        (via ``output.emit_error()``).
        """
        ...


# =============================================================================
# RESPONSE WRITER
# =============================================================================


class ResponseWriter:
    """Wraps an output queue with automatic request_id and routing_id stamping.

    All frames sent via ResponseWriter get the correct request_id and routing_id
    for relay routing. Seq is left at 0 — the wire writer's SeqAssigner handles it.
    """

    def __init__(
        self,
        request_id: MessageId,
        routing_id: Optional[MessageId],
        tx: "queue.Queue",
        max_chunk: int,
    ) -> None:
        self._request_id = request_id
        self._routing_id = routing_id
        self._tx = tx
        self._max_chunk = max_chunk

    def send(self, frame: Frame) -> None:
        """Send a frame, stamping it with the request_id and routing_id."""
        frame.id = self._request_id
        frame.routing_id = self._routing_id
        frame.seq = 0  # SeqAssigner handles this
        self._tx.put(frame)

    @property
    def max_chunk(self) -> int:
        return self._max_chunk

    def emit_response(self, media_urn: str, data: bytes) -> None:
        """Send a complete data response: STREAM_START + CBOR-encoded CHUNK(s) +
        STREAM_END + END."""
        stream_id = "result"
        self.send(Frame.stream_start(MessageId(0), stream_id, media_urn))

        if not data:
            cbor_payload = cbor2.dumps(b"")
            self.send(
                Frame.chunk(
                    MessageId(0), stream_id, 0, cbor_payload, 0, compute_checksum(cbor_payload)
                )
            )
            self.send(Frame.stream_end(MessageId(0), stream_id, 1))
        else:
            chunks = [
                data[i : i + self._max_chunk]
                for i in range(0, len(data), self._max_chunk)
            ]
            for i, chunk_data in enumerate(chunks):
                cbor_payload = cbor2.dumps(chunk_data)
                self.send(
                    Frame.chunk(
                        MessageId(0),
                        stream_id,
                        0,
                        cbor_payload,
                        i,
                        compute_checksum(cbor_payload),
                    )
                )
            self.send(Frame.stream_end(MessageId(0), stream_id, len(chunks)))

        self.send(Frame.end_ok(MessageId(0), None))

    def emit_error(self, code: str, message: str) -> None:
        """Send an error response."""
        self.send(Frame.err(MessageId(0), code, message))


# =============================================================================
# PEER INVOCATION FOR IN-PROCESS HANDLERS
# =============================================================================


class PeerInvoker(ABC):
    """Allows in-process handlers to invoke other caps via the host."""

    @abstractmethod
    def call(self, cap_urn: str) -> "queue.Queue":
        """Invoke a cap on the host; returns a queue of response frames."""
        ...


class _PendingPeerRequest:
    def __init__(self, sender: "queue.Queue", origin_request_id: MessageId) -> None:
        self.sender = sender
        self.origin_request_id = origin_request_id


class InProcessPeerInvoker(PeerInvoker):
    """PeerInvoker implementation for in-process handlers.

    Sends REQ frames through the host's write queue (same queue used for
    handler responses). The host's main read loop routes response frames back
    to this call's receiver via the pending_requests map.
    """

    def __init__(
        self,
        write_tx: "queue.Queue",
        pending_requests: Dict[MessageId, _PendingPeerRequest],
        pending_lock: threading.Lock,
        origin_request_id: MessageId,
        max_chunk: int,
    ) -> None:
        self._write_tx = write_tx
        self._pending = pending_requests
        self._pending_lock = pending_lock
        self._origin_request_id = origin_request_id
        self._max_chunk = max_chunk

    def call(self, cap_urn: str) -> "queue.Queue":
        request_id = MessageId.new_uuid()
        receiver: "queue.Queue" = queue.Queue()

        with self._pending_lock:
            self._pending[request_id] = _PendingPeerRequest(
                receiver, self._origin_request_id
            )

        req_frame = Frame.req(request_id, cap_urn, b"", "application/cbor")
        meta = dict(req_frame.meta or {})
        meta["parent_rid"] = self._origin_request_id.to_cbor()
        req_frame.meta = meta
        self._write_tx.put(req_frame)
        return receiver


# =============================================================================
# INPUT ACCUMULATION UTILITY
# =============================================================================


def accumulate_input(input_q: "queue.Queue") -> Tuple[List[CapArgumentValue], Optional[dict]]:
    """Accumulate all input streams from a frame queue into CapArgumentValues.

    Reads frames until END. CBOR-decodes chunk payloads to extract raw bytes.
    Returns ``(args, meta)`` where ``meta`` is the stream metadata from the
    first input stream's STREAM_START frame. Raises ValueError on CBOR decode
    failure (protocol violation).
    """
    streams: List[Tuple[str, str, bytearray]] = []  # (stream_id, media_urn, data)
    active: Dict[str, int] = {}
    request_meta: Optional[dict] = None

    while True:
        frame = input_q.get()
        if frame is None:
            break
        ft = frame.frame_type
        if ft == FrameType.STREAM_START:
            sid = frame.stream_id or ""
            media_urn = frame.media_urn or ""
            if request_meta is None:
                request_meta = frame.meta
            idx = len(streams)
            streams.append((sid, media_urn, bytearray()))
            active[sid] = idx
        elif ft == FrameType.CHUNK:
            sid = frame.stream_id or ""
            if sid in active:
                idx = active[sid]
                if frame.payload is not None:
                    try:
                        value = cbor2.loads(frame.payload)
                    except Exception as e:
                        raise ValueError(
                            f"chunk payload is not valid CBOR (stream={sid}, "
                            f"{len(frame.payload)} bytes): {e}"
                        )
                    if isinstance(value, bytes):
                        streams[idx][2].extend(value)
                    elif isinstance(value, str):
                        streams[idx][2].extend(value.encode("utf-8"))
                    else:
                        raise ValueError(
                            f"unexpected CBOR type in chunk payload: {type(value)}"
                        )
        elif ft == FrameType.STREAM_END:
            pass
        elif ft == FrameType.END:
            break
        # ignore other frame types

    args = [
        CapArgumentValue(media_urn=media_urn, value=bytes(data))
        for (_, media_urn, data) in streams
    ]
    return args, request_meta


# =============================================================================
# BUILT-IN IDENTITY HANDLER
# =============================================================================


class IdentityHandler(FrameHandler):
    """Identity handler: raw byte passthrough (no CBOR decode/encode).

    Echoes all accumulated chunk payloads back as-is. This is the protocol-level
    identity verification — it proves the transport works end-to-end.
    """

    def handle_request(self, cap_urn, input_q, output, peer):
        data = bytearray()
        while True:
            frame = input_q.get()
            if frame is None:
                break
            if frame.frame_type == FrameType.CHUNK:
                if frame.payload is not None:
                    data.extend(frame.payload)
            elif frame.frame_type == FrameType.END:
                break
            # STREAM_START, STREAM_END — skip

        # Echo back as a single stream (raw bytes, no CBOR encode)
        stream_id = "identity"
        output.send(Frame.stream_start(MessageId(0), stream_id, "media:"))
        payload = bytes(data)
        output.send(
            Frame.chunk(MessageId(0), stream_id, 0, payload, 0, compute_checksum(payload))
        )
        output.send(Frame.stream_end(MessageId(0), stream_id, 1))
        output.send(Frame.end_ok(MessageId(0), None))


# =============================================================================
# IN-PROCESS CARTRIDGE HOST
# =============================================================================


class _HandlerEntry:
    def __init__(self, name: str, caps: List[Cap], handler: FrameHandler) -> None:
        self.name = name
        self.caps = caps
        self.handler = handler


class InProcessHostIdentity:
    """Identity values an ``InProcessCartridgeHost`` advertises in its
    RelayNotify payload.

    The host has no on-disk cartridge directory, so the embedding application
    must supply the same four-tuple identity (``registry_url``, ``channel``,
    ``id``, ``version``) it would have read from a cartridge.json — plus a
    content-derived ``sha256`` so the engine treats the in-process provider
    indistinguishably from any other installed cartridge.
    """

    def __init__(
        self,
        registry_url: Optional[str],
        channel: CartridgeChannel,
        id: str,
        version: str,
        sha256: str,
    ) -> None:
        self.registry_url = registry_url
        self.channel = channel
        self.id = id
        self.version = version
        self.sha256 = sha256

    @classmethod
    def for_test(cls, id: str) -> "InProcessHostIdentity":
        """Identity values for unit/integration tests. Carries a fixed-bytes
        sha256 so the engine's non-empty-hash assertion passes; channel and
        version are stable test defaults."""
        return cls(
            registry_url=None,
            channel=CartridgeChannel.RELEASE,
            id=id,
            version="0.0.0-test",
            sha256="0" * 64,
        )


# Cap table entry: (cap_urn_string, handler_index).
CapTable = List[Tuple[str, int]]


class InProcessCartridgeHost:
    """A cartridge host that dispatches to in-process FrameHandler objects.

    Speaks the Frame protocol to a RelaySlave, but routes requests to
    ``FrameHandler`` objects via frame queues — no accumulation at the host
    level, handlers own the streaming.
    """

    def __init__(
        self,
        identity: InProcessHostIdentity,
        handlers: List[Tuple[str, List[Cap], FrameHandler]],
    ) -> None:
        self.identity = identity
        self.handlers = [
            _HandlerEntry(name, caps, handler) for (name, caps, handler) in handlers
        ]

    def build_manifest(self) -> bytes:
        """Build the aggregate RelayNotify manifest payload.

        Assembles one installed-cartridge entry from the host's identity and
        puts every handler-contributed cap into its lone cap group. The wire
        format is symmetric with out-of-process hosts.
        """
        # Collect all handler caps; prepend CAP_IDENTITY exactly once.
        caps: List[Cap] = [identity_cap()]
        for entry in self.handlers:
            for cap in entry.caps:
                if cap.urn.to_string() != CAP_IDENTITY:
                    caps.append(cap)

        cartridge = {
            "registry_url": self.identity.registry_url,
            "id": self.identity.id,
            "channel": self.identity.channel.value
            if hasattr(self.identity.channel, "value")
            else str(self.identity.channel),
            "version": self.identity.version,
            "sha256": self.identity.sha256,
            "cap_groups": [
                {
                    "name": self.identity.id,
                    "caps": [cap.to_dict() for cap in caps],
                    "adapter_urns": [],
                }
            ],
            "attachment_error": None,
            "runtime_stats": None,
            "lifecycle": "operational",
        }
        payload = {"installed_cartridges": [cartridge]}
        return json.dumps(payload).encode("utf-8")

    @staticmethod
    def build_cap_table(handlers: List[_HandlerEntry]) -> CapTable:
        """Build the cap table for routing: flat list of (cap_urn, handler_idx)."""
        table: CapTable = []
        for idx, entry in enumerate(handlers):
            for cap in entry.caps:
                table.append((cap.urn.to_string(), idx))
        return table

    @staticmethod
    def find_handler_for_cap(cap_table: CapTable, cap_urn: str) -> Optional[int]:
        """Find the best handler for a cap URN.

        Uses ``is_dispatchable(provider, request)`` to find handlers that can
        legally handle the request, then ranks by specificity: equivalent
        matches (distance 0) first, then more specific providers (positive
        distance), then more generic ones (negative distance).
        """
        try:
            request_urn = CapUrn.from_string(cap_urn)
        except (CapUrnError, ValueError):
            return None

        request_specificity = request_urn.specificity()
        matches: List[Tuple[int, int]] = []  # (handler_idx, signed_distance)

        for registered_cap, handler_idx in cap_table:
            try:
                registered_urn = CapUrn.from_string(registered_cap)
            except (CapUrnError, ValueError):
                continue
            if registered_urn.is_dispatchable(request_urn):
                specificity = registered_urn.specificity()
                signed_distance = specificity - request_specificity
                matches.append((handler_idx, signed_distance))

        if not matches:
            return None

        # Ranking: non-negative distances before negative; within same sign,
        # prefer smaller absolute distance.
        def sort_key(m: Tuple[int, int]):
            _, dist = m
            return (0 if dist >= 0 else 1, abs(dist))

        matches.sort(key=sort_key)
        return matches[0][0]

    def run(self, local_read, local_write) -> None:
        """Run the host. Returns when the local connection closes.

        ``local_read`` / ``local_write`` connect to the RelaySlave's local side.
        """
        reader = FrameReader(local_read)

        # Writer runs in a separate thread with a SeqAssigner.
        write_tx: "queue.Queue" = queue.Queue()

        def writer_loop():
            writer = FrameWriter(local_write)
            seq_assigner = SeqAssigner()
            while True:
                frame = write_tx.get()
                if frame is None:
                    break
                seq_assigner.assign(frame)
                try:
                    writer.write(frame)
                except Exception:
                    break
                if frame.frame_type in (FrameType.END, FrameType.ERR):
                    seq_assigner.remove(FlowKey.from_frame(frame))

        writer_thread = threading.Thread(target=writer_loop, daemon=True)
        writer_thread.start()

        # Send initial RelayNotify with aggregate caps.
        manifest = self.build_manifest()
        limits = Limits(DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK)
        write_tx.put(
            Frame.relay_notify(manifest, limits.max_frame, limits.max_chunk)
        )

        cap_table = self.build_cap_table(self.handlers)

        # request_id -> input queue for forwarding frames to handler.
        active: Dict[MessageId, "queue.Queue"] = {}
        handler_threads: Dict[MessageId, threading.Thread] = {}

        # peer_rid -> pending peer request (shared with InProcessPeerInvoker).
        pending_peer_requests: Dict[MessageId, _PendingPeerRequest] = {}
        pending_lock = threading.Lock()

        identity_handler: FrameHandler = IdentityHandler()
        max_chunk = limits.max_chunk

        try:
            while True:
                frame = reader.read()
                if frame is None:
                    break

                ft = frame.frame_type

                if ft == FrameType.REQ:
                    rid = frame.id
                    xid = frame.routing_id
                    cap_urn = frame.cap
                    if cap_urn is None:
                        err = Frame.err(rid, "PROTOCOL_ERROR", "REQ missing cap URN")
                        err.routing_id = xid
                        write_tx.put(err)
                        continue

                    is_identity = cap_urn == CAP_IDENTITY
                    if is_identity:
                        handler = identity_handler
                    else:
                        idx = self.find_handler_for_cap(cap_table, cap_urn)
                        if idx is None:
                            err = Frame.err(
                                rid, "NO_HANDLER", f"no handler for cap: {cap_urn}"
                            )
                            err.routing_id = xid
                            write_tx.put(err)
                            continue
                        handler = self.handlers[idx].handler

                    input_q: "queue.Queue" = queue.Queue()
                    active[rid] = input_q

                    peer = InProcessPeerInvoker(
                        write_tx, pending_peer_requests, pending_lock, rid, max_chunk
                    )
                    output = ResponseWriter(rid, xid, write_tx, max_chunk)

                    def run_handler(h=handler, c=cap_urn, iq=input_q, o=output, p=peer):
                        h.handle_request(c, iq, o, p)

                    t = threading.Thread(target=run_handler, daemon=True)
                    handler_threads[rid] = t
                    t.start()

                elif ft in (
                    FrameType.STREAM_START,
                    FrameType.CHUNK,
                    FrameType.STREAM_END,
                    FrameType.LOG,
                ):
                    if frame.id in active:
                        active[frame.id].put(frame)
                        continue
                    with pending_lock:
                        pr = pending_peer_requests.get(frame.id)
                    if pr is not None:
                        pr.sender.put(frame)

                elif ft == FrameType.END:
                    if frame.id in active:
                        rid = frame.id
                        active[rid].put(frame)
                        active[rid].put(None)  # sentinel: no more input
                        del active[rid]
                        handler_threads.pop(rid, None)
                        continue
                    with pending_lock:
                        pr = pending_peer_requests.pop(frame.id, None)
                    if pr is not None:
                        pr.sender.put(frame)

                elif ft == FrameType.ERR:
                    if frame.id in active:
                        rid = frame.id
                        active[rid].put(frame)
                        active[rid].put(None)
                        del active[rid]
                        handler_threads.pop(rid, None)
                        continue
                    with pending_lock:
                        pr = pending_peer_requests.pop(frame.id, None)
                    if pr is not None:
                        pr.sender.put(frame)

                elif ft == FrameType.CANCEL:
                    target_rid = frame.id
                    xid = frame.routing_id
                    force_kill = bool(frame.force_kill)

                    if target_rid in active:
                        # Signal handler input is done.
                        active[target_rid].put(None)
                        del active[target_rid]
                    handler_threads.pop(target_rid, None)

                    with pending_lock:
                        to_cancel = [
                            rid
                            for rid, pr in pending_peer_requests.items()
                            if pr.origin_request_id == target_rid
                        ]
                        for peer_rid in to_cancel:
                            del pending_peer_requests[peer_rid]
                            write_tx.put(Frame.cancel(peer_rid, force_kill))

                    err = Frame.err(target_rid, "CANCELLED", "Request cancelled")
                    err.routing_id = xid
                    write_tx.put(err)

                elif ft == FrameType.HEARTBEAT:
                    write_tx.put(Frame.heartbeat(frame.id))

                # else: RelayNotify, RelayState, etc. — not expected from relay side
        finally:
            # Drop all active channels to signal handlers to exit.
            for q in active.values():
                q.put(None)
            active.clear()
            # Stop writer thread.
            write_tx.put(None)
            writer_thread.join(timeout=2)
