"""Backwards-compatible import surface for the media-side registry.

The cap and media registries were merged into a single
``capdag.fabric.registry.FabricRegistry``. This module re-exports
the unified type and the media-related symbols under the historical
``capdag.media.registry`` import path.
"""

from capdag.fabric.registry import (
    CACHE_DURATION_HOURS,
    ExtensionNotFoundError,
    FabricRegistry,
    FabricRegistryError,
    HttpError,
    MediaCacheEntry,
    NotFoundError,
    ParseError,
    CacheError,
    RegistryConfig,
    StoredMediaDef,
    normalize_media_urn,
)

__all__ = [
    "CACHE_DURATION_HOURS",
    "ExtensionNotFoundError",
    "FabricRegistry",
    "FabricRegistryError",
    "HttpError",
    "MediaCacheEntry",
    "NotFoundError",
    "ParseError",
    "CacheError",
    "RegistryConfig",
    "StoredMediaDef",
    "normalize_media_urn",
]
