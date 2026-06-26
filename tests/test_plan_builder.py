"""Tests for plan builder argument requirement models."""

import json

from capdag import MEDIA_FILE_PATH
from capdag.cap.definition import Cap, CapArg, CapOutput, StdinSource
from capdag.fabric.registry import FabricRegistry
from capdag.media.spec import MediaValidation
from capdag.planner.plan_builder import (
    ArgumentInfo,
    ArgumentResolution,
    MachinePlanBuilder,
    PathArgumentRequirements,
    StepArgumentRequirements,
)
from capdag.urn.cap_urn import CapUrn


def _make_test_cap(op: str, in_spec: str, out_spec: str, title: str) -> Cap:
    urn = CapUrn.from_string(f'cap:{op};in="{in_spec}";out="{out_spec}"')
    cap = Cap.with_description(urn, title, "test-command", f"{title} cap")
    cap.add_arg(
        CapArg(
            media_urn=str(urn.in_spec()),
            required=True,
            sources=[StdinSource(str(urn.in_spec()))],
        )
    )
    cap.set_output(CapOutput(str(urn.out_spec()), f"{title} output"))
    return cap


def _test_builder() -> MachinePlanBuilder:
    return MachinePlanBuilder.new_for_test(FabricRegistry.new_for_test())


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


# TEST768: Tests PathArgumentRequirements structure for single-step execution paths Verifies that argument requirements are correctly organized by step with resolution information
def test_768_path_argument_requirements_structure():
    requirements = PathArgumentRequirements(
        source_media_urn="media:ext=pdf",
        target_media_urn="media:ext=png;image",
        steps=[
            StepArgumentRequirements(
                cap_urn="cap:generate-thumbnail;in=pdf;out=png",
                step_index=0,
                title="Generate Thumbnail",
                arguments=[
                    ArgumentInfo(
                        name="file_path",
                        media_urn="media:string",
                        description="Path to file",
                        resolution=ArgumentResolution.FROM_INPUT_FILE,
                        default_value=None,
                        is_required=True,
                        is_sequence=False,
                        validation=None,
                    )
                ],
                slots=[],
            )
        ],
        can_execute_without_input=True,
    )

    assert requirements.can_execute_without_input
    assert len(requirements.steps) == 1
    assert len(requirements.steps[0].slots) == 0
    assert requirements.steps[0].arguments[0].resolution == ArgumentResolution.FROM_INPUT_FILE


# TEST769: Tests PathArgumentRequirements tracking of required user-input slots Verifies that arguments requiring user input are collected in slots and can_execute_without_input is false
def test_769_path_with_required_slot():
    slot_arg = ArgumentInfo(
        name="target_language",
        media_urn="media:string",
        description="Target language code",
        resolution=ArgumentResolution.REQUIRES_USER_INPUT,
        default_value=None,
        is_required=True,
        is_sequence=False,
        validation=None,
    )
    requirements = PathArgumentRequirements(
        source_media_urn="media:text",
        target_media_urn="media:translated",
        steps=[
            StepArgumentRequirements(
                cap_urn="cap:translate;in=text;out=translated",
                step_index=0,
                title="Translate",
                arguments=[
                    ArgumentInfo(
                        name="file_path",
                        media_urn="media:string",
                        description="Path to file",
                        resolution=ArgumentResolution.FROM_INPUT_FILE,
                        default_value=None,
                        is_required=True,
                        is_sequence=False,
                        validation=None,
                    ),
                    slot_arg,
                ],
                slots=[slot_arg],
            )
        ],
        can_execute_without_input=False,
    )

    assert not requirements.can_execute_without_input
    assert len(requirements.steps[0].slots) == 1
    assert requirements.steps[0].slots[0].name == "target_language"


# TEST991: Tests duplicate detection identifies caps with identical URNs Verifies that check_for_duplicate_caps() returns an error when multiple caps share the same cap_urn
def test_991_detects_duplicate_cap_urns():
    caps = [
        _make_test_cap("disbind", "media:ext=pdf", "media:disbound-pages;enc=utf-8;list", "Disbind PDF"),
        _make_test_cap("disbind", "media:ext=pdf", "media:disbound-pages;enc=utf-8;list", "Disbind PDF Again"),
    ]

    try:
        MachinePlanBuilder.check_for_duplicate_caps(caps)
        assert False, "Expected duplicate cap URN detection"
    except ValueError as exc:
        message = str(exc)
        assert "Duplicate cap_urn detected" in message
        assert "disbind" in message
        assert "media:ext=pdf" in message


# TEST880: Tests duplicate detection passes for caps with unique URN combinations Verifies that check_for_duplicate_caps() correctly accepts caps with different op/in/out combinations
def test_880_no_duplicates_with_unique_caps():
    caps = [
        _make_test_cap("extract_metadata", "media:ext=pdf", "media:enc=utf-8;file-metadata;record", "Extract Metadata"),
        _make_test_cap("extract_outline", "media:ext=pdf", "media:document-outline;enc=utf-8;record", "Extract Outline"),
        _make_test_cap("disbind", "media:ext=pdf", "media:disbound-pages;enc=utf-8;list", "Disbind PDF"),
    ]

    assert MachinePlanBuilder.check_for_duplicate_caps(caps) == 3


# TEST992: Tests caps with different operations but same input/output types are not duplicates Verifies that only the complete URN (including op) is used for duplicate detection
def test_992_different_ops_same_types_not_duplicates():
    caps = [
        _make_test_cap("disbind", "media:ext=pdf", "media:disbound-pages;enc=utf-8;list", "Disbind"),
        _make_test_cap("grind", "media:ext=pdf", "media:disbound-pages;enc=utf-8;list", "Grind"),
    ]

    assert MachinePlanBuilder.check_for_duplicate_caps(caps) == 2


# TEST993: Tests caps with same operation but different input types are not duplicates Verifies that input type differences distinguish caps with the same operation name
def test_993_same_op_different_input_types_not_duplicates():
    caps = [
        _make_test_cap("extract_metadata", "media:ext=pdf", "media:enc=utf-8;file-metadata;record", "Extract PDF Metadata"),
        _make_test_cap("extract_metadata", "media:enc=utf-8;ext=txt", "media:enc=utf-8;file-metadata;record", "Extract TXT Metadata"),
    ]

    assert MachinePlanBuilder.check_for_duplicate_caps(caps) == 2


# TEST994: Tests first cap's input argument is automatically resolved from input file Verifies that determine_resolution_with_io_check() returns FromInputFile for the first cap in a chain
def test_994_input_arg_first_cap_auto_resolved_from_input():
    builder = _test_builder()
    resolution = builder.determine_resolution_with_io_check(
        "media:ext=pdf",
        "media:ext=pdf",
        "media:ext=png;image",
        0,
        True,
        None,
    )
    assert resolution == ArgumentResolution.FROM_INPUT_FILE


# TEST995: Tests subsequent caps' input arguments are automatically resolved from previous output Verifies that determine_resolution_with_io_check() returns FromPreviousOutput for caps after the first
def test_995_input_arg_subsequent_cap_auto_resolved_from_previous():
    builder = _test_builder()
    resolution = builder.determine_resolution_with_io_check(
        "media:ext=pdf",
        "media:ext=pdf",
        "media:ext=png;image",
        1,
        True,
        None,
    )
    assert resolution == ArgumentResolution.FROM_PREVIOUS_OUTPUT

    resolution = builder.determine_resolution_with_io_check(
        "media:ext=pdf",
        "media:ext=pdf",
        "media:ext=png;image",
        2,
        True,
        None,
    )
    assert resolution == ArgumentResolution.FROM_PREVIOUS_OUTPUT


# TEST996: Tests output arguments are automatically resolved from previous cap's output Verifies that arguments matching the output spec are always resolved as FromPreviousOutput
def test_996_output_arg_auto_resolved():
    builder = _test_builder()
    resolution = builder.determine_resolution_with_io_check(
        "media:ext=png;image",
        "media:ext=pdf",
        "media:ext=png;image",
        0,
        True,
        None,
    )
    assert resolution == ArgumentResolution.FROM_PREVIOUS_OUTPUT


# TEST997: Tests MEDIA_FILE_PATH argument type resolves to input file for first cap Verifies that generic file-path arguments are bound to input file in the first cap
def test_997_file_path_type_fallback_first_cap():
    builder = _test_builder()
    resolution = builder.determine_resolution_with_io_check(
        MEDIA_FILE_PATH,
        "media:ext=pdf",
        "media:ext=png;image",
        0,
        True,
        None,
    )
    assert resolution == ArgumentResolution.FROM_INPUT_FILE


# TEST998: Tests MEDIA_FILE_PATH argument type resolves to previous output for subsequent caps Verifies that generic file-path arguments are bound to previous cap's output after the first cap
def test_998_file_path_type_fallback_subsequent_cap():
    builder = _test_builder()
    resolution = builder.determine_resolution_with_io_check(
        MEDIA_FILE_PATH,
        "media:ext=pdf",
        "media:ext=png;image",
        1,
        True,
        None,
    )
    assert resolution == ArgumentResolution.FROM_PREVIOUS_OUTPUT




# TEST1009: Tests required non-IO arguments with default values are marked as HasDefault Verifies that arguments like integers with defaults don't require user input
def test_1009_non_io_arg_with_default_has_default():
    builder = _test_builder()
    resolution = builder.determine_resolution_with_io_check(
        "media:integer",
        "media:ext=pdf",
        "media:ext=png;image",
        0,
        True,
        200,
    )
    assert resolution == ArgumentResolution.HAS_DEFAULT


# TEST886: Tests optional non-IO arguments with default values are marked as HasDefault Verifies that optional arguments with defaults behave the same as required ones with defaults
def test_886_optional_non_io_arg_with_default_has_default():
    builder = _test_builder()
    resolution = builder.determine_resolution_with_io_check(
        "media:integer",
        "media:ext=pdf",
        "media:ext=png;image",
        0,
        False,
        300,
    )
    assert resolution == ArgumentResolution.HAS_DEFAULT


# TEST1012: Tests required non-IO arguments without defaults require user input Verifies that arguments like strings without defaults are marked as RequiresUserInput
def test_1012_non_io_arg_without_default_requires_user_input():
    builder = _test_builder()
    resolution = builder.determine_resolution_with_io_check(
        "media:string",
        "media:ext=pdf",
        "media:ext=png;image",
        0,
        True,
        None,
    )
    assert resolution == ArgumentResolution.REQUIRES_USER_INPUT


# TEST1015: Tests optional non-IO arguments without defaults still require user input Verifies that optional arguments without defaults must be explicitly provided or skipped
def test_1015_optional_non_io_arg_without_default_requires_user_input():
    builder = _test_builder()
    resolution = builder.determine_resolution_with_io_check(
        "media:boolean",
        "media:ext=pdf",
        "media:ext=png;image",
        0,
        False,
        None,
    )
    assert resolution == ArgumentResolution.REQUIRES_USER_INPUT


# TEST1019: Tests validation_to_json() returns None for None input Verifies that missing validation metadata is converted to JSON None
def test_1019_validation_to_json_none():
    assert MachinePlanBuilder.validation_to_json(None) is None
