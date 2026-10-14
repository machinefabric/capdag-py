"""Tests for plan builder argument requirement models."""

import json

import pytest

from capdag.cap.definition import Cap, CapArg, CapOutput, StdinSource
from capdag.fabric.registry import FabricRegistry
from capdag.media.spec import MediaValidation
from capdag.planner.live_cap_fab import (
    StepToken,
    StepTokenError,
    StrandStep,
    StrandStepType,
)
from capdag.planner.plan_builder import (
    ArgumentInfo,
    ArgumentResolution,
    MachinePlanBuilder,
)
from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn


def _make_test_cap(op: str, in_spec: str, out_spec: str, title: str) -> Cap:
    urn = CapUrn.from_string(f'cap:{op};in="{in_spec}";out="{out_spec}"')
    cap = Cap.with_description(urn, title, ["test-command"], f"{title} cap")
    cap.add_arg(
        CapArg(
            media_urn=str(urn.in_spec()), name="input",
            required=True,
            sources=[StdinSource(str(urn.in_spec()))],
        )
    )
    cap.add_output(CapOutput(str(urn.out_spec()), "output", f"{title} output"))
    return cap


# TEST765: Tests validation_to_json() returns None for empty validation constraints Verifies that default MediaValidation with no constraints produces JSON None
def test_765_validation_to_json_empty():
    validation = MediaValidation()
    payload = MachinePlanBuilder.validation_to_json(validation)
    assert payload is None


# TEST766: Tests validation_to_json() converts MediaValidation with constraints to JSON Verifies that min/max validation rules are correctly serialized as JSON fields
def test_766_validation_to_json_with_constraints():
    validation = MediaValidation(min=50.0, max=2000.0)
    payload = MachinePlanBuilder.validation_to_json(validation)
    assert payload is not None
    assert payload["min"] == 50.0
    assert payload["max"] == 2000.0


# TEST767: Tests ArgumentInfo struct serialization to JSON Verifies that argument metadata including resolution status and validation is correctly serialized
def test_767_argument_info_serialization():
    arg_info = ArgumentInfo(
        name="width",
        media_urn="media:integer",
        description="Width in pixels",
        resolution=ArgumentResolution.HAS_DEFAULT,
        default_value=200,
        is_required=False,
        is_sequence=False,
        validation={"min": 50, "max": 2000},
    )
    payload = json.dumps(arg_info.to_dict())
    assert '"name": "width"' in payload or '"name":"width"' in payload
    assert '"resolution": "has_default"' in payload or '"resolution":"has_default"' in payload
    assert '"default_value": 200' in payload or '"default_value":200' in payload


# TEST991: Tests duplicate detection identifies caps with identical URNs Verifies that check_for_duplicate_caps() returns an error when multiple caps share the same cap_urn
def test_991_detects_duplicate_cap_urns():
    caps = [
        _make_test_cap("disbind", "media:document;ext=pdf", "media:disbound-pages;enc=utf-8;list", "Disbind PDF"),
        _make_test_cap("disbind", "media:document;ext=pdf", "media:disbound-pages;enc=utf-8;list", "Disbind PDF Again"),
    ]

    try:
        MachinePlanBuilder.check_for_duplicate_caps(caps)
        assert False, "Expected duplicate cap URN detection"
    except ValueError as exc:
        message = str(exc)
        assert "Duplicate cap_urn detected" in message
        assert "disbind" in message
        assert "media:document;ext=pdf" in message


# TEST880: Tests duplicate detection passes for caps with unique URN combinations Verifies that check_for_duplicate_caps() correctly accepts caps with different op/in/out combinations
def test_880_no_duplicates_with_unique_caps():
    caps = [
        _make_test_cap("extract_metadata", "media:document;ext=pdf", "media:enc=utf-8;file-metadata;record", "Extract Metadata"),
        _make_test_cap("extract_outline", "media:document;ext=pdf", "media:document-outline;enc=utf-8;record", "Extract Outline"),
        _make_test_cap("disbind", "media:document;ext=pdf", "media:disbound-pages;enc=utf-8;list", "Disbind PDF"),
    ]

    assert MachinePlanBuilder.check_for_duplicate_caps(caps) == 3


# TEST992: Tests caps with different operations but same input/output types are not duplicates Verifies that only the complete URN (including op) is used for duplicate detection
def test_992_different_ops_same_types_not_duplicates():
    caps = [
        _make_test_cap("disbind", "media:document;ext=pdf", "media:disbound-pages;enc=utf-8;list", "Disbind"),
        _make_test_cap("grind", "media:document;ext=pdf", "media:disbound-pages;enc=utf-8;list", "Grind"),
    ]

    assert MachinePlanBuilder.check_for_duplicate_caps(caps) == 2


# TEST993: Tests caps with same operation but different input types are not duplicates Verifies that input type differences distinguish caps with the same operation name
def test_993_same_op_different_input_types_not_duplicates():
    caps = [
        _make_test_cap("extract_metadata", "media:document;ext=pdf", "media:enc=utf-8;file-metadata;record", "Extract PDF Metadata"),
        _make_test_cap("extract_metadata", "media:enc=utf-8;ext=txt", "media:enc=utf-8;file-metadata;record", "Extract TXT Metadata"),
    ]

    assert MachinePlanBuilder.check_for_duplicate_caps(caps) == 2


# TEST1019: Tests validation_to_json() returns None for None input Verifies that missing validation metadata is converted to JSON None
def test_1019_validation_to_json_none():
    assert MachinePlanBuilder.validation_to_json(None) is None


# TEST1462: An unidentified step is not a state the program can hold. StepToken is the type that makes it so - minting is the only way to create one and parse, the sole path back from text, refuses an empty id
def test_1462_a_step_token_cannot_be_empty():
    with pytest.raises(StepTokenError):
        StepToken.parse("")

    # Decoding is the one boundary where a strand arrives as data rather than
    # being constructed, so it is the one place the illegal state could enter.
    with pytest.raises(StepTokenError):
        StrandStep(
            step_type=StrandStepType.FOR_EACH,
            from_spec=MediaUrn.from_string("media:ext=txt;text"),
            to_spec=MediaUrn.from_string("media:ext=txt;text"),
            token_id="",
        )

    # A minted token survives the round trip through its text unchanged.
    minted = StepToken.mint()
    assert StepToken.parse(str(minted)) == minted
