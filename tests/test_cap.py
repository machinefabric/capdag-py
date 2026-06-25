"""Tests for Cap - mirroring capdag Rust tests

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
import json
from capdag import CapUrn
from capdag.cap.definition import Cap, CapArg, CapOutput, RegisteredBy, StdinSource, PositionSource, CliFlagSource
from capdag.urn.media_urn import MEDIA_STRING, MEDIA_INTEGER, MEDIA_VOID, MEDIA_OBJECT


def _test_urn(tags: str) -> str:
    """Helper to build cap URN with standard in/out for testing"""
    return f'cap:in="{MEDIA_VOID}";out="{MEDIA_OBJECT}";{tags}'


# TEST108: Test creating new cap with URN, title, and command verifies correct initialization
def test_108_cap_creation():
    urn = CapUrn.from_string(_test_urn("extract;target=metadata"))
    cap = Cap(urn, "Extract Metadata", "extract-metadata")

    assert cap.urn == urn
    assert cap.title == "Extract Metadata"
    assert cap.command == "extract-metadata"
    assert cap.urn_string() == urn.to_string()


# TEST109: Test creating cap with metadata initializes and retrieves metadata correctly
def test_109_cap_with_args():
    urn = CapUrn.from_string(_test_urn("process"))
    cap = Cap(urn, "Process Data", "process-data")

    # Add positional argument
    arg = CapArg(
        media_urn=MEDIA_STRING,
        required=True,
        sources=[PositionSource(0)],
    )
    cap.add_arg(arg)

    args = cap.get_args()
    assert len(args) == 1
    assert args[0].media_urn == MEDIA_STRING
    assert args[0].required is True


# TEST110: Test cap matching with subset semantics for request fulfillment
def test_110_cap_with_stdin():
    urn = CapUrn.from_string(_test_urn("convert"))
    cap = Cap(urn, "Convert", "convert")

    # Add stdin argument
    stdin_arg = CapArg(
        media_urn="media:pdf",
        required=True,
        sources=[StdinSource("media:pdf")],
    )
    cap.add_arg(stdin_arg)

    assert cap.get_stdin_media_urn() == "media:pdf"


# TEST111: Test getting and setting cap title updates correctly
def test_111_cap_without_stdin():
    urn = CapUrn.from_string(_test_urn("process"))
    cap = Cap(urn, "Process", "process")

    # Add non-stdin argument
    arg = CapArg(
        media_urn=MEDIA_STRING,
        required=True,
        sources=[PositionSource(0)],
    )
    cap.add_arg(arg)

    assert cap.get_stdin_media_urn() is None


# TEST112: Test cap equality based on URN and title matching
def test_112_cap_with_output():
    urn = CapUrn.from_string(_test_urn("generate"))
    cap = Cap(urn, "Generate", "generate")

    output = CapOutput(
        media_urn=MEDIA_OBJECT,
        output_description="Generated output",
    )
    cap.set_output(output)

    assert cap.output is not None
    assert cap.output.media_urn == MEDIA_OBJECT
    assert cap.output.output_description == "Generated output"


# TEST113: Test cap stdin support via args with stdin source and serialization roundtrip
def test_113_cap_with_metadata():
    urn = CapUrn.from_string(_test_urn("test"))
    metadata = {"supports_streaming": "true", "version": "2.0"}
    cap = Cap.with_metadata(urn, "Test Cap", "test-cap", metadata)

    assert cap.has_metadata("supports_streaming")
    assert cap.get_metadata("supports_streaming") == "true"
    assert cap.has_metadata("version")
    assert cap.get_metadata("version") == "2.0"
    assert not cap.has_metadata("nonexistent")


# TEST114: Test ArgSource type variants stdin, position, and cli_flag with their accessors
def test_114_cap_json_serialization():
    urn = CapUrn.from_string(_test_urn("process"))
    cap = Cap(urn, "Process", "process-cmd")
    cap.set_description("A processing capability")

    arg = CapArg(
        media_urn=MEDIA_STRING,
        required=True,
        sources=[PositionSource(0)],
        arg_description="Input file",
    )
    cap.add_arg(arg)

    output = CapOutput(
        media_urn=MEDIA_OBJECT,
        output_description="Processed output",
    )
    cap.set_output(output)

    cap_dict = cap.to_dict()

    assert "urn" in cap_dict
    assert "title" in cap_dict
    assert cap_dict["title"] == "Process"
    assert "command" in cap_dict
    assert cap_dict["command"] == "process-cmd"
    assert "cap_description" in cap_dict
    assert "args" in cap_dict
    assert len(cap_dict["args"]) == 1
    assert "output" in cap_dict


# TEST115: Test CapArg serialization and deserialization with multiple sources
def test_115_cap_arg_serialization():
    arg = CapArg(
        media_urn="media:string",
        required=True,
        sources=[CliFlagSource("--name"), PositionSource(0)],
        arg_description="The name argument",
        default_value=400,
        metadata={"kind": "example", "flags": [True, False]},
    )

    json_str = json.dumps(arg.to_dict())
    parsed_dict = json.loads(json_str)
    restored_arg = CapArg.from_dict(parsed_dict)

    assert restored_arg.media_urn == arg.media_urn
    assert restored_arg.required == arg.required
    assert restored_arg.arg_description == arg.arg_description
    assert restored_arg.default_value == 400
    assert restored_arg.metadata == {"kind": "example", "flags": [True, False]}
    assert len(restored_arg.sources) == 2
    assert isinstance(restored_arg.sources[0], CliFlagSource)
    assert isinstance(restored_arg.sources[1], PositionSource)


# TEST116: Test CapArg constructor methods basic and with_description create args correctly
def test_116_cap_arg_constructors():
    basic_arg = CapArg(
        media_urn="media:string",
        required=True,
        sources=[CliFlagSource("--name")],
    )
    assert basic_arg.media_urn == "media:string"
    assert basic_arg.required is True
    assert len(basic_arg.sources) == 1
    assert basic_arg.arg_description is None
    assert basic_arg.default_value is None

    described_arg = CapArg(
        media_urn="media:integer",
        required=False,
        sources=[PositionSource(0)],
        arg_description="The count argument",
        default_value=10,
    )
    assert described_arg.media_urn == "media:integer"
    assert described_arg.required is False
    assert described_arg.arg_description == "The count argument"
    assert described_arg.default_value == 10


# TEST591: is_more_specific_than returns true when self has more tags for same request
def test_591_is_more_specific_than():
    general = Cap(
        CapUrn.from_string(_test_urn("transform")),
        "General",
        "cmd",
    )
    specific = Cap(
        CapUrn.from_string(_test_urn("transform;format=json")),
        "Specific",
        "cmd",
    )
    unrelated = Cap(
        CapUrn.from_string(_test_urn("convert")),
        "Unrelated",
        "cmd",
    )

    # Specific is more specific than general for the general request
    assert specific.is_more_specific_than(general, _test_urn("transform")), \
        "specific cap must be more specific than general"
    assert not general.is_more_specific_than(specific, _test_urn("transform")), \
        "general cap must not be more specific than specific"

    # If either doesn't accept the request, returns false
    assert not general.is_more_specific_than(unrelated, _test_urn("transform")), \
        "unrelated cap doesn't accept request, so no comparison possible"


# TEST592: remove_metadata adds then removes metadata correctly
def test_592_remove_metadata():
    urn = CapUrn.from_string(_test_urn("test"))
    cap = Cap(urn, "Test", "cmd")

    cap.set_metadata("key1", "val1")
    cap.set_metadata("key2", "val2")
    assert cap.has_metadata("key1")
    assert cap.has_metadata("key2")

    removed = cap.remove_metadata("key1")
    assert removed == "val1"
    assert not cap.has_metadata("key1")
    assert cap.has_metadata("key2")

    # Removing non-existent returns None
    assert cap.remove_metadata("nonexistent") is None


# TEST593: registered_by lifecycle — set, get, clear
def test_593_registered_by_lifecycle():
    urn = CapUrn.from_string(_test_urn("test"))
    cap = Cap(urn, "Test", "cmd")

    # Initially None
    assert cap.get_registered_by() is None

    # Set
    reg = RegisteredBy(username="alice", registered_at="2026-02-19T10:00:00Z")
    cap.set_registered_by(reg)
    got = cap.get_registered_by()
    assert got is not None
    assert got.username == "alice"
    assert got.registered_at == "2026-02-19T10:00:00Z"

    # Clear
    cap.clear_registered_by()
    assert cap.get_registered_by() is None


# TEST594: metadata_json lifecycle — set, get, clear
def test_594_metadata_json_lifecycle():
    urn = CapUrn.from_string(_test_urn("test"))
    cap = Cap(urn, "Test", "cmd")

    # Initially None
    assert cap.get_metadata_json() is None

    # Set
    json_data = {"version": 2, "tags": ["experimental"]}
    cap.set_metadata_json(json_data)
    assert cap.get_metadata_json() == json_data

    # Clear
    cap.clear_metadata_json()
    assert cap.get_metadata_json() is None


# TEST595: with_args constructor stores args correctly
def test_595_with_args_constructor():
    urn = CapUrn.from_string(_test_urn("test"))
    args = [
        CapArg(
            media_urn="media:string",
            required=True,
            sources=[PositionSource(0)],
        ),
        CapArg(
            media_urn="media:integer",
            required=False,
            sources=[CliFlagSource("--count")],
        ),
    ]

    cap = Cap.with_args(urn, "Test", "cmd", args)
    assert len(cap.get_args()) == 2
    assert cap.get_args()[0].media_urn == "media:string"
    assert cap.get_args()[0].required is True
    assert cap.get_args()[1].media_urn == "media:integer"
    assert cap.get_args()[1].required is False


# TEST596: with_full_definition constructor stores all fields
def test_596_with_full_definition_constructor():
    urn = CapUrn.from_string(_test_urn("test"))
    metadata = {"env": "prod"}
    args = [CapArg(media_urn="media:string", required=True, sources=[])]
    output = CapOutput(media_urn="media:object", output_description="Output object")
    json_meta = {"v": 1}

    cap = Cap.with_full_definition(
        urn=urn,
        title="Full Cap",
        cap_description="Description",
        metadata=metadata,
        command="full-cmd",
        args=args,
        output=output,
        metadata_json=json_meta,
    )

    assert cap.title == "Full Cap"
    assert cap.cap_description == "Description"
    assert cap.get_metadata("env") == "prod"
    assert cap.get_command() == "full-cmd"
    assert len(cap.get_args()) == 1
    assert cap.get_output() is not None
    assert cap.get_output().media_urn == "media:object"
    assert cap.get_metadata_json() == json_meta
    # registered_by is not set by with_full_definition
    assert cap.get_registered_by() is None


# TEST597: CapArg::with_full_definition stores all fields including optional ones
def test_597_cap_arg_with_full_definition():
    default_val = {"chunk_size": 400, "timestamps": False}
    meta = {"hint": "enter name"}

    arg = CapArg.with_full_definition(
        media_urn="media:string",
        required=True,
        sources=[CliFlagSource("--name")],
        arg_description="User name",
        default_value=default_val,
        metadata=meta,
    )

    assert arg.media_urn == "media:string"
    assert arg.required is True
    assert arg.arg_description == "User name"
    assert arg.default_value == default_val
    assert arg.get_metadata() == meta

    # Metadata lifecycle
    import copy
    arg2 = copy.deepcopy(arg)
    arg2.clear_metadata()
    assert arg2.get_metadata() is None
    arg2.set_metadata("new")
    assert arg2.get_metadata() == "new"


# TEST598: CapOutput lifecycle — set_output, set/clear metadata
def test_598_cap_output_lifecycle():
    urn = CapUrn.from_string(_test_urn("test"))
    cap = Cap(urn, "Test", "cmd")

    # Initially no output
    assert cap.get_output() is None

    # Set output
    output = CapOutput(media_urn="media:string", output_description="Text output")
    output.set_metadata({"format": "plain"})
    cap.set_output(output)

    got = cap.get_output()
    assert got is not None
    assert got.get_media_urn() == "media:string"
    assert got.output_description == "Text output"
    assert got.get_metadata() is not None

    # CapOutput with_full_definition
    output2 = CapOutput.with_full_definition(
        media_urn="media:json",
        output_description="JSON output",
        metadata={"v": 2},
    )
    assert output2.get_media_urn() == "media:json"
    assert output2.get_metadata() is not None

    # Clear metadata on output
    import copy
    output3 = copy.deepcopy(output2)
    output3.clear_metadata()
    assert output3.get_metadata() is None


# TEST0054: Cap.version=0 round-trip — zero is the default and must NOT appear in the serialized dict
def test_0054_cap_version_zero_round_trip():
    urn = CapUrn.from_string(_test_urn("test"))
    cap = Cap(urn, "Test", "cmd")

    # Default is 0
    assert cap.version == 0

    # Serialize: "version" key must be absent when version==0
    d = cap.to_dict()
    assert "version" not in d, f"version key must be absent when version==0, got dict: {d}"

    # Deserialize from a dict that has no "version" key
    cap2 = Cap.from_dict(d)
    assert cap2.version == 0, f"expected version==0 after deserializing from dict without version key, got {cap2.version}"


# TEST0055: Cap.version nonzero round-trip — emitted in dict and restored on deserialization
def test_0055_cap_version_nonzero_round_trip():
    urn = CapUrn.from_string(_test_urn("test"))
    cap = Cap(urn, "Test", "cmd")
    cap.version = 3

    # Serialize: "version" must be present and equal to 3
    d = cap.to_dict()
    assert "version" in d, f"version key must be present when version!=0, got dict: {d}"
    assert d["version"] == 3, f"expected version==3 in dict, got {d['version']}"

    # Deserialize from a dict that has "version": 3
    d2 = dict(d)
    d2["version"] = 3
    cap2 = Cap.from_dict(d2)
    assert cap2.version == 3, f"expected version==3 after round-trip, got {cap2.version}"
