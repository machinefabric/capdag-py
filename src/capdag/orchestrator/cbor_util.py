"""CBOR split/assemble utilities for ForEach execution.

The bifaci protocol uses CBOR throughout. These utilities handle:

**CBOR Sequence (RFC 8742)** — the primary format for list data in the DAG:
- Splitting an RFC 8742 CBOR sequence (concatenated self-delimiting CBOR values) into items
- Assembling individually-serialized CBOR items into a CBOR sequence (concatenation, no wrapper)

**CBOR Array** — wrapping/unwrapping items in a CBOR array:
- Splitting a CBOR array into individually-serialized items
- Assembling individually-serialized items into a single CBOR array

Mirrors Rust's orchestrator/cbor_util.rs exactly.
"""

from __future__ import annotations

import io
from typing import List

import cbor2


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
        value = cbor2.loads(data)
    except Exception as e:
        raise CborDeserializeError(str(e)) from e

    if not isinstance(value, list):
        raise CborNotAnArrayError()

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
            values.append(cbor2.loads(item))
        except Exception as e:
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
    stream = io.BytesIO(data)

    while stream.tell() < len(data):
        try:
            decoder = cbor2.CBORDecoder(stream)
            value = decoder.decode()
        except Exception as e:
            raise CborDeserializeError(str(e)) from e

        try:
            items.append(cbor2.dumps(value))
        except Exception as e:
            raise CborSerializeError(str(e)) from e

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
            cbor2.loads(item)
        except Exception as e:
            raise CborDeserializeError(f"Item {i}: {e}") from e
        result.extend(item)
    return bytes(result)
