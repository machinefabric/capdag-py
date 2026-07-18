"""Tests for Cap - mirroring capdag Rust tests

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
import json
from capdag import CapUrn
from capdag.cap.definition import Cap, CapArg, CapOutput, RegisteredBy, StdinSource, PositionSource, CliFlagSource
from capdag.urn.media_urn import MEDIA_STRING, MEDIA_INTEGER, MEDIA_VOID, MEDIA_OBJECT, MediaUrn


def _test_urn(tags: str) -> str:
    """Helper to build cap URN with standard in/out for testing"""
    return f'cap:in="{MEDIA_VOID}";out="{MEDIA_OBJECT}";{tags}'


# TEST108: Test creating new cap with URN, title, and command verifies correct initialization
def test_108_cap_creation():
    urn = CapUrn.from_string(_test_urn("extract;target=metadata"))
    cap = Cap(urn, "Extract Metadata", ["extract-metadata"])

    assert cap.urn == urn
    assert cap.title == "Extract Metadata"
    assert cap.primary_alias() == "extract-metadata"
    assert cap.urn_string() == urn.to_string()


# TEST109: Test creating cap with metadata initializes and retrieves metadata correctly
def test_109_cap_with_metadata():
    urn = CapUrn.from_string(_test_urn("arithmetic;compute;subtype=math"))
    metadata = {
        "precision": "double",
        "operations": "add,subtract,multiply,divide",
    }
    cap = Cap.with_metadata(urn, "Perform Mathematical Operations", ["test-command"], metadata)

    assert cap.title == "Perform Mathematical Operations"
    assert cap.get_metadata("precision") == "double"
    assert cap.get_metadata("operations") == "add,subtract,multiply,divide"
    assert cap.has_metadata("precision")
    assert not cap.has_metadata("nonexistent")


# TEST110: Test cap matching with subset semantics for request fulfillment
def test_110_cap_matching():
    urn = CapUrn.from_string(_test_urn("transform;format=json;type=data_processing"))
    cap = Cap(urn, "Transform JSON Data", ["test-command"])

    assert cap.accepts_request(_test_urn("transform;format=json;type=data_processing"))
    assert cap.accepts_request(_test_urn("transform;format=*;type=data_processing"))
    assert cap.accepts_request(_test_urn("type=data_processing"))
    assert not cap.accepts_request(_test_urn("type=compute"))


# TEST111: Test getting and setting cap title updates correctly
def test_111_cap_title():
    urn = CapUrn.from_string(_test_urn("extract;target=metadata"))
    cap = Cap(urn, "Extract Document Metadata", ["extract-metadata"])

    assert cap.title == "Extract Document Metadata"

    cap.title = "Extract File Metadata"
    assert cap.title == "Extract File Metadata"


# TEST112: Test cap equality based on URN and title matching
def test_112_cap_definition_equality():
    urn1 = CapUrn.from_string(_test_urn("transform;format=json"))
    urn2 = CapUrn.from_string(_test_urn("transform;format=json"))

    cap1 = Cap(urn1, "Transform JSON Data", ["transform"])
    cap2 = Cap(urn2, "Transform JSON Data", ["transform"])
    cap3 = Cap(CapUrn.from_string(_test_urn("transform;format=json")), "Convert JSON Format", ["transform"])

    assert cap1 == cap2
    assert cap1 != cap3
    assert cap2 != cap3


# TEST113: Test cap stdin support via args with stdin source and serialization roundtrip
def test_113_cap_stdin():
    urn = CapUrn.from_string(_test_urn("generate;target=embeddings"))
    cap = Cap(urn, "Generate Embeddings", ["generate"])

    # By default, caps should not accept stdin
    assert not cap.accepts_stdin()
    assert cap.get_stdin_media_urn() is None

    # Enable stdin support by adding an arg with a stdin source
    cap.add_arg(CapArg(
        media_urn="media:enc=utf-8",
        required=True,
        sources=[StdinSource("media:enc=utf-8")],
        arg_description="Input text",
    ))

    assert cap.accepts_stdin()
    assert cap.get_stdin_media_urn() == "media:enc=utf-8"

    # Serialization preserves the args + stdin source.
    serialized = json.dumps(cap.to_dict())
    assert '"args"' in serialized
    assert '"stdin"' in serialized
    restored = Cap.from_dict(json.loads(serialized))
    assert restored.accepts_stdin()
    assert restored.get_stdin_media_urn() == "media:enc=utf-8"


# TEST114: Test ArgSource type variants stdin, position, and cli_flag with their accessors
def test_114_arg_source_types():
    stdin_src = StdinSource("media:enc=utf-8")
    assert stdin_src.stdin == "media:enc=utf-8"

    pos_src = PositionSource(2)
    assert pos_src.position == 2

    flag_src = CliFlagSource("--verbose")
    assert flag_src.cli_flag == "--verbose"


# TEST8101: (py-specific) Cap.to_dict emits the full wire shape including args
# and output. Behavior beyond the shared cross-mirror set, kept here as
# implementation-specific coverage.
def test_8101_cap_to_dict_wire_shape():
    urn = CapUrn.from_string(_test_urn("process"))
    cap = Cap(urn, "Process", ["process-cmd"])
    cap.set_description("A processing capability")
    cap.add_arg(CapArg(
        media_urn=MEDIA_STRING,
        required=True,
        sources=[PositionSource(0)],
        arg_description="Input file",
    ))
    cap.set_output(CapOutput(media_urn=MEDIA_OBJECT, output_description="Processed output"))

    cap_dict = cap.to_dict()
    assert cap_dict["title"] == "Process"
    assert cap_dict["aliases"] == ["process-cmd"]
    assert "cap_description" in cap_dict
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
    cap = Cap(urn, "Test", ["cmd"])

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
    cap = Cap(urn, "Test", ["cmd"])

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
    cap = Cap(urn, "Test", ["cmd"])

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

    cap = Cap.with_args(urn, "Test", ["cmd"], args)
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
        aliases=["full-cmd"],
        args=args,
        output=output,
        metadata_json=json_meta,
    )

    assert cap.title == "Full Cap"
    assert cap.cap_description == "Description"
    assert cap.get_metadata("env") == "prod"
    assert cap.primary_alias() == "full-cmd"
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
    cap = Cap(urn, "Test", ["cmd"])

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


# TEST6211: Cap.version=0 round-trip — zero is the default and must NOT appear in the serialized dict
def test_6211_cap_version_zero_round_trip():
    urn = CapUrn.from_string(_test_urn("test"))
    cap = Cap(urn, "Test", ["cmd"])

    # Default is 0
    assert cap.version == 0

    # Serialize: "version" key must be absent when version==0
    d = cap.to_dict()
    assert "version" not in d, f"version key must be absent when version==0, got dict: {d}"

    # Deserialize from a dict that has no "version" key
    cap2 = Cap.from_dict(d)
    assert cap2.version == 0, f"expected version==0 after deserializing from dict without version key, got {cap2.version}"


# TEST6215: Cap.version nonzero round-trip — emitted in dict and restored on deserialization
def test_6215_cap_version_nonzero_round_trip():
    urn = CapUrn.from_string(_test_urn("test"))
    cap = Cap(urn, "Test", ["cmd"])
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


# TEST1127: Documentation field round-trips through JSON serialize/deserialize.
def test_1127_cap_documentation_round_trip_with_markdown_body():
    urn = CapUrn.from_string(_test_urn("documented"))
    cap = Cap(urn, "Documented Cap", ["documented"])

    # A non-trivial markdown body — multi-line, headings, code blocks,
    # backticks, embedded quotes, and a literal CRLF and Unicode dingbat
    # (★) — to make sure escaping is end-to-end correct.
    body = "# Documented Cap\r\n\nDoes the thing.\n\n```bash\necho \"hi\"\n```\n\nSee also: ★\n"
    cap.set_documentation(body)
    assert cap.get_documentation() == body

    serialized = json.dumps(cap.to_dict())
    # The serializer must emit the documentation field.
    assert '"documentation"' in serialized, \
        f"documentation field absent in JSON output: {serialized}"

    deserialized = Cap.from_dict(json.loads(serialized))
    assert deserialized.get_documentation() == body, \
        "documentation body mutated during round-trip"

    # Identity through copy/equality
    import copy
    cloned = copy.deepcopy(deserialized)
    assert cloned == deserialized


# TEST1128: When documentation is None, the serializer must skip the field entirely.
def test_1128_cap_documentation_omitted_when_none():
    urn = CapUrn.from_string(_test_urn("undocumented"))
    cap = Cap(urn, "Undocumented Cap", ["undocumented"])
    assert cap.get_documentation() is None

    serialized = json.dumps(cap.to_dict())
    assert "documentation" not in serialized, \
        f"documentation field must be omitted when None, got: {serialized}"

    # Round-trip through deserialize: should still be None.
    deserialized = Cap.from_dict(json.loads(serialized))
    assert deserialized.get_documentation() is None


# TEST1129: A JSON document produced by capfab (the canonical source) with a `documentation` field must deserialize into a Cap with the body intact. Models the actual on-disk shape — not a synthetic round-trip — to catch a mismatch between the JSON schema and the Rust struct field naming.
def test_1129_cap_documentation_parses_from_capfab_json():
    data = {
        "urn": "cap:in=\"media:enc=utf-8\";docparse;out=\"media:enc=utf-8\"",
        "title": "Doc Parse",
        "aliases": ["docparse"],
        "cap_description": "short",
        "documentation": "## Heading\n\nbody text",
        "metadata": {},
    }
    cap = Cap.from_dict(data)
    assert cap.get_documentation() == "## Heading\n\nbody text"
    assert cap.cap_description == "short"


# TEST8102: (py-specific) CapArg.stream_urn() falls back to the declared
# slot media URN when the arg declares no Stdin source at all — a
# producer-fed arg may be delivered by its declared URN without ever
# appearing on stdin.
def test_8102_cap_arg_stream_urn_falls_back_to_media_urn_without_stdin_source():
    arg = CapArg(
        media_urn="media:enc=utf-8;system-prompt",
        required=True,
        sources=[CliFlagSource("--system-prompt")],
    )
    assert arg.stream_urn() == "media:enc=utf-8;system-prompt"


# TEST8103: (py-specific) CapArg.stream_urn() returns the Stdin source's
# URN, not the declared slot media URN, when the two differ — e.g. a
# file-path slot whose piped content is actually a pdf-stream.
def test_8103_cap_arg_stream_urn_uses_stdin_source_urn_when_present():
    arg = CapArg(
        media_urn="media:enc=utf-8;file-path",
        required=True,
        sources=[StdinSource("media:ext=pdf;pdf-stream")],
    )
    assert arg.stream_urn() == "media:ext=pdf;pdf-stream"
    assert arg.stream_urn() != arg.media_urn


# TEST8104: (py-specific) CapArg.is_main_input() is True when the arg's
# Stdin source URN is order-theoretically equivalent to the cap's in=
# spec — even when the two strings list their tags in a different order.
# Compared by tagged-URN equivalence, never as strings.
def test_8104_cap_arg_is_main_input_true_when_stdin_urn_equivalent_to_in_spec():
    in_spec = MediaUrn.from_string("media:ext=pdf;pdf-stream")
    arg = CapArg(
        media_urn="media:enc=utf-8;file-path",
        required=True,
        sources=[StdinSource("media:pdf-stream;ext=pdf")],  # same tags, different order
    )
    assert arg.is_main_input(in_spec)
    # Confirm the raw strings genuinely differ (proves the comparison is
    # order-theoretic equivalence, not a string/canonical-form comparison).
    assert arg.stream_urn() != in_spec.to_string()


# TEST8105: (py-specific) CapArg.is_main_input() is False when the arg has
# no Stdin source, and False when it has a Stdin source whose URN does not
# match in_spec.
def test_8105_cap_arg_is_main_input_false_without_matching_stdin_source():
    in_spec = MediaUrn.from_string("media:ext=pdf;pdf-stream")

    no_stdin_arg = CapArg(
        media_urn="media:max-tokens;numeric",
        required=False,
        sources=[CliFlagSource("--max-tokens")],
    )
    assert not no_stdin_arg.is_main_input(in_spec)

    mismatched_stdin_arg = CapArg(
        media_urn="media:enc=utf-8;system-prompt",
        required=False,
        sources=[StdinSource("media:enc=utf-8;system-prompt")],
    )
    assert not mismatched_stdin_arg.is_main_input(in_spec)


# TEST8106: (py-specific) A malformed Stdin source URN must not raise out
# of is_main_input — mirrors the Rust reference's `unwrap_or(false)`
# fail-soft on MediaUrn parse failure.
def test_8106_cap_arg_is_main_input_false_on_unparseable_stdin_urn():
    in_spec = MediaUrn.from_string("media:ext=pdf;pdf-stream")
    arg = CapArg(
        media_urn="media:enc=utf-8;file-path",
        required=True,
        sources=[StdinSource("not a valid tagged urn")],
    )
    assert arg.is_main_input(in_spec) is False


# TEST1130: documentation set/clear lifecycle parallels cap_description.
def test_1130_cap_documentation_set_and_clear_lifecycle():
    urn = CapUrn.from_string(_test_urn("lifecycle"))
    cap = Cap.with_description(urn, "Lifecycle", ["lifecycle"], "short")
    assert cap.cap_description == "short"
    assert cap.get_documentation() is None

    cap.set_documentation("long body")
    assert cap.get_documentation() == "long body"
    # setter must not touch cap_description
    assert cap.cap_description == "short"

    cap.clear_documentation()
    assert cap.get_documentation() is None
    # clearer must not touch cap_description
    assert cap.cap_description == "short"


# ===========================================================================
# Shared parity tests 7100-7104: CapArg.stream_urn / CapArg.is_main_input.
# Same substantive assertions in every capdag mirror (rust, go, js, objc, py).
# The py-specific 8102-8106 tests above predate these shared numbers and
# stay as-is; 7100-7104 are the cross-mirror contract.
# ===========================================================================


# TEST7100: stream_urn() returns the Stdin source's URN when it differs from
# the declared slot media_urn — the stdin URN, not the slot URN, is what the
# runtime demuxes the arg's input stream by.
def test_7100_stream_urn_returns_stdin_source_urn_when_it_differs_from_slot_urn():
    arg = CapArg(
        media_urn="media:enc=utf-8;file-path",
        required=True,
        sources=[StdinSource("media:ext=pdf;pdf-stream")],
    )
    assert arg.stream_urn() == "media:ext=pdf;pdf-stream"
    assert arg.stream_urn() != arg.media_urn


# TEST7101: stream_urn() falls back to the declared slot media_urn when the
# arg declares no Stdin source — a producer-fed arg may be delivered by its
# declared URN without ever appearing on stdin.
def test_7101_stream_urn_falls_back_to_declared_media_urn_without_stdin_source():
    arg = CapArg(
        media_urn="media:enc=utf-8;system-prompt",
        required=True,
        sources=[CliFlagSource("--system-prompt")],
    )
    assert arg.stream_urn() == "media:enc=utf-8;system-prompt"


# TEST7102: is_main_input() is True when the Stdin URN is order-theoretically
# EQUIVALENT to the cap's in= spec even when the two strings list their tags
# in a different order — the comparison is the MediaUrn equivalence
# predicate, never a string comparison.
def test_7102_is_main_input_true_on_tag_order_insensitive_equivalence_to_in_spec():
    in_spec = MediaUrn.from_string("media:ext=pdf;pdf-stream")
    arg = CapArg(
        media_urn="media:enc=utf-8;file-path",
        required=True,
        sources=[StdinSource("media:pdf-stream;ext=pdf")],  # same tags, different order
    )
    assert arg.is_main_input(in_spec)
    # The raw strings genuinely differ — proves the match is equivalence,
    # not string equality.
    assert in_spec.to_string() != "media:pdf-stream;ext=pdf"


# TEST7103: is_main_input() is False for cli_flag-only and position-only args
# (no Stdin source means never the main input, whatever the declared slot URN
# says), and False when the Stdin URN is not equivalent to in=.
def test_7103_is_main_input_false_without_equivalent_stdin_source():
    in_spec = MediaUrn.from_string("media:ext=pdf;pdf-stream")

    cli_flag_only = CapArg(
        media_urn="media:ext=pdf;pdf-stream",  # slot URN even matches in= — irrelevant
        required=True,
        sources=[CliFlagSource("--input")],
    )
    assert not cli_flag_only.is_main_input(in_spec)

    position_only = CapArg(
        media_urn="media:ext=pdf;pdf-stream",
        required=True,
        sources=[PositionSource(0)],
    )
    assert not position_only.is_main_input(in_spec)

    non_equivalent_stdin = CapArg(
        media_urn="media:enc=utf-8;system-prompt",
        required=False,
        sources=[StdinSource("media:enc=utf-8;system-prompt")],
    )
    assert not non_equivalent_stdin.is_main_input(in_spec)


# TEST7104: A realistic multi-arg cap (one stdin main input; one required,
# defaultless cli_flag arg; several defaulted cli_flag args): exactly one arg
# is the main input, and partitioning the remaining args by
# required-without-default vs has-default yields the expected sets.
def test_7104_multi_arg_cap_exactly_one_main_input_and_partition_of_rest():
    in_spec = MediaUrn.from_string("media:ext=pdf;pdf-stream")

    args = [
        CapArg(
            media_urn="media:enc=utf-8;file-path",
            required=True,
            # Main input may ALSO be delivered by cli-flag; stdin is the
            # defining route.
            sources=[StdinSource("media:pdf-stream;ext=pdf"), CliFlagSource("--input")],
        ),
        CapArg(
            media_urn="media:enc=utf-8;question",
            required=True,
            sources=[CliFlagSource("--question")],
        ),
        CapArg(
            media_urn="media:max-tokens;numeric",
            required=False,
            sources=[CliFlagSource("--max-tokens")],
            default_value=1024,
        ),
        CapArg(
            media_urn="media:numeric;temperature",
            required=False,
            sources=[CliFlagSource("--temperature")],
            default_value=0.7,
        ),
        CapArg(
            media_urn="media:enc=utf-8;system-prompt",
            required=False,
            sources=[CliFlagSource("--system-prompt")],
            default_value="You are a helpful assistant.",
        ),
    ]

    main_inputs = [a.media_urn for a in args if a.is_main_input(in_spec)]
    rest = [a for a in args if not a.is_main_input(in_spec)]
    required_without_default = [
        a.media_urn for a in rest if a.required and a.default_value is None
    ]
    with_default = [a.media_urn for a in rest if a.default_value is not None]

    assert main_inputs == ["media:enc=utf-8;file-path"], \
        "exactly one arg must be the main input"
    assert required_without_default == ["media:enc=utf-8;question"]
    assert with_default == [
        "media:max-tokens;numeric",
        "media:numeric;temperature",
        "media:enc=utf-8;system-prompt",
    ]
