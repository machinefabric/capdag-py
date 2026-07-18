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
from enum import Enum
from pathlib import Path
from typing import Callable, Protocol, Optional, Dict, List, Any, Tuple
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import cbor2

from ops import Op, OpMetadata, DryContext, WetContext, ExecutionFailedError

from capdag.bifaci.frame import (
    Frame, FrameType, Limits, MessageId, DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK,
    DEFAULT_INITIAL_CREDIT, CreditDirection, DropReason, FailureClass,
    compute_checksum, verify_chunk_checksum, SeqAssigner, FlowKey,
)
from capdag.bifaci.io import handshake_accept, FrameReader, FrameWriter, CborError, ProtocolError
from capdag.bifaci.credit import CreditGate, CreditRouter, CreditClosed
from capdag.bifaci.stats import DropCounters, DropSnapshot, TerminatedFlows
from capdag.cap.caller import CapArgumentValue
from capdag.cap.definition import ArgSource, Cap, CapArg, CliFlagSource
from capdag.urn.cap_urn import CapUrn
from capdag.bifaci.manifest import CapManifest
from capdag.urn.media_urn import MediaUrn, MediaUrnError, MEDIA_FILE_PATH


class RuntimeError(Exception):
    """Errors that can occur in the cartridge runtime"""

    def failure_class(self) -> FailureClass:
        """The failure class this error DECLARES (docs/failure-taxonomy.md).
        `ClassifiedError` carries its origin's declaration; a `RemoteError`
        carries the class the PEER's frame declared; everything else is
        INTERNAL — unclassified means "ours", never a guess."""
        return FailureClass.INTERNAL

    def failure_code(self) -> Optional[str]:
        """The machine-readable code declared at the emit source, when carried."""
        return None

    def failure_arg_urn(self) -> Optional[str]:
        """The media URN of the argument the failure is attributed to,
        declared at the emit source (docs/failure-taxonomy.md); None when
        the failure carries no attribution."""
        return None

    def failure_reason(self) -> str:
        """The LEAF human reason — the origin's own message for classified
        failures, the exception text otherwise."""
        return str(self)


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


class ClassifiedError(RuntimeError):
    """A handler failure carrying its FULL identity: the machine-readable
    code the cartridge's typed error declares (`error_code()`-style), the
    failure class it declares (whose problem it is), the human message, and
    — when the failure is attributed to a specific argument — the media URN
    of that argument, declared at the emit source. Handlers raise this
    instead of folding the code into message text; the ERR frame carries the
    declared fields to the engine (docs/failure-taxonomy.md). Untyped
    failures stay `HandlerError` and classify as INTERNAL at the frame
    boundary. (matches Rust RuntimeError::Classified)
    """

    def __init__(self, code: str, failure_class: FailureClass, message: str,
                 arg_urn: Optional[str] = None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.declared_class = failure_class
        self.message = message
        self.arg_urn = arg_urn

    def failure_class(self) -> FailureClass:
        return self.declared_class

    def failure_code(self) -> Optional[str]:
        return self.code

    def failure_arg_urn(self) -> Optional[str]:
        return self.arg_urn

    def failure_reason(self) -> str:
        return self.message


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


# =============================================================================
# WRITER-THREAD TERMINAL GATE (L4) — drop post-terminal flow frames, counted
# =============================================================================

class GatedWrite(str, Enum):
    """Outcome of pushing one frame through the terminal gate + writer.

    (matches Rust cartridge_runtime::GatedWrite — WriterDead has no Python
    counterpart: a failed write raises instead, since callers in this mirror
    already handle write failures via exceptions rather than a sentinel.)
    """
    WRITTEN = "written"
    DROPPED_POST_TERMINAL = "dropped_post_terminal"


def write_gated(
    frame: Frame,
    writer: "FrameWriter",
    seq_assigner: SeqAssigner,
    terminated: TerminatedFlows,
    drops: DropCounters,
) -> GatedWrite:
    """Write one frame through the terminal gate (L4).

    Once a flow's END/ERR has been written, any later flow frame for the same
    FlowKey is post-terminal: it is dropped and counted, never written. This
    is the single point where wire order is decided, so gating here
    deterministically closes every detached-sender race (ProgressSender,
    keepalive tickers) — mirrors Rust's `write_gated` free function exactly,
    adapted to the mirror's synchronous single-writer-lock design (there is
    no separate writer *thread* here — `SyncFrameWriter.write()` IS the
    writer-thread equivalent, called from whichever handler thread is
    emitting).

    Raises whatever `writer.write()` raises on I/O failure — the caller's
    existing exception handling covers that path.
    """
    key = FlowKey.from_frame(frame)
    if frame.is_flow_frame() and terminated.contains(key):
        total = drops.record(DropReason.POST_TERMINAL)
        print(
            f"[CartridgeRuntime] writer: dropped post-terminal flow frame — "
            f"END/ERR already written for this flow (L4) "
            f"type={frame.frame_type} rid={frame.id.to_string()} "
            f"post_terminal_total={total}",
            file=sys.stderr,
        )
        return GatedWrite.DROPPED_POST_TERMINAL

    seq_assigner.assign(frame)
    writer.write(frame)
    if frame.frame_type in (FrameType.END, FrameType.ERR):
        seq_assigner.remove(key)
        terminated.insert(key)
    return GatedWrite.WRITTEN


class SyncFrameWriter:
    """Thread-safe frame writer with centralized SeqAssigner and the L4
    writer-terminal gate.

    All frames pass through the SeqAssigner before writing, ensuring
    monotonically increasing seq per flow (RID + optional XID). This matches
    the Rust cartridge_runtime writer thread with SeqAssigner and Go's
    syncFrameWriter — extended for protocol v3 with the terminal gate
    (post-terminal flow frames are dropped and counted, never written) and
    counted drops on write failure (L8): a send on a dead writer is a counted
    `channel_closed` drop, never a silent loss, even for callers that ignore
    the outcome.
    """

    def __init__(self, writer: FrameWriter, drops: Optional[DropCounters] = None):
        self._writer = writer
        self._lock = threading.Lock()
        self._seq_assigner = SeqAssigner()
        self._terminated = TerminatedFlows(1024)
        self.drops = drops if drops is not None else DropCounters()

    def write(self, frame: Frame) -> GatedWrite:
        """Write a frame with centralized seq assignment (thread-safe),
        gated against post-terminal flow frames (L4).

        A write failure (e.g. broken pipe) is a counted `channel_closed`
        drop (L8) before the exception propagates — callers that swallow the
        exception (fire-and-forget best-effort sends) still get it counted.
        """
        with self._lock:
            try:
                return write_gated(frame, self._writer, self._seq_assigner, self._terminated, self.drops)
            except Exception:
                total = self.drops.record(DropReason.CHANNEL_CLOSED)
                print(
                    f"[CartridgeRuntime] frame dropped: output channel closed "
                    f"(channel_closed_total={total}) type={frame.frame_type} "
                    f"rid={frame.id.to_string()}",
                    file=sys.stderr,
                )
                raise

    def set_limits(self, limits: Limits) -> None:
        with self._lock:
            self._writer.set_limits(limits)


# =============================================================================
# CONCURRENCY CAPACITY — dynamic handler-slot limit
# =============================================================================

class CapacityHandle:
    """Shared handle for dynamic concurrency capacity adjustment (thread-safe).

    Cartridges receive this via `CartridgeRuntime.capacity_handle()` and can
    call `set(n)` at any time to adjust how many concurrent requests the
    runtime will dispatch to handlers. 0 means unlimited.
    (matches Rust CapacityHandle)
    """

    def __init__(self, initial: int):
        self._lock = threading.Lock()
        self._value = initial

    def set(self, n: int) -> None:
        with self._lock:
            self._value = n

    def get(self) -> int:
        with self._lock:
            return self._value


# =============================================================================
# LIVE INPUT MODEL — incremental per-item demux, never buffer-then-dispatch
# (protocol v3, L16). Replaces the old CreditWindowAccountant/buffered-
# PendingIncomingRequest regime: input streams are consumed item-by-item as
# frames arrive, exactly mirroring the Rust reference's InputStream::recv()/
# demux_multi_stream. Buffering collectors (collect_*) refuse unbounded
# streams (L16) instead of buffering without bound.
# =============================================================================

class StreamError(RuntimeError):
    """Error raised/returned by the live input-stream primitives
    (InputStream, InputPackage, PeerResponse, the demux threads). Mirrors
    the Rust reference's `StreamError` enum — the mirror uses a single
    exception type with a descriptive message rather than separate variants,
    consistent with this codebase's exception-per-concern idiom."""
    pass


class RemoteError(StreamError):
    """The peer's ERR frame, kept STRUCTURAL: its machine-readable code, the
    failure class the peer's frame declared (docs/failure-taxonomy.md), its
    message — never folded into prose — and the media URN of the argument
    the peer's frame attributed the failure to (None when the frame carried
    no attribution). (matches Rust StreamError::RemoteError)
    """

    def __init__(self, code: str, failure_class: FailureClass, message: str,
                 arg_urn: Optional[str] = None):
        super().__init__(f"Remote error [{code}]: {message}")
        self.code = code
        self.declared_class = failure_class
        self.message = message
        self.arg_urn = arg_urn

    def failure_class(self) -> FailureClass:
        return self.declared_class

    def failure_code(self) -> Optional[str]:
        return self.code

    def failure_arg_urn(self) -> Optional[str]:
        return self.arg_urn

    def failure_reason(self) -> str:
        return self.message


def _classify_handler_error(e: Exception) -> tuple:
    """Resolve the identity a failed handler's terminal ERR frame declares
    (docs/failure-taxonomy.md): the code, class, and argument attribution
    from the emit source when the exception is classified (a
    `ClassifiedError`, or a peer's `RemoteError` propagated as-is),
    HANDLER_ERROR/INTERNAL without attribution when the handler never
    declared one. Returns (code, failure_class, message, arg_urn).
    (matches Rust RuntimeError's accessors at the frame-emit boundary)"""
    if isinstance(e, RuntimeError):
        code = e.failure_code()
        if code is not None:
            return code, e.failure_class(), e.failure_reason(), e.failure_arg_urn()
    return "HANDLER_ERROR", FailureClass.INTERNAL, str(e), None


class _WindowCounter:
    """Thread-safe per-stream credit window used for receive-side violation
    accounting (L12). The demux decrements it per arriving chunk; the
    handler's consumption grants (via `InputGrantEmitter`) extend it."""

    def __init__(self, initial: int):
        self._lock = threading.Lock()
        self._value = initial

    def add(self, n: int) -> None:
        with self._lock:
            self._value += n

    def fetch_sub_one(self) -> int:
        """Decrement by one; return the value BEFORE the decrement."""
        with self._lock:
            before = self._value
            self._value -= 1
            return before


class InputGrantEmitter:
    """Emits CREDIT grants for one input stream as the handler consumes it
    (L10). Grants are batched: one CREDIT per `batch` consumed chunks.

    Deadlock-freedom rule (L10): a receiver MUST flush pending grants before
    blocking on an empty input — `InputStream.recv()` calls `flush()` right
    before it would otherwise block on `queue.Queue.get()`. Batching is a
    latency optimization negotiated per link; the sender's window may come
    from a DIFFERENT link's negotiation, so a sender can legally stall below
    this receiver's batch threshold. Flushing at the block point guarantees
    progress under any window/batch mismatch.
    """

    def __init__(
        self,
        writer: "SyncFrameWriter",
        rid: MessageId,
        xid: Optional[MessageId],
        stream_id: Optional[str],
        direction: CreditDirection,
        batch: int,
        window: _WindowCounter,
    ):
        self._writer = writer
        self._rid = rid
        self._xid = xid
        self._stream_id = stream_id
        self._direction = direction
        self._batch = max(batch, 1)
        self._consumed_since_grant = 0
        self._window = window
        self._lock = threading.Lock()

    def consumed(self) -> None:
        """Record one consumed chunk; emit a batched CREDIT grant when due."""
        with self._lock:
            self._consumed_since_grant += 1
            due = self._consumed_since_grant >= self._batch
        if due:
            self.flush()

    def flush(self) -> None:
        """Emit any pending (sub-batch) grant immediately."""
        with self._lock:
            if self._consumed_since_grant == 0:
                return
            n = self._consumed_since_grant
            self._consumed_since_grant = 0
        self._window.add(n)
        frame = Frame.credit(self._rid, self._stream_id, n, self._direction)
        frame.routing_id = self._xid
        try:
            self._writer.write(frame)
        except Exception:
            # A failed grant send means the runtime is shutting down; the
            # sender-side gate will be closed by the terminal path.
            pass

    def fragment_sibling(self) -> "InputGrantEmitter":
        """Build a second emitter over the SAME window/sender for the
        demux's fragment crediting on sequence streams, with `batch = 1` so
        every grant flushes immediately. Immediate flushing is load-bearing:
        the demux only runs when frames arrive, so a batched (held) grant
        while the producer is stalled on exactly that credit would deadlock
        the stream mid-item (L10 has no other flush point inside the demux).
        """
        return InputGrantEmitter(
            writer=self._writer,
            rid=self._rid,
            xid=self._xid,
            stream_id=self._stream_id,
            direction=self._direction,
            batch=1,
            window=self._window,
        )


@dataclass
class InputCreditContext:
    """Everything the demux needs to credit a request's input streams: grant
    plumbing for the handler side and per-stream violation windows."""
    writer: "SyncFrameWriter"
    rid: MessageId
    xid: Optional[MessageId]
    initial_credit: int


@dataclass
class SeqReassembly:
    """Reassembly state for one sequence-mode input stream (`is_sequence =
    True` on STREAM_START). Sequence producers (`emit_list_item`) CBOR-encode
    each item once and split the encoded bytes across CHUNK frames at
    max_chunk boundaries — a frame payload is a raw RFC 8742 fragment, NOT a
    self-contained CBOR value. The demux must therefore buffer fragments and
    decode at item granularity; decoding per frame fails with a truncated-CBOR
    error on any item larger than max_chunk (the bug class that broke
    cap→cap forwarding of rendered page images)."""
    buf: bytearray = field(default_factory=bytearray)
    item_meta: Optional[dict] = None
    fragment_grants: Optional[InputGrantEmitter] = None


def try_decode_sequence_item(buf: bytes):
    """Try to decode one self-delimiting CBOR item from the front of `buf`.

    Returns a 3-tuple ``(status, value_or_error, consumed)``:
    - ``("ok", value, consumed)`` — one complete item; `consumed` bytes used.
    - ``("prefix", None, None)`` — `buf` holds only a prefix of an item; wait
      for more frames. (CBOR definite-length encoding is prefix-free, so a
      truncated item can never mis-decode as a complete one.)
    - ``("error", exception, None)`` — the bytes are not valid CBOR at all.
    """
    stream = io.BytesIO(buf)
    try:
        value = cbor2.load(stream)
        return ("ok", value, stream.tell())
    except cbor2.CBORDecodeEOF:
        return ("prefix", None, None)
    except Exception as e:
        return ("error", e, None)


class StreamEmitter(Protocol):
    """A streaming emitter that writes chunks immediately to the output.
    Thread-safe for use in concurrent handlers.
    Handlers emit CBOR values via emit_cbor() or logs via emit_log().
    The value is CBOR-encoded once and sent as raw CBOR bytes in CHUNK frames.
    No double-encoding: one CBOR layer from handler to consumer.
    """

    def start(self, is_sequence: bool = False, meta: Optional[dict] = None) -> None:
        """Send STREAM_START with the given mode, carrying whole-stream
        metadata (provenance, titles, …). Must be called (if at all) before
        the first emission — mirrors the reference's
        ``OutputStream::start(is_sequence, meta)``."""
        ...

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
    def data_ok(value, meta: Optional[dict] = None) -> "PeerResponseItem":
        """Create a Data item with a decoded CBOR value and optional per-item metadata."""
        return PeerResponseItem(data=("ok", value, meta))

    @staticmethod
    def data_err(error: Exception, meta: Optional[dict] = None) -> "PeerResponseItem":
        """Create a Data item with an error."""
        return PeerResponseItem(data=("err", error, meta))

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
        kind, val, _meta = self._data
        if kind == "err":
            raise val
        return val

    @property
    def data_error(self) -> Optional[Exception]:
        """Get the error if this is a Data(Err) item, None otherwise."""
        if self._data is None:
            return None
        kind, val, _meta = self._data
        return val if kind == "err" else None

    @property
    def data_meta(self) -> Optional[dict]:
        """Get the per-item metadata of a Data item, None if absent or not a Data item."""
        if self._data is None:
            return None
        _kind, _val, meta = self._data
        return meta

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

    def __init__(self, q: queue.Queue, grants: Optional[InputGrantEmitter] = None):
        self._queue = q
        # Consumption grants for the responding peer's output window
        # (L10/L14). None = uncredited context (synthetic test responses).
        self._grants = grants

    def recv(self) -> Optional[PeerResponseItem]:
        """Receive the next item (data or LOG) from the peer response.
        Returns None when the stream ends.

        Data consumption replenishes the responding peer's output window —
        a slow consumer naturally throttles the producer (L10). About to
        block: flushes any pending grant first (L10 deadlock-freedom rule).
        """
        try:
            item = self._queue.get_nowait()
        except queue.Empty:
            if self._grants is not None:
                self._grants.flush()
            item = self._queue.get()
        if item is not None and item.is_data and item.data_error is None and self._grants is not None:
            self._grants.consumed()
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
class ActiveRequest:
    """Tracks one in-flight incoming request for LIVE frame routing (protocol
    v3, L16). Unlike the old buffer-then-dispatch regime (PendingIncomingRequest),
    this holds no accumulated stream state — every STREAM_START/CHUNK/
    STREAM_END/END frame for this request is routed onto `raw_queue` the
    instant it arrives, and the handler thread's `demux_multi_stream` drains
    it live. Registered the instant REQ is seen (mirrors the Rust reference's
    `active_requests` map — frames route here even before the handler thread
    is actually spawned, e.g. while capacity-queued).
    """
    cap_urn: str
    routing_id: Optional["MessageId"]
    raw_queue: queue.Queue = field(default_factory=queue.Queue)


class PeerInvokerImpl:
    """Implementation of PeerInvoker that sends REQ frames to the host.

    Enables bidirectional communication where a cartridge handler can invoke caps
    on the host while processing a request.
    """

    def __init__(
        self,
        writer: SyncFrameWriter,
        pending_requests: Dict[str, PendingPeerRequest],
        max_chunk: Optional[int] = None,
        credit_router: Optional[CreditRouter] = None,
        initial_credit: int = DEFAULT_INITIAL_CREDIT,
    ):
        self.writer = writer
        self.pending_requests = pending_requests
        self.pending_lock = threading.Lock()
        self.max_chunk = max_chunk if max_chunk is not None else DEFAULT_MAX_CHUNK
        # Router that delivers inbound CREDIT grants to this cartridge's
        # outgoing peer-argument streams (L14 — peer args are credited too).
        # None = uncredited context (in-process host, tests).
        self.credit_router = credit_router
        self.initial_credit = initial_credit

    def invoke(self, cap_urn: str, arguments: List[CapArgumentValue]) -> queue.Queue:
        """Invoke a cap on the host with arguments.

        Protocol v2: Sends REQ(empty) + STREAM_START + CHUNK(s) + STREAM_END + END
        for each argument as an independent stream.
        Returns a queue that receives bare Frame objects from the host.
        Seq is assigned centrally by SyncFrameWriter's SeqAssigner.

        Each argument stream acquires one credit per CHUNK before sending it
        when a credit_router was supplied (L9/L14) — a slow peer naturally
        throttles this cartridge's arg emission. Blocking acquisition:
        `invoke()` already runs on a plain thread by design.
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

                # Credit gate for this arg stream — registers with the shared
                # router so inbound CREDIT frames from the host replenish it.
                gate = None
                if self.credit_router is not None:
                    gate = CreditGate(self.initial_credit)
                    self.credit_router.register(request_id, stream_id, gate)

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

                    if gate is not None:
                        try:
                            gate.acquire(1)
                        except CreditClosed as e:
                            raise PeerRequestError(str(e))
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


@dataclass
class FinalStatus:
    """A handler's terminal status override, carried in the END frame's
    terminal metadata (L3/L5). Declared via `ThreadSafeEmitter.finish()`.
    (matches Rust OutputStream::FinalStatus)
    """
    progress: float
    message: Optional[str] = None


class ThreadSafeEmitter:
    """Thread-safe implementation of StreamEmitter using Protocol v2 stream multiplexing.

    Automatically sends STREAM_START before the first emission, then CHUNK frames
    with stream_id. Caller MUST call finalize() after handler returns to send
    STREAM_END + END.

    Seq is assigned centrally by the SyncFrameWriter's SeqAssigner — this emitter
    does NOT track seq itself. This matches the Rust cartridge_runtime writer thread
    with SeqAssigner and Go's threadSafeEmitter with syncFrameWriter.

    Flow control (protocol v3, L9): when constructed with a `credit_router`,
    every CHUNK acquires one credit before it is sent — a slow consumer
    naturally throttles this emitter. `write`/`emit_list_item` block the
    calling thread on an exhausted window; `blocking_write`/
    `blocking_emit_list_item` are aliases (this emitter is already
    thread-based, so there is no separate async/blocking distinction to
    make — matches `capdag.bifaci.credit`'s own alias idiom). LOG/progress
    frames are never credited (L14) — they must flow even while the data
    window is exhausted.
    """

    def __init__(
        self,
        writer: SyncFrameWriter,
        request_id: MessageId,
        stream_id: str,
        media_urn: str,
        routing_id: Optional[MessageId] = None,
        max_chunk: Optional[int] = None,
        credit_router: Optional[CreditRouter] = None,
        initial_credit: int = DEFAULT_INITIAL_CREDIT,
    ):
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
        # Whether the started stream is sequence-mode (emit_list_item — CBOR
        # fragments reassembled at item granularity on the receiving end) or
        # write-mode (write/emit_cbor — each CHUNK is a self-contained CBOR
        # value). None until the stream is started. Mixing modes on one
        # stream is a protocol error — the receiver's demux decodes the two
        # shapes completely differently (scalar-per-frame vs RFC-8742
        # fragment reassembly), so declaring the wrong one on STREAM_START
        # silently corrupts every downstream cap→cap forward of a
        # multi-fragment item.
        self._is_sequence_mode: Optional[bool] = None
        # Whether this stream was started unbounded (no length promise, L16).
        self.unbounded = False
        # Per-stream flow-control window (L9). None = uncredited context
        # (CLI mode, tests, in-process host) — writes never wait.
        self._credit_gate = CreditGate(initial_credit) if credit_router is not None else None
        self._credit_router = credit_router
        # Handler-declared terminal status (progress + message), read by the
        # runtime after the handler returns to stamp the END frame (L3/L5).
        self._final_status_lock = threading.Lock()
        self._final_status: Optional[FinalStatus] = None

    def _check_mode(self, is_sequence: bool) -> None:
        """Fail hard on mixing write-mode (write/emit_cbor) and sequence-mode
        (emit_list_item) emissions on the same stream — the receiver's demux
        decodes the two shapes incompatibly, so a mismatch here silently
        corrupts the stream instead of failing at the point of misuse."""
        if self._is_sequence_mode is not None and self._is_sequence_mode != is_sequence:
            raise HandlerError(
                f"stream already started in {'sequence' if self._is_sequence_mode else 'write'} "
                f"mode; cannot emit in {'sequence' if is_sequence else 'write'} mode"
            )

    def _ensure_stream_started(
        self, is_sequence: bool = False, meta: Optional[dict] = None, unbounded: bool = False,
    ) -> None:
        """Send STREAM_START if not yet sent, declaring the wire mode this
        stream actually uses (`is_sequence`) — REQUIRED for the receiver's
        demux to reassemble multi-fragment sequence items correctly (L16/
        RFC 8742). Seq and routing_id assigned here.

        Registers this stream's credit gate so inbound CREDIT frames find it.
        """
        with self.stream_lock:
            self._check_mode(is_sequence)
            if not self.stream_started:
                self.stream_started = True
                self._is_sequence_mode = is_sequence
                self.unbounded = unbounded
                if self._credit_gate is not None and self._credit_router is not None:
                    self._credit_router.register(self.request_id, self.stream_id, self._credit_gate)
                if unbounded:
                    start_frame = Frame.stream_start_unbounded(
                        self.request_id, self.stream_id, self.media_urn, is_sequence,
                    )
                else:
                    start_frame = Frame.stream_start(
                        self.request_id, self.stream_id, self.media_urn, is_sequence,
                    )
                if meta is not None:
                    start_frame.meta = dict(meta)
                start_frame.routing_id = self.routing_id  # Propagate XID from incoming REQ
                self.writer.write(start_frame)

    def start(self, is_sequence: bool = False, meta: Optional[dict] = None) -> None:
        """Send STREAM_START with the given mode, carrying whole-stream
        metadata (provenance, titles, …) — mirrors the reference's
        ``OutputStream::start(is_sequence, meta)``. Handlers propagate their
        input's stream meta here so provenance survives the hop. Must be
        called (if at all) before the first emission; emissions without an
        explicit start still auto-start the stream, but with no meta."""
        self._ensure_stream_started(is_sequence=is_sequence, meta=meta, unbounded=False)

    def start_unbounded(self, is_sequence: bool = False, meta: Optional[dict] = None) -> None:
        """Send STREAM_START for an UNBOUNDED response — one that makes no
        length promise (L16). `finalize()` then sends STREAM_END without a
        chunk_count. Must be called (if at all) before the first emission."""
        self._ensure_stream_started(is_sequence=is_sequence, meta=meta, unbounded=True)

    def _acquire_credit(self) -> None:
        """Acquire one chunk of credit, blocking if the window is exhausted.
        Uncredited emitters return immediately. A closed gate (request
        terminated/cancelled) fails the write — the producer must stop (L13).
        """
        if self._credit_gate is not None:
            try:
                self._credit_gate.acquire(1)
            except CreditClosed as e:
                raise HandlerError(str(e))

    def finish(self, progress: float, message: str = "") -> None:
        """Declare the request's terminal status (final progress + message),
        delivered in the END frame's terminal metadata when the handler
        completes successfully (L3/L5). Optional — without a call, a
        successful END carries progress 1.0. The last call before the
        handler returns wins. Do NOT emit a trailing 100% progress LOG
        frame; the END terminal metadata IS the final progress event and
        cannot race END.
        """
        with self._final_status_lock:
            self._final_status = FinalStatus(
                progress=float(progress),
                message=message if message else None,
            )

    def take_final_status(self) -> Optional[FinalStatus]:
        """Read (and clear) the handler-declared terminal status. Called by
        the runtime after the handler returns to stamp the END frame."""
        with self._final_status_lock:
            status = self._final_status
            self._final_status = None
            return status

    def emit_cbor(self, value: Any) -> None:
        """Emit a CBOR value as output.

        CHUNK payloads = complete, independently decodable CBOR values.

        Streams might never end (logs, video, real-time data), so each CHUNK must be
        processable immediately without waiting for END frame.

        For bytes/str: split raw data, encode each chunk as complete value
        For other types: encode once (typically small)

        Each CHUNK payload can be decoded independently: cbor2.loads(chunk.payload)
        Seq is assigned by SyncFrameWriter — pass 0 as placeholder.
        Awaits (blocks) per chunk when the flow-control window is exhausted (L9).
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
                self._acquire_credit()
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
                self._acquire_credit()
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
                self._acquire_credit()
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
                self._acquire_credit()
                self.writer.write(frame)

        else:
            # For other types (int, float, bool, None): encode as single chunk
            cbor_payload = cbor2.dumps(value)

            with self.chunk_lock:
                idx = self.chunk_index
                self.chunk_index += 1

            frame = Frame.chunk(self.request_id, self.stream_id, 0, cbor_payload, idx, compute_checksum(cbor_payload))
            frame.routing_id = self.routing_id  # Propagate XID from incoming REQ
            self._acquire_credit()
            self.writer.write(frame)

    def finalize(self) -> None:
        """Send STREAM_END + END to complete the response.
        Must be called exactly once after the handler returns.
        If handler never emitted, sends STREAM_START first for protocol consistency.
        Seq assigned by SyncFrameWriter for all frames.

        The END frame carries the terminal metadata (L3/L5): the handler's
        declared final status (via `finish()`), or the 1.0 default. Final
        progress rides IN the terminal frame — it cannot race it.
        """
        # Ensure STREAM_START was sent (even if handler emitted nothing)
        self._ensure_stream_started()

        # STREAM_END (seq assigned by SyncFrameWriter). Unbounded streams
        # (started via start_unbounded) carry no chunk_count promise (L16).
        if self.unbounded:
            stream_end = Frame.stream_end_unbounded(self.request_id, self.stream_id)
        else:
            stream_end = Frame.stream_end(self.request_id, self.stream_id, self.chunk_index)
        stream_end.routing_id = self.routing_id  # Propagate XID from incoming REQ
        self.writer.write(stream_end)

        # END (seq assigned by SyncFrameWriter) — carries the final progress.
        declared = self.take_final_status()
        progress = declared.progress if declared is not None else 1.0
        message = declared.message if declared is not None else None
        end_frame = Frame.end_ok_with(self.request_id, None, progress, message)
        end_frame.routing_id = self.routing_id  # Propagate XID from incoming REQ
        self.writer.write(end_frame)

    def write(self, data: bytes) -> None:
        """Write raw bytes as output, split into max_chunk-sized CHUNK frames.

        Unlike emit_cbor which CBOR-encodes the value, this sends raw bytes
        directly as frame payloads. Each chunk is independently processable.

        Awaits (blocks) per chunk when the flow-control window is exhausted
        (L9); the receiver's consumption replenishes it. `blocking_write` is
        an alias — see class docstring.
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
            self._acquire_credit()
            self.writer.write(frame)

            offset += chunk_size

    def blocking_write(self, data: bytes) -> None:
        """Alias for `write` — see class docstring on the blocking/async split."""
        self.write(data)

    def emit_list_item(self, value: Any) -> None:
        """Emit a single CBOR value as one item in an RFC 8742 CBOR sequence.

        For list outputs: the receiver concatenates raw frame payloads and stores
        the result as a CBOR sequence. This method CBOR-encodes the value, then
        splits the encoded bytes across chunk frames at max_chunk boundaries.
        The receiver's concatenation reconstructs the original CBOR encoding,
        producing exactly one self-delimiting CBOR value in the sequence per call.

        Unlike emit_cbor (which re-wraps each piece as a separate CBOR value),
        this sends raw CBOR bytes as frame payloads directly.

        Awaits (blocks) per chunk when the flow-control window is exhausted
        (L9). `blocking_emit_list_item` is an alias — see class docstring.

        Declares the stream sequence-mode on STREAM_START (`is_sequence=True`)
        — REQUIRED so the receiver's demux reassembles multi-fragment items
        at item granularity (RFC 8742) instead of trying to decode each raw
        fragment as an independent CBOR value.
        """
        self._ensure_stream_started(is_sequence=True)
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
            self._acquire_credit()
            self.writer.write(frame)

            offset += chunk_size

    def blocking_emit_list_item(self, value: Any) -> None:
        """Alias for `emit_list_item` — see class docstring on the blocking/async split."""
        self.emit_list_item(value)

    def emit_log(self, level: str, message: str) -> None:
        """Emit a log message at the given level.
        Sends a LOG frame (side-channel, does not affect response stream).
        Seq assigned by SyncFrameWriter. Never credited (L14) — control
        frames must flow even while the data window is exhausted."""
        frame = Frame.log(self.request_id, level, message)
        frame.routing_id = self.routing_id  # Propagate XID from incoming REQ
        self.writer.write(frame)

    def progress(self, progress: float, message: str) -> None:
        """Emit a progress update (0.0-1.0) with a human-readable status message.
        Never credited (L14) — control frames must flow even while the data
        window is exhausted."""
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
    to access streaming input, output emitter, and peer invocation.
    """

    def __init__(self, input_package: "InputPackage", emitter: "StreamEmitter", peer: "PeerInvoker"):
        self._input = input_package
        self._emitter = emitter
        self._peer = peer
        self._consumed = False
        self._lock = threading.Lock()

    def take_input(self) -> "InputPackage":
        """Take the input package. Can only be called once — second call raises error."""
        with self._lock:
            if self._consumed:
                raise HandlerError("Input already consumed")
            self._consumed = True
            return self._input

    def emitter(self) -> "StreamEmitter":
        """Access the output stream emitter."""
        return self._emitter

    def peer(self) -> "PeerInvoker":
        """Access the peer invoker."""
        return self._peer


class InputStream:
    """A single input stream — yields decoded CBOR values with optional
    per-item metadata from CHUNK frames, delivered INCREMENTALLY as they
    arrive off the wire (protocol v3, L16) — never buffered to completion.
    Handler never sees Frame, STREAM_START, STREAM_END, checksum, seq, or index.

    Metadata semantics depend on mode:
    - Non-sequence: `stream_meta()` returns the STREAM_START metadata (whole-stream).
    - Sequence: `recv()` delivers per-item metadata from CHUNK frames.

    `recv()` returns one of: ``None`` (stream ended), an ``Exception``
    instance (a decode/protocol error — inspect or raise it), or a
    ``(value, meta)`` tuple. This mirrors the Rust reference's
    ``Option<Result<(Value, Option<StreamMeta>), StreamError>>`` without a
    dedicated Result wrapper type — callers that don't care about the error
    path can just check `isinstance(item, Exception)`.
    """

    def __init__(
        self,
        media_urn: str,
        stream_meta: Optional[dict],
        q: queue.Queue,
        unbounded: bool = False,
        grants: Optional[InputGrantEmitter] = None,
    ):
        self._media_urn = media_urn
        self._stream_meta = stream_meta
        self._queue = q
        self._unbounded = unbounded
        self._grants = grants

    def media_urn(self) -> str:
        return self._media_urn

    def stream_meta(self) -> Optional[dict]:
        """Stream-level metadata from STREAM_START (non-sequence mode)."""
        return self._stream_meta

    def is_unbounded(self) -> bool:
        """Whether the sender declared this stream unbounded — no length
        promise; consume incrementally with `recv()`, never with the
        `collect_*` buffering helpers (L16)."""
        return self._unbounded

    def recv(self):
        """Receive the next (value, meta) item, an Exception on a stream
        error, or None when the stream ends.

        Consumption replenishes the sender's flow-control window (L10) — a
        slow handler naturally throttles the producer. About to block:
        flushes any pending batched grant first (L10 deadlock-freedom rule)
        — the producer may be stalled waiting for exactly this credit.
        """
        try:
            item = self._queue.get_nowait()
        except queue.Empty:
            if self._grants is not None:
                self._grants.flush()
            item = self._queue.get()
        if item is not None and not isinstance(item, Exception) and self._grants is not None:
            self._grants.consumed()
        return item

    def recv_data(self):
        """Like `recv()` but discards per-item metadata: value, Exception, or None."""
        item = self.recv()
        if item is None or isinstance(item, Exception):
            return item
        value, _meta = item
        return value

    def _check_bounded(self, method: str) -> None:
        """Refuse buffering on unbounded streams (L16) — buffering an
        unbounded stream is unbounded memory; the failure must be explicit,
        not an OOM."""
        if self._unbounded:
            raise StreamError(
                f"{method} refused: stream is unbounded (no length promise) — "
                "consume incrementally with recv() (L16)"
            )

    def collect_items(self) -> List[Tuple[bytes, Optional[dict]]]:
        """Collect each chunk as a separate item with its metadata.
        For sequence streams (is_sequence=True), each delivered value is one
        item. Returns a list of (raw_bytes, optional_per_item_meta).

        Fails hard on streams declared unbounded (L16)."""
        self._check_bounded("collect_items")
        items: List[Tuple[bytes, Optional[dict]]] = []
        while True:
            item = self.recv()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            value, meta = item
            if isinstance(value, bytes):
                b = value
            elif isinstance(value, str):
                b = value.encode("utf-8")
            else:
                b = cbor2.dumps(value)
            items.append((b, meta))
        return items

    def collect_bytes(self) -> bytes:
        """Collect all chunks into a single byte vector. Extracts inner
        bytes from bytes/str values and concatenates; other types are
        CBOR-encoded. Per-item metadata is discarded.

        Fails hard on streams declared unbounded (L16) — there is no finite
        buffer for a stream with no length promise."""
        self._check_bounded("collect_bytes")
        result = bytearray()
        while True:
            item = self.recv()
            if item is None:
                return bytes(result)
            if isinstance(item, Exception):
                raise item
            value, _meta = item
            if isinstance(value, bytes):
                result.extend(value)
            elif isinstance(value, str):
                result.extend(value.encode("utf-8"))
            else:
                result.extend(cbor2.dumps(value))

    def collect_value(self):
        """Collect a single CBOR value (expects exactly one chunk).
        Per-item metadata is discarded.

        Fails hard on streams declared unbounded (L16)."""
        self._check_bounded("collect_value")
        item = self.recv()
        if item is None:
            raise StreamError("Stream closed")
        if isinstance(item, Exception):
            raise item
        value, _meta = item
        return value


class InputPackage:
    """The bundle of all input arg streams for one request. Yields
    InputStream objects as STREAM_START frames arrive from the wire — LIVE,
    not buffered to completion. Returns None after END (all args delivered).
    """

    def __init__(self, q: queue.Queue):
        self._queue = q

    def recv(self):
        """Get the next input stream, an Exception on a demux-level protocol
        error, or None at request end."""
        return self._queue.get()

    def collect_all_bytes(self) -> bytes:
        """Collect all streams' bytes into a single byte vector.

        WARNING: Only call this if you know all streams are finite (and
        bounded — this fails hard on any unbounded stream, L16)."""
        result = bytearray()
        while True:
            stream = self.recv()
            if stream is None:
                return bytes(result)
            if isinstance(stream, Exception):
                raise stream
            result.extend(stream.collect_bytes())

    def collect_streams(self) -> List[Tuple[str, bytes, Optional[dict]]]:
        """Collect each stream individually into a list of
        (media_urn, bytes, stream_meta) triples. Each stream's bytes are
        accumulated separately — NOT concatenated. Use `find_stream()`
        helpers to retrieve args by URN pattern matching.

        WARNING: Only call this if you know all streams are finite."""
        result: List[Tuple[str, bytes, Optional[dict]]] = []
        while True:
            stream = self.recv()
            if stream is None:
                return result
            if isinstance(stream, Exception):
                raise stream
            urn = stream.media_urn()
            meta = stream.stream_meta()
            data = stream.collect_bytes()
            result.append((urn, data, meta))


def demux_multi_stream(
    raw_rx: queue.Queue,
    credit: Optional[InputCreditContext] = None,
) -> InputPackage:
    """Demux for multi-stream mode (handler input). Spawns a background
    thread that reads the raw per-request Frame queue and splits it into
    per-stream InputStream channels, delivered LIVE as frames arrive — never
    buffered to completion (protocol v3, L16).

    `raw_rx` is fed by the main loop's live per-request routing: frames for
    this request are `put()` onto it as they arrive off the wire, even while
    this thread is still draining earlier ones. The loop below blocks on
    `raw_rx.get()` exactly like the Rust reference's `for frame in raw_rx`
    over a crossbeam receiver — it terminates on an explicit END/ERR frame,
    matching the wire protocol rather than relying on the queue being closed.

    Mirrors the Rust reference's `demux_multi_stream` (this mirror has no
    FilePathContext-driven CBOR-mode file materialization, so that branch of
    the reference is not ported — CLI-mode file-path resolution is handled
    entirely before frames reach this demux, see `build_payload_from_cli`).
    """
    streams_queue: queue.Queue = queue.Queue()

    def _worker() -> None:
        # stream_id -> per-stream item queue delivered to the handler.
        stream_channels: Dict[str, queue.Queue] = {}
        # stream_id -> remaining credit window (L10/L12). Starts at the
        # negotiated initial_credit; handler consumption (grants) extends
        # it; a chunk arriving with the window at zero is a fatal
        # CREDIT_VIOLATION. The demux itself never blocks on this — it only
        # accounts, so control frames keep flowing regardless of data
        # pressure.
        stream_windows: Dict[str, _WindowCounter] = {}
        # stream_id -> item reassembly state for sequence-mode streams (see
        # `SeqReassembly` — frame payloads are RFC 8742 fragments, decoded
        # at item granularity).
        seq_reassembly: Dict[str, SeqReassembly] = {}

        def _close_all_open_streams() -> None:
            for tx in stream_channels.values():
                tx.put(None)
            stream_channels.clear()

        while True:
            frame: Frame = raw_rx.get()

            if frame.frame_type == FrameType.STREAM_START:
                stream_id = frame.stream_id
                if stream_id is None:
                    streams_queue.put(StreamError("STREAM_START missing stream_id"))
                    break
                media_urn = frame.media_urn or ""

                chunk_q: queue.Queue = queue.Queue()
                stream_channels[stream_id] = chunk_q
                grants: Optional[InputGrantEmitter] = None
                if credit is not None:
                    window = _WindowCounter(credit.initial_credit)
                    stream_windows[stream_id] = window
                    grants = InputGrantEmitter(
                        writer=credit.writer,
                        rid=credit.rid,
                        xid=credit.xid,
                        stream_id=stream_id,
                        direction=CreditDirection.REQUEST,
                        batch=max(credit.initial_credit // 2, 1),
                        window=window,
                    )
                if frame.is_sequence:
                    seq_reassembly[stream_id] = SeqReassembly(
                        fragment_grants=grants.fragment_sibling() if grants is not None else None,
                    )
                input_stream = InputStream(
                    media_urn=media_urn,
                    stream_meta=frame.meta,
                    q=chunk_q,
                    unbounded=frame.is_unbounded(),
                    grants=grants,
                )
                streams_queue.put(input_stream)

            elif frame.frame_type == FrameType.CHUNK:
                stream_id = frame.stream_id or ""

                # Credit-violation check (L12): a chunk beyond the granted
                # window is a fatal protocol error for this request.
                window = stream_windows.get(stream_id)
                if window is not None:
                    before = window.fetch_sub_one()
                    if before <= 0:
                        tx = stream_channels.get(stream_id)
                        if tx is not None:
                            tx.put(StreamError(
                                f"CREDIT_VIOLATION: chunk received beyond the granted window "
                                f"on stream {stream_id} (L12)"
                            ))
                        continue

                tx = stream_channels.get(stream_id)
                if tx is not None and frame.payload:
                    payload = frame.payload
                    expected_checksum = frame.checksum
                    if expected_checksum is None:
                        tx.put(StreamError("CHUNK frame missing required checksum field"))
                        continue
                    actual = compute_checksum(payload)
                    if actual != expected_checksum:
                        tx.put(StreamError(
                            f"Checksum mismatch: expected={expected_checksum}, actual={actual}"
                        ))
                        continue
                    chunk_meta = frame.meta
                    seq = seq_reassembly.get(stream_id)
                    if seq is not None:
                        # Sequence stream: the payload is a raw RFC 8742
                        # fragment. Buffer it and deliver at ITEM granularity.
                        if len(seq.buf) == 0:
                            # First fragment of a new item carries the
                            # per-item metadata (emit_list_item contract).
                            seq.item_meta = chunk_meta
                        elif seq.fragment_grants is not None:
                            # Continuation fragment: credit it back
                            # immediately — the handler grants one frame per
                            # consumed ITEM, so without this an item
                            # spanning more frames than the credit window
                            # could never finish arriving.
                            seq.fragment_grants.consumed()
                        seq.buf.extend(payload)
                        while True:
                            status, a, b = try_decode_sequence_item(bytes(seq.buf))
                            if status == "ok":
                                value, consumed = a, b
                                del seq.buf[:consumed]
                                meta = seq.item_meta
                                seq.item_meta = None
                                tx.put((value, meta))
                                if len(seq.buf) == 0:
                                    break
                            elif status == "prefix":
                                break  # need more frames
                            else:
                                tx.put(StreamError(f"CBOR decode error: {a}"))
                                seq.buf.clear()
                                break
                    else:
                        # Scalar stream: every frame payload is a
                        # self-contained CBOR value (`write` wraps each
                        # piece as its own Value).
                        try:
                            value = cbor2.loads(payload)
                            tx.put((value, chunk_meta))
                        except Exception as e:
                            tx.put(StreamError(f"CBOR decode error: {e}"))

            elif frame.frame_type == FrameType.STREAM_END:
                stream_id = frame.stream_id or ""
                # Sequence stream ending mid-item is a truncation — surface
                # it, never silently drop the partial item.
                seq = seq_reassembly.pop(stream_id, None)
                tx = stream_channels.get(stream_id)
                if seq is not None and len(seq.buf) > 0 and tx is not None:
                    tx.put(StreamError(
                        f"sequence stream ended mid-item: {len(seq.buf)} trailing bytes "
                        "do not form a complete CBOR item"
                    ))
                tx = stream_channels.pop(stream_id, None)
                if tx is not None:
                    tx.put(None)
                stream_windows.pop(stream_id, None)

            elif frame.frame_type == FrameType.END:
                break

            elif frame.frame_type == FrameType.ERR:
                # Keep the peer's declared code/class/message structural —
                # never folded into prose (docs/failure-taxonomy.md).
                code = frame.error_code() or "UNKNOWN"
                failure_class = frame.error_class() or FailureClass.INTERNAL
                message = frame.error_message() or "Unknown error"
                arg_urn = frame.error_arg_urn()
                err = RemoteError(code, failure_class, message, arg_urn)
                for tx in stream_channels.values():
                    tx.put(err)
                _close_all_open_streams()
                streams_queue.put(RemoteError(code, failure_class, message, arg_urn))
                break

            else:
                pass  # Ignore LOG, HEARTBEAT, CREDIT, etc. — not demux concerns.

        _close_all_open_streams()
        streams_queue.put(None)

    threading.Thread(target=_worker, daemon=True).start()
    return InputPackage(streams_queue)


class OutputStream:
    """Synchronous output stream that emits STREAM_START/CHUNK/STREAM_END frames.

    Flow control (protocol v3, L9): when constructed with a `credit_router`,
    every CHUNK acquires one credit before it is sent — the receiver's
    consumption replenishes it. `write`/`emit_list_item` block the calling
    thread on an exhausted window; `blocking_write`/`blocking_emit_list_item`
    are aliases (this class is already thread-based/blocking throughout —
    matches `capdag.bifaci.credit`'s own alias idiom).
    """

    def __init__(
        self,
        writer: SyncFrameWriter,
        request_id: MessageId,
        stream_id: str,
        media_urn: str,
        routing_id: Optional[MessageId] = None,
        max_chunk: Optional[int] = None,
        credit_router: Optional[CreditRouter] = None,
        initial_credit: int = DEFAULT_INITIAL_CREDIT,
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
        # Whether this stream was started unbounded (no length promise, L16).
        self.unbounded = False
        self._lock = threading.Lock()
        # Per-stream flow-control window (L9). None = uncredited context —
        # writes never wait.
        self._credit_gate = CreditGate(initial_credit) if credit_router is not None else None
        self._credit_router = credit_router

    def _start_unlocked(
        self, is_sequence: bool = False, meta: Optional[dict] = None, unbounded: bool = False,
    ) -> None:
        if self.started:
            return
        # Register this stream's credit gate so inbound CREDIT frames find it.
        if self._credit_gate is not None and self._credit_router is not None:
            self._credit_router.register(self.request_id, self.stream_id, self._credit_gate)
        if unbounded:
            frame = Frame.stream_start_unbounded(
                self.request_id,
                self.stream_id,
                self.media_urn,
                is_sequence if is_sequence else None,
            )
        else:
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
        self.unbounded = unbounded

    def start(self, is_sequence: bool = False, meta: Optional[dict] = None) -> None:
        """Emit STREAM_START exactly once."""
        with self._lock:
            self._start_unlocked(is_sequence=is_sequence, meta=meta)

    def start_unbounded(self, is_sequence: bool = False, meta: Optional[dict] = None) -> None:
        """Send STREAM_START for an UNBOUNDED stream — one that makes no
        length promise (L16). The receiver must consume it incrementally;
        buffering collectors refuse it. `close()` on an unbounded stream
        sends STREAM_END without a chunk_count. Otherwise identical to
        `start()`."""
        with self._lock:
            self._start_unlocked(is_sequence=is_sequence, meta=meta, unbounded=True)

    def _acquire_credit(self) -> None:
        """Acquire one chunk of credit, blocking if the window is exhausted.
        Uncredited streams return immediately. A closed gate (request
        terminated/cancelled) fails the write — the producer must stop (L13).
        """
        if self._credit_gate is not None:
            try:
                self._credit_gate.acquire(1)
            except CreditClosed as e:
                raise RuntimeError(str(e))

    def _write_chunk_payload(self, payload: bytes) -> None:
        self._acquire_credit()
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

    def write(self, data: bytes) -> None:
        """Write raw bytes. Splits into max_chunk pieces, each wrapped as
        CBOR bytes. Requires `start(False)` (write mode) to have been called
        first. Awaits (blocks) per chunk when the flow-control window is
        exhausted (L9)."""
        with self._lock:
            if self.closed:
                raise RuntimeError("OutputStream already closed")
            if not self.started:
                self._start_unlocked()
            offset = 0
            while offset < len(data):
                chunk_size = min(self.max_chunk, len(data) - offset)
                self._write_chunk_payload(cbor2.dumps(data[offset:offset + chunk_size]))
                offset += chunk_size

    def blocking_write(self, data: bytes) -> None:
        """Alias for `write` — see class docstring on the blocking/async split."""
        self.write(data)

    def emit_cbor(self, value: Any) -> None:
        """Emit a CBOR value split into max_chunk-sized CHUNK payloads.
        Awaits (blocks) per chunk when the flow-control window is exhausted (L9)."""
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
        """Emit STREAM_END exactly once. Unbounded streams (started via
        `start_unbounded`) send STREAM_END with no chunk_count promise (L16)."""
        with self._lock:
            if self.closed:
                raise RuntimeError("OutputStream already closed")
            if not self.started:
                self._start_unlocked()
            if self.unbounded:
                frame = Frame.stream_end_unbounded(self.request_id, self.stream_id)
            else:
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
        credit_router: Optional[CreditRouter] = None,
        initial_credit: int = DEFAULT_INITIAL_CREDIT,
    ):
        self.writer = writer
        self.request_id = request_id
        self.response = response
        self.routing_id = routing_id
        self.max_chunk = max_chunk if max_chunk is not None else DEFAULT_MAX_CHUNK
        self.credit_router = credit_router
        self.initial_credit = initial_credit

    def arg(self, media_urn: str) -> OutputStream:
        """Create a new arg OutputStream for this peer call. Each arg is an
        independent stream (own stream_id, no routing_id), flow-controlled
        by the callee's consumption (L14)."""
        import uuid as _uuid

        return OutputStream(
            writer=self.writer,
            request_id=self.request_id,
            stream_id=str(_uuid.uuid4()),
            media_urn=media_urn,
            routing_id=self.routing_id,
            max_chunk=self.max_chunk,
            credit_router=self.credit_router,
            initial_credit=self.initial_credit,
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
    """Standard identity handler — pure passthrough. Forwards all input to output, live."""

    async def perform(self, dry: DryContext, wet: WetContext) -> None:
        req: Request = wet.get_required(WET_KEY_REQUEST)
        input_pkg = req.take_input()
        started = False
        while True:
            stream = input_pkg.recv()
            if stream is None:
                break
            if isinstance(stream, Exception):
                raise HandlerError(f"Identity input error: {stream}")
            if not started:
                # Propagate the first input stream's meta (provenance context).
                req.emitter().start(False, stream.stream_meta())
                started = True
            while True:
                item = stream.recv()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise HandlerError(f"Identity chunk error: {item}")
                value, _meta = item
                req.emitter().emit_cbor(value)
        if not started:
            # No input streams arrived — still start and close the output.
            req.emitter().start(False, None)

    def metadata(self) -> OpMetadata:
        return OpMetadata.builder("IdentityOp") \
            .description("Pure passthrough — forwards all input to output") \
            .build()


class DiscardOp(Op):
    """Standard discard handler — terminal morphism. Drains all input, produces nothing."""

    async def perform(self, dry: DryContext, wet: WetContext) -> None:
        req: Request = wet.get_required(WET_KEY_REQUEST)
        input_pkg = req.take_input()
        while True:
            stream = input_pkg.recv()
            if stream is None:
                break
            if isinstance(stream, Exception):
                raise HandlerError(f"Discard input error: {stream}")
            while True:
                item = stream.recv()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise HandlerError(f"Discard chunk error: {item}")

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
        input_pkg = req.take_input()
        while True:
            stream = input_pkg.recv()
            if stream is None:
                break
            if isinstance(stream, Exception):
                raise HandlerError(f"AdapterSelection input error: {stream}")
            while True:
                item = stream.recv()
                if item is None:
                    break
                if isinstance(item, Exception):
                    raise HandlerError(f"AdapterSelection chunk error: {item}")

    def metadata(self) -> OpMetadata:
        return OpMetadata.builder("AdapterSelectionOp") \
            .description("Default adapter selection — returns empty END (no match)") \
            .build()


def dispatch_op(
    op: Op,
    input_package: "InputPackage",
    emitter: "StreamEmitter",
    peer: "PeerInvoker",
) -> None:
    """Dispatch an Op with a Request via WetContext. Bridges sync handler threads to async Op.perform.

    `input_package` is the live, incrementally-delivered stream bundle
    produced by `demux_multi_stream()` — NOT a pre-buffered frame queue
    (protocol v3, L16).

    Raises HandlerError on Op failure.
    """
    req = Request(input_package, emitter, peer)
    dry = DryContext()
    wet = WetContext()
    wet.insert_ref(WET_KEY_REQUEST, req)
    try:
        asyncio.run(op.perform(dry, wet))
    except Exception as e:
        raise HandlerError(str(e))


def demux_peer_response(
    raw_frames: queue.Queue,
    writer: Optional[SyncFrameWriter] = None,
    request_id: Optional[MessageId] = None,
    initial_credit: int = DEFAULT_INITIAL_CREDIT,
) -> PeerResponse:
    """Demux a raw frame queue into a PeerResponse that yields PeerResponseItems,
    LIVE — items are delivered as frames arrive, never buffered to completion
    (protocol v3, L16). Spawns a background thread that reads frames from the
    raw queue and converts them into PeerResponseItems (Data or Log). Returns
    immediately so LOG frames can be consumed before data arrives (critical
    for keeping the engine's activity timer alive during long peer calls).

    This mirrors the Rust reference's `demux_single_stream()`, including
    item-granular sequence reassembly (SeqReassembly): a sequence-mode
    response (`is_sequence=True` on STREAM_START) CBOR-encodes each item once
    and splits it across CHUNK frames as raw RFC 8742 fragments — decoding
    each frame independently corrupts any item bigger than one chunk (the bug
    class that broke cap→cap forwarding of rendered page images). A sequence
    that ends mid-item is a hard decode error, never a silently dropped
    partial item.

    When `writer` and `request_id` are both supplied, data consumption emits
    batched RESPONSE-direction CREDIT grants (L10/L14) — a slow consumer
    naturally throttles the responding peer's output; continuation fragments
    of a sequence item are credited back immediately on arrival (fragment
    grants), matching the handler-input demux's fragment crediting. Mirrors
    the Rust reference's response-side crediting: consumption is granted, but
    (unlike the handler-input demux) the response side is not window-checked
    for violations.
    """
    item_queue: queue.Queue = queue.Queue(maxsize=256)
    grants: Optional[InputGrantEmitter] = None
    if writer is not None and request_id is not None:
        grants = InputGrantEmitter(
            writer=writer,
            rid=request_id,
            xid=None,
            stream_id=None,
            direction=CreditDirection.RESPONSE,
            batch=max(initial_credit // 2, 1),
            window=_WindowCounter(0),
        )
    # Fragment crediting for sequence-mode responses (same scheme as
    # `demux_multi_stream`): the caller grants one frame per consumed ITEM,
    # so continuation fragments are credited back on arrival here.
    fragment_grants = grants.fragment_sibling() if grants is not None else None

    def _demux_worker():
        # Sequence reassembly for the single response stream (None until a
        # STREAM_START with is_sequence=True arrives). Sequence frame
        # payloads are RFC 8742 fragments — decode at item granularity.
        seq: Optional[SeqReassembly] = None
        nonlocal fragment_grants
        for frame in iter(raw_frames.get, None):
            if frame.frame_type == FrameType.STREAM_START:
                if frame.is_sequence:
                    seq = SeqReassembly(fragment_grants=fragment_grants)
                    fragment_grants = None
            elif frame.frame_type == FrameType.CHUNK:
                if frame.payload:
                    payload = frame.payload
                    # Verify checksum
                    expected_checksum = frame.checksum
                    if expected_checksum is None:
                        item_queue.put(PeerResponseItem.data_err(
                            PeerResponseError("CHUNK frame missing required checksum field")
                        ))
                        continue
                    actual = compute_checksum(payload)
                    if actual != expected_checksum:
                        item_queue.put(PeerResponseItem.data_err(
                            PeerResponseError(f"Checksum mismatch: expected={expected_checksum}, actual={actual}")
                        ))
                        continue
                    chunk_meta = frame.meta
                    if seq is not None:
                        if len(seq.buf) == 0:
                            seq.item_meta = chunk_meta
                        elif seq.fragment_grants is not None:
                            seq.fragment_grants.consumed()
                        seq.buf.extend(payload)
                        while True:
                            status, a, b = try_decode_sequence_item(bytes(seq.buf))
                            if status == "ok":
                                value, consumed = a, b
                                del seq.buf[:consumed]
                                meta = seq.item_meta
                                seq.item_meta = None
                                item_queue.put(PeerResponseItem.data_ok(value, meta))
                                if len(seq.buf) == 0:
                                    break
                            elif status == "prefix":
                                break
                            else:
                                item_queue.put(PeerResponseItem.data_err(
                                    PeerResponseError(f"CBOR decode error: {a}")
                                ))
                                seq.buf.clear()
                                break
                    else:
                        try:
                            value = cbor2.loads(payload)
                            item_queue.put(PeerResponseItem.data_ok(value, chunk_meta))
                        except Exception as e:
                            item_queue.put(PeerResponseItem.data_err(
                                PeerResponseError(f"CBOR decode error: {e}")
                            ))
            elif frame.frame_type == FrameType.LOG:
                item_queue.put(PeerResponseItem.log_frame(frame))
            elif frame.frame_type in (FrameType.STREAM_END, FrameType.END):
                if seq is not None and len(seq.buf) > 0:
                    item_queue.put(PeerResponseItem.data_err(PeerResponseError(
                        f"sequence stream ended mid-item: {len(seq.buf)} trailing bytes "
                        "do not form a complete CBOR item"
                    )))
                break
            elif frame.frame_type == FrameType.ERR:
                # Keep the peer's declared code/class/message structural —
                # never folded into prose (docs/failure-taxonomy.md).
                code = frame.error_code() or "UNKNOWN"
                failure_class = frame.error_class() or FailureClass.INTERNAL
                message = frame.error_message() or "Unknown error"
                item_queue.put(PeerResponseItem.data_err(
                    RemoteError(code, failure_class, message, frame.error_arg_urn())
                ))
                break
        # Signal end of stream
        item_queue.put(None)

    thread = threading.Thread(target=_demux_worker, daemon=True)
    thread.start()

    return PeerResponse(item_queue, grants=grants)


def find_stream(
    streams: List[Tuple[str, bytes, Optional[dict]]], media_urn: str
) -> Optional[bytes]:
    """Find a stream's bytes by exact URN equivalence.

    Uses MediaUrn.is_equivalent() — matches only if both URNs have the
    exact same tag set (order-independent). Both the caller and the cartridge
    know the arg media URNs from the cap definition, so this is always an
    exact match — never a subsumption/pattern match.

    Args:
        streams: List of (media_urn, bytes, stream_meta) triples from
            `InputPackage.collect_streams()` / `collect_streams()`
        media_urn: Full media URN from cap arg definition (e.g., "media:enc=utf-8;model-spec")

    Returns:
        Stream bytes if found, None otherwise
    """
    try:
        target = MediaUrn.from_string(media_urn)
    except Exception:
        return None

    for urn_str, data, _meta in streams:
        try:
            urn = MediaUrn.from_string(urn_str)
            if target.is_equivalent(urn):
                return data
        except Exception:
            continue

    return None


def find_stream_meta(
    streams: List[Tuple[str, bytes, Optional[dict]]], media_urn: str
) -> Optional[dict]:
    """Find the stream-level metadata (from STREAM_START) for a stream by media URN."""
    try:
        target = MediaUrn.from_string(media_urn)
    except Exception:
        return None

    for urn_str, _data, meta in streams:
        try:
            urn = MediaUrn.from_string(urn_str)
            if target.is_equivalent(urn):
                return meta
        except Exception:
            continue

    return None


def find_stream_str(
    streams: List[Tuple[str, bytes, Optional[dict]]], media_urn: str
) -> Optional[str]:
    """Like find_stream but returns a UTF-8 string."""
    data = find_stream(streams, media_urn)
    if data is None:
        return None
    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return None


def require_stream(
    streams: List[Tuple[str, bytes, Optional[dict]]], media_urn: str
) -> bytes:
    """Like find_stream but fails hard if not found.

    Raises:
        RuntimeError: If stream not found
    """
    data = find_stream(streams, media_urn)
    if data is None:
        raise RuntimeError(f"Missing required arg: {media_urn}")
    return data


def require_stream_str(
    streams: List[Tuple[str, bytes, Optional[dict]]], media_urn: str
) -> str:
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

        # Concurrency capacity: 0 = unlimited, N = max N concurrent handlers.
        # Shared via CapacityHandle so handlers can adjust dynamically.
        self._capacity = CapacityHandle(0)

        # Process-wide dropped-frame accounting (L8). Shared with the writer's
        # terminal gate, every write-failure drop, and the stats surface.
        self._drop_counters = DropCounters()

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
                "Manifest validation failed - cartridge MUST declare CAP_IDENTITY (cap:effect=none). "
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

    def set_capacity(self, n: int) -> None:
        """Set the maximum number of concurrent handler invocations.

        When set to N > 0, the runtime queues incoming requests beyond N
        active handlers. Queued requests receive a LOG frame with
        `level="queued"` so the pipeline's activity timeout pauses for that
        body.

        * `0` — unlimited (default)
        * `1` — serial execution (e.g. a cartridge with a single loaded model)
        * `N` — up to N concurrent handlers
        """
        self._capacity.set(n)

    def capacity_handle(self) -> CapacityHandle:
        """Get a shared handle to the concurrency capacity.

        Handlers can use this to adjust capacity dynamically at runtime —
        for example, increasing capacity after freeing VRAM or decreasing it
        under memory pressure.
        """
        return self._capacity

    def protocol_drops(self) -> DropSnapshot:
        """Protocol observability snapshot (L8): this runtime's dropped-frame
        counters (post-terminal gate, write failures)."""
        return self._drop_counters.snapshot()

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

        Uses is_dispatchable(candidate, request): can this registered handler
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
                # Use is_dispatchable: can this candidate handle this request?
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
            cap = self.find_cap_by_alias(self.manifest, subcommand)
            if cap:
                self.print_cap_help(cap)
                return

        # Find cap by command name
        cap = self.find_cap_by_alias(self.manifest, subcommand)
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
        request_id = MessageId.new_uuid()
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

        emitter = CliStreamEmitter()
        peer = NoPeerInvoker()

        try:
            input_package = demux_multi_stream(frames)  # Uncredited: CLI mode has no wire peer.
            dispatch_op(factory(), input_package, emitter, peer)
        except Exception as e:
            # CLI mode still owes the caller the real failure identity
            # (docs/failure-taxonomy.md).
            code, failure_class, message, arg_urn = _classify_handler_error(e)
            error_json = {"error": message, "code": code, "class": failure_class.as_str()}
            if arg_urn is not None:
                error_json["arg_urn"] = arg_urn
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
        # Shared, process-wide drop accounting (L8): the writer's terminal
        # gate and every write-failure share this runtime's counters.
        sync_writer = SyncFrameWriter(raw_writer, drops=self._drop_counters)

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

        # Track active incoming requests for LIVE frame routing (protocol v3,
        # L16): registered the instant REQ is seen, so subsequent
        # STREAM_START/CHUNK/STREAM_END/END frames route onto the request's
        # raw_queue as they arrive — even before the handler thread is
        # actually spawned (e.g. while capacity-queued). The handler thread's
        # `demux_multi_stream` drains this queue live; there is no
        # buffer-then-dispatch step. Mirrors the Rust reference's
        # `active_requests` map.
        active_requests: Dict[str, ActiveRequest] = {}
        active_requests_lock = threading.Lock()

        # Track active handler threads for cleanup
        active_handlers: List[threading.Thread] = []

        # Routes inbound CREDIT frames to the gates of streams local senders
        # are writing (protocol v3 flow control, both directions). Gates
        # register when an emitter/OutputStream starts a credited stream;
        # close_request releases waiters on handler completion.
        credit_router = CreditRouter()

        # Concurrency capacity queueing (set_capacity/capacity_handle): when
        # the runtime is at capacity, dispatch-ready requests are queued
        # instead of spawned, with a "queued" LOG frame telling the pipeline
        # to pause its activity timeout for that body. A slot frees the
        # instant a handler finishes (not on the next stdin frame) — the
        # finishing handler itself drains the queue.
        capacity_lock = threading.Lock()
        running_handler_count = 0
        # Each entry: (request_id, routing_id, zero-arg target callable).
        request_queue: List[Tuple[MessageId, Optional[MessageId], Callable[[], None]]] = []

        def _spawn_thread(target_fn: Callable[[], None]) -> None:
            nonlocal running_handler_count
            running_handler_count += 1
            thread = threading.Thread(target=target_fn, daemon=True)
            thread.start()
            active_handlers.append(thread)

        def _drain_queue_locked() -> None:
            """Spawn handlers for queued requests while capacity allows.
            Caller must hold capacity_lock."""
            nonlocal running_handler_count
            cap = self._capacity.get()
            while request_queue and (cap == 0 or running_handler_count < cap):
                qrid, qxid, qfn = request_queue.pop(0)
                dequeued_log = Frame.log(qrid, "dequeued", "Request dequeued, handler starting")
                dequeued_log.routing_id = qxid
                try:
                    sync_writer.write(dequeued_log)
                except Exception:
                    pass
                _spawn_thread(qfn)
                cap = self._capacity.get()

        def _on_handler_done(request_id: MessageId) -> None:
            """Called by a handler thread right after it finishes (success or
            error) — releases its credit waiters (L13) and immediately drains
            one queued request into the freed slot."""
            nonlocal running_handler_count
            credit_router.close_request(request_id, "END")
            with capacity_lock:
                running_handler_count -= 1
                _drain_queue_locked()

        def _spawn_or_queue(request_id: MessageId, routing_id: Optional[MessageId], target_fn: Callable[[], None]) -> None:
            """Dispatch a live-routed request: spawn its handler immediately
            under capacity, else queue it with a "queued" LOG frame. Input
            frames route onto the request's raw_queue as they arrive
            regardless (protocol v3, L16) — nothing is buffered to completion
            before dispatch."""
            nonlocal running_handler_count
            with capacity_lock:
                cap = self._capacity.get()
                if cap > 0 and running_handler_count >= cap:
                    queue_pos = len(request_queue) + 1
                    log_frame = Frame.log(
                        request_id, "queued",
                        f"Request queued (position {queue_pos}, {running_handler_count} active)",
                    )
                    log_frame.routing_id = routing_id
                    try:
                        sync_writer.write(log_frame)
                    except Exception:
                        pass
                    request_queue.append((request_id, routing_id, target_fn))
                else:
                    _spawn_thread(target_fn)

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

                factory = self.find_handler(cap_urn)
                if factory is None:
                    # A dispatched cap this binary doesn't handle is a
                    # deployment/manifest mismatch — Environment.
                    err_frame = Frame.err_classified(
                        frame.id,
                        "NO_HANDLER",
                        FailureClass.ENVIRONMENT,
                        f"No handler registered for cap: {cap_urn}",
                    )
                    err_frame.routing_id = routing_id_for_errors
                    try:
                        sync_writer.write(err_frame)
                    except Exception:
                        pass
                    continue

                # Register the LIVE per-request frame queue NOW — before the
                # handler thread is spawned — so subsequent STREAM_START/
                # CHUNK/STREAM_END/END frames route onto it immediately
                # (even while capacity-queued). The handler's
                # `demux_multi_stream` drains this queue incrementally as
                # frames arrive (protocol v3, L16) — never buffered to
                # completion first.
                request_id = frame.id
                routing_id = frame.routing_id
                with active_requests_lock:
                    active_requests[request_id.to_string()] = ActiveRequest(
                        cap_urn=cap_urn, routing_id=routing_id,
                    )
                raw_queue = active_requests[request_id.to_string()].raw_queue

                _max_chunk = self.limits.max_chunk
                _initial_credit = self.limits.initial_credit

                def handle_request(
                    request_id=request_id,
                    raw_queue=raw_queue,
                    factory=factory,
                    max_chunk=_max_chunk,
                    routing_id=routing_id,
                    initial_credit=_initial_credit,
                ):
                    import uuid as _uuid
                    response_stream_id = f"resp-{_uuid.uuid4().hex[:8]}"
                    # SyncFrameWriter assigns seq centrally for all frames.
                    # routing_id (XID) is propagated from incoming REQ to all response frames.
                    # Output is credited (L9): the receiver's consumption
                    # grants this stream's window.
                    emitter = ThreadSafeEmitter(
                        sync_writer, request_id, response_stream_id, "media:", routing_id, max_chunk,
                        credit_router=credit_router, initial_credit=initial_credit,
                    )
                    peer_invoker = PeerInvokerImpl(
                        sync_writer, pending_peer_requests, max_chunk,
                        credit_router=credit_router, initial_credit=initial_credit,
                    )

                    try:
                        # Input streams are credited (L14): the handler's
                        # consumption grants the engine's sender window;
                        # over-window chunks are CREDIT_VIOLATION. Delivered
                        # LIVE as frames arrive on raw_queue — never
                        # buffered to completion first.
                        input_package = demux_multi_stream(
                            raw_queue,
                            InputCreditContext(
                                writer=sync_writer, rid=request_id, xid=routing_id,
                                initial_credit=initial_credit,
                            ),
                        )
                        try:
                            dispatch_op(factory(), input_package, emitter, peer_invoker)

                            # Finalize: STREAM_END + END (seq assigned by
                            # SyncFrameWriter). END carries the handler's
                            # declared final progress (L3/L5).
                            emitter.finalize()

                        except Exception as e:
                            # The ERR frame carries the failure's DECLARED
                            # identity (docs/failure-taxonomy.md): the code,
                            # class, and argument attribution from the emit
                            # source when classified, HANDLER_ERROR/INTERNAL
                            # when the handler never declared one.
                            code, failure_class, message, arg_urn = _classify_handler_error(e)
                            err_frame = Frame.err_classified(request_id, code, failure_class, message, arg_urn)
                            err_frame.routing_id = routing_id  # Propagate XID
                            try:
                                sync_writer.write(err_frame)
                            except Exception as write_err:
                                print(f"[CartridgeRuntime] Failed to write error response: {write_err}", file=sys.stderr)
                    finally:
                        # Release this request's credit waiters (L13) and
                        # immediately drain one queued request into the
                        # freed capacity slot.
                        _on_handler_done(request_id)

                _spawn_or_queue(request_id, routing_id, handle_request)
                continue  # Wait for STREAM_START/CHUNK/STREAM_END/END frames

            elif frame.frame_type == FrameType.HEARTBEAT:
                # Respond to heartbeat immediately - never blocked by handlers
                response = Frame.heartbeat(frame.id)
                # Protocol observability (L8): this cartridge's dropped-frame
                # total rides every heartbeat so the host can surface it
                # without a dedicated stats round-trip.
                response.meta = {"drops_total": self._drop_counters.total()}
                try:
                    sync_writer.write(response)
                except Exception as e:
                    print(f"[CartridgeRuntime] Failed to write heartbeat response: {e}", file=sys.stderr)
                    break

            elif frame.frame_type == FrameType.CREDIT:
                # Flow-control grant for one of this request's output streams
                # (ours or a peer-call arg stream). Grants only ever unblock a
                # credit-waiting sender; a grant for a request with no
                # registered gate (request finished, or its output is not
                # credit-blocked) is a correct no-op.
                credit_router.grant(frame)

            elif frame.frame_type == FrameType.HELLO:
                # Unexpected HELLO after handshake - protocol error
                err_frame = Frame.err(frame.id, "PROTOCOL_ERROR", "Unexpected HELLO after handshake")
                try:
                    sync_writer.write(err_frame)
                except Exception:
                    pass

            elif frame.frame_type in (
                FrameType.STREAM_START, FrameType.CHUNK, FrameType.STREAM_END, FrameType.LOG,
            ):
                # Route to the active (live) request's raw queue, or to a
                # pending peer-response queue. No frame-level validation
                # here — that is the receiving demux's job
                # (`demux_multi_stream` / peer-response consumption), exactly
                # like the Rust reference's routing-only main loop.
                frame_id_str = frame.id.to_string()
                with active_requests_lock:
                    ar = active_requests.get(frame_id_str)
                if ar is not None:
                    ar.raw_queue.put(frame)
                    continue
                with pending_lock:
                    if frame_id_str in pending_peer_requests:
                        pending_peer_requests[frame_id_str].queue.put(frame)
                    else:
                        print(
                            f"[CartridgeRuntime] {frame.frame_type} rid={frame_id_str} not found "
                            "in active_requests or pending_peer_requests",
                            file=sys.stderr,
                        )

            elif frame.frame_type == FrameType.END:
                # Route END like any other flow frame, then stop routing
                # further frames for this request — the demux thread sees
                # END and stops draining (matches the Rust reference: the
                # active_requests entry is dropped right after routing END).
                frame_id_str = frame.id.to_string()
                with active_requests_lock:
                    ar = active_requests.pop(frame_id_str, None)
                if ar is not None:
                    ar.raw_queue.put(frame)
                    continue

                # Not an incoming request end - must be a peer response end
                # Forward bare Frame to handler's queue and close channel
                with pending_lock:
                    if frame_id_str in pending_peer_requests:
                        pending_req = pending_peer_requests[frame_id_str]
                        pending_req.ended = True
                        pending_req.queue.put(frame)
                        pending_req.queue.put(None)  # Signal end of stream
                        del pending_peer_requests[frame_id_str]

            elif frame.frame_type == FrameType.ERR:
                # Error frame from host - could be response to peer request
                # Forward bare Frame to handler's queue and close channel
                frame_id_str = frame.id.to_string()
                with active_requests_lock:
                    ar = active_requests.pop(frame_id_str, None)
                if ar is not None:
                    ar.raw_queue.put(frame)
                    continue
                with pending_lock:
                    if frame_id_str in pending_peer_requests:
                        pending_req = pending_peer_requests[frame_id_str]
                        pending_req.ended = True
                        pending_req.queue.put(frame)
                        pending_req.queue.put(None)  # Signal end of stream
                        del pending_peer_requests[frame_id_str]

            elif frame.frame_type in (FrameType.RELAY_NOTIFY, FrameType.RELAY_STATE):
                # Relay-level frames must never reach a cartridge runtime.
                # If they do, it's a bug in the relay layer — fail hard.
                raise ProtocolError(
                    f"Relay frame {frame.frame_type} must not reach cartridge runtime"
                )

        # Wait for all active handlers to complete before exiting
        for thread in active_handlers:
            thread.join(timeout=5.0)  # 5 second timeout per thread

    def find_cap_by_alias(self, manifest: CapManifest, alias: str) -> Optional[Cap]:
        """Find a cap by one of its aliases (the CLI subcommand). Aliases are
        globally unique, so at most one cap matches."""
        for cap in manifest.all_caps():
            if cap.has_alias(alias):
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

        # Try default value.
        #
        # The wire contract for an arg stream is "bytes of the typed
        # media URN". For a `media:enc=utf-8`-shaped arg that's plain
        # UTF-8 text — NOT a JSON-encoded form. A naive
        # `json.dumps(default).encode('utf-8')` would corrupt every
        # string default by wrapping it in `"…"` quotes — the
        # handler's UTF-8 decode would surface a literal quoted
        # string and downstream parsers (model-spec, system-prompt,
        # etc.) would silently choke. Encode each scalar JSON
        # value as its lexical wire form, matching exactly what
        # the same value typed at the CLI flag would produce.
        # Composite defaults (list, dict) ARE JSON on the wire by
        # design and route through `json.dumps`.
        if arg_def.default_value is not None:
            default = arg_def.default_value
            try:
                # `bool` is a subclass of `int` in Python; check it
                # first or `True` falls into the integer branch and
                # serialises as `b"1"` instead of `b"true"`.
                if isinstance(default, bool):
                    return (b'true' if default else b'false'), False
                if isinstance(default, str):
                    return default.encode('utf-8'), False
                if isinstance(default, (int, float)):
                    # JSON's numeric grammar matches Python's
                    # `json.dumps` here — and consumers parse via
                    # `int()` / `float()` which accept the same
                    # forms. Route through `json.dumps` so the wire
                    # form is exactly the JSON representation.
                    return json.dumps(default).encode('utf-8'), False
                if default is None:
                    return b'', False
                # list / dict / nested structures — JSON on the wire.
                return json.dumps(default).encode('utf-8'), False
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
            print(f"    {cap.primary_alias():<12} {desc}", file=sys.stderr)

        print(file=sys.stderr)
        print(f"Run '{manifest.name.lower()} <COMMAND> --help' for more information on a command.", file=sys.stderr)

    def print_cap_help(self, cap: Cap) -> None:
        """Print help for a specific cap."""
        print(cap.title, file=sys.stderr)
        if cap.cap_description:
            print(cap.cap_description, file=sys.stderr)
        print(file=sys.stderr)
        print("USAGE:", file=sys.stderr)
        print(f"    cartridge {cap.primary_alias()} [OPTIONS]", file=sys.stderr)
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
