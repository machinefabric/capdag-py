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


# TEST108: Test Cap creation with URN, title, and command
def test_108_cap_creation():
    urn = CapUrn.from_string(_test_urn("op=extract;target=metadata"))
    cap = Cap(urn, "Extract Metadata", "extract-metadata")

    assert cap.urn == urn
    assert cap.title == "Extract Metadata"
    assert cap.command == "extract-metadata"
    assert cap.urn_string() == urn.to_string()


# TEST109: Test Cap with args stores and retrieves arguments correctly
def test_109_cap_with_args():
    urn = CapUrn.from_string(_test_urn("op=process"))
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


# TEST110: Test Cap with stdin source stores stdin media URN correctly
def test_110_cap_with_stdin():
    urn = CapUrn.from_string(_test_urn("op=convert"))
    cap = Cap(urn, "Convert", "convert")

    # Add stdin argument
    stdin_arg = CapArg(
        media_urn="media:pdf",
        required=True,
        sources=[StdinSource("media:pdf")],
    )
    cap.add_arg(stdin_arg)

    assert cap.get_stdin_media_urn() == "media:pdf"


# TEST111: Test Cap with no stdin returns None for get_stdin_media_urn
def test_111_cap_without_stdin():
    urn = CapUrn.from_string(_test_urn("op=process"))
    cap = Cap(urn, "Process", "process")

    # Add non-stdin argument
    arg = CapArg(
        media_urn=MEDIA_STRING,
        required=True,
        sources=[PositionSource(0)],
    )
    cap.add_arg(arg)

    assert cap.get_stdin_media_urn() is None


# TEST112: Test Cap with output stores output definition correctly
def test_112_cap_with_output():
    urn = CapUrn.from_string(_test_urn("op=generate"))
    cap = Cap(urn, "Generate", "generate")

    output = CapOutput(
        media_urn=MEDIA_OBJECT,
        output_description="Generated output",
    )
    cap.set_output(output)

    assert cap.output is not None
    assert cap.output.media_urn == MEDIA_OBJECT
    assert cap.output.output_description == "Generated output"


# TEST113: Test Cap with metadata stores and retrieves metadata correctly
def test_113_cap_with_metadata():
    urn = CapUrn.from_string(_test_urn("op=test"))
    metadata = {"supports_streaming": "true", "version": "2.0"}
    cap = Cap.with_metadata(urn, "Test Cap", "test-cap", metadata)

    assert cap.has_metadata("supports_streaming")
    assert cap.get_metadata("supports_streaming") == "true"
    assert cap.has_metadata("version")
    assert cap.get_metadata("version") == "2.0"
    assert not cap.has_metadata("nonexistent")


# TEST114: Test Cap JSON serialization includes all fields
def test_114_cap_json_serialization():
    urn = CapUrn.from_string(_test_urn("op=process"))
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


# TEST115: Test Cap JSON deserialization roundtrip preserves all data
def test_115_cap_json_roundtrip():
    urn = CapUrn.from_string(_test_urn("op=convert"))
    cap = Cap(urn, "Convert", "convert-cmd")

    stdin_arg = CapArg(
        media_urn="media:pdf",
        required=True,
        sources=[StdinSource("media:pdf")],
    )
    cap.add_arg(stdin_arg)

    # Serialize and deserialize
    cap_dict = cap.to_dict()
    json_str = json.dumps(cap_dict)
    parsed_dict = json.loads(json_str)
    restored_cap = Cap.from_dict(parsed_dict)

    assert restored_cap.title == cap.title
    assert restored_cap.command == cap.command
    assert restored_cap.urn_string() == cap.urn_string()
    assert len(restored_cap.get_args()) == len(cap.get_args())
    assert restored_cap.get_stdin_media_urn() == cap.get_stdin_media_urn()


# TEST116: Test CapArg with multiple sources stores all source types
def test_116_cap_arg_multiple_sources():
    sources = [
        StdinSource("media:"),
        PositionSource(0),
        CliFlagSource("--input"),
    ]

    arg = CapArg(
        media_urn=MEDIA_STRING,
        required=True,
        sources=sources,
    )

    assert len(arg.sources) == 3
    assert isinstance(arg.sources[0], StdinSource)
    assert isinstance(arg.sources[1], PositionSource)
    assert isinstance(arg.sources[2], CliFlagSource)

    # Test serialization
    arg_dict = arg.to_dict()
    assert len(arg_dict["sources"]) == 3
    assert "stdin" in arg_dict["sources"][0]
    assert "position" in arg_dict["sources"][1]
    assert "cli_flag" in arg_dict["sources"][2]


# TEST591: is_more_specific_than returns true when self has more tags for same request
def test_591_is_more_specific_than():
    general = Cap(
        CapUrn.from_string(_test_urn("op=transform")),
        "General",
        "cmd",
    )
    specific = Cap(
        CapUrn.from_string(_test_urn("op=transform;format=json")),
        "Specific",
        "cmd",
    )
    unrelated = Cap(
        CapUrn.from_string(_test_urn("op=convert")),
        "Unrelated",
        "cmd",
    )

    # Specific is more specific than general for the general request
    assert specific.is_more_specific_than(general, _test_urn("op=transform")), \
        "specific cap must be more specific than general"
    assert not general.is_more_specific_than(specific, _test_urn("op=transform")), \
        "general cap must not be more specific than specific"

    # If either doesn't accept the request, returns false
    assert not general.is_more_specific_than(unrelated, _test_urn("op=transform")), \
        "unrelated cap doesn't accept request, so no comparison possible"


# TEST592: remove_metadata adds then removes metadata correctly
def test_592_remove_metadata():
    urn = CapUrn.from_string(_test_urn("op=test"))
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
    urn = CapUrn.from_string(_test_urn("op=test"))
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
    urn = CapUrn.from_string(_test_urn("op=test"))
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
    urn = CapUrn.from_string(_test_urn("op=test"))
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
    urn = CapUrn.from_string(_test_urn("op=test"))
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
        media_specs=[],
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


# TEST597: CapArg.with_full_definition stores all fields including optional ones
def test_597_cap_arg_with_full_definition():
    default_val = "default_text"
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
    urn = CapUrn.from_string(_test_urn("op=test"))
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
