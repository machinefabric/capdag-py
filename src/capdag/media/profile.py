"""Profile Schema Registry

Registry for JSON Schema profiles. Validates data against media def type
definitions.

Schemas are not bundled into the library — callers seed the in-memory cache
explicitly via ``insert_schema`` (e.g. after fetching a schema body from the
public registry). A registry constructed via ``ProfileSchemaRegistry()`` is
empty until populated.
"""

import json
from typing import Any, Dict, List, Optional

import jsonschema  # required dependency; failure to import is a fatal config error


class ProfileSchemaError(Exception):
    """Error from profile schema operations"""
    pass


class ProfileSchemaRegistry:
    """Registry for JSON Schema profiles.

    Validates data against caller-supplied JSON Schema bodies indexed by
    profile URL. The registry does not embed schemas of its own and does not
    fetch over HTTP — populate it explicitly via ``insert_schema`` from
    whichever source is appropriate (the public registry, a local file,
    a test fixture).
    """

    def __init__(self) -> None:
        """Create an empty ProfileSchemaRegistry."""
        self._schemas: Dict[str, Dict[str, Any]] = {}

    def insert_schema(self, profile_url: str, schema: Dict[str, Any]) -> None:
        """Insert a JSON Schema body into the cache, validating that the
        body itself is a syntactically valid JSON Schema. Raises
        ``ProfileSchemaError`` on invalid schemas — never silently caches
        a broken schema."""
        try:
            jsonschema.Draft202012Validator.check_schema(schema)
        except jsonschema.SchemaError as e:
            raise ProfileSchemaError(
                f"Invalid JSON Schema for {profile_url}: {e.message}"
            )
        self._schemas[profile_url] = schema

    def validate(self, profile_url: str, value: Any) -> Optional[List[str]]:
        """Validate a value against a profile schema.

        Returns ``None`` if valid or if the schema is not in the cache;
        a list of error strings if the value is invalid. Callers that want
        to fail loudly when a schema is missing should pre-check with
        ``schema_exists``.
        """
        schema = self._schemas.get(profile_url)
        if schema is None:
            return None

        try:
            jsonschema.validate(instance=value, schema=schema)
            return None
        except jsonschema.ValidationError as e:
            return [str(e.message)]

    def validate_cached(self, profile_url: str, value: Any) -> Optional[List[str]]:
        """Alias for ``validate``. The Python implementation has no async
        fetch path, so cached and live validation are the same operation."""
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
