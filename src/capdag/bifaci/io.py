"""CBOR I/O - Reading and Writing CBOR Frames

This module provides streaming CBOR frame encoding/decoding over stdio pipes.
Frames are written as length-prefixed CBOR (same framing as before, but CBOR payload).

## Wire Format

```
┌─────────────────────────────────────────────────────────┐
│  4 bytes: u32 big-endian length                         │
├─────────────────────────────────────────────────────────┤
│  N bytes: CBOR-encoded Frame                            │
└─────────────────────────────────────────────────────────┘
```

The CBOR payload is a map with integer keys (see cbor_frame.py).
"""

import asyncio
import io
import os
from typing import BinaryIO, Optional
from dataclasses import dataclass

try:
    import cbor2
    CBOR2_AVAILABLE = True
except ImportError:
    CBOR2_AVAILABLE = False

from capdag.bifaci.frame import (
    Frame,
    FrameType,
    MessageId,
    Limits,
    Keys,
    DEFAULT_MAX_FRAME,
    DEFAULT_MAX_CHUNK,
    DEFAULT_MAX_REORDER_BUFFER,
    DEFAULT_INITIAL_CREDIT,
    PROTOCOL_VERSION,
    compute_checksum,
    verify_chunk_checksum,
)
from capdag.standard.caps import CAP_IDENTITY


# Maximum frame size (16 MB) - hard limit to prevent memory exhaustion
MAX_FRAME_HARD_LIMIT = 16 * 1024 * 1024


class CborError(Exception):
    """Base CBOR I/O error"""
    pass


class EncodeError(CborError):
    """CBOR encoding error"""
    pass


class DecodeError(CborError):
    """CBOR decoding error"""
    pass


class FrameTooLargeError(CborError):
    """Frame exceeds size limits"""
    def __init__(self, size: int, max_size: int):
        super().__init__(f"Frame too large: {size} bytes (max {max_size})")
        self.size = size
        self.max = max_size


class InvalidFrameError(CborError):
    """Invalid frame structure"""
    pass


class UnexpectedEofError(CborError):
    """Unexpected end of stream"""
    pass


class ProtocolError(CborError):
    """Protocol error"""
    pass


class HandshakeError(CborError):
    """Handshake failed"""
    pass


def encode_frame(frame: Frame) -> bytes:
    """Encode a frame to CBOR bytes

    Args:
        frame: Frame to encode

    Returns:
        CBOR-encoded bytes

    Raises:
        EncodeError: If encoding fails
    """
    if not CBOR2_AVAILABLE:
        raise EncodeError("cbor2 not available")

    frame_map = {}

    # Required fields
    frame_map[Keys.VERSION] = frame.version
    frame_map[Keys.FRAME_TYPE] = int(frame.frame_type)

    # Message ID
    if frame.id.is_uuid():
        frame_map[Keys.ID] = frame.id.uuid_bytes  # CBOR bytes
    else:
        frame_map[Keys.ID] = frame.id.uint_value  # CBOR integer

    # Sequence number
    frame_map[Keys.SEQ] = frame.seq

    # Optional fields
    if frame.content_type is not None:
        frame_map[Keys.CONTENT_TYPE] = frame.content_type

    if frame.meta is not None:
        frame_map[Keys.META] = frame.meta

    if frame.payload is not None:
        frame_map[Keys.PAYLOAD] = frame.payload

    if frame.len is not None:
        frame_map[Keys.LEN] = frame.len

    if frame.offset is not None:
        frame_map[Keys.OFFSET] = frame.offset

    if frame.eof is not None:
        frame_map[Keys.EOF] = frame.eof

    if frame.cap is not None:
        frame_map[Keys.CAP] = frame.cap

    if frame.stream_id is not None:
        frame_map[Keys.STREAM_ID] = frame.stream_id

    if frame.media_urn is not None:
        frame_map[Keys.MEDIA_URN] = frame.media_urn

    if frame.routing_id is not None:
        frame_map[Keys.ROUTING_ID] = frame.routing_id.to_cbor()

    if frame.chunk_index is not None:
        frame_map[Keys.INDEX] = frame.chunk_index

    if frame.chunk_count is not None:
        frame_map[Keys.CHUNK_COUNT] = frame.chunk_count

    if frame.checksum is not None:
        frame_map[Keys.CHECKSUM] = frame.checksum

    if frame.is_sequence is not None:
        frame_map[Keys.IS_SEQUENCE] = frame.is_sequence

    if frame.force_kill is not None:
        frame_map[Keys.FORCE_KILL] = frame.force_kill

    if frame.credit is not None:
        frame_map[Keys.CREDIT] = frame.credit

    if frame.unbounded is not None:
        frame_map[Keys.UNBOUNDED] = frame.unbounded

    try:
        return cbor2.dumps(frame_map)
    except Exception as e:
        raise EncodeError(f"CBOR encoding failed: {e}")


def decode_frame(data: bytes) -> Frame:
    """Decode a frame from CBOR bytes

    Args:
        data: CBOR-encoded bytes

    Returns:
        Decoded Frame

    Raises:
        DecodeError: If decoding fails
        InvalidFrameError: If frame structure is invalid
    """
    if not CBOR2_AVAILABLE:
        raise DecodeError("cbor2 not available")

    try:
        frame_map = cbor2.loads(data)
    except Exception as e:
        raise DecodeError(f"CBOR decoding failed: {e}")

    if not isinstance(frame_map, dict):
        raise InvalidFrameError("expected map")

    # Convert keys to integers if they're not already
    lookup = {}
    for k, v in frame_map.items():
        if isinstance(k, int):
            lookup[k] = v

    # Extract required fields
    version = lookup.get(Keys.VERSION)
    if version is None:
        raise InvalidFrameError("missing version")

    frame_type_u8 = lookup.get(Keys.FRAME_TYPE)
    if frame_type_u8 is None:
        raise InvalidFrameError("missing frame_type")

    frame_type = FrameType.from_u8(frame_type_u8)
    if frame_type is None:
        raise InvalidFrameError(f"invalid frame_type: {frame_type_u8}")

    # Extract ID
    id_value = lookup.get(Keys.ID)
    if id_value is None:
        id_obj = MessageId.default()
    elif isinstance(id_value, bytes):
        if len(id_value) == 16:
            id_obj = MessageId(id_value)
        else:
            # Treat as uint fallback
            id_obj = MessageId(0)
    elif isinstance(id_value, int):
        id_obj = MessageId(id_value)
    else:
        id_obj = MessageId(0)

    # Extract seq
    seq = lookup.get(Keys.SEQ, 0)

    # Optional fields
    content_type = lookup.get(Keys.CONTENT_TYPE)
    meta = lookup.get(Keys.META)
    payload = lookup.get(Keys.PAYLOAD)
    len_field = lookup.get(Keys.LEN)
    offset = lookup.get(Keys.OFFSET)
    eof = lookup.get(Keys.EOF)
    cap = lookup.get(Keys.CAP)
    stream_id = lookup.get(Keys.STREAM_ID)
    media_urn = lookup.get(Keys.MEDIA_URN)

    routing_id_cbor = lookup.get(Keys.ROUTING_ID)
    routing_id = MessageId.from_cbor(routing_id_cbor) if routing_id_cbor is not None else None

    chunk_index = lookup.get(Keys.INDEX)
    chunk_count = lookup.get(Keys.CHUNK_COUNT)
    checksum = lookup.get(Keys.CHECKSUM)

    is_sequence_raw = lookup.get(Keys.IS_SEQUENCE)
    is_sequence = bool(is_sequence_raw) if is_sequence_raw is not None else None

    force_kill_raw = lookup.get(Keys.FORCE_KILL)
    force_kill = bool(force_kill_raw) if force_kill_raw is not None else None

    credit = lookup.get(Keys.CREDIT)
    if credit is not None and not isinstance(credit, int):
        credit = None

    unbounded_raw = lookup.get(Keys.UNBOUNDED)
    unbounded = bool(unbounded_raw) if unbounded_raw is not None else None

    # Validate required fields based on frame type
    if frame_type == FrameType.CHUNK:
        if chunk_index is None:
            raise InvalidFrameError("CHUNK frame missing required field: chunk_index")
        if checksum is None:
            raise InvalidFrameError("CHUNK frame missing required field: checksum")
    # STREAM_END: chunk_count is optional on the wire — unbounded streams make
    # no length promise. Bounded-stream receivers that want to verify
    # completeness check chunk_count when present.
    if frame_type == FrameType.CREDIT:
        if credit is None:
            raise InvalidFrameError("CREDIT frame missing required field: credit")

    return Frame(
        frame_type=frame_type,
        id=id_obj,
        version=version,
        seq=seq,
        content_type=content_type,
        meta=meta,
        payload=payload,
        len=len_field,
        offset=offset,
        eof=eof,
        cap=cap,
        stream_id=stream_id,
        media_urn=media_urn,
        routing_id=routing_id,
        chunk_index=chunk_index,
        chunk_count=chunk_count,
        checksum=checksum,
        is_sequence=is_sequence,
        force_kill=force_kill,
        credit=credit,
        unbounded=unbounded,
    )


def write_frame(writer: BinaryIO, frame: Frame, limits: Limits) -> None:
    """Write a length-prefixed CBOR frame

    Args:
        writer: Binary output stream
        frame: Frame to write
        limits: Protocol limits

    Raises:
        FrameTooLargeError: If frame exceeds limits
        CborError: If write fails
    """
    frame_bytes = encode_frame(frame)

    if len(frame_bytes) > limits.max_frame:
        raise FrameTooLargeError(len(frame_bytes), limits.max_frame)

    if len(frame_bytes) > MAX_FRAME_HARD_LIMIT:
        raise FrameTooLargeError(len(frame_bytes), MAX_FRAME_HARD_LIMIT)

    length = len(frame_bytes)
    length_bytes = length.to_bytes(4, byteorder='big')

    try:
        writer.write(length_bytes)
        writer.write(frame_bytes)
        writer.flush()
    except Exception as e:
        raise CborError(f"Write failed: {e}")


def read_frame(reader: BinaryIO, limits: Limits) -> Optional[Frame]:
    """Read a length-prefixed CBOR frame from a reader

    Returns Ok(None) on clean EOF, Err(UnexpectedEof) on partial read.

    Args:
        reader: Binary input stream
        limits: Protocol limits

    Returns:
        Frame or None on EOF

    Raises:
        UnexpectedEofError: On partial read
        FrameTooLargeError: If frame exceeds limits
        CborError: If read fails
    """
    # Read 4-byte length prefix
    try:
        len_buf = reader.read(4)
    except Exception as e:
        raise CborError(f"Read failed: {e}")

    if len(len_buf) == 0:
        # Clean EOF
        return None

    if len(len_buf) < 4:
        raise UnexpectedEofError()

    length = int.from_bytes(len_buf, byteorder='big')

    # Validate length
    if length > limits.max_frame or length > MAX_FRAME_HARD_LIMIT:
        raise FrameTooLargeError(length, min(limits.max_frame, MAX_FRAME_HARD_LIMIT))

    # Read payload
    try:
        payload = reader.read(length)
    except Exception as e:
        raise CborError(f"Read failed: {e}")

    if len(payload) < length:
        raise UnexpectedEofError()

    frame = decode_frame(payload)
    return frame


class FrameReader:
    """CBOR frame reader with buffering"""

    def __init__(self, reader: BinaryIO, limits: Optional[Limits] = None):
        """Create a new frame reader

        Args:
            reader: Binary input stream
            limits: Optional limits (defaults to Limits.default())
        """
        self.reader = reader
        self.limits = limits if limits is not None else Limits.default()

    @classmethod
    def new(cls, reader: BinaryIO) -> "FrameReader":
        """Create a new frame reader with default limits"""
        return cls(reader)

    @classmethod
    def with_limits(cls, reader: BinaryIO, limits: Limits) -> "FrameReader":
        """Create a new frame reader with specified limits"""
        return cls(reader, limits)

    def set_limits(self, limits: Limits) -> None:
        """Update limits (after handshake)"""
        self.limits = limits

    def read(self) -> Optional[Frame]:
        """Read the next frame

        Returns:
            Frame or None on EOF

        Raises:
            CborError: If read fails
        """
        return read_frame(self.reader, self.limits)

    def get_limits(self) -> Limits:
        """Get the current limits"""
        return self.limits

    def inner_mut(self) -> BinaryIO:
        """Get mutable access to the underlying reader"""
        return self.reader


class FrameWriter:
    """CBOR frame writer with buffering"""

    def __init__(self, writer: BinaryIO, limits: Optional[Limits] = None):
        """Create a new frame writer

        Args:
            writer: Binary output stream
            limits: Optional limits (defaults to Limits.default())
        """
        self.writer = writer
        self.limits = limits if limits is not None else Limits.default()

    @classmethod
    def new(cls, writer: BinaryIO) -> "FrameWriter":
        """Create a new frame writer with default limits"""
        return cls(writer)

    @classmethod
    def with_limits(cls, writer: BinaryIO, limits: Limits) -> "FrameWriter":
        """Create a new frame writer with specified limits"""
        return cls(writer, limits)

    def set_limits(self, limits: Limits) -> None:
        """Update limits (after handshake)"""
        self.limits = limits

    def write(self, frame: Frame) -> None:
        """Write a frame

        Args:
            frame: Frame to write

        Raises:
            CborError: If write fails
        """
        write_frame(self.writer, frame, self.limits)

    def write_chunked(self, request_id: MessageId, stream_id: str, content_type: str, data: bytes) -> None:
        """Write CHUNK frames directly, matching the reference chunking semantics.

        Chunks emitted by this helper always have `seq=0`. Ordering is carried by
        `chunk_index`; the final output stage is responsible for assigning wire
        sequence numbers when needed.

        The first chunk carries the total payload length and content type. The
        final chunk carries `eof=true`. Empty payloads still emit a single EOF
        chunk.
        """
        max_chunk = self.limits.max_chunk

        if len(data) == 0:
            empty = Frame.chunk(
                request_id,
                stream_id,
                0,
                b"",
                0,
                compute_checksum(b""),
            )
            empty.len = 0
            empty.content_type = content_type
            empty.eof = True
            self.write(empty)
            return

        offset = 0
        chunk_index = 0
        total_len = len(data)
        while offset < total_len:
            chunk_size = min(total_len - offset, max_chunk)
            chunk_data = data[offset:offset + chunk_size]
            offset += chunk_size

            frame = Frame.chunk(
                request_id,
                stream_id,
                0,
                chunk_data,
                chunk_index,
                compute_checksum(chunk_data),
            )
            if chunk_index == 0:
                frame.len = total_len
                frame.content_type = content_type
            if offset == total_len:
                frame.eof = True
            self.write(frame)
            chunk_index += 1

    def write_stream_chunked(self, request_id: MessageId, stream_id: str, media_urn: str, payload: bytes) -> None:
        """Write a response using Protocol v2 stream multiplexing.

        Sends: STREAM_START → CHUNK(s) → STREAM_END → END

        Args:
            request_id: The request message ID
            stream_id: Unique stream identifier
            media_urn: Media URN for the stream content type
            payload: The full response payload

        Raises:
            CborError: If write fails
        """
        max_chunk = self.limits.max_chunk

        # STREAM_START
        self.write(Frame.stream_start(request_id, stream_id, media_urn))

        # CHUNK(s)
        offset = 0
        chunk_index = 0
        while offset < len(payload):
            chunk_size = min(len(payload) - offset, max_chunk)
            chunk_data = payload[offset:offset + chunk_size]
            offset += chunk_size
            frame = Frame.chunk(
                request_id,
                stream_id,
                0,
                chunk_data,
                chunk_index,
                compute_checksum(chunk_data),
            )
            self.write(frame)
            chunk_index += 1

        # STREAM_END
        self.write(Frame.stream_end(request_id, stream_id, chunk_index))

        # END
        self.write(Frame.end(request_id, None))

    def get_limits(self) -> Limits:
        """Get the current limits"""
        return self.limits

    def inner_mut(self) -> BinaryIO:
        """Get mutable access to the underlying writer"""
        return self.writer


@dataclass
class HandshakeResult:
    """Result of handshake negotiation"""
    limits: Limits
    manifest: bytes


def handshake(
    reader: FrameReader,
    writer: FrameWriter,
) -> HandshakeResult:
    """Perform HELLO handshake and extract cartridge manifest (host side - sends first)

    Args:
        reader: Frame reader
        writer: Frame writer

    Returns:
        HandshakeResult with negotiated limits and manifest

    Raises:
        HandshakeError: If handshake fails
    """
    # Send our HELLO
    our_hello = Frame.hello(DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK, DEFAULT_MAX_REORDER_BUFFER, DEFAULT_INITIAL_CREDIT)
    writer.write(our_hello)

    # Read their HELLO (should include manifest)
    their_frame = reader.read()
    if their_frame is None:
        raise HandshakeError("connection closed before receiving HELLO")

    if their_frame.frame_type != FrameType.HELLO:
        raise HandshakeError(f"expected HELLO, got {their_frame.frame_type}")

    # Protocol version must match exactly (L1). No cross-version operation.
    their_version = their_frame.hello_version()
    if their_version is None:
        their_version = their_frame.version
    if their_version != PROTOCOL_VERSION:
        raise HandshakeError(
            f"protocol version mismatch: ours {PROTOCOL_VERSION}, theirs {their_version}"
        )

    # Extract manifest - REQUIRED for cartridges
    manifest = their_frame.hello_manifest()
    if manifest is None:
        raise HandshakeError("Cartridge HELLO missing required manifest")

    # Negotiate minimum of both
    their_max_frame = their_frame.hello_max_frame() or DEFAULT_MAX_FRAME
    their_max_chunk = their_frame.hello_max_chunk() or DEFAULT_MAX_CHUNK
    their_max_reorder_buffer = their_frame.hello_max_reorder_buffer() or DEFAULT_MAX_REORDER_BUFFER
    their_initial_credit = their_frame.hello_initial_credit() or DEFAULT_INITIAL_CREDIT

    limits = Limits(
        max_frame=min(DEFAULT_MAX_FRAME, their_max_frame),
        max_chunk=min(DEFAULT_MAX_CHUNK, their_max_chunk),
        max_reorder_buffer=min(DEFAULT_MAX_REORDER_BUFFER, their_max_reorder_buffer),
        initial_credit=min(DEFAULT_INITIAL_CREDIT, their_initial_credit),
    )

    # Update both reader and writer with negotiated limits
    reader.set_limits(limits)
    writer.set_limits(limits)

    return HandshakeResult(limits=limits, manifest=bytes(manifest))


def handshake_accept(
    reader: FrameReader,
    writer: FrameWriter,
    manifest: bytes,
) -> Limits:
    """Accept HELLO handshake with manifest (cartridge side - receives first, sends manifest in response)

    Reads host's HELLO, sends our HELLO with manifest, returns negotiated limits.
    The manifest is REQUIRED - cartridges MUST provide their manifest.

    Args:
        reader: Frame reader
        writer: Frame writer
        manifest: Cartridge manifest bytes (REQUIRED)

    Returns:
        Negotiated limits

    Raises:
        HandshakeError: If handshake fails
    """
    # Read their HELLO first (host initiates)
    their_frame = reader.read()
    if their_frame is None:
        raise HandshakeError("connection closed before receiving HELLO")

    if their_frame.frame_type != FrameType.HELLO:
        raise HandshakeError(f"expected HELLO, got {their_frame.frame_type}")

    # Protocol version must match exactly (L1). No cross-version operation.
    their_version = their_frame.hello_version()
    if their_version is None:
        their_version = their_frame.version
    if their_version != PROTOCOL_VERSION:
        raise HandshakeError(
            f"protocol version mismatch: ours {PROTOCOL_VERSION}, theirs {their_version}"
        )

    # Negotiate minimum of both
    their_max_frame = their_frame.hello_max_frame() or DEFAULT_MAX_FRAME
    their_max_chunk = their_frame.hello_max_chunk() or DEFAULT_MAX_CHUNK
    their_max_reorder_buffer = their_frame.hello_max_reorder_buffer() or DEFAULT_MAX_REORDER_BUFFER
    their_initial_credit = their_frame.hello_initial_credit() or DEFAULT_INITIAL_CREDIT

    limits = Limits(
        max_frame=min(DEFAULT_MAX_FRAME, their_max_frame),
        max_chunk=min(DEFAULT_MAX_CHUNK, their_max_chunk),
        max_reorder_buffer=min(DEFAULT_MAX_REORDER_BUFFER, their_max_reorder_buffer),
        initial_credit=min(DEFAULT_INITIAL_CREDIT, their_initial_credit),
    )

    # Send our HELLO with manifest
    our_hello = Frame.hello_with_manifest(
        limits.max_frame, limits.max_chunk, manifest, limits.max_reorder_buffer, limits.initial_credit
    )
    writer.write(our_hello)

    # Update both reader and writer with negotiated limits
    reader.set_limits(limits)
    writer.set_limits(limits)

    return limits


def identity_nonce() -> bytes:
    """CBOR-encoded Text("bifaci") — deterministic 7-byte nonce for identity verification.

    Mirrors Rust ``bifaci::io::identity_nonce``. Used by the in-process
    cartridge host's identity handler, which echoes the raw nonce bytes
    back unchanged (no CBOR decode/encode).
    """
    import cbor2
    return cbor2.dumps("bifaci")


def verify_identity(reader: FrameReader, writer: FrameWriter) -> None:
    """Verify a peer's CAP_IDENTITY handler by round-tripping a nonce."""
    request_id = MessageId.new_uuid()
    stream_id = "identity-verify"
    nonce = os.urandom(32)

    # CBOR-encode nonce (protocol v2: CHUNK payload = CBOR-encoded data)
    import cbor2
    cbor_nonce = cbor2.dumps(nonce)

    writer.write(Frame.req(request_id, CAP_IDENTITY, b"", "application/cbor"))
    writer.write(Frame.stream_start(request_id, stream_id, "media:"))
    writer.write(Frame.chunk(request_id, stream_id, 0, cbor_nonce, 0, compute_checksum(cbor_nonce)))
    writer.write(Frame.stream_end(request_id, stream_id, 1))
    writer.write(Frame.end(request_id, None))

    saw_stream_start = False
    saw_stream_end = False
    echoed = bytearray()

    while True:
        frame = reader.read()
        if frame is None:
            raise HandshakeError("identity verification failed: connection closed before response")

        if frame.frame_type == FrameType.STREAM_START:
            saw_stream_start = True
            continue
        if frame.frame_type == FrameType.CHUNK:
            verify_chunk_checksum(frame)
            # Decode CBOR wrapper to extract raw bytes
            payload = frame.payload or b""
            decoded = cbor2.loads(payload)
            if isinstance(decoded, bytes):
                echoed.extend(decoded)
            else:
                raise HandshakeError(
                    f"identity verification failed: expected bytes chunk, got {type(decoded)}"
                )
            continue
        if frame.frame_type == FrameType.STREAM_END:
            saw_stream_end = True
            continue
        if frame.frame_type == FrameType.ERR:
            raise HandshakeError(
                f"identity verification failed: "
                f"{frame.error_code() or 'ERR'} {frame.error_message() or ''}".strip()
            )
        if frame.frame_type == FrameType.END:
            if not saw_stream_start or not saw_stream_end:
                raise HandshakeError("identity verification failed: incomplete response stream")
            if bytes(echoed) != nonce:
                raise HandshakeError("identity verification failed: nonce mismatch")
            return


# =============================================================================
# Async I/O - for CartridgeHostRuntime
# =============================================================================


class AsyncFrameReader:
    """Async frame reader for reading CBOR frames from an async stream"""

    def __init__(self, stream):
        """Create async frame reader

        Args:
            stream: Async readable stream (asyncio.StreamReader or similar)
        """
        self.stream = stream
        self.limits = Limits(max_frame=DEFAULT_MAX_FRAME, max_chunk=DEFAULT_MAX_CHUNK)

    def set_limits(self, limits: Limits):
        """Update frame size limits"""
        self.limits = limits

    async def read(self) -> Optional[Frame]:
        """Read one frame from the stream

        Returns:
            Frame if read successfully, None on EOF

        Raises:
            CborError: If read fails
        """
        # Read 4-byte length prefix
        try:
            length_bytes = await self.stream.readexactly(4)
        except asyncio.IncompleteReadError:
            return None  # EOF
        except Exception as e:
            raise UnexpectedEofError(f"Failed to read length prefix: {e}")

        frame_len = int.from_bytes(length_bytes, byteorder='big')

        # Check against limits
        if frame_len > self.limits.max_frame:
            raise FrameTooLargeError(frame_len, self.limits.max_frame)

        # Read frame data
        try:
            frame_data = await self.stream.readexactly(frame_len)
        except asyncio.IncompleteReadError:
            raise UnexpectedEofError("Incomplete frame data")
        except Exception as e:
            raise CborError(f"Failed to read frame data: {e}")

        # Decode frame
        return decode_frame(frame_data)


class AsyncFrameWriter:
    """Async frame writer for writing CBOR frames to an async stream"""

    def __init__(self, stream):
        """Create async frame writer

        Args:
            stream: Async writable stream (asyncio.StreamWriter or similar)
        """
        self.stream = stream
        self.limits = Limits(max_frame=DEFAULT_MAX_FRAME, max_chunk=DEFAULT_MAX_CHUNK)

    def set_limits(self, limits: Limits):
        """Update frame size limits"""
        self.limits = limits

    async def write(self, frame: Frame):
        """Write one frame to the stream

        Args:
            frame: Frame to write

        Raises:
            CborError: If write fails
        """
        # Encode frame
        frame_data = encode_frame(frame)
        frame_len = len(frame_data)

        # Check against limits
        if frame_len > self.limits.max_frame:
            raise FrameTooLargeError(frame_len, self.limits.max_frame)

        # Write length prefix + frame data
        length_bytes = frame_len.to_bytes(4, byteorder='big')
        self.stream.write(length_bytes + frame_data)
        await self.stream.drain()


@dataclass
class HandshakeResult:
    """Result of handshake"""
    limits: Limits
    manifest: bytes


async def handshake_async(
    reader: AsyncFrameReader,
    writer: AsyncFrameWriter,
) -> HandshakeResult:
    """Perform HELLO handshake (host side - sends first, expects manifest in response)

    Sends host's HELLO, reads cartridge's HELLO with manifest, returns negotiated limits and manifest.

    Args:
        reader: Async frame reader
        writer: Async frame writer

    Returns:
        HandshakeResult with limits and manifest

    Raises:
        HandshakeError: If handshake fails
    """
    # Send our HELLO
    our_hello = Frame.hello(DEFAULT_MAX_FRAME, DEFAULT_MAX_CHUNK, DEFAULT_MAX_REORDER_BUFFER, DEFAULT_INITIAL_CREDIT)
    await writer.write(our_hello)

    # Read their HELLO (should include manifest)
    their_frame = await reader.read()
    if their_frame is None:
        raise HandshakeError("connection closed before receiving HELLO")

    if their_frame.frame_type != FrameType.HELLO:
        raise HandshakeError(f"expected HELLO, got {their_frame.frame_type}")

    # Protocol version must match exactly (L1). No cross-version operation.
    their_version = their_frame.hello_version()
    if their_version is None:
        their_version = their_frame.version
    if their_version != PROTOCOL_VERSION:
        raise HandshakeError(
            f"protocol version mismatch: ours {PROTOCOL_VERSION}, theirs {their_version}"
        )

    # Extract manifest - REQUIRED for cartridges
    manifest = their_frame.hello_manifest()
    if manifest is None:
        raise HandshakeError("Cartridge HELLO missing required manifest")

    # Negotiate minimum of both
    their_max_frame = their_frame.hello_max_frame() or DEFAULT_MAX_FRAME
    their_max_chunk = their_frame.hello_max_chunk() or DEFAULT_MAX_CHUNK
    their_max_reorder_buffer = their_frame.hello_max_reorder_buffer() or DEFAULT_MAX_REORDER_BUFFER
    their_initial_credit = their_frame.hello_initial_credit() or DEFAULT_INITIAL_CREDIT

    limits = Limits(
        max_frame=min(DEFAULT_MAX_FRAME, their_max_frame),
        max_chunk=min(DEFAULT_MAX_CHUNK, their_max_chunk),
        max_reorder_buffer=min(DEFAULT_MAX_REORDER_BUFFER, their_max_reorder_buffer),
        initial_credit=min(DEFAULT_INITIAL_CREDIT, their_initial_credit),
    )

    # Update both reader and writer with negotiated limits
    reader.set_limits(limits)
    writer.set_limits(limits)

    return HandshakeResult(limits=limits, manifest=bytes(manifest))
