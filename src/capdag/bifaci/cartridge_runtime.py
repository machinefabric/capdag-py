"""Cartridge Runtime - Unified I/O handling for cartridge binaries

The CartridgeRuntime provides a unified interface for cartridge binaries to handle
cap invocations. Cartridges register handlers for caps they provide, and the
runtime handles all I/O mechanics:

- **Automatic mode detection**: CLI mode vs Cartridge CBOR mode
- CBOR frame encoding/decoding (Cartridge mode)
- CLI argument parsing from cap definitions (CLI mode)
- Handler routing by cap URN
- Real-time streaming response support
- HELLO handshake for limit negotiation
- **Multiplexed concurrent request handling**

# Invocation Modes

- **No CLI arguments**: Cartridge CBOR mode - HELLO handshake, REQ/RES frames via stdin/stdout
- **Any CLI arguments**: CLI mode - parse args based on cap definitions

# Example

```python
from capdag import CartridgeRuntime, CapManifest

def main():
    manifest = build_manifest()  # Your manifest with caps
    runtime = CartridgeRuntime.with_manifest(manifest)

    def my_handler(request, emitter, peer):
        emitter.emit_status("processing", "Starting work...")
        # Do work, emit chunks in real-time
        emitter.emit_bytes(b"partial result")
        # Return final result
        return b"final result"

    runtime.register_raw("cap:in=*;my-op;out=*", my_handler)

    # runtime.run() automatically detects CLI vs Cartridge CBOR mode
    runtime.run()
```
"""

import sys
import os
import json
import io
import asyncio
import threading
import queue
import glob
from pathlib import Path
from typing import Callable, Protocol, Optional, Dict, List, Any, Tuple
from abc import ABC, abstractmethod
from dataclasses import dataclass
import cbor2

from ops import Op, OpMetadata, DryContext, WetContext, ExecutionFailedError

from capdag.bifaci.frame import Frame, FrameType, Limits, MessageId, DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK, compute_checksum, verify_chunk_checksum, SeqAssigner, FlowKey
from capdag.bifaci.io import handshake_accept, FrameReader, FrameWriter, CborError, ProtocolError
from capdag.cap.caller import CapArgumentValue
from capdag.cap.definition import ArgSource, Cap, CapArg, CliFlagSource
from capdag.urn.cap_urn import CapUrn
from capdag.bifaci.manifest import CapManifest
from capdag.urn.media_urn import MediaUrn, MediaUrnError, MEDIA_FILE_PATH


class RuntimeError(Exception):
    """Errors that can occur in the cartridge runtime"""
    pass


class CborRuntimeError(RuntimeError):
    """CBOR error"""
    pass


class IoRuntimeError(RuntimeError):
    """I/O error"""
    pass


class NoHandlerError(RuntimeError):
    """No handler registered for cap"""
    pass


class HandlerError(RuntimeError):
    """Handler error"""
    pass


class CapUrnError(RuntimeError):
    """Cap URN parse error"""
    pass


class DeserializeError(RuntimeError):
    """Deserialization error"""
    pass


class SerializeError(RuntimeError):
    """Serialization error"""
    pass


class PeerRequestError(RuntimeError):
    """Peer request error"""
    pass


class PeerResponseError(RuntimeError):
    """Peer response error"""
    pass


class CliError(RuntimeError):
    """CLI error"""
    pass


class MissingArgumentError(RuntimeError):
    """Missing required argument"""
    pass


class UnknownSubcommandError(RuntimeError):
    """Unknown subcommand"""
    pass


class ManifestError(RuntimeError):
    """Manifest error"""
    pass


class SyncFrameWriter:
    """Thread-safe frame writer with centralized SeqAssigner.

    All frames pass through the SeqAssigner before writing, ensuring
    monotonically increasing seq per flow (RID + optional XID).
    This matches the Rust cartridge_runtime writer thread with SeqAssigner
    and Go's syncFrameWriter.
    """

    def __init__(self, writer: FrameWriter):
        self._writer = writer
        self._lock = threading.Lock()
        self._seq_assigner = SeqAssigner()

    def write(self, frame: Frame) -> None:
        """Write a frame with centralized seq assignment (thread-safe)."""
        with self._lock:
            self._seq_assigner.assign(frame)
            self._writer.write(frame)
            # Clean up flow tracking after terminal frames
            if frame.frame_type in (FrameType.END, FrameType.ERR):
                key = FlowKey.from_frame(frame)
                self._seq_assigner.remove(key)

    def set_limits(self, limits: Limits) -> None:
        with self._lock:
            self._writer.set_limits(limits)


class StreamEmitter(Protocol):
    """A streaming emitter that writes chunks immediately to the output.
    Thread-safe for use in concurrent handlers.
    Handlers emit CBOR values via emit_cbor() or logs via emit_log().
    The value is CBOR-encoded once and sent as raw CBOR bytes in CHUNK frames.
    No double-encoding: one CBOR layer from handler to consumer.
    """

    def emit_cbor(self, value: Any) -> None:
        """Emit a CBOR value as output.
        The value is CBOR-encoded once and sent as raw CBOR bytes in CHUNK frames.
        Raises: RuntimeError on write failure."""
        ...

    def write(self, data: bytes) -> None:
        """Write raw bytes as output, split into max_chunk-sized CHUNK frames.
        Unlike emit_cbor which CBOR-encodes the value, this sends raw bytes directly."""
        ...

    def emit_list_item(self, value: Any) -> None:
        """Emit a single CBOR value as one item in an RFC 8742 CBOR sequence.
        For list outputs: CBOR-encodes the value, then splits across chunk frames.
        The receiver concatenates raw payloads to reconstruct the CBOR sequence."""
        ...

    def emit_log(self, level: str, message: str) -> None:
        """Emit a log message at the given level.
        Sends a LOG frame (side-channel, does not affect response stream)."""
        ...

    def progress(self, progress: float, message: str) -> None:
        """Emit a progress update (0.0-1.0) with a human-readable status message."""
        ...


class PeerInvoker(Protocol):
    """Allows handlers to invoke caps on the peer (host).

    Sends REQ + streaming argument frames to the host. The main reader loop
    (running in a separate thread) receives response frames and forwards them
    to a queue. Returns a queue that yields bare CBOR Frame objects (STREAM_START,
    CHUNK, STREAM_END, END, ERR) as they arrive from the host. The consumer
    processes frames directly - no decoding, no wrapper types.
    """

    def invoke(self, cap_urn: str, arguments: List[CapArgumentValue]) -> queue.Queue:
        """Invoke a cap on the host with arguments.

        Returns a queue that receives bare Frame objects.
        """
        ...


class NoPeerInvoker:
    """A no-op PeerInvoker that always returns an error.
    Used when peer invocation is not supported (CLI mode only).
    """

    def invoke(self, cap_urn: str, arguments: List[CapArgumentValue]) -> queue.Queue:
        raise PeerRequestError("Peer invocation not supported in this context")


class PeerResponseItem:
    """A single item from a peer response — either decoded data or a LOG frame.

    PeerResponse.recv() yields these interleaved in arrival order. Handlers
    match on each variant to decide how to react (e.g., forward progress, accumulate data).
    """

    def __init__(self, *, data=None, log=None):
        if data is not None and log is not None:
            raise ValueError("PeerResponseItem must be either Data or Log, not both")
        if data is None and log is None:
            raise ValueError("PeerResponseItem must be either Data or Log")
        self._data = data
        self._log = log

    @staticmethod
    def data_ok(value) -> "PeerResponseItem":
        """Create a Data item with a decoded CBOR value."""
        return PeerResponseItem(data=("ok", value))

    @staticmethod
    def data_err(error: Exception) -> "PeerResponseItem":
        """Create a Data item with an error."""
        return PeerResponseItem(data=("err", error))

    @staticmethod
    def log_frame(frame: Frame) -> "PeerResponseItem":
        """Create a Log item with a LOG frame."""
        return PeerResponseItem(log=frame)

    @property
    def is_data(self) -> bool:
        return self._data is not None

    @property
    def is_log(self) -> bool:
        return self._log is not None

    @property
    def data_value(self):
        """Get the decoded data value. Raises if this is an error or LOG item."""
        if self._data is None:
            raise ValueError("Not a Data item")
        kind, val = self._data
        if kind == "err":
            raise val
        return val

    @property
    def data_error(self) -> Optional[Exception]:
        """Get the error if this is a Data(Err) item, None otherwise."""
        if self._data is None:
            return None
        kind, val = self._data
        return val if kind == "err" else None

    @property
    def log(self) -> Optional[Frame]:
        """Get the LOG frame if this is a Log item, None otherwise."""
        return self._log


class PeerResponse:
    """Response from a peer call — yields both data items and LOG frames from a single queue.

    The handler drains this with recv() and reacts to each PeerResponseItem as it arrives.
    LOG frames are delivered in real-time as they arrive (not buffered until data starts).
    For callers that don't care about LOG frames, collect_bytes() and collect_value()
    silently discard them and return only data.
    """

    def __init__(self, q: queue.Queue):
        self._queue = q

    def recv(self) -> Optional[PeerResponseItem]:
        """Receive the next item (data or LOG) from the peer response.
        Returns None when the stream ends."""
        item = self._queue.get()
        if item is None:
            return None
        return item

    def collect_bytes(self) -> bytes:
        """Collect all data chunks into a single byte vector, discarding LOG frames.

        WARNING: Only call this if you know the stream is finite.
        """
        result = bytearray()
        while True:
            item = self.recv()
            if item is None:
                break
            if item.is_log:
                continue  # Discard LOG frames
            err = item.data_error
            if err is not None:
                raise err
            value = item.data_value
            if isinstance(value, bytes):
                result.extend(value)
            elif isinstance(value, str):
                result.extend(value.encode("utf-8"))
            else:
                # CBOR-encode non-bytes/str values
                result.extend(cbor2.dumps(value))
        return bytes(result)

    def collect_value(self):
        """Collect a single CBOR data value (expects exactly one data chunk), discarding LOG frames."""
        while True:
            item = self.recv()
            if item is None:
                raise PeerResponseError("Peer response ended without data")
            if item.is_log:
                continue  # Discard LOG frames
            err = item.data_error
            if err is not None:
                raise err
            return item.data_value


class PendingPeerRequest:
    """Internal struct to track pending peer requests (cartridge invoking host caps).
    The reader loop forwards response frames to the queue."""
    def __init__(self):
        # Bounded queue for response frames (buffer up to 64 frames)
        self.queue: queue.Queue = queue.Queue(maxsize=64)
        self.ended: bool = False  # True after END frame (close channel)


@dataclass
class PendingStream:
    """A single stream within a multiplexed request."""
    media_urn: str
    chunks: List[bytes]
    complete: bool


@dataclass
class PendingIncomingRequest:
    """Internal struct to track incoming multiplexed request streams.
    Protocol v2: Requests arrive as REQ (empty) → STREAM_START → CHUNK(s) → STREAM_END → END.
    """
    cap_urn: str
    content_type: Optional[str]
    streams: List  # List of (stream_id, PendingStream) tuples — ordered
    ended: bool  # True after END frame — any stream activity after is FATAL
    routing_id: Optional["MessageId"] = None  # XID from incoming REQ (preserved for response routing)


class PeerInvokerImpl:
    """Implementation of PeerInvoker that sends REQ frames to the host.

    Enables bidirectional communication where a cartridge handler can invoke caps
    on the host while processing a request.
    """

    def __init__(self, writer: SyncFrameWriter, pending_requests: Dict[str, PendingPeerRequest], max_chunk: Optional[int] = None):
        self.writer = writer
        self.pending_requests = pending_requests
        self.pending_lock = threading.Lock()
        self.max_chunk = max_chunk if max_chunk is not None else DEFAULT_MAX_CHUNK

    def invoke(self, cap_urn: str, arguments: List[CapArgumentValue]) -> queue.Queue:
        """Invoke a cap on the host with arguments.

        Protocol v2: Sends REQ(empty) + STREAM_START + CHUNK(s) + STREAM_END + END
        for each argument as an independent stream.
        Returns a queue that receives bare Frame objects from the host.
        Seq is assigned centrally by SyncFrameWriter's SeqAssigner.
        """
        import uuid as _uuid

        request_id = MessageId.new_uuid()
        request_id_str = request_id.to_string()

        pending_req = PendingPeerRequest()

        with self.pending_lock:
            self.pending_requests[request_id_str] = pending_req

        max_chunk = self.max_chunk

        try:
            # 1. REQ with empty payload
            self.writer.write(Frame.req(request_id, cap_urn, b"", "application/cbor"))

            # 2. Each argument as an independent stream
            for arg in arguments:
                stream_id = str(_uuid.uuid4())

                # STREAM_START (seq assigned by SyncFrameWriter)
                self.writer.write(Frame.stream_start(request_id, stream_id, arg.media_urn))

                # CHUNK(s): Send argument data as CBOR-encoded chunks
                # Each CHUNK payload MUST be independently decodable CBOR
                # Seq is assigned by SyncFrameWriter — pass 0 as placeholder
                offset = 0
                chunk_index = 0
                while offset < len(arg.value):
                    chunk_size = min(len(arg.value) - offset, max_chunk)
                    chunk_bytes = arg.value[offset:offset + chunk_size]

                    # CBOR-encode chunk as bytes - independently decodable
                    cbor_payload = cbor2.dumps(chunk_bytes)

                    self.writer.write(Frame.chunk(request_id, stream_id, 0, cbor_payload, chunk_index, compute_checksum(cbor_payload)))
                    offset += chunk_size
                    chunk_index += 1

                # STREAM_END (seq assigned by SyncFrameWriter)
                self.writer.write(Frame.stream_end(request_id, stream_id, chunk_index))

            # 3. END (seq assigned by SyncFrameWriter)
            self.writer.write(Frame.end(request_id, None))

        except Exception as e:
            with self.pending_lock:
                del self.pending_requests[request_id_str]
            raise PeerRequestError(f"Failed to send peer request frames: {e}")

        # Return the queue directly - caller will receive bare Frame objects
        return pending_req.queue


class CliStreamEmitter:
    """CLI-mode emitter that writes directly to stdout.
    Used when the cartridge is invoked via CLI (with arguments).
    """

    def __init__(self, ndjson: bool = True):
        """Create a new CLI emitter

        Args:
            ndjson: Whether to add newlines after each emit (NDJSON style)
        """
        self.ndjson = ndjson

    @classmethod
    def without_ndjson(cls):
        """Create a CLI emitter without NDJSON formatting"""
        return cls(ndjson=False)

    def emit_cbor(self, value: Any) -> None:
        """Emit a CBOR value to stdout.
        In CLI mode: extract raw bytes/text from CBOR and emit to stdout.
        Supported types: bytes, str, list of bytes/str.
        NO FALLBACK - fail hard if unsupported type.
        """
        stdout = sys.stdout.buffer

        if isinstance(value, bytes):
            stdout.write(value)
        elif isinstance(value, str):
            stdout.write(value.encode('utf-8'))
        elif isinstance(value, list):
            # Array - emit each element's raw content
            for item in value:
                if isinstance(item, bytes):
                    stdout.write(item)
                elif isinstance(item, str):
                    stdout.write(item.encode('utf-8'))
                else:
                    raise RuntimeError(f"Handler emitted unsupported list element type: {type(item)}")
        else:
            raise RuntimeError(f"Handler emitted unsupported CBOR type: {type(value)}")

        if self.ndjson:
            stdout.write(b'\n')
        stdout.flush()

    def write(self, data: bytes) -> None:
        """In CLI mode, write raw bytes to stdout"""
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

    def emit_list_item(self, value: Any) -> None:
        """In CLI mode, emit list items as individual output"""
        self.emit_cbor(value)

    def emit_log(self, level: str, message: str) -> None:
        """In CLI mode, logs go to stderr"""
        print(f"[{level.upper()}] {message}", file=sys.stderr)

    def progress(self, progress: float, message: str) -> None:
        """In CLI mode, progress goes to stderr"""
        print(f"[PROGRESS {progress*100:.0f}%] {message}", file=sys.stderr)


class ThreadSafeEmitter:
    """Thread-safe implementation of StreamEmitter using Protocol v2 stream multiplexing.

    Automatically sends STREAM_START before the first emission, then CHUNK frames
    with stream_id. Caller MUST call finalize() after handler returns to send
    STREAM_END + END.

    Seq is assigned centrally by the SyncFrameWriter's SeqAssigner — this emitter
    does NOT track seq itself. This matches the Rust cartridge_runtime writer thread
    with SeqAssigner and Go's threadSafeEmitter with syncFrameWriter.
    """

    def __init__(self, writer: SyncFrameWriter, request_id: MessageId, stream_id: str, media_urn: str, routing_id: Optional[MessageId] = None, max_chunk: Optional[int] = None):
        self.writer = writer
        self.request_id = request_id
        self.stream_id = stream_id
        self.media_urn = media_urn
        self.routing_id = routing_id  # XID from incoming REQ — set on all response frames
        self.chunk_index = 0
        self.chunk_lock = threading.Lock()
        self.max_chunk = max_chunk if max_chunk is not None else DEFAULT_MAX_CHUNK
        self.stream_started = False
        self.stream_lock = threading.Lock()

    def _ensure_stream_started(self) -> None:
        """Send STREAM_START if not yet sent. Seq and routing_id assigned here."""
        with self.stream_lock:
            if not self.stream_started:
                self.stream_started = True
                start_frame = Frame.stream_start(self.request_id, self.stream_id, self.media_urn)
                start_frame.routing_id = self.routing_id  # Propagate XID from incoming REQ
                self.writer.write(start_frame)

    def emit_cbor(self, value: Any) -> None:
        """Emit a CBOR value as output.

        CHUNK payloads = complete, independently decodable CBOR values.

        Streams might never end (logs, video, real-time data), so each CHUNK must be
        processable immediately without waiting for END frame.

        For bytes/str: split raw data, encode each chunk as complete value
        For other types: encode once (typically small)

        Each CHUNK payload can be decoded independently: cbor2.loads(chunk.payload)
        Seq is assigned by SyncFrameWriter — pass 0 as placeholder.
        Raises: RuntimeError on write failure."""
        self._ensure_stream_started()

        # Split large byte/text data, encode each chunk as complete CBOR value
        if isinstance(value, bytes):
            # Split bytes BEFORE encoding, encode each chunk as bytes
            offset = 0
            while offset < len(value):
                chunk_size = min(self.max_chunk, len(value) - offset)
                chunk_bytes = value[offset:offset + chunk_size]

                # Encode as complete bytes - independently decodable
                cbor_payload = cbor2.dumps(chunk_bytes)

                with self.chunk_lock:
                    idx = self.chunk_index
                    self.chunk_index += 1

                # Seq=0 placeholder — SyncFrameWriter assigns the real seq
                frame = Frame.chunk(self.request_id, self.stream_id, 0, cbor_payload, idx, compute_checksum(cbor_payload))
                frame.routing_id = self.routing_id  # Propagate XID from incoming REQ
                self.writer.write(frame)

                offset += chunk_size

        elif isinstance(value, str):
            # Split string BEFORE encoding, encode each chunk as str
            str_bytes = value.encode('utf-8')
            offset = 0
            while offset < len(str_bytes):
                chunk_size = min(self.max_chunk, len(str_bytes) - offset)
                # Ensure we split on UTF-8 character boundaries
                while chunk_size > 0:
                    try:
                        chunk_str = str_bytes[offset:offset + chunk_size].decode('utf-8')
                        break
                    except UnicodeDecodeError:
                        chunk_size -= 1
                if chunk_size == 0:
                    raise RuntimeError("Cannot split string on character boundary")

                # Encode as complete str - independently decodable
                cbor_payload = cbor2.dumps(chunk_str)

                with self.chunk_lock:
                    idx = self.chunk_index
                    self.chunk_index += 1

                # Seq=0 placeholder — SyncFrameWriter assigns the real seq
                frame = Frame.chunk(self.request_id, self.stream_id, 0, cbor_payload, idx, compute_checksum(cbor_payload))
                frame.routing_id = self.routing_id  # Propagate XID from incoming REQ
                self.writer.write(frame)

                offset += len(chunk_str.encode('utf-8'))

        elif isinstance(value, list):
            # Array: send each element as independent CBOR chunk
            for element in value:
                cbor_payload = cbor2.dumps(element)

                with self.chunk_lock:
                    idx = self.chunk_index
                    self.chunk_index += 1

                frame = Frame.chunk(self.request_id, self.stream_id, 0, cbor_payload, idx, compute_checksum(cbor_payload))
                frame.routing_id = self.routing_id  # Propagate XID from incoming REQ
                self.writer.write(frame)

        elif isinstance(value, dict):
            # Map: send each entry as [key, value] pair chunk
            for key, val in value.items():
                entry = [key, val]
                cbor_payload = cbor2.dumps(entry)

                with self.chunk_lock:
                    idx = self.chunk_index
                    self.chunk_index += 1

                frame = Frame.chunk(self.request_id, self.stream_id, 0, cbor_payload, idx, compute_checksum(cbor_payload))
                frame.routing_id = self.routing_id  # Propagate XID from incoming REQ
                self.writer.write(frame)

        else:
            # For other types (int, float, bool, None): encode as single chunk
            cbor_payload = cbor2.dumps(value)

            with self.chunk_lock:
                idx = self.chunk_index
                self.chunk_index += 1

            frame = Frame.chunk(self.request_id, self.stream_id, 0, cbor_payload, idx, compute_checksum(cbor_payload))
            frame.routing_id = self.routing_id  # Propagate XID from incoming REQ
            self.writer.write(frame)

    def finalize(self) -> None:
        """Send STREAM_END + END to complete the response.
        Must be called exactly once after the handler returns.
        If handler never emitted, sends STREAM_START first for protocol consistency.
        Seq assigned by SyncFrameWriter for all frames.
        """
        # Ensure STREAM_START was sent (even if handler emitted nothing)
        with self.stream_lock:
            if not self.stream_started:
                self.stream_started = True
                start_frame = Frame.stream_start(self.request_id, self.stream_id, self.media_urn)
                start_frame.routing_id = self.routing_id  # Propagate XID from incoming REQ
                self.writer.write(start_frame)

        # STREAM_END (seq assigned by SyncFrameWriter)
        stream_end = Frame.stream_end(self.request_id, self.stream_id, self.chunk_index)
        stream_end.routing_id = self.routing_id  # Propagate XID from incoming REQ
        self.writer.write(stream_end)

        # END (seq assigned by SyncFrameWriter)
        end_frame = Frame.end(self.request_id, None)
        end_frame.routing_id = self.routing_id  # Propagate XID from incoming REQ
        self.writer.write(end_frame)

    def write(self, data: bytes) -> None:
        """Write raw bytes as output, split into max_chunk-sized CHUNK frames.

        Unlike emit_cbor which CBOR-encodes the value, this sends raw bytes
        directly as frame payloads. Each chunk is independently processable.
        """
        self._ensure_stream_started()
        offset = 0
        while offset < len(data):
            chunk_size = min(self.max_chunk, len(data) - offset)
            chunk_payload = data[offset:offset + chunk_size]

            with self.chunk_lock:
                idx = self.chunk_index
                self.chunk_index += 1

            frame = Frame.chunk(self.request_id, self.stream_id, 0, chunk_payload, idx, compute_checksum(chunk_payload))
            frame.routing_id = self.routing_id
            self.writer.write(frame)

            offset += chunk_size

    def emit_list_item(self, value: Any) -> None:
        """Emit a single CBOR value as one item in an RFC 8742 CBOR sequence.

        For list outputs: the receiver concatenates raw frame payloads and stores
        the result as a CBOR sequence. This method CBOR-encodes the value, then
        splits the encoded bytes across chunk frames at max_chunk boundaries.
        The receiver's concatenation reconstructs the original CBOR encoding,
        producing exactly one self-delimiting CBOR value in the sequence per call.

        Unlike emit_cbor (which re-wraps each piece as a separate CBOR value),
        this sends raw CBOR bytes as frame payloads directly.
        """
        self._ensure_stream_started()
        cbor_bytes = cbor2.dumps(value)

        offset = 0
        while offset < len(cbor_bytes):
            chunk_size = min(self.max_chunk, len(cbor_bytes) - offset)
            chunk_payload = cbor_bytes[offset:offset + chunk_size]

            with self.chunk_lock:
                idx = self.chunk_index
                self.chunk_index += 1

            frame = Frame.chunk(self.request_id, self.stream_id, 0, chunk_payload, idx, compute_checksum(chunk_payload))
            frame.routing_id = self.routing_id
            self.writer.write(frame)

            offset += chunk_size

    def emit_log(self, level: str, message: str) -> None:
        """Emit a log message at the given level.
        Sends a LOG frame (side-channel, does not affect response stream).
        Seq assigned by SyncFrameWriter."""
        frame = Frame.log(self.request_id, level, message)
        frame.routing_id = self.routing_id  # Propagate XID from incoming REQ
        self.writer.write(frame)

    def progress(self, progress: float, message: str) -> None:
        """Emit a progress update (0.0-1.0) with a human-readable status message."""
        frame = Frame.progress(self.request_id, progress, message)
        frame.routing_id = self.routing_id
        self.writer.write(frame)

    def progress_sender(self) -> "ProgressSender":
        """Create a detached progress sender that can be moved into background threads.

        The returned ProgressSender is thread-safe and can emit progress and log
        frames from any thread without holding a reference to this ThreadSafeEmitter.
        Use this when blocking work (FFI model loads, inference) needs to emit
        per-token or keepalive progress from a dedicated thread.
        """
        return ProgressSender(
            writer=self.writer,
            request_id=self.request_id,
            routing_id=self.routing_id,
        )


class ProgressSender:
    """Detached progress/log emitter that can be moved into background threads.

    Holds a SyncFrameWriter and the request routing info needed to
    construct LOG frames. Thread-safe by construction (delegates to SyncFrameWriter).
    """

    def __init__(self, writer: SyncFrameWriter, request_id: MessageId, routing_id: Optional[MessageId]):
        self._writer = writer
        self._request_id = request_id
        self._routing_id = routing_id

    def progress(self, progress: float, message: str) -> None:
        """Emit a progress update (0.0–1.0) with a human-readable status message."""
        frame = Frame.progress(self._request_id, progress, message)
        frame.routing_id = self._routing_id
        self._writer.write(frame)

    def log(self, level: str, message: str) -> None:
        """Emit a log message."""
        frame = Frame.log(self._request_id, level, message)
        frame.routing_id = self._routing_id
        self._writer.write(frame)


# =============================================================================
# OP-BASED HANDLER SYSTEM — handlers implement ops.Op[None]
# =============================================================================

class Request:
    """Bundles capdag I/O for WetContext. Op handlers extract this from WetContext
    to access streaming input frames, output emitter, and peer invocation.
    """

    def __init__(self, frames: queue.Queue, emitter: "StreamEmitter", peer: "PeerInvoker"):
        self._frames = frames
        self._emitter = emitter
        self._peer = peer
        self._consumed = False
        self._lock = threading.Lock()

    def take_frames(self) -> queue.Queue:
        """Take the input frames queue. Can only be called once — second call raises error."""
        with self._lock:
            if self._consumed:
                raise HandlerError("Input already consumed")
            self._consumed = True
            return self._frames

    def emitter(self) -> "StreamEmitter":
        """Access the output stream emitter."""
        return self._emitter

    def peer(self) -> "PeerInvoker":
        """Access the peer invoker."""
        return self._peer


class InputStream:
    """Synchronous input stream of decoded items for a single media URN."""

    def __init__(self, media_urn: str, q: queue.Queue):
        self._media_urn = media_urn
        self._queue = q

    def recv_data(self):
        """Receive the next item, or None when the stream ends."""
        item = self._queue.get()
        if item is None:
            return None
        return item

    def collect_bytes(self) -> bytes:
        """Collect all byte/text chunks into a single byte string."""
        result = bytearray()
        while True:
            item = self.recv_data()
            if item is None:
                return bytes(result)
            if isinstance(item, Exception):
                raise item
            if isinstance(item, bytes):
                result.extend(item)
                continue
            if isinstance(item, str):
                result.extend(item.encode("utf-8"))
                continue
            raise RuntimeError(
                f"InputStream.collect_bytes only supports bytes/str chunks, got {type(item).__name__}"
            )

    def media_urn(self) -> str:
        return self._media_urn


class InputPackage:
    """Synchronous package of InputStreams."""

    def __init__(self, q: queue.Queue):
        self._queue = q

    def recv(self):
        """Receive the next InputStream, or None when the package ends."""
        item = self._queue.get()
        if item is None:
            return None
        return item

    def collect_all_bytes(self) -> bytes:
        """Collect bytes from every stream in order."""
        result = bytearray()
        while True:
            stream = self.recv()
            if stream is None:
                return bytes(result)
            if isinstance(stream, Exception):
                raise stream
            if not isinstance(stream, InputStream):
                raise RuntimeError(
                    f"InputPackage expected InputStream items, got {type(stream).__name__}"
                )
            result.extend(stream.collect_bytes())


class OutputStream:
    """Synchronous output stream that emits STREAM_START/CHUNK/STREAM_END frames."""

    def __init__(
        self,
        writer: SyncFrameWriter,
        request_id: MessageId,
        stream_id: str,
        media_urn: str,
        routing_id: Optional[MessageId] = None,
        max_chunk: Optional[int] = None,
    ):
        self.writer = writer
        self.request_id = request_id
        self.stream_id = stream_id
        self.media_urn = media_urn
        self.routing_id = routing_id
        self.max_chunk = max_chunk if max_chunk is not None else DEFAULT_MAX_CHUNK
        self.chunk_index = 0
        self.started = False
        self.closed = False
        self._lock = threading.Lock()

    def _start_unlocked(self, is_sequence: bool = False, meta: Optional[dict] = None) -> None:
        if self.started:
            return
        frame = Frame.stream_start(
            self.request_id,
            self.stream_id,
            self.media_urn,
            is_sequence if is_sequence else None,
        )
        if meta is not None:
            frame.meta = dict(meta)
        frame.routing_id = self.routing_id
        self.writer.write(frame)
        self.started = True

    def start(self, is_sequence: bool = False, meta: Optional[dict] = None) -> None:
        """Emit STREAM_START exactly once."""
        with self._lock:
            self._start_unlocked(is_sequence=is_sequence, meta=meta)

    def _write_chunk_payload(self, payload: bytes) -> None:
        frame = Frame.chunk(
            self.request_id,
            self.stream_id,
            0,
            payload,
            self.chunk_index,
            compute_checksum(payload),
        )
        frame.routing_id = self.routing_id
        self.writer.write(frame)
        self.chunk_index += 1

    def emit_cbor(self, value: Any) -> None:
        """Emit a CBOR value split into max_chunk-sized CHUNK payloads."""
        with self._lock:
            if self.closed:
                raise RuntimeError("OutputStream already closed")
            if not self.started:
                self._start_unlocked()

            if isinstance(value, bytes):
                offset = 0
                while offset < len(value):
                    chunk_size = min(self.max_chunk, len(value) - offset)
                    chunk_bytes = value[offset:offset + chunk_size]
                    self._write_chunk_payload(cbor2.dumps(chunk_bytes))
                    offset += chunk_size
                return

            if isinstance(value, str):
                encoded = value.encode("utf-8")
                offset = 0
                while offset < len(encoded):
                    chunk_size = min(self.max_chunk, len(encoded) - offset)
                    while chunk_size > 0:
                        try:
                            chunk_str = encoded[offset:offset + chunk_size].decode("utf-8")
                            break
                        except UnicodeDecodeError:
                            chunk_size -= 1
                    if chunk_size == 0:
                        raise RuntimeError("Cannot split string on character boundary")
                    self._write_chunk_payload(cbor2.dumps(chunk_str))
                    offset += len(chunk_str.encode("utf-8"))
                return

            self._write_chunk_payload(cbor2.dumps(value))

    def close(self) -> None:
        """Emit STREAM_END exactly once."""
        with self._lock:
            if self.closed:
                raise RuntimeError("OutputStream already closed")
            if not self.started:
                self._start_unlocked()
            frame = Frame.stream_end(self.request_id, self.stream_id, self.chunk_index)
            frame.routing_id = self.routing_id
            self.writer.write(frame)
            self.closed = True


class PeerCall:
    """Peer-call helper that owns request-level output streams and final END."""

    def __init__(
        self,
        writer: SyncFrameWriter,
        request_id: MessageId,
        response: Optional[PeerResponse] = None,
        routing_id: Optional[MessageId] = None,
        max_chunk: Optional[int] = None,
    ):
        self.writer = writer
        self.request_id = request_id
        self.response = response
        self.routing_id = routing_id
        self.max_chunk = max_chunk if max_chunk is not None else DEFAULT_MAX_CHUNK

    def arg(self, media_urn: str) -> OutputStream:
        import uuid as _uuid

        return OutputStream(
            writer=self.writer,
            request_id=self.request_id,
            stream_id=str(_uuid.uuid4()),
            media_urn=media_urn,
            routing_id=self.routing_id,
            max_chunk=self.max_chunk,
        )

    def finish(self) -> Optional[PeerResponse]:
        frame = Frame.end(self.request_id, None)
        frame.routing_id = self.routing_id
        self.writer.write(frame)
        return self.response


# WetContext key for the Request object.
WET_KEY_REQUEST: str = "request"

# Factory function that creates a fresh Op[None] instance per invocation.
OpFactory = Callable[[], Op]


class IdentityOp(Op):
    """Standard identity handler — pure passthrough. Forwards all input chunks to output."""

    async def perform(self, dry: DryContext, wet: WetContext) -> None:
        req: Request = wet.get_required(WET_KEY_REQUEST)
        frames = req.take_frames()
        for frame in iter(frames.get, None):
            if frame.frame_type == FrameType.CHUNK:
                # Verify checksum (protocol v2 integrity check)
                verify_chunk_checksum(frame)
                if frame.payload is not None:
                    req.emitter().write(frame.payload)
            elif frame.frame_type == FrameType.END:
                break

    def metadata(self) -> OpMetadata:
        return OpMetadata.builder("IdentityOp") \
            .description("Pure passthrough — forwards all input to output") \
            .build()


class DiscardOp(Op):
    """Standard discard handler — terminal morphism. Drains all input, produces nothing."""

    async def perform(self, dry: DryContext, wet: WetContext) -> None:
        req: Request = wet.get_required(WET_KEY_REQUEST)
        frames = req.take_frames()
        for frame in iter(frames.get, None):
            if frame is None or frame.frame_type == FrameType.END:
                break

    def metadata(self) -> OpMetadata:
        return OpMetadata.builder("DiscardOp") \
            .description("Terminal morphism — drains all input, produces nothing") \
            .build()


class AdapterSelectionOp(Op):
    """Default adapter-selection handler — drains input, returns empty END (no match).

    Cartridges that inspect file content override this with a handler that
    returns {"media_urns": [...]}.
    """

    async def perform(self, dry: DryContext, wet: WetContext) -> None:
        req: Request = wet.get_required(WET_KEY_REQUEST)
        frames = req.take_frames()
        for frame in iter(frames.get, None):
            if frame is None or frame.frame_type == FrameType.END:
                break

    def metadata(self) -> OpMetadata:
        return OpMetadata.builder("AdapterSelectionOp") \
            .description("Default adapter selection — returns empty END (no match)") \
            .build()


def dispatch_op(
    op: Op,
    frames: queue.Queue,
    emitter: "StreamEmitter",
    peer: "PeerInvoker",
) -> None:
    """Dispatch an Op with a Request via WetContext. Bridges sync handler threads to async Op.perform.

    Raises HandlerError on Op failure.
    """
    req = Request(frames, emitter, peer)
    dry = DryContext()
    wet = WetContext()
    wet.insert_ref(WET_KEY_REQUEST, req)
    try:
        asyncio.run(op.perform(dry, wet))
    except Exception as e:
        raise HandlerError(str(e))


def collect_args_by_media_urn(frames: queue.Queue, media_urn: str) -> bytes:
    """Collect and concatenate payload chunks for a specific media URN from frame stream.

    Processes frames in order: STREAM_START → CHUNK(s) → STREAM_END → END
    Returns the concatenated payload for the first stream matching the media URN.

    Args:
        frames: Queue of Frame objects (will be consumed)
        media_urn: Media URN to match (e.g., "media:")

    Returns:
        Concatenated payload bytes for matching stream

    Raises:
        RuntimeError: If no matching stream found or protocol error
    """
    try:
        target_urn = MediaUrn.from_string(media_urn)
    except Exception as e:
        raise RuntimeError(f"Invalid media URN '{media_urn}': {e}")

    # Track streams: stream_id → (media_urn, chunks)
    streams = {}
    result = None

    for frame in iter(frames.get, None):
        if frame.frame_type == FrameType.STREAM_START:
            if frame.stream_id and frame.media_urn:
                streams[frame.stream_id] = (frame.media_urn, [])

        elif frame.frame_type == FrameType.CHUNK:
            # Verify checksum (protocol v2 integrity check)
            verify_chunk_checksum(frame)
            if frame.stream_id and frame.stream_id in streams:
                if frame.payload:
                    streams[frame.stream_id][1].append(frame.payload)

        elif frame.frame_type == FrameType.STREAM_END:
            if frame.stream_id and frame.stream_id in streams:
                stream_media_urn, chunks = streams[frame.stream_id]
                # Check if this stream matches target using is_equivalent
                # Both URNs are concrete — exact tag-set match required
                try:
                    stream_urn = MediaUrn.from_string(stream_media_urn)
                    if target_urn.is_equivalent(stream_urn):
                        result = b''.join(chunks)
                        # Found match - consume rest of frames and return
                        for _ in iter(frames.get, None):
                            pass
                        return result
                except Exception:
                    continue

        elif frame.frame_type == FrameType.END:
            break

        elif frame.frame_type == FrameType.ERR:
            code = frame.error_code() or "UNKNOWN"
            message = frame.error_message() or "Unknown error"
            raise RuntimeError(f"[{code}] {message}")

    if result is not None:
        return result

    # No matching stream found
    raise RuntimeError(f"No stream found matching media URN '{media_urn}'")


def collect_peer_response(frames: queue.Queue) -> bytes:
    """Collect and concatenate all CHUNK payloads from a peer response frame stream.

    Processes frames in order: STREAM_START → CHUNK(s) → STREAM_END → END
    Returns concatenated payload from all chunks.

    Args:
        frames: Queue of Frame objects from PeerInvoker.invoke()

    Returns:
        Concatenated payload bytes

    Raises:
        RuntimeError: If ERR frame received or protocol error
    """
    chunks = []

    for frame in iter(frames.get, None):
        if frame.frame_type == FrameType.CHUNK:
            # Verify checksum (protocol v2 integrity check)
            verify_chunk_checksum(frame)
            if frame.payload:
                chunks.append(frame.payload)

        elif frame.frame_type == FrameType.END:
            break

        elif frame.frame_type == FrameType.ERR:
            code = frame.error_code() or "UNKNOWN"
            message = frame.error_message() or "Unknown error"
            raise RuntimeError(f"Peer error: [{code}] {message}")

    return b''.join(chunks)


def collect_streams(frames: queue.Queue) -> List[Tuple[str, bytes]]:
    """Collect each stream individually into a list of (media_urn, bytes) pairs.

    Each stream's bytes are accumulated separately — NOT concatenated.
    Use find_stream() helpers to retrieve args by URN pattern matching.

    Args:
        frames: Queue of Frame objects (will be consumed)

    Returns:
        List of (media_urn, bytes) tuples, one per stream

    Raises:
        RuntimeError: If protocol error occurs
    """
    # Track streams: stream_id → (media_urn, chunks)
    streams = {}
    result = []

    for frame in iter(frames.get, None):
        if frame.frame_type == FrameType.STREAM_START:
            if frame.stream_id and frame.media_urn:
                streams[frame.stream_id] = (frame.media_urn, [])

        elif frame.frame_type == FrameType.CHUNK:
            # Verify checksum (protocol v2 integrity check)
            verify_chunk_checksum(frame)
            if frame.stream_id and frame.stream_id in streams:
                if frame.payload:
                    streams[frame.stream_id][1].append(frame.payload)

        elif frame.frame_type == FrameType.STREAM_END:
            if frame.stream_id and frame.stream_id in streams:
                media_urn, chunks = streams[frame.stream_id]
                result.append((media_urn, b''.join(chunks)))
                del streams[frame.stream_id]

        elif frame.frame_type == FrameType.END:
            break

        elif frame.frame_type == FrameType.ERR:
            code = frame.error_code() or "UNKNOWN"
            message = frame.error_message() or "Unknown error"
            raise RuntimeError(f"Error: [{code}] {message}")

    return result


def demux_peer_response(raw_frames: queue.Queue) -> PeerResponse:
    """Demux a raw frame queue into a PeerResponse that yields PeerResponseItems.

    Spawns a background thread that reads frames from the raw queue and
    converts them into PeerResponseItems (Data or Log). Returns immediately
    so LOG frames can be consumed before data arrives (critical for keeping
    the engine's activity timer alive during long peer calls).

    This mirrors Rust's demux_single_stream() function.
    """
    item_queue: queue.Queue = queue.Queue(maxsize=256)

    def _demux_worker():
        for frame in iter(raw_frames.get, None):
            if frame.frame_type == FrameType.STREAM_START:
                # Structural frame — no item to deliver
                pass
            elif frame.frame_type == FrameType.CHUNK:
                if frame.payload:
                    # Verify checksum
                    expected_checksum = frame.checksum
                    if expected_checksum is None:
                        item_queue.put(PeerResponseItem.data_err(
                            PeerResponseError("CHUNK frame missing required checksum field")
                        ))
                        continue
                    actual = compute_checksum(frame.payload)
                    if actual != expected_checksum:
                        item_queue.put(PeerResponseItem.data_err(
                            PeerResponseError(f"Checksum mismatch: expected={expected_checksum}, actual={actual}")
                        ))
                        continue
                    try:
                        value = cbor2.loads(frame.payload)
                        item_queue.put(PeerResponseItem.data_ok(value))
                    except Exception as e:
                        item_queue.put(PeerResponseItem.data_err(
                            PeerResponseError(f"CBOR decode error: {e}")
                        ))
            elif frame.frame_type == FrameType.LOG:
                item_queue.put(PeerResponseItem.log_frame(frame))
            elif frame.frame_type in (FrameType.STREAM_END, FrameType.END):
                break
            elif frame.frame_type == FrameType.ERR:
                code = frame.error_code() or "UNKNOWN"
                message = frame.error_message() or "Unknown error"
                item_queue.put(PeerResponseItem.data_err(
                    PeerResponseError(f"Remote error: [{code}] {message}")
                ))
                break
        # Signal end of stream
        item_queue.put(None)

    thread = threading.Thread(target=_demux_worker, daemon=True)
    thread.start()

    return PeerResponse(item_queue)


def find_stream(streams: List[Tuple[str, bytes]], media_urn: str) -> Optional[bytes]:
    """Find a stream's bytes by exact URN equivalence.

    Uses MediaUrn.is_equivalent() — matches only if both URNs have the
    exact same tag set (order-independent). Both the caller and the cartridge
    know the arg media URNs from the cap definition, so this is always an
    exact match — never a subsumption/pattern match.

    Args:
        streams: List of (media_urn, bytes) tuples from collect_streams()
        media_urn: Full media URN from cap arg definition (e.g., "media:model-spec;textable")

    Returns:
        Stream bytes if found, None otherwise
    """
    try:
        target = MediaUrn.from_string(media_urn)
    except Exception:
        return None

    for urn_str, data in streams:
        try:
            urn = MediaUrn.from_string(urn_str)
            if target.is_equivalent(urn):
                return data
        except Exception:
            continue

    return None


def find_stream_str(streams: List[Tuple[str, bytes]], media_urn: str) -> Optional[str]:
    """Like find_stream but returns a UTF-8 string."""
    data = find_stream(streams, media_urn)
    if data is None:
        return None
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return None


def require_stream(streams: List[Tuple[str, bytes]], media_urn: str) -> bytes:
    """Like find_stream but fails hard if not found.

    Raises:
        RuntimeError: If stream not found
    """
    data = find_stream(streams, media_urn)
    if data is None:
        raise RuntimeError(f"Missing required arg: {media_urn}")
    return data


def require_stream_str(streams: List[Tuple[str, bytes]], media_urn: str) -> str:
    """Like require_stream but returns a UTF-8 string.

    Raises:
        RuntimeError: If stream not found or not valid UTF-8
    """
    data = require_stream(streams, media_urn)
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError as e:
        raise RuntimeError(f"Arg '{media_urn}' is not valid UTF-8: {e}")


def extract_effective_payload(
    payload: bytes,
    content_type: Optional[str],
    cap: Cap,
    is_cli_mode: bool,
) -> bytes:
    """Extract the effective payload from a REQ frame.

    Mirrors capdag/src/bifaci/cartridge_runtime.rs::extract_effective_payload.

    When `content_type` is "application/cbor", decode the CBOR arguments,
    perform file-path auto-conversion (reading file bytes and relabeling
    the arg's media_urn to the stdin source's target URN), validate that
    at least one argument matches the cap's declared in= spec (unless the
    cap takes media:void), and return the re-serialized CBOR array.
    """
    # Not CBOR arguments - return raw payload
    if content_type != "application/cbor":
        return payload

    # Parse cap URN to get expected input media URN
    try:
        cap_urn = CapUrn.from_string(cap.urn_string())
    except Exception as e:
        raise CapUrnError(f"Invalid cap URN: {e}")
    expected_input = cap_urn.in_spec()
    try:
        expected_media_urn = MediaUrn.from_string(expected_input)
    except Exception:
        expected_media_urn = None

    # Build arg-definition lookup: parsed MediaUrn -> (stdin_target, is_sequence).
    arg_defs: List[Tuple[MediaUrn, Optional[str], bool]] = []
    for a in cap.get_args():
        try:
            parsed = MediaUrn.from_string(a.media_urn)
        except Exception:
            continue
        stdin_target = None
        from capdag.cap.definition import StdinSource as _StdinSource
        for s in a.sources:
            if isinstance(s, _StdinSource):
                stdin_target = s.stdin
                break
        arg_defs.append((parsed, stdin_target, a.is_sequence))

    # Parse the CBOR payload as an array of argument maps
    try:
        arguments = cbor2.loads(payload)
    except Exception as e:
        raise DeserializeError(f"Failed to parse CBOR arguments: {e}")
    if not isinstance(arguments, list):
        raise DeserializeError("CBOR arguments must be an array")

    # File-path auto-conversion.
    file_path_base = MediaUrn.from_string("media:file-path")

    for arg in arguments:
        if not isinstance(arg, dict):
            continue
        urn_str = arg.get("media_urn")
        value = arg.get("value")
        if not isinstance(urn_str, str) or value is None:
            continue
        try:
            arg_urn = MediaUrn.from_string(urn_str)
        except Exception as e:
            raise RuntimeError(f"Invalid argument media URN '{urn_str}': {e}")

        if not file_path_base.accepts(arg_urn):
            continue

        # Look up the cap's arg definition by URN equivalence (NOT string compare).
        matched = None
        for parsed, stdin_target, is_seq in arg_defs:
            if parsed.is_equivalent(arg_urn):
                matched = (stdin_target, is_seq)
                break
        if matched is None:
            continue
        stdin_target, is_sequence = matched
        if stdin_target is None:
            continue

        paths = expand_file_path_value(value, urn_str, is_cli_mode)

        if not is_sequence:
            if len(paths) != 1:
                raise RuntimeError(
                    f"File-path arg '{urn_str}' declared is_sequence=False resolved to "
                    f"{len(paths)} files; expected exactly 1. CLI-mode dispatch should "
                    f"have iterated the handler across the expanded files before "
                    f"calling the runtime."
                )
            try:
                file_bytes = paths[0].read_bytes()
            except IOError as e:
                raise RuntimeError(f"Failed to read file '{paths[0]}': {e}")
            replace_arg_value(arg, file_bytes, stdin_target)
        else:
            items: List[bytes] = []
            for p in paths:
                try:
                    items.append(p.read_bytes())
                except IOError as e:
                    raise RuntimeError(f"Failed to read file '{p}': {e}")
            replace_arg_value(arg, items, stdin_target)

    # Validate: at least ONE argument must match the cap's declared in=spec,
    # unless the cap takes no input (in=media:void).
    void_urn = MediaUrn.from_string("media:void")
    is_void_input = (
        expected_media_urn is not None and expected_media_urn.is_equivalent(void_urn)
    )

    if not is_void_input:
        valid_targets: List[MediaUrn] = []
        if expected_media_urn is not None:
            valid_targets.append(expected_media_urn)
        for _parsed, stdin_target, _is_seq in arg_defs:
            if stdin_target is not None:
                try:
                    valid_targets.append(MediaUrn.from_string(stdin_target))
                except Exception:
                    continue

        found_matching_arg = False
        for arg in arguments:
            if not isinstance(arg, dict):
                continue
            urn_str = arg.get("media_urn")
            if not isinstance(urn_str, str):
                continue
            try:
                arg_urn = MediaUrn.from_string(urn_str)
            except Exception:
                continue
            for target in valid_targets:
                # Use is_comparable for discovery: are they on the same chain?
                if arg_urn.is_comparable(target):
                    found_matching_arg = True
                    break
            if found_matching_arg:
                break

        if not found_matching_arg:
            raise DeserializeError(
                f"No argument found matching expected input media type "
                f"'{expected_input}' in CBOR arguments"
            )

    # After file-path conversion and validation, return the full CBOR array.
    try:
        return cbor2.dumps(arguments)
    except Exception as e:
        raise SerializeError(f"Failed to serialize modified CBOR: {e}")


def replace_arg_value(arg_map: dict, new_value, new_urn: str) -> None:
    """Replace an argument map's "value" and "media_urn" entries in place.

    Mirrors capdag/src/bifaci/cartridge_runtime.rs::replace_arg_value.
    """
    arg_map["value"] = new_value
    arg_map["media_urn"] = new_urn


def expand_file_path_value(value, urn_str: str, is_cli_mode: bool) -> List["Path"]:
    """Expand a file-path arg value into a concrete list of filesystem paths.

    Mirrors capdag/src/bifaci/cartridge_runtime.rs::expand_file_path_value.

    The incoming value may be:
      - bytes/str containing a single path or a single glob pattern
      - list of bytes/str items, each a path or a glob (CBOR mode only)

    Globs (detected via `*`, `?`, or `[`) are expanded and the results filtered
    to regular files. Literal paths must exist and point at a regular file.
    Returns at least one path on success; empty matches fail hard so the caller
    never has to guard against a silently-empty list.
    """
    raw_paths: List[str] = []
    if isinstance(value, bytes):
        raw_paths = [value.decode('utf-8', errors='replace')]
    elif isinstance(value, str):
        raw_paths = [value]
    elif isinstance(value, list):
        if is_cli_mode:
            raise RuntimeError(
                f"File-path arg '{urn_str}' received a CBOR Array value in CLI mode; "
                f"CLI dispatch must expand globs before calling into the runtime"
            )
        for item in value:
            if isinstance(item, str):
                raw_paths.append(item)
            elif isinstance(item, bytes):
                raw_paths.append(item.decode('utf-8', errors='replace'))
            else:
                raise RuntimeError(
                    f"File-path arg '{urn_str}' array contained an unsupported "
                    f"CBOR item: {type(item).__name__}"
                )
    else:
        raise RuntimeError(
            f"File-path arg '{urn_str}' value must be Bytes, Text, or (CBOR mode) "
            f"Array — got {type(value).__name__}"
        )

    resolved: List[Path] = []
    for raw in raw_paths:
        is_glob = ('*' in raw) or ('?' in raw) or ('[' in raw)
        if is_glob:
            # Validate bracket balance; Python's glob accepts unbalanced
            # brackets silently, which we want to surface as a hard error.
            bracket_count = 0
            for char in raw:
                if char == '[':
                    bracket_count += 1
                elif char == ']':
                    bracket_count -= 1
                    if bracket_count < 0:
                        raise RuntimeError(f"Invalid glob pattern '{raw}': unmatched ']'")
            if bracket_count != 0:
                raise RuntimeError(f"Invalid glob pattern '{raw}': unclosed '['")
            try:
                matches = glob.glob(raw)
            except Exception as e:
                raise RuntimeError(f"Invalid glob pattern '{raw}': {e}")
            before = len(resolved)
            for p in matches:
                pth = Path(p)
                try:
                    if pth.is_file():
                        resolved.append(pth)
                except OSError:
                    continue
            if len(resolved) == before:
                raise RuntimeError(f"No files matched glob pattern '{raw}'")
        else:
            pth = Path(raw)
            if not pth.exists():
                raise RuntimeError(f"File not found: '{raw}'")
            if not pth.is_file():
                raise RuntimeError(f"Path is not a regular file: '{raw}'")
            resolved.append(pth)

    return resolved


def build_cli_foreach_iterations(raw_payload: bytes, cap: Cap) -> List[bytes]:
    """Compute per-iteration CBOR argument payloads for a CLI invocation.

    Mirrors capdag/src/bifaci/cartridge_runtime.rs::build_cli_foreach_iterations.

    The input is the raw payload produced by build_payload_from_cli — a CBOR
    array of {media_urn, value} maps where file-path values are still raw
    path or glob strings.

    Rules:
    - An arg whose media URN specializes `media:file-path` is iterable iff
      its arg-definition declares `is_sequence = False` AND its raw value
      expands to more than one concrete file.
    - Zero iterable args -> return the payload unchanged (single iteration).
    - One iterable arg -> return one payload per expanded file, each with
      the iterable arg's value replaced by that single path as a string
      value. extract_effective_payload then reads the single file and emits
      bytes.
    - Two or more iterable args -> hard error: the ForEach axis is ambiguous.
    """
    file_path_base = MediaUrn.from_string("media:file-path")

    try:
        arguments = cbor2.loads(raw_payload)
    except Exception as e:
        raise DeserializeError(f"Failed to parse CBOR arguments: {e}")
    if not isinstance(arguments, list):
        raise DeserializeError("CBOR arguments must be an array")

    arg_defs: List[Tuple[MediaUrn, bool]] = []
    for a in cap.get_args():
        try:
            parsed = MediaUrn.from_string(a.media_urn)
        except Exception:
            continue
        arg_defs.append((parsed, a.is_sequence))

    iterable: Optional[Tuple[int, List[Path]]] = None
    for idx, arg in enumerate(arguments):
        if not isinstance(arg, dict):
            continue
        urn_str = arg.get("media_urn")
        value = arg.get("value")
        if not isinstance(urn_str, str) or value is None:
            continue
        try:
            arg_urn = MediaUrn.from_string(urn_str)
        except Exception as e:
            raise RuntimeError(f"Invalid argument media URN '{urn_str}': {e}")
        if not file_path_base.accepts(arg_urn):
            continue
        is_seq = False
        for parsed, seq in arg_defs:
            if parsed.is_equivalent(arg_urn):
                is_seq = seq
                break
        if is_seq:
            continue
        paths = expand_file_path_value(value, urn_str, True)
        if len(paths) <= 1:
            continue
        if iterable is not None:
            raise RuntimeError(
                "Multiple file-path arguments with is_sequence=False each "
                "resolved to more than one file; the ForEach axis is "
                "ambiguous. Declare at most one such arg as scalar, or mark "
                "additional args as is_sequence=True."
            )
        iterable = (idx, paths)

    if iterable is None:
        return [raw_payload]

    idx, paths = iterable
    out: List[bytes] = []
    for path in paths:
        # Deep-clone the arguments list and replace value at idx.
        args_for_iter = []
        for i, a in enumerate(arguments):
            if i == idx and isinstance(a, dict):
                new_map = dict(a)
                new_map["value"] = str(path)
                args_for_iter.append(new_map)
            else:
                args_for_iter.append(a)
        try:
            out.append(cbor2.dumps(args_for_iter))
        except Exception as e:
            raise SerializeError(f"Failed to re-encode iter payload: {e}")
    return out


class CartridgeRuntime:
    """The cartridge runtime that handles all I/O for cartridge binaries.

    Cartridges create a runtime with their manifest, register handlers for their caps,
    then call `run()` to process requests.

    The manifest is REQUIRED - cartridges MUST provide their manifest which is sent
    in the HELLO response during handshake. This is the ONLY way for cartridges to
    communicate their capabilities to the host.

    **Invocation Modes**:
    - No CLI args: Cartridge CBOR mode (stdin/stdout binary frames)
    - Any CLI args: CLI mode (parse args from cap definitions)

    **Multiplexed execution** (CBOR mode): Multiple requests can be processed concurrently.
    Each request handler runs in its own thread, allowing the runtime to:
    - Respond to heartbeats while handlers are running
    - Accept new requests while previous ones are still processing
    - Handle multiple concurrent cap invocations
    """

    def __init__(self, manifest_data: bytes):
        """Create a new cartridge runtime with the required manifest.

        The manifest is JSON-encoded cartridge metadata including:
        - name: Cartridge name
        - version: Cartridge version
        - caps: Array of capability definitions with args and sources

        This manifest is sent in the HELLO response to the host (CBOR mode)
        and used for CLI argument parsing (CLI mode).
        **Cartridges MUST provide a manifest - there is no fallback.**
        """
        self.handlers: Dict[str, OpFactory] = {}
        self.manifest_data = manifest_data
        self.limits = Limits.default()

        # Try to parse the manifest for CLI mode support
        try:
            manifest_dict = json.loads(manifest_data)
            self.manifest = CapManifest.from_dict(manifest_dict)
        except Exception:
            self.manifest = None

        # Auto-register standard handlers
        self._register_standard_caps()

    @classmethod
    def with_manifest(cls, manifest: CapManifest):
        """Create a new cartridge runtime with a pre-built CapManifest.
        This is the preferred method as it ensures the manifest is valid.

        IMPORTANT: Manifest MUST declare CAP_IDENTITY - fails hard if missing.
        """
        # Validate manifest - FAIL HARD if CAP_IDENTITY not declared
        from capdag.standard.caps import CAP_IDENTITY
        identity_urn = CapUrn.from_string(CAP_IDENTITY)

        has_identity = any(
            identity_urn.conforms_to(cap.urn) or cap.urn.conforms_to(identity_urn)
            for cap in manifest.all_caps()
        )

        if not has_identity:
            raise ValueError(
                "Manifest validation failed - cartridge MUST declare CAP_IDENTITY (cap:). "
                "All cartridges must explicitly declare capabilities, no implicit fallbacks allowed."
            )

        manifest_data = json.dumps(manifest.to_dict()).encode('utf-8')
        instance = cls(manifest_data)
        instance.manifest = manifest
        return instance

    @classmethod
    def with_manifest_json(cls, manifest_json: str):
        """Create a new cartridge runtime with manifest JSON string."""
        return cls(manifest_json.encode('utf-8'))

    def _register_standard_caps(self) -> None:
        """Register the standard identity, discard, and adapter-selection handlers.

        Cartridge authors can override any by calling register_op() after construction.
        """
        from capdag.standard.caps import CAP_IDENTITY, CAP_DISCARD, CAP_ADAPTER_SELECTION

        # Auto-register if not already present (mirrors Rust: find_handler check)
        if self.find_handler(CAP_IDENTITY) is None:
            self.register_op_type(CAP_IDENTITY, IdentityOp)

        if self.find_handler(CAP_DISCARD) is None:
            self.register_op_type(CAP_DISCARD, DiscardOp)

        if self.find_handler(CAP_ADAPTER_SELECTION) is None:
            self.register_op_type(CAP_ADAPTER_SELECTION, AdapterSelectionOp)

    def register_op(self, cap_urn: str, factory: OpFactory) -> None:
        """Register an Op factory for a cap URN.
        The factory creates a fresh Op[None] instance per invocation.
        """
        self.handlers[cap_urn] = factory

    def register_op_type(self, cap_urn: str, op_class: type) -> None:
        """Register an Op class for a cap URN. Instance created via op_class() per invocation."""
        self.handlers[cap_urn] = op_class

    def find_handler(self, cap_urn: str) -> Optional[OpFactory]:
        """Find an Op factory for a cap URN.
        Returns the factory if found, None otherwise.

        Uses is_dispatchable(provider, request): can this registered handler
        dispatch the incoming request? Mirrors Rust exactly:
          `registered_urn.is_dispatchable(&request_urn)`

        Ranks by: non-negative signed distance (refinement/exact) first,
        then by smallest absolute distance. This prevents identity handlers
        from stealing routes from specific handlers.
        """
        # First try exact match
        if cap_urn in self.handlers:
            return self.handlers[cap_urn]

        # Then try pattern matching via CapUrn
        try:
            request_urn = CapUrn.from_string(cap_urn)
        except Exception:
            return None

        request_specificity = request_urn.specificity()
        matches = []  # (handler, signed_distance)

        for registered_cap_str, handler in self.handlers.items():
            try:
                registered_urn = CapUrn.from_string(registered_cap_str)
                # Use is_dispatchable: can this provider handle this request?
                if registered_urn.is_dispatchable(request_urn):
                    specificity = registered_urn.specificity()
                    signed_distance = specificity - request_specificity
                    matches.append((handler, signed_distance))
            except Exception:
                continue

        if not matches:
            return None

        # Rank: non-negative distance (refinement/exact) before negative (fallback),
        # then by smallest absolute distance
        matches.sort(key=lambda m: (0 if m[1] >= 0 else 1, abs(m[1])))
        return matches[0][0]

    def run(self) -> None:
        """Run the cartridge runtime.

        **Mode Detection**:
        - No CLI arguments: Cartridge CBOR mode (stdin/stdout binary frames)
        - Any CLI arguments: CLI mode (parse args from cap definitions)

        **CLI Mode**:
        - `manifest` subcommand: output manifest JSON
        - `<op>` subcommand: find cap by op tag, parse args, invoke handler
        - `--help`: show available subcommands

        **Cartridge CBOR Mode** (no CLI args):
        1. Receive HELLO from host
        2. Send HELLO back with manifest (handshake)
        3. Main loop reads frames:
           - REQ frames: spawn handler thread, continue reading
           - HEARTBEAT frames: respond immediately
           - RES/CHUNK/END frames: route to pending peer requests
           - Other frames: ignore
        4. Exit when stdin closes, wait for active handlers to complete

        **Multiplexing** (CBOR mode): The main loop never blocks on handler execution.
        Handlers run in separate threads, allowing concurrent processing
        of multiple requests and immediate heartbeat responses.

        **Bidirectional communication** (CBOR mode): Handlers can invoke caps on the host
        using the `PeerInvoker` parameter. Response frames from the host are
        routed to the appropriate pending request by MessageId.
        """
        args = sys.argv

        # No CLI arguments at all → Cartridge CBOR mode
        if len(args) == 1:
            return self.run_cbor_mode()

        # Any CLI arguments → CLI mode
        return self.run_cli_mode(args)

    def run_cli_mode(self, args: List[str]) -> None:
        """Run in CLI mode - parse arguments and invoke handler."""
        if self.manifest is None:
            raise ManifestError("Failed to parse manifest for CLI mode")

        # Handle --help at top level
        if len(args) == 2 and args[1] in ['--help', '-h']:
            self.print_help(self.manifest)
            return

        subcommand = args[1]

        # Handle manifest subcommand (always provided by runtime)
        if subcommand == 'manifest':
            print(json.dumps(self.manifest.to_dict(), indent=2))
            return

        # Handle subcommand --help
        if len(args) == 3 and args[2] in ['--help', '-h']:
            cap = self.find_cap_by_command(self.manifest, subcommand)
            if cap:
                self.print_cap_help(cap)
                return

        # Find cap by command name
        cap = self.find_cap_by_command(self.manifest, subcommand)
        if cap is None:
            raise UnknownSubcommandError(
                f"Unknown subcommand '{subcommand}'. Run with --help to see available commands."
            )

        # Find handler factory
        factory = self.find_handler(cap.urn_string())
        if factory is None:
            raise NoHandlerError(f"No handler registered for cap '{cap.urn_string()}'")

        # Build raw CBOR arguments payload (file-path values still raw strings).
        cli_args = args[2:]
        raw_payload = self.build_payload_from_cli(cap, cli_args)

        # CLI-mode foreach iteration. If any file-path arg with is_sequence=False
        # resolved to multiple files, this returns one per-iteration payload per
        # resolved file. Otherwise it returns the single original payload.
        iterations = build_cli_foreach_iterations(raw_payload, cap)
        for per_iter in iterations:
            payload = extract_effective_payload(per_iter, "application/cbor", cap, True)
            self._dispatch_cli_payload(cap, factory, payload)

    def _dispatch_cli_payload(self, cap: Cap, factory: 'OpFactory', payload: bytes) -> None:
        """Dispatch one CLI-mode invocation: take the (already file-path-resolved)
        CBOR arguments payload, build input frames, and run the handler.

        Mirrors capdag/src/bifaci/cartridge_runtime.rs::dispatch_cli_payload.
        """
        request_id = MessageId(0)
        frames: queue.Queue = queue.Queue()

        try:
            arguments = cbor2.loads(payload) if payload else []
        except Exception as e:
            print(f"Failed to decode CBOR arguments: {e}", file=sys.stderr)
            return

        for i, arg in enumerate(arguments):
            if not isinstance(arg, dict):
                continue
            media_urn = arg.get("media_urn")
            value = arg.get("value")
            if not isinstance(media_urn, str) or value is None:
                continue
            stream_id = f"arg-{i}"
            frames.put(Frame.stream_start(request_id, stream_id, media_urn))
            cbor_encoded = cbor2.dumps(value)
            frames.put(Frame.chunk(request_id, stream_id, 0, cbor_encoded, 0, compute_checksum(cbor_encoded)))
            frames.put(Frame.stream_end(request_id, stream_id, 1))

        frames.put(Frame.end(request_id, None))
        frames.put(None)  # Signal end of stream

        emitter = CliStreamEmitter()
        peer = NoPeerInvoker()

        try:
            dispatch_op(factory(), frames, emitter, peer)
        except Exception as e:
            error_json = {"error": str(e), "code": "HANDLER_ERROR"}
            print(json.dumps(error_json), file=sys.stderr)
            raise

    def run_cbor_mode(self) -> None:
        """Run in Cartridge CBOR mode - binary frame protocol via stdin/stdout."""
        # Lock stdin for reading (single reader)
        reader = FrameReader(sys.stdin.buffer)
        # SyncFrameWriter: thread-safe writer with centralized SeqAssigner.
        # All frames written through this get monotonically increasing seq per flow.
        # Matches Rust cartridge_runtime writer thread + SeqAssigner.
        raw_writer = FrameWriter(sys.stdout.buffer)
        sync_writer = SyncFrameWriter(raw_writer)

        # Perform handshake - send our manifest in the HELLO response
        # Handshake uses raw_writer directly (HELLO is non-flow, seq doesn't matter)
        try:
            limits = handshake_accept(reader, raw_writer, self.manifest_data)
            reader.set_limits(limits)
            sync_writer.set_limits(limits)
            self.limits = limits
        except Exception as e:
            print(f"[CartridgeRuntime] Handshake failed: {e}", file=sys.stderr)
            raise

        # Track pending peer requests (cartridge invoking host caps)
        pending_peer_requests: Dict[str, PendingPeerRequest] = {}
        pending_lock = threading.Lock()

        # Track incoming requests that are being chunked
        pending_incoming: Dict[str, PendingIncomingRequest] = {}
        pending_incoming_lock = threading.Lock()

        # Track active handler threads for cleanup
        active_handlers: List[threading.Thread] = []

        # Process requests - main loop stays responsive
        while True:
            # Clean up finished handlers periodically
            active_handlers = [h for h in active_handlers if h.is_alive()]

            try:
                frame = reader.read()
            except Exception as e:
                print(f"[CartridgeRuntime] Read error: {e}", file=sys.stderr)
                break

            if frame is None:
                # EOF - stdin closed, exit cleanly
                break

            if frame.frame_type == FrameType.REQ:
                # Extract routing_id (XID) FIRST — all error paths must include it
                routing_id_for_errors = frame.routing_id

                cap_urn = frame.cap
                if cap_urn is None:
                    err_frame = Frame.err(
                        frame.id,
                        "INVALID_REQUEST",
                        "Request missing cap URN"
                    )
                    err_frame.routing_id = routing_id_for_errors
                    try:
                        sync_writer.write(err_frame)
                    except Exception:
                        pass
                    continue

                raw_payload = frame.payload if frame.payload is not None else b""

                # Protocol v2: REQ must have empty payload — arguments come as streams
                if len(raw_payload) > 0:
                    err_frame = Frame.err(
                        frame.id,
                        "PROTOCOL_ERROR",
                        "REQ frame must have empty payload — use STREAM_START for arguments"
                    )
                    err_frame.routing_id = routing_id_for_errors
                    try:
                        sync_writer.write(err_frame)
                    except Exception:
                        pass
                    continue

                # Start tracking this request — streams will be added via STREAM_START
                # Capture routing_id (XID) from the REQ frame — must be propagated to all response frames
                with pending_incoming_lock:
                    pending_incoming[frame.id.to_string()] = PendingIncomingRequest(
                        cap_urn=cap_urn,
                        content_type=frame.content_type,
                        streams=[],
                        ended=False,
                        routing_id=frame.routing_id,  # XID for response routing
                    )
                continue  # Wait for STREAM_START/CHUNK/STREAM_END/END frames

            elif frame.frame_type == FrameType.HEARTBEAT:
                # Respond to heartbeat immediately - never blocked by handlers
                response = Frame.heartbeat(frame.id)
                try:
                    sync_writer.write(response)
                except Exception as e:
                    print(f"[CartridgeRuntime] Failed to write heartbeat response: {e}", file=sys.stderr)
                    break

            elif frame.frame_type == FrameType.HELLO:
                # Unexpected HELLO after handshake - protocol error
                err_frame = Frame.err(frame.id, "PROTOCOL_ERROR", "Unexpected HELLO after handshake")
                try:
                    sync_writer.write(err_frame)
                except Exception:
                    pass

            elif frame.frame_type == FrameType.CHUNK:
                # Protocol v2: CHUNK must have stream_id
                if frame.stream_id is None:
                    err_frame = Frame.err(frame.id, "PROTOCOL_ERROR", "CHUNK frame missing stream_id")
                    try:
                        sync_writer.write(err_frame)
                    except Exception:
                        pass
                    continue

                # Verify checksum (protocol v2 integrity check)
                try:
                    verify_chunk_checksum(frame)
                except ValueError as e:
                    err_frame = Frame.err(frame.id, "CORRUPTED_DATA", str(e))
                    try:
                        sync_writer.write(err_frame)
                    except Exception:
                        pass
                    continue

                stream_id = frame.stream_id

                # Check if this is a chunk for an incoming request
                with pending_incoming_lock:
                    frame_id_str = frame.id.to_string()
                    if frame_id_str in pending_incoming:
                        pending_req = pending_incoming[frame_id_str]

                        # FAIL HARD: Request already ended
                        if pending_req.ended:
                            del pending_incoming[frame_id_str]
                            err_frame = Frame.err(frame.id, "PROTOCOL_ERROR", "CHUNK after request END")
                            try:
                                sync_writer.write(err_frame)
                            except Exception:
                                pass
                            continue

                        # FAIL HARD: Unknown stream
                        found_stream = None
                        for sid, stream in pending_req.streams:
                            if sid == stream_id:
                                found_stream = stream
                                break

                        if found_stream is None:
                            del pending_incoming[frame_id_str]
                            err_frame = Frame.err(frame.id, "PROTOCOL_ERROR", f"CHUNK for unknown stream_id: {stream_id}")
                            try:
                                sync_writer.write(err_frame)
                            except Exception:
                                pass
                            continue

                        # FAIL HARD: Stream already ended
                        if found_stream.complete:
                            del pending_incoming[frame_id_str]
                            err_frame = Frame.err(frame.id, "PROTOCOL_ERROR", f"CHUNK for ended stream: {stream_id}")
                            try:
                                sync_writer.write(err_frame)
                            except Exception:
                                pass
                            continue

                        # Valid chunk for active stream
                        if frame.payload:
                            found_stream.chunks.append(frame.payload)
                        continue  # Wait for more chunks or STREAM_END

                # Not an incoming request chunk - must be a peer response chunk
                # Forward bare Frame to handler's queue
                frame_id_str = frame.id.to_string()
                with pending_lock:
                    if frame_id_str in pending_peer_requests:
                        pending_req = pending_peer_requests[frame_id_str]
                        pending_req.queue.put(frame)

            elif frame.frame_type == FrameType.END:
                # Protocol v2: END marks the end of all streams for this request
                pending_req = None
                with pending_incoming_lock:
                    frame_id_str = frame.id.to_string()
                    if frame_id_str in pending_incoming:
                        pending_req = pending_incoming.pop(frame_id_str)
                        if pending_req:
                            pending_req.ended = True

                if pending_req:
                    # Find handler factory
                    factory = self.find_handler(pending_req.cap_urn)
                    if not factory:
                        err_frame = Frame.err(frame.id, "NO_HANDLER", f"No handler registered for cap: {pending_req.cap_urn}")
                        err_frame.routing_id = pending_req.routing_id  # Propagate XID
                        try:
                            sync_writer.write(err_frame)
                        except Exception:
                            pass
                        continue

                    # Bind values for handler thread (default args capture by value,
                    # not by reference — avoids closure-in-a-loop bug where the
                    # loop reassigns these variables before the thread starts).
                    _request_id = frame.id
                    _streams_snapshot = list(pending_req.streams)
                    _cap_urn = pending_req.cap_urn
                    _factory = factory
                    _max_chunk = self.limits.max_chunk
                    _routing_id = pending_req.routing_id  # XID from incoming REQ

                    def handle_streamed_request(
                        request_id=_request_id,
                        streams_snapshot=_streams_snapshot,
                        cap_urn_clone=_cap_urn,
                        factory=_factory,
                        max_chunk=_max_chunk,
                        routing_id=_routing_id,
                    ):
                        import uuid as _uuid
                        response_stream_id = f"resp-{_uuid.uuid4().hex[:8]}"
                        # SyncFrameWriter assigns seq centrally for all frames
                        # routing_id (XID) is propagated from incoming REQ to all response frames
                        emitter = ThreadSafeEmitter(sync_writer, request_id, response_stream_id, "media:", routing_id, max_chunk)
                        peer_invoker = PeerInvokerImpl(sync_writer, pending_peer_requests, max_chunk)

                        # Create queue and populate with request frames
                        frames = queue.Queue()
                        try:
                            # Convert streams to Frame sequence: STREAM_START → CHUNK → STREAM_END → END
                            for stream_id, stream in streams_snapshot:
                                # STREAM_START
                                frames.put(Frame.stream_start(request_id, stream_id, stream.media_urn))

                                # CHUNKs
                                for seq, chunk_data in enumerate(stream.chunks):
                                    frames.put(Frame.chunk(request_id, stream_id, seq, chunk_data, seq, compute_checksum(chunk_data)))

                                # STREAM_END
                                frames.put(Frame.stream_end(request_id, stream_id, len(stream.chunks)))

                            # END
                            frames.put(Frame.end(request_id, None))
                            frames.put(None)  # Signal end of stream
                        except Exception as e:
                            err_frame = Frame.err(request_id, "PAYLOAD_ERROR", str(e))
                            err_frame.routing_id = routing_id  # Propagate XID
                            try:
                                sync_writer.write(err_frame)
                            except Exception as write_err:
                                print(f"[CartridgeRuntime] Failed to write error response: {write_err}", file=sys.stderr)
                            return

                        # Execute Op handler
                        try:
                            dispatch_op(factory(), frames, emitter, peer_invoker)

                            # Finalize: STREAM_END + END (seq assigned by SyncFrameWriter)
                            emitter.finalize()

                        except Exception as e:
                            err_frame = Frame.err(request_id, "HANDLER_ERROR", str(e))
                            err_frame.routing_id = routing_id  # Propagate XID
                            try:
                                sync_writer.write(err_frame)
                            except Exception as write_err:
                                print(f"[CartridgeRuntime] Failed to write error response: {write_err}", file=sys.stderr)

                    thread = threading.Thread(target=handle_streamed_request, daemon=True)
                    thread.start()
                    active_handlers.append(thread)
                    continue

                # Not an incoming request end - must be a peer response end
                # Forward bare Frame to handler's queue and close channel
                frame_id_str = frame.id.to_string()
                with pending_lock:
                    if frame_id_str in pending_peer_requests:
                        pending_req = pending_peer_requests[frame_id_str]
                        pending_req.ended = True
                        pending_req.queue.put(frame)
                        pending_req.queue.put(None)  # Signal end of stream
                        del pending_peer_requests[frame_id_str]

            elif frame.frame_type == FrameType.STREAM_START:
                # Protocol v2: A new stream is starting for a request
                if frame.stream_id is None:
                    err_frame = Frame.err(frame.id, "PROTOCOL_ERROR", "STREAM_START missing stream_id")
                    try:
                        sync_writer.write(err_frame)
                    except Exception:
                        pass
                    continue

                if frame.media_urn is None:
                    err_frame = Frame.err(frame.id, "PROTOCOL_ERROR", "STREAM_START missing media_urn")
                    try:
                        sync_writer.write(err_frame)
                    except Exception:
                        pass
                    continue

                stream_id = frame.stream_id
                media_urn = frame.media_urn

                # Check if this is for an incoming request (cartridge receiving from host)
                with pending_incoming_lock:
                    frame_id_str = frame.id.to_string()
                    if frame_id_str in pending_incoming:
                        pending_req = pending_incoming[frame_id_str]

                        # FAIL HARD: Request already ended
                        if pending_req.ended:
                            del pending_incoming[frame_id_str]
                            err_frame = Frame.err(frame.id, "PROTOCOL_ERROR", "STREAM_START after request END")
                            try:
                                sync_writer.write(err_frame)
                            except Exception:
                                pass
                            continue

                        # FAIL HARD: Duplicate stream_id
                        for sid, _ in pending_req.streams:
                            if sid == stream_id:
                                del pending_incoming[frame_id_str]
                                err_frame = Frame.err(frame.id, "PROTOCOL_ERROR", f"Duplicate stream_id: {stream_id}")
                                try:
                                    sync_writer.write(err_frame)
                                except Exception:
                                    pass
                                break
                        else:
                            # No duplicate — add new stream
                            pending_req.streams.append((stream_id, PendingStream(
                                media_urn=media_urn,
                                chunks=[],
                                complete=False
                            )))
                        continue

                # Not an incoming request - must be a peer response stream start
                # Forward bare Frame to handler's queue
                with pending_lock:
                    if frame_id_str in pending_peer_requests:
                        pending_req = pending_peer_requests[frame_id_str]
                        pending_req.queue.put(frame)

            elif frame.frame_type == FrameType.STREAM_END:
                # Protocol v2: A stream has ended for a request
                if frame.stream_id is None:
                    err_frame = Frame.err(frame.id, "PROTOCOL_ERROR", "STREAM_END missing stream_id")
                    try:
                        sync_writer.write(err_frame)
                    except Exception:
                        pass
                    continue

                stream_id = frame.stream_id

                # Check if this is for an incoming request (cartridge receiving from host)
                with pending_incoming_lock:
                    frame_id_str = frame.id.to_string()
                    if frame_id_str in pending_incoming:
                        pending_req = pending_incoming[frame_id_str]

                        # Find and mark stream as complete
                        found = False
                        for sid, stream in pending_req.streams:
                            if sid == stream_id:
                                stream.complete = True
                                found = True
                                break

                        if not found:
                            del pending_incoming[frame_id_str]
                            err_frame = Frame.err(frame.id, "PROTOCOL_ERROR", f"STREAM_END for unknown stream_id: {stream_id}")
                            try:
                                sync_writer.write(err_frame)
                            except Exception:
                                pass
                        continue

                # Not an incoming request - must be a peer response stream end
                # Forward bare Frame to handler's queue
                with pending_lock:
                    if frame_id_str in pending_peer_requests:
                        pending_req = pending_peer_requests[frame_id_str]
                        pending_req.queue.put(frame)

            elif frame.frame_type == FrameType.ERR:
                # Error frame from host - could be response to peer request
                # Forward bare Frame to handler's queue and close channel
                frame_id_str = frame.id.to_string()
                with pending_lock:
                    if frame_id_str in pending_peer_requests:
                        pending_req = pending_peer_requests[frame_id_str]
                        pending_req.ended = True
                        pending_req.queue.put(frame)
                        pending_req.queue.put(None)  # Signal end of stream
                        del pending_peer_requests[frame_id_str]

            elif frame.frame_type == FrameType.LOG:
                # Route LOG frames to peer response channels.
                # During peer calls, the peer sends LOG frames (progress, status)
                # that the handler needs to receive in real-time for activity
                # timeout prevention and progress forwarding.
                frame_id_str = frame.id.to_string()
                with pending_lock:
                    if frame_id_str in pending_peer_requests:
                        pending_req = pending_peer_requests[frame_id_str]
                        pending_req.queue.put(frame)

            elif frame.frame_type in (FrameType.RELAY_NOTIFY, FrameType.RELAY_STATE):
                # Relay-level frames must never reach a cartridge runtime.
                # If they do, it's a bug in the relay layer — fail hard.
                raise ProtocolError(
                    f"Relay frame {frame.frame_type} must not reach cartridge runtime"
                )

        # Wait for all active handlers to complete before exiting
        for thread in active_handlers:
            thread.join(timeout=5.0)  # 5 second timeout per thread

    def find_cap_by_command(self, manifest: CapManifest, command_name: str) -> Optional[Cap]:
        """Find a cap by its command name (the CLI subcommand)."""
        for cap in manifest.all_caps():
            if cap.command == command_name:
                return cap
        return None

    def _get_positional_args(self, args: List[str]) -> List[str]:
        """Get positional arguments (non-flag arguments).

        Filters out CLI flags (starting with '-') and their values.
        """
        positional = []
        skip_next = False

        for arg in args:
            if skip_next:
                skip_next = False
                continue
            if arg.startswith('-'):
                # This is a flag - skip its value too
                if '=' not in arg:
                    skip_next = True
            else:
                positional.append(arg)

        return positional

    def _get_cli_flag_value(self, args: List[str], flag: str) -> Optional[str]:
        """Get value for a CLI flag (e.g., --model "value").

        Supports both formats:
        - --flag value
        - --flag=value
        """
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == flag:
                if i + 1 < len(args):
                    return args[i + 1]
                return None
            # Handle --flag=value format
            if arg.startswith(f"{flag}="):
                return arg[len(flag) + 1:]
            i += 1
        return None

    def _read_stdin_if_available(self) -> Optional[bytes]:
        """Read stdin if data is available (non-blocking check).

        Returns None immediately if stdin is a terminal or no data is ready.
        """
        import select

        # Don't read from stdin if it's a terminal (interactive)
        if sys.stdin.isatty():
            return None

        # Check if we're in a test environment where stdin is captured
        # (DontReadFromInput from pytest)
        if hasattr(sys.stdin, 'read') and 'DontReadFromInput' in type(sys.stdin).__name__:
            return None

        try:
            # Non-blocking check: use select with 0 timeout to see if data is ready
            ready, _, _ = select.select([sys.stdin], [], [], 0)

            # No data ready - return None immediately without blocking
            if not ready:
                return None

            # Data is ready - read it
            data = sys.stdin.buffer.read()
            if not data:
                return None
            return data
        except (OSError, IOError):
            # stdin not available or can't be read
            return None

    def _build_payload_from_streaming_reader(self, cap: Cap, reader, max_chunk: int) -> bytes:
        """Build CBOR payload from streaming reader (testable version).

        This simulates the CBOR chunked request flow for CLI piped stdin:
        - Pure binary chunks from reader
        - Accumulated in chunks (respecting max_chunk size)
        - Built into CBOR arguments array (same format as CBOR mode)

        This makes all 4 modes use the SAME payload format:
        - CLI file path → read file → payload
        - CLI piped binary → chunk reader → payload
        - CBOR chunked → payload
        - CBOR file path → auto-convert → payload

        Args:
            cap: The capability being invoked
            reader: Binary stream reader (e.g., io.BytesIO)
            max_chunk: Maximum chunk size for reading

        Returns:
            CBOR-encoded array of CapArgumentValue objects

        Raises:
            IOError: If reader encounters an error
        """
        # Accumulate chunks
        chunks = []
        total_bytes = 0

        while True:
            chunk = reader.read(max_chunk)
            if not chunk:
                break
            chunks.append(chunk)
            total_bytes += len(chunk)

        # Concatenate chunks
        complete_payload = b''.join(chunks)

        # Build CBOR arguments array (same format as CBOR mode)
        cap_urn = CapUrn.from_string(cap.urn_string())
        expected_media_urn = cap_urn.in_spec()

        arg = CapArgumentValue(media_urn=expected_media_urn, value=complete_payload)

        # Encode as CBOR array
        cbor_args = [
            {
                "media_urn": arg.media_urn,
                "value": arg.value,
            }
        ]

        return cbor2.dumps(cbor_args)


    def build_payload_from_cli(self, cap: Cap, cli_args: List[str]) -> bytes:
        """Build the raw CBOR arguments payload from CLI args.

        Mirrors capdag/src/bifaci/cartridge_runtime.rs::build_payload_from_cli.

        File-path values stay as raw path/glob strings here — file reading
        and glob expansion happen later in extract_effective_payload (after
        CLI-mode foreach iteration via build_cli_foreach_iterations).
        """
        # Check for stdin data if cap accepts stdin (non-blocking).
        stdin_data: Optional[bytes] = None
        if cap.accepts_stdin():
            stdin_data = self._read_stdin_if_available()

        arguments: List[CapArgumentValue] = []
        for arg_def in cap.get_args():
            value, came_from_stdin = self._extract_arg_value(arg_def, cli_args, stdin_data)
            if value is not None:
                # Determine media_urn: if value came from stdin source, use stdin's media_urn.
                # Otherwise use arg's media_urn as-is (file-path conversion happens later).
                media_urn = arg_def.media_urn
                if came_from_stdin:
                    from capdag.cap.definition import StdinSource as _StdinSource
                    for s in arg_def.sources:
                        if isinstance(s, _StdinSource):
                            media_urn = s.stdin
                            break
                arguments.append(CapArgumentValue(media_urn=media_urn, value=value))
            elif arg_def.required:
                raise MissingArgumentError(f"Required argument '{arg_def.media_urn}' not provided")

        # If no arguments are defined but stdin data exists, use it as raw payload.
        if not cap.get_args():
            if stdin_data is not None:
                return stdin_data
            return b''

        if arguments:
            cbor_args = [
                {"media_urn": arg.media_urn, "value": arg.value}
                for arg in arguments
            ]
            try:
                return cbor2.dumps(cbor_args)
            except Exception as e:
                raise SerializeError(f"Failed to encode CBOR payload: {e}")

        return b''

    def _extract_arg_value(
        self,
        arg_def: CapArg,
        cli_args: List[str],
        stdin_data: Optional[bytes],
    ) -> Tuple[Optional[bytes], bool]:
        """Extract a single argument value from CLI args or stdin.

        Mirrors capdag/src/bifaci/cartridge_runtime.rs::extract_arg_value.

        Returns (value, came_from_stdin). RAW values only — file-path
        auto-conversion happens later in extract_effective_payload, after
        CLI-mode foreach iteration.
        """
        from capdag.cap.definition import StdinSource, PositionSource, CliFlagSource

        for source in arg_def.sources:
            if isinstance(source, CliFlagSource):
                value = self._get_cli_flag_value(cli_args, source.cli_flag)
                if value is not None:
                    return value.encode('utf-8'), False
            elif isinstance(source, PositionSource):
                positional = self._get_positional_args(cli_args)
                pos = source.position
                if pos < len(positional):
                    return positional[pos].encode('utf-8'), False
            elif isinstance(source, StdinSource):
                if stdin_data is not None:
                    return stdin_data, True

        # Try default value
        if arg_def.default_value is not None:
            try:
                return json.dumps(arg_def.default_value).encode('utf-8'), False
            except Exception as e:
                raise SerializeError(str(e))

        return None, False


    def print_help(self, manifest: CapManifest) -> None:
        """Print help message showing all available subcommands."""
        print(f"{manifest.name} v{manifest.version}", file=sys.stderr)
        print(manifest.description, file=sys.stderr)
        print(file=sys.stderr)
        print("USAGE:", file=sys.stderr)
        print(f"    {manifest.name.lower()} <COMMAND> [OPTIONS]", file=sys.stderr)
        print(file=sys.stderr)
        print("COMMANDS:", file=sys.stderr)
        print("    manifest    Output the cartridge manifest as JSON", file=sys.stderr)

        for cap in manifest.all_caps():
            desc = cap.cap_description or cap.title
            print(f"    {cap.command:<12} {desc}", file=sys.stderr)

        print(file=sys.stderr)
        print(f"Run '{manifest.name.lower()} <COMMAND> --help' for more information on a command.", file=sys.stderr)

    def print_cap_help(self, cap: Cap) -> None:
        """Print help for a specific cap."""
        print(cap.title, file=sys.stderr)
        if cap.cap_description:
            print(cap.cap_description, file=sys.stderr)
        print(file=sys.stderr)
        print("USAGE:", file=sys.stderr)
        print(f"    cartridge {cap.command} [OPTIONS]", file=sys.stderr)
        print(file=sys.stderr)

        args = cap.get_args()
        if args:
            print("OPTIONS:", file=sys.stderr)
            for arg in args:
                required = " (required)" if arg.required else ""
                desc = arg.arg_description or ""

                for source in arg.sources:
                    if isinstance(source, dict) and 'cli_flag' in source:
                        print(f"    {source['cli_flag']:<16} {desc}{required}", file=sys.stderr)
                    elif isinstance(source, dict) and 'position' in source:
                        print(f"    <arg{source['position']}>          {desc}{required}", file=sys.stderr)
                    elif isinstance(source, dict) and 'stdin' in source:
                        print(f"    (stdin: {source['stdin']}) {desc}{required}", file=sys.stderr)

    def get_limits(self) -> Limits:
        """Get the current protocol limits"""
        return self.limits
