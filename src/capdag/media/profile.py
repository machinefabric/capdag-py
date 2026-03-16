"""Profile Schema Registry

Registry for JSON Schema profiles. Validates data against media spec type definitions.
Embeds default schemas for standard types (string, integer, number, boolean, object, arrays).
Uses an in-memory cache of compiled schemas.
"""

import hashlib
import json
from typing import Any, Dict, List, Optional

from capdag.media.spec import (
    PROFILE_STR,
    PROFILE_INT,
    PROFILE_NUM,
    PROFILE_BOOL,
    PROFILE_OBJ,
    PROFILE_STR_ARRAY,
    PROFILE_NUM_ARRAY,
    PROFILE_BOOL_ARRAY,
    PROFILE_OBJ_ARRAY,
)


class ProfileSchemaError(Exception):
    """Error from profile schema operations"""
    pass


# =============================================================================
# Embedded default schemas
# =============================================================================

_EMBEDDED_SCHEMAS: Dict[str, Dict[str, Any]] = {
    PROFILE_STR: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": PROFILE_STR,
        "title": "String",
        "description": "A JSON string value",
        "type": "string",
    },
    PROFILE_INT: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": PROFILE_INT,
        "title": "Integer",
        "description": "A JSON integer value",
        "type": "integer",
    },
    PROFILE_NUM: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": PROFILE_NUM,
        "title": "Number",
        "description": "A JSON number value (integer or floating point)",
        "type": "number",
    },
    PROFILE_BOOL: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": PROFILE_BOOL,
        "title": "Boolean",
        "description": "A JSON boolean value (true or false)",
        "type": "boolean",
    },
    PROFILE_OBJ: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": PROFILE_OBJ,
        "title": "Object",
        "description": "A JSON object value",
        "type": "object",
    },
    PROFILE_STR_ARRAY: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": PROFILE_STR_ARRAY,
        "title": "String Array",
        "description": "A JSON array of string values",
        "type": "array",
        "items": {"type": "string"},
    },
    PROFILE_NUM_ARRAY: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": PROFILE_NUM_ARRAY,
        "title": "Number Array",
        "description": "A JSON array of number values",
        "type": "array",
        "items": {"type": "number"},
    },
    PROFILE_BOOL_ARRAY: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": PROFILE_BOOL_ARRAY,
        "title": "Boolean Array",
        "description": "A JSON array of boolean values",
        "type": "array",
        "items": {"type": "boolean"},
    },
    PROFILE_OBJ_ARRAY: {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": PROFILE_OBJ_ARRAY,
        "title": "Object Array",
        "description": "A JSON array of object values",
        "type": "array",
        "items": {"type": "object"},
    },
}

# All 9 embedded profile URLs
_EMBEDDED_PROFILE_URLS = frozenset(_EMBEDDED_SCHEMAS.keys())


def is_embedded_profile(profile_url: str) -> bool:
    """Check if a profile URL is one of the 9 standard embedded profiles."""
    return profile_url in _EMBEDDED_PROFILE_URLS


class ProfileSchemaRegistry:
    """Registry for JSON Schema profiles.

    Downloads and caches schemas from profile URLs for validating data
    against media spec type definitions. Embeds default schemas for
    standard types.
    """

    def __init__(self) -> None:
        """Create a new ProfileSchemaRegistry with standard schemas loaded."""
        self._schemas: Dict[str, Dict[str, Any]] = {}
        # Install embedded schemas
        for url, schema in _EMBEDDED_SCHEMAS.items():
            self._schemas[url] = schema

    def validate(self, profile_url: str, value: Any) -> Optional[List[str]]:
        """Validate a value against a profile schema.

        Args:
            profile_url: The profile URL to validate against
            value: The JSON value to validate

        Returns:
            None if valid (or schema not found), list of error strings if invalid
        """
        schema = self._schemas.get(profile_url)
        if schema is None:
            # Schema not available — skip validation (matches Rust behavior)
            return None

        return self._validate_against_schema(schema, value)

    def validate_cached(self, profile_url: str, value: Any) -> Optional[List[str]]:
        """Synchronous validation using only cached schemas.

        Same as validate() since we don't do async HTTP fetching.
        """
        return self.validate(profile_url, value)

    def schema_exists(self, profile_url: str) -> bool:
        """Check if a schema is available in the registry."""
        return profile_url in self._schemas

    def get_cached_profiles(self) -> List[str]:
        """Get all profile URLs in the registry."""
        return list(self._schemas.keys())

    def clear_cache(self) -> None:
        """Clear all schemas from the registry."""
        self._schemas.clear()

    @staticmethod
    def _validate_against_schema(
        schema: Dict[str, Any], value: Any
    ) -> Optional[List[str]]:
        """Validate a value against a JSON schema.

        Returns None if valid, list of error strings if invalid.
        Uses jsonschema library if available, falls back to basic type checking.
        """
        try:
            import jsonschema

            try:
                jsonschema.validate(instance=value, schema=schema)
                return None
            except jsonschema.ValidationError as e:
                return [str(e.message)]
            except jsonschema.SchemaError as e:
                return [f"Invalid schema: {e.message}"]
        except ImportError:
            # Fallback: basic type validation without jsonschema library
            return _basic_type_validate(schema, value)


def _basic_type_validate(schema: Dict[str, Any], value: Any) -> Optional[List[str]]:
    """Basic type validation without jsonschema library.

    Handles the simple cases used in embedded schemas.
    """
    expected_type = schema.get("type")
    if expected_type is None:
        return None

    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }

    expected_python_type = type_map.get(expected_type)
    if expected_python_type is None:
        return None

    # Special case: bool is a subclass of int in Python
    if expected_type == "integer" and isinstance(value, bool):
        return [f"Expected {expected_type}, got boolean"]
    if expected_type == "number" and isinstance(value, bool):
        return [f"Expected {expected_type}, got boolean"]

    if not isinstance(value, expected_python_type):
        return [f"Expected {expected_type}, got {type(value).__name__}"]

    # For arrays, validate items
    if expected_type == "array" and "items" in schema:
        items_errors = []
        for i, item in enumerate(value):
            item_errors = _basic_type_validate(schema["items"], item)
            if item_errors:
                items_errors.extend(item_errors)
        if items_errors:
            return items_errors

    return None
