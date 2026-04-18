"""Tests for orchestrator CBOR array utilities."""

import cbor2
import pytest

from capdag.orchestrator.cbor_util import (
    CborDeserializeError,
    CborEmptyArrayError,
    CborNotAnArrayError,
    assemble_cbor_array,
    assemble_cbor_sequence,
    split_cbor_array,
    split_cbor_sequence,
)


# TEST780: split_cbor_array splits a simple array of integers
def test_780_split_integer_array():
    data = cbor2.dumps([1, 2, 3])
    items = split_cbor_array(data)
    assert len(items) == 3
    for index, item in enumerate(items, start=1):
        assert cbor2.loads(item) == index


# TEST782: split_cbor_array rejects non-array input
def test_782_split_non_array():
    data = cbor2.dumps("not an array")
    with pytest.raises(CborNotAnArrayError):
        split_cbor_array(data)


# TEST783: split_cbor_array rejects empty array
def test_783_split_empty_array():
    data = cbor2.dumps([])
    with pytest.raises(CborEmptyArrayError):
        split_cbor_array(data)


# TEST784: split_cbor_array rejects invalid CBOR bytes
def test_784_split_invalid_cbor():
    with pytest.raises(CborDeserializeError):
        split_cbor_array(bytes([0xFF, 0xFE, 0xFD]))


# TEST785: assemble_cbor_array creates array from individual items
def test_785_assemble_integer_array():
    items = [cbor2.dumps(10), cbor2.dumps(20), cbor2.dumps(30)]
    assembled = assemble_cbor_array(items)
    assert cbor2.loads(assembled) == [10, 20, 30]


# TEST786: split then assemble roundtrip preserves data
def test_786_roundtrip_split_assemble():
    original = [
        {"name": "Alice", "age": 30},
        {"name": "Bob", "age": 25},
        {"name": "Carol", "age": 35},
    ]
    encoded = cbor2.dumps(original)
    items = split_cbor_array(encoded)
    reassembled = assemble_cbor_array(items)
    assert cbor2.loads(reassembled) == original


# TEST955: split_cbor_array with nested maps
def test_955_split_map_array():
    original = [{"name": "Alice"}, {"name": "Bob"}]
    items = split_cbor_array(cbor2.dumps(original))
    assert len(items) == 2
    assert cbor2.loads(items[0]) == {"name": "Alice"}
    assert cbor2.loads(items[1]) == {"name": "Bob"}


# TEST956: assemble then split roundtrip preserves data
def test_956_roundtrip_assemble_split():
    items = [cbor2.dumps("a"), cbor2.dumps("b")]
    assembled = assemble_cbor_array(items)
    split_back = split_cbor_array(assembled)
    assert split_back == items


# TEST961: assemble empty list produces empty CBOR array
def test_961_assemble_empty():
    assert cbor2.loads(assemble_cbor_array([])) == []


# TEST962: assemble rejects invalid CBOR item
def test_962_assemble_invalid_item():
    with pytest.raises(CborDeserializeError):
        assemble_cbor_array([cbor2.dumps(1), bytes([0xFF, 0xFE])])


# TEST963: split preserves CBOR byte strings (binary data — the common case in bifaci)
def test_963_split_binary_items():
    pdf_bytes = bytes([0x25, 0x50, 0x44, 0x46])
    png_bytes = bytes([0x89, 0x50, 0x4E, 0x47])
    items = split_cbor_array(cbor2.dumps([pdf_bytes, png_bytes]))
    assert len(items) == 2
    assert cbor2.loads(items[0]) == pdf_bytes
    assert cbor2.loads(items[1]) == png_bytes


def _build_cbor_sequence(values):
    return b"".join(cbor2.dumps(v) for v in values)


# TEST964: split_cbor_sequence splits concatenated CBOR Bytes values
def test_964_split_sequence_bytes():
    seq = _build_cbor_sequence([b"page1 json data", b"page2 json data", b"page3 json data"])
    items = split_cbor_sequence(seq)
    assert len(items) == 3
    assert cbor2.loads(items[0]) == b"page1 json data"
    assert cbor2.loads(items[1]) == b"page2 json data"
    assert cbor2.loads(items[2]) == b"page3 json data"


# TEST965: split_cbor_sequence splits concatenated CBOR Text values
def test_965_split_sequence_text():
    seq = _build_cbor_sequence(["hello", "world"])
    items = split_cbor_sequence(seq)
    assert len(items) == 2
    assert cbor2.loads(items[0]) == "hello"
    assert cbor2.loads(items[1]) == "world"


# TEST966: split_cbor_sequence handles mixed types
def test_966_split_sequence_mixed():
    seq = _build_cbor_sequence([bytes([1, 2, 3]), "mixed", {"key": 42}, 99])
    items = split_cbor_sequence(seq)
    assert len(items) == 4
    assert cbor2.loads(items[0]) == bytes([1, 2, 3])
    assert cbor2.loads(items[3]) == 99


# TEST967: split_cbor_sequence single-item sequence
def test_967_split_sequence_single():
    seq = _build_cbor_sequence([bytes([0xDE, 0xAD])])
    items = split_cbor_sequence(seq)
    assert len(items) == 1
    assert cbor2.loads(items[0]) == bytes([0xDE, 0xAD])


# TEST968: roundtrip — assemble then split preserves items
def test_968_roundtrip_assemble_split_sequence():
    items = [cbor2.dumps(b"first"), cbor2.dumps(b"second"), cbor2.dumps("third")]
    assembled = assemble_cbor_sequence(items)
    assert split_cbor_sequence(assembled) == items


# TEST969: roundtrip — split then assemble preserves byte-for-byte
def test_969_roundtrip_split_assemble_sequence():
    seq = _build_cbor_sequence([b"alpha", b"beta"])
    items = split_cbor_sequence(seq)
    assert assemble_cbor_sequence(items) == seq


# TEST970: split_cbor_sequence rejects empty data
def test_970_split_sequence_empty():
    with pytest.raises(CborEmptyArrayError):
        split_cbor_sequence(b"")


# TEST971: split_cbor_sequence rejects truncated CBOR
def test_971_split_sequence_truncated():
    seq = bytearray(_build_cbor_sequence([b"complete"]))
    seq.append(0x4A)
    seq.extend([0x01, 0x02, 0x03])
    with pytest.raises(CborDeserializeError):
        split_cbor_sequence(bytes(seq))


# TEST972: assemble_cbor_sequence rejects invalid CBOR item
def test_972_assemble_sequence_invalid_item():
    with pytest.raises(CborDeserializeError):
        assemble_cbor_sequence([cbor2.dumps(1), bytes([0xFF, 0xFE])])


# TEST973: assemble_cbor_sequence with empty items list produces empty bytes
def test_973_assemble_sequence_empty():
    assert assemble_cbor_sequence([]) == b""


# TEST974: CBOR sequence is NOT a CBOR array — split_cbor_array rejects a sequence
def test_974_sequence_is_not_array():
    seq = _build_cbor_sequence([b"item1", b"item2"])
    with pytest.raises(CborNotAnArrayError):
        split_cbor_array(seq)


# TEST975: split_cbor_sequence works on data that is also a valid CBOR array (single top-level value)
def test_975_single_value_sequence():
    single = cbor2.dumps(b"solo")
    items = split_cbor_sequence(single)
    assert len(items) == 1
    assert cbor2.loads(items[0]) == b"solo"
