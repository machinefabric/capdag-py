"""Tests for schema_validation - mirroring capdag Rust tests

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
import tempfile
from pathlib import Path
from capdag import Cap, CapArg, CapOutput, CapUrn
from capdag.cap.definition import PositionSource
from capdag.media.spec import MediaSpecDef
from capdag.cap.schema_validation import (
    SchemaValidator,
    ArgumentValidationError,
    OutputValidationError,
    SchemaCompilationError,
)
from capdag.media.registry import FabricRegistry
from capdag.urn.media_urn import MEDIA_STRING


@pytest.fixture
def registry():
    """A clean, in-memory FabricRegistry for tests to seed via ``add_spec``."""
    cache_dir = Path(tempfile.mkdtemp(prefix="capdag-fabric-"))
    return FabricRegistry.new_for_test(cache_dir)


# TEST163: Test argument schema validation succeeds with valid JSON matching schema
@pytest.mark.asyncio
async def test_163_argument_schema_validation_success(registry):
    validator = SchemaValidator()

    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer", "minimum": 0}
        },
        "required": ["name"]
    }

    # Create cap with media_specs containing the schema
    registry.add_spec(MediaSpecDef(
        urn="media:user-data",
        media_type="application/json",
        title="User Data",
        profile_uri="https://example.com/schema/user-data",
        schema=schema,
    ).to_stored())

    arg = CapArg("media:user-data", True, [PositionSource(0)])

    valid_value = {"name": "John", "age": 30}
    # Should succeed without raising
    await validator.validate_argument(arg, valid_value, registry)


# TEST164: Test argument schema validation fails with JSON missing required fields
@pytest.mark.asyncio
async def test_164_argument_schema_validation_failure(registry):
    validator = SchemaValidator()

    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"}
        },
        "required": ["name"]
    }

    # Create cap with media_specs containing the schema
    registry.add_spec(MediaSpecDef(
        urn="media:user-data",
        media_type="application/json",
        title="User Data",
        profile_uri="https://example.com/schema/user-data",
        schema=schema,
    ).to_stored())

    arg = CapArg("media:user-data", True, [PositionSource(0)])

    invalid_value = {"age": 30}  # Missing required "name"

    with pytest.raises(ArgumentValidationError) as exc_info:
        await validator.validate_argument(arg, invalid_value, registry)

    assert "name" in exc_info.value.details.lower() or "required" in exc_info.value.details.lower()


# TEST165: Test output schema validation succeeds with valid JSON matching schema
@pytest.mark.asyncio
async def test_165_output_schema_validation_success(registry):
    validator = SchemaValidator()

    schema = {
        "type": "object",
        "properties": {
            "result": {"type": "string"},
            "timestamp": {"type": "string", "format": "date-time"}
        },
        "required": ["result"]
    }

    # Create cap with media_specs containing the schema
    registry.add_spec(MediaSpecDef(
        urn="media:query-result",
        media_type="application/json",
        title="Query Result",
        profile_uri="https://example.com/schema/query-result",
        schema=schema,
    ).to_stored())

    output = CapOutput("media:query-result", "Query result")

    valid_value = {"result": "success", "timestamp": "2023-01-01T00:00:00Z"}
    # Should succeed without raising
    await validator.validate_output(output, valid_value, registry)


# TEST166: Test validation skipped when resolved media spec has no schema
@pytest.mark.asyncio
async def test_166_skip_validation_without_schema(registry):
    """A spec resolves but has no schema → validate_argument is a no-op.

    Mirrors the Rust ``test166_skip_validation_without_schema``: a media
    spec without a ``schema`` field is a successful resolution and
    yields no validation, distinct from the unresolvable case.
    """
    validator = SchemaValidator()

    # Seed a spec for MEDIA_STRING with NO schema. Resolve succeeds,
    # validate_argument has nothing to validate against, returns cleanly.
    registry.add_spec(MediaSpecDef(
        urn=MEDIA_STRING,
        media_type="text/plain",
        title="String",
        profile_uri="https://capdag.com/schema/string",
    ).to_stored())

    arg = CapArg(MEDIA_STRING, True, [PositionSource(0)])

    # Should succeed — spec has no schema, so validation is a no-op.
    await validator.validate_argument(arg, "any string value", registry)


# TEST167: Test validation fails hard when media URN cannot be resolved.
@pytest.mark.asyncio
async def test_167_unresolvable_media_urn_fails_hard(registry):
    """An unresolvable media URN is a real problem — fail hard.

    Caps' referenced media URNs land in the registry as part of the
    atomic cap fetch, so a missing spec at validation time is an
    invariant violation. Surfacing the failure is the only honest
    behaviour.
    """
    validator = SchemaValidator()

    arg = CapArg(
        "media:completely-unknown-urn-that-does-not-exist",
        True,
        [PositionSource(0)],
    )

    with pytest.raises(Exception):
        await validator.validate_argument(arg, "test", registry)


# Additional comprehensive schema validation tests


# TEST126: Schema validation with nested object schemas
@pytest.mark.asyncio
async def test_126_nested_object_schema_validation(registry):
    validator = SchemaValidator()

    schema = {
        "type": "object",
        "properties": {
            "user": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string", "format": "email"}
                },
                "required": ["name", "email"]
            },
            "timestamp": {"type": "integer"}
        },
        "required": ["user"]
    }

    registry.add_spec(MediaSpecDef(
        urn="media:user-event",
        media_type="application/json",
        title="User Event",
        schema=schema,
    ).to_stored())

    arg = CapArg("media:user-event", True, [PositionSource(0)])

    # Valid nested object
    valid_value = {
        "user": {
            "name": "Alice",
            "email": "alice@example.com"
        },
        "timestamp": 1234567890
    }
    await validator.validate_argument(arg, valid_value, registry)

    # Invalid nested object (missing email)
    invalid_value = {
        "user": {
            "name": "Alice"
        },
        "timestamp": 1234567890
    }

    with pytest.raises(ArgumentValidationError):
        await validator.validate_argument(arg, invalid_value, registry)


# TEST127: Schema validation with array schemas including minItems and item constraints
@pytest.mark.asyncio
async def test_127_array_schema_validation(registry):
    validator = SchemaValidator()

    schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {
                "id": {"type": "integer"},
                "name": {"type": "string"}
            },
            "required": ["id"]
        },
        "minItems": 1
    }

    registry.add_spec(MediaSpecDef(
        urn="media:item-list",
        media_type="application/json",
        title="Item List",
        schema=schema,
    ).to_stored())

    arg = CapArg("media:item-list", True, [PositionSource(0)])

    # Valid array
    valid_value = [
        {"id": 1, "name": "Item 1"},
        {"id": 2, "name": "Item 2"}
    ]
    await validator.validate_argument(arg, valid_value, registry)

    # Invalid array (empty - violates minItems)
    with pytest.raises(ArgumentValidationError):
        await validator.validate_argument(arg, [], registry)

    # Invalid array (item missing required id)
    with pytest.raises(ArgumentValidationError):
        await validator.validate_argument(arg, [{"name": "Item 1"}], registry)


# TEST128: Schema validation with type constraints (integer, number, boolean)
@pytest.mark.asyncio
async def test_128_type_constraint_validation(registry):
    validator = SchemaValidator()

    schema = {
        "type": "object",
        "properties": {
            "count": {"type": "integer"},
            "price": {"type": "number"},
            "active": {"type": "boolean"}
        },
        "required": ["count"]
    }

    registry.add_spec(MediaSpecDef(
        urn="media:product",
        media_type="application/json",
        title="Product",
        schema=schema,
    ).to_stored())

    arg = CapArg("media:product", True, [PositionSource(0)])

    # Valid types
    valid_value = {"count": 5, "price": 9.99, "active": True}
    await validator.validate_argument(arg, valid_value, registry)

    # Invalid type (count is string instead of integer)
    invalid_value = {"count": "five"}
    with pytest.raises(ArgumentValidationError):
        await validator.validate_argument(arg, invalid_value, registry)


# TEST129: Schema validation with multiple arguments validates each independently
@pytest.mark.asyncio
async def test_129_validate_multiple_arguments(registry):
    validator = SchemaValidator()

    schema1 = {
        "type": "string",
        "minLength": 1
    }

    schema2 = {
        "type": "integer",
        "minimum": 0,
        "maximum": 100
    }

    registry.add_spec(MediaSpecDef(
        urn="media:name",
        media_type="text/plain",
        title="Name",
        schema=schema1,
    ).to_stored())
    registry.add_spec(MediaSpecDef(
        urn="media:score",
        media_type="application/json",
        title="Score",
        schema=schema2,
    ).to_stored())

    # Build a cap carrying the two positional arguments. The
    # validator drives off cap.get_args() and the registry — there
    # is no separate "arg list" parameter to validate against.
    arg1 = CapArg("media:name", True, [PositionSource(0)])
    arg2 = CapArg("media:score", True, [PositionSource(1)])
    cap = Cap.with_args(
        CapUrn.from_string('cap:in="media:void";multi-arg-test;out="media:void"'),
        "Multi-arg test",
        "test",
        [arg1, arg2],
    )

    # Valid arguments
    await validator.validate_arguments(cap, ["John", 85], registry)

    # Invalid first argument (empty string fails minLength=1).
    with pytest.raises(ArgumentValidationError):
        await validator.validate_arguments(cap, ["", 85], registry)

    # Invalid second argument (150 exceeds maximum=100).
    with pytest.raises(ArgumentValidationError):
        await validator.validate_arguments(cap, ["John", 150], registry)


# TEST130: Output validation surfaces schema violation details
@pytest.mark.asyncio
async def test_130_output_validation_with_details(registry):
    validator = SchemaValidator()

    schema = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["success", "failure"]},
            "data": {"type": "object"}
        },
        "required": ["status"]
    }

    registry.add_spec(MediaSpecDef(
        urn="media:response",
        media_type="application/json",
        title="Response",
        schema=schema,
    ).to_stored())

    output = CapOutput("media:response", "Response")

    # Invalid output (wrong enum value)
    invalid_value = {"status": "pending"}

    with pytest.raises(OutputValidationError) as exc_info:
        await validator.validate_output(output, invalid_value, registry)

    # Error should contain validation details
    assert exc_info.value.details
