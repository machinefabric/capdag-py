"""JSON Schema validation for capability arguments and outputs

Provides validation of JSON data against JSON Schema Draft-07.
Schemas are embedded in cap definitions or resolved from registry.
"""

import json
from typing import Dict, Any, Optional
try:
    import jsonschema
    from jsonschema import Draft7Validator, ValidationError as JsonSchemaValidationError
    JSONSCHEMA_AVAILABLE = True
except ImportError:
    JSONSCHEMA_AVAILABLE = False
    # Provide stub for when jsonschema is not available
    class Draft7Validator:
        pass


class SchemaValidationError(Exception):
    """Schema validation error"""
    pass


class SchemaCompilationError(SchemaValidationError):
    """Schema compilation failed"""
    def __init__(self, msg: str):
        super().__init__(f"Schema compilation failed: {msg}")


class ArgumentValidationError(SchemaValidationError):
    """Argument validation failed"""
    def __init__(self, argument: str, details: str):
        super().__init__(f"Validation failed for argument '{argument}': {details}")
        self.argument = argument
        self.details = details


class OutputValidationError(SchemaValidationError):
    """Output validation failed"""
    def __init__(self, details: str):
        super().__init__(f"Validation failed for output: {details}")
        self.details = details


class MediaUrnNotResolvedError(SchemaValidationError):
    """Media URN could not be resolved"""
    def __init__(self, media_urn: str, error: str):
        super().__init__(f"Media URN '{media_urn}' could not be resolved: {error}")
        self.media_urn = media_urn
        self.error = error


class SchemaValidator:
    """Schema validator with caching for performance"""

    def __init__(self):
        self.schema_cache: Dict[str, Any] = {}
        if not JSONSCHEMA_AVAILABLE:
            raise ImportError("jsonschema package is required for schema validation. Install with: pip install jsonschema")

    def validate_value_against_schema(self, name: str, value: Any, schema: Dict[str, Any]) -> None:
        """Validate a JSON value against a schema"""
        # Cache compiled schemas by schema JSON
        schema_key = json.dumps(schema, sort_keys=True)

        if schema_key not in self.schema_cache:
            try:
                validator = Draft7Validator(schema)
                self.schema_cache[schema_key] = validator
            except Exception as e:
                raise SchemaCompilationError(str(e))

        validator = self.schema_cache[schema_key]

        # Validate the value
        errors = list(validator.iter_errors(value))
        if errors:
            error_details = "\n".join([f"  - {e.message}" for e in errors])

            if name == "output":
                raise OutputValidationError(error_details)
            else:
                raise ArgumentValidationError(name, error_details)

    async def validate_argument(self, arg_def, value: Any, registry) -> None:
        """Validate a single argument against its registry-resolved schema.

        The cap's referenced media URNs land in the registry as part of
        the atomic cap fetch, so resolution failure here is a real
        problem — surface it instead of silently skipping validation.
        Specs without a schema return early as a normal no-op.
        """
        from capdag.media.spec import resolve_media_urn

        resolved = await resolve_media_urn(arg_def.media_urn, registry)
        schema = resolved.schema
        if schema is None:
            return
        self.validate_value_against_schema(arg_def.media_urn, value, schema)

    async def validate_output(self, output_def, value: Any, registry) -> None:
        """Validate output against its registry-resolved schema."""
        from capdag.media.spec import resolve_media_urn

        resolved = await resolve_media_urn(output_def.media_urn, registry)
        schema = resolved.schema
        if schema is None:
            return
        self.validate_value_against_schema("output", value, schema)

    async def validate_arguments(self, cap, arguments: list, registry) -> None:
        """Validate all positional arguments for a capability against the
        schemas resolved through the unified ``FabricRegistry``."""
        from capdag.cap.definition import PositionSource

        args = cap.get_args()

        # Get positional args sorted by position
        positional_args = []
        for arg in args:
            for source in arg.sources:
                if isinstance(source, PositionSource):
                    positional_args.append((arg, source.position))
                    break

        positional_args.sort(key=lambda x: x[1])

        for arg_def, position in positional_args:
            if position < len(arguments):
                await self.validate_argument(arg_def, arguments[position], registry)
