"""Pure cap-based execution with strict input validation

This module provides data structures and execution infrastructure for calling capabilities.
"""

import cbor2

from enum import Enum
from typing import Optional, List, Dict, Tuple, Union
from dataclasses import dataclass

from capdag.bifaci.frame import Frame, MessageId, compute_checksum


@dataclass
class StdinSourceData:
    """Raw byte data for stdin - used for providers (in-process) or small inline data"""
    data: bytes

    def __repr__(self):
        return f"StdinSource::Data({len(self.data)} bytes)"


@dataclass
class StdinSourceFileReference:
    """File reference for stdin - used for cartridges to read files locally on Mac side

    Avoids the 4MB gRPC limit by letting the Swift/XPC side read the file locally
    instead of sending bytes over the wire.
    """
    tracked_file_id: str
    original_path: str
    security_bookmark: bytes
    media_urn: str

    def __repr__(self):
        return (
            f"StdinSource::FileReference("
            f"id={self.tracked_file_id}, "
            f"path={self.original_path}, "
            f"bookmark={len(self.security_bookmark)} bytes, "
            f"media_urn={self.media_urn})"
        )


# Union type for StdinSource
StdinSource = StdinSourceData | StdinSourceFileReference


class CapArgumentValue:
    """Unified argument type - arguments are identified by media_urn

    The cap definition's sources specify how to extract values (stdin, position, cli_flag).
    """

    def __init__(self, media_urn: str, value: bytes):
        """Create a new CapArgumentValue

        Args:
            media_urn: Semantic identifier (e.g., "media:model-spec;textable")
            value: Value bytes (UTF-8 for text, raw for binary)
        """
        self.media_urn = media_urn
        self.value = value

    @classmethod
    def from_str(cls, media_urn: str, value: str) -> "CapArgumentValue":
        """Create a new CapArgumentValue from a string value"""
        return cls(media_urn, value.encode('utf-8'))

    def value_as_str(self) -> str:
        """Get the value as a UTF-8 string

        Raises:
            UnicodeDecodeError: If the value contains non-UTF-8 binary data
        """
        return self.value.decode('utf-8')

    def __repr__(self):
        try:
            str_value = self.value_as_str()
            if len(str_value) > 50:
                str_value = str_value[:50] + "..."
            return f"CapArgumentValue(media_urn={self.media_urn!r}, value={str_value!r})"
        except UnicodeDecodeError:
            return f"CapArgumentValue(media_urn={self.media_urn!r}, value=<{len(self.value)} bytes>)"

    def __eq__(self, other):
        if not isinstance(other, CapArgumentValue):
            return False
        return self.media_urn == other.media_urn and self.value == other.value

    def clone(self) -> "CapArgumentValue":
        """Create an independent copy"""
        return CapArgumentValue(self.media_urn, bytes(self.value))

    @staticmethod
    def build_request_frames(
        request_id: MessageId,
        cap_urn: str,
        arguments: List["CapArgumentValue"],
        max_chunk: int,
    ) -> List[Frame]:
        """Build protocol-v2 request frames preserving each argument media URN."""
        import uuid as _uuid

        frames: List[Frame] = [Frame.req(request_id, cap_urn, b"", "application/cbor")]

        for arg in arguments:
            stream_id = str(_uuid.uuid4())
            frames.append(Frame.stream_start(request_id, stream_id, arg.media_urn))

            offset = 0
            chunk_index = 0
            while offset < len(arg.value):
                chunk_size = min(len(arg.value) - offset, max_chunk)
                chunk_bytes = arg.value[offset:offset + chunk_size]
                cbor_payload = cbor2.dumps(chunk_bytes)
                frames.append(
                    Frame.chunk(
                        request_id,
                        stream_id,
                        0,
                        cbor_payload,
                        chunk_index,
                        compute_checksum(cbor_payload),
                    )
                )
                offset += chunk_size
                chunk_index += 1

            frames.append(Frame.stream_end(request_id, stream_id, chunk_index))

        frames.append(Frame.end(request_id, None))
        return frames


class CapResultKind(Enum):
    SCALAR = "scalar"
    LIST = "list"
    EMPTY = "empty"


class CapResult:
    """Result from a cap execution."""

    def __init__(self, kind: CapResultKind, data: bytes = None, items: list = None):
        self.kind = kind
        self.data = data  # for SCALAR kind
        self.items = items  # for LIST kind (list of CBOR values)

    @classmethod
    def scalar(cls, data: bytes) -> "CapResult":
        return cls(CapResultKind.SCALAR, data=data)

    @classmethod
    def list_items(cls, items: list) -> "CapResult":
        return cls(CapResultKind.LIST, items=items)

    @classmethod
    def empty(cls) -> "CapResult":
        return cls(CapResultKind.EMPTY)
