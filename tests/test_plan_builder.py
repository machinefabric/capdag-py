"""Tests for plan builder argument requirement models."""

import json

from capdag.media.spec import MediaValidation
from capdag.planner.plan_builder import (
    ArgumentInfo,
    ArgumentResolution,
    MachinePlanBuilder,
    PathArgumentRequirements,
    StepArgumentRequirements,
)


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
        source_spec="media:pdf",
        target_spec="media:png",
        steps=[
            StepArgumentRequirements(
                cap_urn="cap:op=generate_thumbnail;in=pdf;out=png",
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
        source_spec="media:text",
        target_spec="media:translated",
        steps=[
            StepArgumentRequirements(
                cap_urn="cap:op=translate;in=text;out=translated",
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
