"""Bifaci protocol — frames, I/O, runtimes."""

from typing import Optional

import cbor2


def decode_chunk_payload(payload: bytes) -> Optional[bytes]:
    """CBOR-decode a response chunk payload to extract raw bytes.

    Converts any CBOR value to its byte representation:
    - Bytes: raw binary data (returned as-is)
    - Text: UTF-8 bytes (e.g., JSON/NDJSON content)
    - Integer: decimal string representation as bytes
    - Float: decimal string representation as bytes
    - Bool: b"true" or b"false"
    - None/Null: empty bytes
    - Tagged: unwraps and decodes inner value
    - Array/Map: not supported (returns None)

    Returns None if the payload is not valid CBOR or contains an unsupported type.
    """
    try:
        value = cbor2.loads(payload)
    except Exception:
        return None
    return _decode_cbor_value(value)


def _decode_cbor_value(value) -> Optional[bytes]:
    """Convert a decoded CBOR value to bytes."""
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, bool):
        # Must check bool BEFORE int (bool is subclass of int in Python)
        return b"true" if value else b"false"
    if isinstance(value, int):
        return str(value).encode("utf-8")
    if isinstance(value, float):
        return str(value).encode("utf-8")
    if value is None:
        return b""
    if isinstance(value, cbor2.CBORTag):
        return _decode_cbor_value(value.value)
    # Array and Map are not directly convertible to bytes
    return None
