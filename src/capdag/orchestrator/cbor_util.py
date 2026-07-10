"""CBOR split/assemble utilities for ForEach execution.

The bifaci protocol uses CBOR throughout. These utilities handle:

**CBOR Sequence (RFC 8742)** — the primary format for list data in the DAG:
- Splitting an RFC 8742 CBOR sequence (concatenated self-delimiting CBOR values) into items
- Assembling individually-serialized CBOR items into a CBOR sequence (concatenation, no wrapper)
- Wrapping RAW (non-CBOR) item bytes into a CBOR sequence of CBOR byte-string
  values (distinct from assemble, which validates rather than wraps)

**CBOR Array** — wrapping/unwrapping items in a CBOR array:
- Splitting a CBOR array into individually-serialized items
- Assembling individually-serialized items into a single CBOR array

Mirrors Rust's orchestrator/cbor_util.rs exactly.
"""

from __future__ import annotations

from typing import List

import cbor2


def _cbor_item_length(data: bytes, offset: int = 0) -> int:
    """Return the byte length of one definite-length CBOR data item."""
    if offset >= len(data):
        raise CborDeserializeError("unexpected end of CBOR data")

    initial = data[offset]
    major = initial >> 5
    additional = initial & 0x1F
    pos = offset + 1

    def read_argument() -> int:
        nonlocal pos
        if additional < 24:
            return additional
        if additional == 24:
            size = 1
        elif additional == 25:
            size = 2
        elif additional == 26:
            size = 4
        elif additional == 27:
            size = 8
        elif additional == 31:
            raise CborDeserializeError("indefinite-length CBOR items are not supported")
        else:
            raise CborDeserializeError("invalid CBOR additional information")
        if pos + size > len(data):
            raise CborDeserializeError("truncated CBOR length")
        value = int.from_bytes(data[pos:pos + size], "big")
        pos += size
        return value

    if major in (0, 1):
        read_argument()
        return pos - offset

    if major in (2, 3):
        length = read_argument()
        if pos + length > len(data):
            raise CborDeserializeError("truncated CBOR data")
        return pos + length - offset

    if major == 4:
        length = read_argument()
        item_offset = pos
        for _ in range(length):
            item_offset += _cbor_item_length(data, item_offset)
        return item_offset - offset

    if major == 5:
        length = read_argument()
        item_offset = pos
        for _ in range(length * 2):
            item_offset += _cbor_item_length(data, item_offset)
        return item_offset - offset

    if major == 6:
        read_argument()
        return pos - offset + _cbor_item_length(data, pos)

    if major == 7:
        if additional < 24:
            if additional == 31:
                raise CborDeserializeError("invalid standalone break marker")
            return pos - offset
        if additional == 24:
            size = 1
        elif additional == 25:
            size = 2
        elif additional == 26:
            size = 4
        elif additional == 27:
            size = 8
        else:
            raise CborDeserializeError("invalid CBOR simple value")
        if pos + size > len(data):
            raise CborDeserializeError("truncated CBOR simple value")
        return pos + size - offset

    raise CborDeserializeError("invalid CBOR major type")


def _is_break_marker(value) -> bool:
    """Return true for cbor2 break-marker sentinels across cbor2 versions."""
    break_marker = getattr(cbor2, "break_marker", None)
    return break_marker is not None and value is break_marker


def _decode_one(data: bytes):
    """Decode exactly one CBOR item and return (value, bytes_consumed)."""
    consumed = _cbor_item_length(data)
    value = cbor2.loads(data[:consumed])
    if _is_break_marker(value):
        raise CborDeserializeError("invalid standalone break marker")
    return value, consumed


def _strict_cbor_loads(data: bytes):
    """Decode one standalone CBOR value and reject invalid top-level break markers."""
    value, consumed = _decode_one(data)
    if consumed != len(data):
        raise CborDeserializeError("trailing bytes after CBOR item")
    return value


class CborUtilError(Exception):
    """Base class for CBOR utility errors."""
    pass


class CborDeserializeError(CborUtilError):
    """Failed to deserialize CBOR data."""
    def __init__(self, message: str) -> None:
        super().__init__(f"Failed to deserialize CBOR data: {message}")


class CborNotAnArrayError(CborUtilError):
    """CBOR data is not an array (expected array for splitting)."""
    def __init__(self) -> None:
        super().__init__("CBOR data is not an array (expected array for splitting)")


class CborSerializeError(CborUtilError):
    """Failed to serialize CBOR value."""
    def __init__(self, message: str) -> None:
        super().__init__(f"Failed to serialize CBOR value: {message}")


class CborEmptyArrayError(CborUtilError):
    """Empty CBOR array — nothing to split."""
    def __init__(self) -> None:
        super().__init__("Empty CBOR array — nothing to split")


def split_cbor_array(data: bytes) -> List[bytes]:
    """Split a CBOR-encoded array into individually-serialized CBOR items.

    Each returned bytes is a complete, independently-parseable CBOR value.

    Raises:
        CborNotAnArrayError: If the input is not a CBOR array.
        CborEmptyArrayError: If the array has zero elements.
        CborDeserializeError: If the input bytes are not valid CBOR.
    """
    try:
        value, consumed = _decode_one(data)
    except Exception as e:
        if isinstance(e, CborDeserializeError):
            raise
        raise CborDeserializeError(str(e)) from e

    if not isinstance(value, list):
        raise CborNotAnArrayError()

    if consumed != len(data):
        raise CborDeserializeError("trailing bytes after CBOR array")

    if len(value) == 0:
        raise CborEmptyArrayError()

    result: List[bytes] = []
    for item in value:
        try:
            result.append(cbor2.dumps(item))
        except Exception as e:
            raise CborSerializeError(str(e)) from e

    return result


def assemble_cbor_array(items: List[bytes]) -> bytes:
    """Assemble individually-serialized CBOR items into a single CBOR array.

    Each input bytes must be a complete CBOR value. The result is a CBOR array
    containing all items in order.

    Raises:
        CborDeserializeError: If any item is not valid CBOR.
        CborSerializeError: If the assembled array cannot be serialized.
    """
    values = []
    for i, item in enumerate(items):
        try:
            values.append(_strict_cbor_loads(item))
        except Exception as e:
            if isinstance(e, CborDeserializeError):
                raise CborDeserializeError(f"Item {i}: {e}") from e
            raise CborDeserializeError(f"Item {i}: {e}") from e

    try:
        return cbor2.dumps(values)
    except Exception as e:
        raise CborSerializeError(str(e)) from e


def split_cbor_sequence(data: bytes) -> List[bytes]:
    """Split an RFC 8742 CBOR sequence into individually-serialized CBOR items.

    A CBOR sequence is a concatenation of independently-encoded CBOR data items
    with no array wrapper. Each item is a complete, self-delimiting CBOR value.
    This function iterates through the sequence by decoding values one at a time.

    Returns each item re-serialized as independent bytes.

    Raises:
        CborEmptyArrayError: If the input is empty or contains no decodable items.
        CborDeserializeError: If any CBOR value is malformed (including truncation).
    """
    if not data:
        raise CborEmptyArrayError()

    items: List[bytes] = []
    offset = 0

    while offset < len(data):
        chunk = data[offset:]
        try:
            value, consumed = _decode_one(chunk)
        except Exception as e:
            if isinstance(e, CborDeserializeError):
                raise
            raise CborDeserializeError(str(e)) from e

        try:
            item_bytes = cbor2.dumps(value)
        except Exception as e:
            raise CborSerializeError(str(e)) from e

        if not item_bytes:
            raise CborDeserializeError("decoded empty CBOR item")

        items.append(item_bytes)
        offset += consumed

    if not items:
        raise CborEmptyArrayError()

    return items


def assemble_cbor_sequence(items: List[bytes]) -> bytes:
    """Assemble individually-serialized CBOR items into an RFC 8742 CBOR sequence.

    Each input item must be a complete CBOR value. The result is their raw
    concatenation (no array wrapper). This is the inverse of split_cbor_sequence.

    Raises:
        CborDeserializeError: If any item is not valid CBOR.
    """
    result = bytearray()
    for i, item in enumerate(items):
        # Validate each item is valid CBOR
        try:
            _strict_cbor_loads(item)
        except Exception as e:
            if isinstance(e, CborDeserializeError):
                raise CborDeserializeError(f"Item {i}: {e}") from e
            raise CborDeserializeError(f"Item {i}: {e}") from e
        result.extend(item)
    return bytes(result)


def wrap_raw_items_as_cbor_sequence(items: List[bytes]) -> bytes:
    """Wrap raw (unwrapped) item bytes into an RFC 8742 CBOR sequence.

    Each raw item -- the bytes yielded by decode_terminal_output /
    unwrap_cbor_value (PNG frames, JSON records, ...) -- is re-encoded as a
    single self-delimiting CBOR byte-string value, and the values are
    concatenated. This is the storage form a *sequence* node's node_data must
    take so that a downstream cap's input (send_one_stream, which splits the
    sequence and forwards each item's CBOR bytes *without* re-wrapping) and
    split_cbor_sequence both see well-formed self-delimiting values.

    Contrast assemble_cbor_sequence, which requires each item to ALREADY be a
    complete CBOR value (it validates rather than wraps) -- the form used when
    the caller has itself CBOR-encoded each item (e.g. machfab's file-item
    interpreter).

    Raises:
        CborSerializeError: If an item cannot be CBOR-serialized (practically
            never for a byte string).
    """
    result = bytearray()
    for item in items:
        try:
            result.extend(cbor2.dumps(item))
        except Exception as e:
            raise CborSerializeError(str(e)) from e
    return bytes(result)
