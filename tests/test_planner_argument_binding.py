"""Tests for planner argument binding — mirroring capdag Rust tests.

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import json

import pytest

from capdag.planner.argument_binding import (
    ArgumentBinding,
    ArgumentBindings,
    ArgumentResolutionContext,
    ArgumentSource,
    CapInputFile,
    SourceEntityType,
    StrandInput,
    resolve_binding,
)
from capdag.planner.error import InternalError


def _empty_context(**overrides):
    """Build a minimal ArgumentResolutionContext with no files."""
    defaults = dict(
        input_files=[],
        current_file_index=0,
        previous_outputs={},
        plan_metadata=None,
        cap_settings=None,
        slot_values=None,
    )
    defaults.update(overrides)
    return ArgumentResolutionContext(**defaults)

# TEST668: resolve_slot_with_populated_byte_slot_values
def test_668_resolve_slot_with_populated_byte_slot_values():
    slot_values = {
        "step_0:media:width;textable;numeric": b"800",
    }
    ctx = _empty_context(slot_values=slot_values)
    binding = ArgumentBinding.slot("media:width;textable;numeric")
    result = resolve_binding(
        binding, ctx,
        'cap:in="media:pdf";resize;out="media:pdf"',
        "step_0",
        None, True,
    )
    assert result is not None
    assert result.value == b"800"
    assert result.source == ArgumentSource.SLOT

# TEST669: resolve_slot_falls_back_to_default
def test_669_resolve_slot_falls_back_to_default():
    ctx = _empty_context()
    binding = ArgumentBinding.slot("media:quality;textable;numeric")
    result = resolve_binding(binding, ctx, "cap:compress", "step_0", 85, False)
    assert result is not None
    assert result.value == json.dumps(85, separators=(",", ":")).encode("utf-8")
    assert result.source == ArgumentSource.CAP_DEFAULT

# TEST670: resolve_required_slot_no_value_returns_err
def test_670_resolve_required_slot_no_value_returns_err():
    ctx = _empty_context()
    binding = ArgumentBinding.slot("media:question;textable")
    with pytest.raises(InternalError) as exc_info:
        resolve_binding(binding, ctx, "cap:generate", "step_0", None, True)
    assert "media:question;textable" in str(exc_info.value)

# TEST671: resolve_optional_slot_no_value_returns_none
def test_671_resolve_optional_slot_no_value_returns_none():
    ctx = _empty_context()
    binding = ArgumentBinding.slot("media:suffix;textable")
    result = resolve_binding(binding, ctx, "cap:rename", "step_0", None, False)
    assert result is None


# ---------------------------------------------------------------------------
# New step-index keying tests (test1105–test1109)
# ---------------------------------------------------------------------------

# TEST1105: Two steps with the same cap_urn get distinct slot values via different node_ids. This is the core disambiguation scenario that step-index keying was designed to solve.
# This is the core disambiguation scenario that step-index keying was designed to solve.
def test_1105_two_steps_same_cap_urn_different_slot_values():
    cap_urn = 'cap:in="media:pdf";make-decision;out="media:bool;textable"'
    slot_name = "media:question;textable;list"
    slot_values = {
        f"step_0:{slot_name}": b"Is this a contract?",
        f"step_2:{slot_name}": b"Is this confidential?",
    }
    ctx = _empty_context(slot_values=slot_values)
    binding = ArgumentBinding.slot(slot_name)

    # step_0 resolves to "Is this a contract?"
    r0 = resolve_binding(binding, ctx, cap_urn, "step_0", None, True)
    assert r0 is not None
    assert r0.value == b"Is this a contract?"
    assert r0.source == ArgumentSource.SLOT

    # step_2 resolves to "Is this confidential?"
    r2 = resolve_binding(binding, ctx, cap_urn, "step_2", None, True)
    assert r2 is not None
    assert r2.value == b"Is this confidential?"
    assert r2.source == ArgumentSource.SLOT

    # Confirm they differ
    assert r0.value != r2.value


# TEST1106: Slot resolution falls through to cap_settings when no slot_value exists. cap_settings are keyed by cap_urn (shared across steps), so both steps get the same value.
# cap_settings are keyed by cap_urn (shared across steps), so both steps get the same value.
def test_1106_slot_falls_through_to_cap_settings_shared():
    cap_urn = 'cap:in="media:pdf";make-decision;out="media:bool;textable"'
    slot_name = "media:language;textable"
    cap_settings = {
        cap_urn: {slot_name: "en"},
    }
    ctx = _empty_context(cap_settings=cap_settings)
    binding = ArgumentBinding.slot(slot_name)

    # Both steps fall through to cap_settings — same value
    r0 = resolve_binding(binding, ctx, cap_urn, "step_0", None, False)
    r1 = resolve_binding(binding, ctx, cap_urn, "step_1", None, False)
    assert r0 is not None and r1 is not None
    assert r0.value == b"en"
    assert r1.value == b"en"
    assert r0.source == ArgumentSource.CAP_SETTING
    assert r1.source == ArgumentSource.CAP_SETTING


# TEST1107: step_0 has a slot_value override, step_1 falls through to cap_settings. Proves per-step override works while shared settings remain as fallback.
# Proves per-step override works while shared settings remain as fallback.
def test_1107_slot_value_overrides_cap_settings_per_step():
    cap_urn = 'cap:in="media:pdf";make-decision;out="media:bool;textable"'
    slot_name = "media:language;textable"
    slot_values = {
        f"step_0:{slot_name}": b"fr",
        # step_1 has no slot_value entry
    }
    cap_settings = {
        cap_urn: {slot_name: "en"},
    }
    ctx = _empty_context(slot_values=slot_values, cap_settings=cap_settings)
    binding = ArgumentBinding.slot(slot_name)

    # step_0: slot_value "fr" (priority 1)
    r0 = resolve_binding(binding, ctx, cap_urn, "step_0", None, False)
    assert r0 is not None
    assert r0.value == b"fr"
    assert r0.source == ArgumentSource.SLOT

    # step_1: no slot_value → falls to cap_settings "en" (priority 2)
    r1 = resolve_binding(binding, ctx, cap_urn, "step_1", None, False)
    assert r1 is not None
    assert r1.value == b"en"
    assert r1.source == ArgumentSource.CAP_SETTING


# TEST1108: ResolveAll with node_id threads correctly through to each binding.
def test_1108_resolve_all_passes_node_id():
    slot_values = {
        "step_3:media:width;textable;numeric": b"1024",
        "step_3:media:quality;textable;numeric": b"95",
    }
    ctx = _empty_context(slot_values=slot_values)

    bindings = ArgumentBindings()
    bindings.add("media:width;textable;numeric",
                 ArgumentBinding.slot("media:width;textable;numeric"))
    bindings.add("media:quality;textable;numeric",
                 ArgumentBinding.slot("media:quality;textable;numeric"))

    results = bindings.resolve_all(ctx, "cap:resize", "step_3")
    assert len(results) == 2

    by_name = {r.name: r for r in results}
    width = by_name["media:width;textable;numeric"]
    assert width.value == b"1024"
    assert width.source == ArgumentSource.SLOT

    quality = by_name["media:quality;textable;numeric"]
    assert quality.value == b"95"
    assert quality.source == ArgumentSource.SLOT


# TEST1109: Slot key uses node_id, NOT cap_urn — a slot_value keyed by cap_urn must not match.
def test_1109_slot_key_uses_node_id_not_cap_urn():
    cap_urn = 'cap:in="media:pdf";resize;out="media:pdf"'
    slot_name = "media:width;textable;numeric"
    # Deliberately key by cap_urn (the OLD format) — should NOT match
    slot_values = {
        f"{cap_urn}:{slot_name}": b"800",
    }
    ctx = _empty_context(slot_values=slot_values)
    binding = ArgumentBinding.slot(slot_name)

    # Should NOT find the value because the key format is wrong (cap_urn instead of node_id)
    result = resolve_binding(binding, ctx, cap_urn, "step_0", None, False)
    assert result is None, "Old cap_urn-based key must not match node_id-based lookup"


# TEST792: Tests ArgumentBinding requires_input distinguishes Slots from Literals Verifies Slot returns true (needs user input) while Literal returns false
def test_792_argument_binding_requires_input():
    assert ArgumentBinding.slot("width").requires_input()
    assert not ArgumentBinding.literal(100).requires_input()


# TEST793: Tests ArgumentBinding PreviousOutput serializes/deserializes correctly Verifies JSON round-trip preserves node_id and output_field values
def test_793_argument_binding_serialization():
    binding = ArgumentBinding.previous_output("node_0", "result_path")
    payload = binding.to_dict()
    assert payload["type"] == "previous_output"
    assert payload["node_id"] == "node_0"
    round_trip = ArgumentBinding.from_dict(payload)
    assert round_trip.kind == ArgumentBinding.PREVIOUS_OUTPUT
    assert round_trip.node_id == "node_0"
    assert round_trip.output_field == "result_path"


# TEST794: Tests ArgumentBindings add_file_path adds InputFilePath binding Verifies add_file_path() creates binding map entry with InputFilePath variant
def test_794_argument_bindings_add_file_path():
    bindings = ArgumentBindings()
    bindings.add_file_path("input")
    assert "input" in bindings.bindings
    assert bindings.bindings["input"].kind == ArgumentBinding.INPUT_FILE_PATH


# TEST795: Tests ArgumentBindings identifies unresolved Slot bindings Verifies has_unresolved_slots() and get_unresolved_slots() detect Slots needing values
def test_795_argument_bindings_unresolved_slots():
    bindings = ArgumentBindings()
    bindings.add("width", ArgumentBinding.slot("width"))
    bindings.add("height", ArgumentBinding.literal(100))
    assert bindings.has_unresolved_slots()
    assert bindings.get_unresolved_slots() == ["width"]


# TEST796: Tests resolve_binding resolves InputFilePath to current file path Verifies InputFilePath binding resolves to file path bytes with InputFile source
def test_796_resolve_input_file_path():
    files = [CapInputFile("/path/to/file.pdf", "media:pdf")]
    ctx = _empty_context(input_files=files)
    result = resolve_binding(
        ArgumentBinding.input_file_path(),
        ctx,
        "cap:test",
        "step_0",
        None,
        True,
    )
    assert result is not None
    assert result.value == b"/path/to/file.pdf"
    assert result.source == ArgumentSource.INPUT_FILE


# TEST797: Tests resolve_binding resolves Literal to JSON-encoded bytes Verifies Literal binding serializes value to bytes with Literal source
def test_797_resolve_literal():
    result = resolve_binding(
        ArgumentBinding.literal(42),
        _empty_context(),
        "cap:test",
        "step_0",
        None,
        True,
    )
    assert result is not None
    assert result.value == json.dumps(42, separators=(",", ":")).encode("utf-8")
    assert result.source == ArgumentSource.LITERAL


# TEST798: Tests resolve_binding extracts value from previous node output Verifies PreviousOutput binding fetches field from earlier execution results
def test_798_resolve_previous_output():
    ctx = _empty_context(previous_outputs={"node_0": {"result_path": "/output/result.png"}})
    result = resolve_binding(
        ArgumentBinding.previous_output("node_0", "result_path"),
        ctx,
        "cap:test",
        "step_0",
        None,
        True,
    )
    assert result is not None
    assert result.value == b"/output/result.png"
    assert result.source == ArgumentSource.PREVIOUS_OUTPUT


# TEST799: Tests StrandInput single constructor creates valid Single cardinality input Verifies single() wraps one file with Single cardinality and validates correctly
def test_799_machine_input_single():
    input_file = CapInputFile("/path/to/file.pdf", "media:pdf")
    strand_input = StrandInput.single(input_file)
    assert len(strand_input.files) == 1
    assert strand_input.cardinality.value == "single"
    assert strand_input.is_valid()


# TEST800: Tests StrandInput sequence constructor creates valid Sequence cardinality input Verifies sequence() wraps multiple files with Sequence cardinality
def test_800_machine_input_vector():
    files = [
        CapInputFile("/path/1.pdf", "media:pdf"),
        CapInputFile("/path/2.pdf", "media:pdf"),
    ]
    strand_input = StrandInput.sequence(files, "media:pdf")
    assert len(strand_input.files) == 2
    assert strand_input.cardinality.value == "sequence"
    assert strand_input.is_valid()


# TEST801: Tests CapInputFile deserializes from JSON with source metadata fields Verifies JSON with source_id and source_type deserializes to CapInputFile correctly
def test_801_cap_input_file_deserialization_from_dry_context():
    payload = [
        {
            "file_path": "/Users/bahram/ws/prj/machinefabric/pdfcartridge/test_files/aws_in_action.pdf",
            "media_urn": "media:pdf",
            "source_id": "1b964d3b-f409-4f51-8684-884348ec2501",
            "source_type": "listing",
        }
    ]
    files = [CapInputFile.from_dict(item) for item in payload]
    assert len(files) == 1
    assert files[0].source_type == SourceEntityType.LISTING


# TEST802: Tests CapInputFile deserializes from compact JSON via serde_json::Value Verifies deserialization through Value intermediate works correctly
def test_802_cap_input_file_deserialization_via_value():
    payload = json.loads(
        '[{"file_path":"/path/to/file.pdf","media_urn":"media:pdf","source_id":"abc123","source_type":"listing"}]'
    )
    files = [CapInputFile.from_dict(item) for item in payload]
    assert len(files) == 1
    assert files[0].source_id == "abc123"


# TEST803: Tests StrandInput validation detects mismatched Single cardinality with multiple files Verifies is_valid() returns false when Single cardinality has more than one file
def test_803_machine_input_invalid_single():
    strand_input = StrandInput(
        files=[
            CapInputFile("/path/1.pdf", "media:pdf"),
            CapInputFile("/path/2.pdf", "media:pdf"),
        ],
        expected_media_urn="media:pdf",
        cardinality=StrandInput.single(CapInputFile("/tmp/x.pdf", "media:pdf")).cardinality,
    )
    assert not strand_input.is_valid()


# TEST957: Tests CapInputFile constructor creates file with correct path and media URN Verifies new() initializes file_path, media_urn and leaves metadata/source_id as None
def test_957_cap_input_file_new():
    file = CapInputFile("/path/to/file.pdf", "media:pdf")
    assert file.file_path == "/path/to/file.pdf"
    assert file.media_urn == "media:pdf"
    assert file.metadata is None
    assert file.source_id is None


# TEST958: Tests CapInputFile from_listing sets source metadata correctly Verifies from_listing() populates source_id and source_type as Listing
def test_958_cap_input_file_from_listing():
    file = CapInputFile.from_listing("listing-123", "/path/to/file.pdf", "media:pdf")
    assert file.source_id == "listing-123"
    assert file.source_type == SourceEntityType.LISTING


# TEST959: Tests CapInputFile extracts filename from full path correctly Verifies filename() returns just the basename without directory path
def test_959_cap_input_file_filename():
    file = CapInputFile("/path/to/document.pdf", "media:pdf")
    assert file.filename() == "document.pdf"


# TEST960: Tests ArgumentBinding literal_string creates Literal variant with string value Verifies literal_string() wraps string in JSON Value::String
def test_960_argument_binding_literal_string():
    binding = ArgumentBinding.literal_string("test")
    assert binding.kind == ArgumentBinding.LITERAL
    assert binding.value == "test"
