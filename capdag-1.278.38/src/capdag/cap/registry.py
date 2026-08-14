"""Backwards-compatible import surface for the cap-side registry.

The cap and media registries were merged into a single
``capdag.fabric.registry.FabricRegistry``. This module re-exports
the unified type and the cap-related symbols under the historical
``capdag.cap.registry`` import path.
"""

from capdag.fabric.registry import (
    CACHE_DURATION_HOURS,
    DEFAULT_REGISTRY_BASE_URL,
    CacheEntry,
    CacheError,
    FabricRegistry,
    FabricRegistryError,
    HttpError,
    NetworkBlockedError,
    NotFoundError,
    ParseError,
    RegistryConfig,
    ValidationError,
    normalize_cap_urn,
)

__all__ = [
    "CACHE_DURATION_HOURS",
    "DEFAULT_REGISTRY_BASE_URL",
    "CacheEntry",
    "CacheError",
    "FabricRegistry",
    "FabricRegistryError",
    "HttpError",
    "NetworkBlockedError",
    "NotFoundError",
    "ParseError",
    "RegistryConfig",
    "ValidationError",
    "normalize_cap_urn",
]
