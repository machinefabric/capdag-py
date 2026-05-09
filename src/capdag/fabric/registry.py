"""Unified Fabric Registry — merged cap and media-spec lookup/cache.

Replaces the previous split between `cap.registry.FabricRegistry` (cap
definitions) and `media.registry.FabricRegistry` (media specs). Holds
one HTTP client, one disk cache root with `caps/` and `media/`
subdirectories, two in-memory dicts (cached caps, cached specs), and
the extension index.

Atomic cap fetch: a cap is only cached after every media URN it
references has also been successfully fetched. If any referenced media
URN cannot be resolved, the cap is NOT cached, NOT persisted to disk,
and the caller sees the error.
"""

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

from capdag.cap.definition import Cap, StdinSource
from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn


DEFAULT_REGISTRY_BASE_URL = "https://fabric.capdag.com"
CACHE_DURATION_HOURS = 24


# =============================================================================
# Errors
# =============================================================================


class FabricRegistryError(Exception):
    """Base exception for fabric registry errors."""


class HttpError(FabricRegistryError):
    """HTTP request error."""


class NetworkBlockedError(FabricRegistryError):
    """Network access was explicitly blocked by offline mode."""


class NotFoundError(FabricRegistryError):
    """Cap or media spec not found in registry."""


class ParseError(FabricRegistryError):
    """Failed to parse registry response."""


class CacheError(FabricRegistryError):
    """Cache operation error."""


class ValidationError(FabricRegistryError):
    """Validation error."""


class ExtensionNotFoundError(FabricRegistryError):
    """Extension not found in registry."""


# =============================================================================
# URN normalization
# =============================================================================


def normalize_cap_urn(urn: str) -> str:
    """Normalize a Cap URN. Returns the input unchanged on parse failure
    so the lookup proceeds and the caller sees the real fetch error."""
    try:
        return CapUrn.from_string(urn).to_string()
    except Exception:
        return urn


def normalize_media_urn(urn: str) -> str:
    """Normalize a Media URN. Returns the input unchanged on parse
    failure so the lookup proceeds and the caller sees the real fetch error."""
    try:
        return MediaUrn.from_string(urn).to_string()
    except Exception:
        return urn


# =============================================================================
# Cache entries
# =============================================================================


@dataclass
class CacheEntry:
    """On-disk cache entry for a Cap definition."""

    definition: Cap
    cached_at: int
    ttl_hours: int

    def is_expired(self) -> bool:
        return int(time.time()) > self.cached_at + (self.ttl_hours * 3600)

    def to_dict(self) -> Dict:
        return {
            "definition": self.definition.to_dict(),
            "cached_at": self.cached_at,
            "ttl_hours": self.ttl_hours,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "CacheEntry":
        return cls(
            definition=Cap.from_dict(data["definition"]),
            cached_at=data["cached_at"],
            ttl_hours=data["ttl_hours"],
        )


class StoredMediaSpec:
    """Stored media spec format (matches registry API response)."""

    def __init__(
        self,
        urn: str,
        media_type: str,
        title: str,
        profile_uri: Optional[str] = None,
        schema: Optional[Any] = None,
        description: Optional[str] = None,
        documentation: Optional[str] = None,
        validation: Optional[Dict] = None,
        metadata: Optional[Any] = None,
        extensions: Optional[List[str]] = None,
    ):
        self.urn = urn
        self.media_type = media_type
        self.title = title
        self.profile_uri = profile_uri
        self.schema = schema
        self.description = description
        self.documentation = documentation
        self.validation = validation
        self.metadata = metadata
        self.extensions = extensions or []

    def to_dict(self) -> Dict:
        result: Dict[str, Any] = {
            "urn": self.urn,
            "media_type": self.media_type,
            "title": self.title,
        }
        if self.profile_uri is not None:
            result["profile_uri"] = self.profile_uri
        if self.schema is not None:
            result["schema"] = self.schema
        if self.description is not None:
            result["description"] = self.description
        if self.documentation is not None:
            result["documentation"] = self.documentation
        if self.validation is not None:
            result["validation"] = self.validation
        if self.metadata is not None:
            result["metadata"] = self.metadata
        if self.extensions:
            result["extensions"] = self.extensions
        return result

    @classmethod
    def from_dict(cls, data: Dict) -> "StoredMediaSpec":
        return cls(
            urn=data["urn"],
            media_type=data["media_type"],
            title=data["title"],
            profile_uri=data.get("profile_uri"),
            schema=data.get("schema"),
            description=data.get("description"),
            documentation=data.get("documentation"),
            validation=data.get("validation"),
            metadata=data.get("metadata"),
            extensions=data.get("extensions", []),
        )


class MediaCacheEntry:
    """On-disk cache entry for a media spec."""

    def __init__(self, spec: StoredMediaSpec, cached_at: int, ttl_hours: int):
        self.spec = spec
        self.cached_at = cached_at
        self.ttl_hours = ttl_hours

    def is_expired(self) -> bool:
        return int(time.time()) > self.cached_at + (self.ttl_hours * 3600)

    def to_dict(self) -> Dict:
        return {
            "spec": self.spec.to_dict(),
            "cached_at": self.cached_at,
            "ttl_hours": self.ttl_hours,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "MediaCacheEntry":
        return cls(
            spec=StoredMediaSpec.from_dict(data["spec"]),
            cached_at=data["cached_at"],
            ttl_hours=data["ttl_hours"],
        )


# =============================================================================
# Configuration
# =============================================================================


class RegistryConfig:
    """Configuration for the unified fabric registry.

    Resolution order:
    1. Explicit constructor argument.
    2. Environment variable (`CAPDAG_REGISTRY_URL`, `CAPDAG_SCHEMA_BASE_URL`).
    3. Default values.
    """

    def __init__(
        self,
        registry_base_url: Optional[str] = None,
        schema_base_url: Optional[str] = None,
    ):
        if registry_base_url is None:
            registry_base_url = os.getenv(
                "CAPDAG_REGISTRY_URL", DEFAULT_REGISTRY_BASE_URL
            )

        if schema_base_url is None:
            schema_base_url = os.getenv(
                "CAPDAG_SCHEMA_BASE_URL", f"{registry_base_url}/schema"
            )

        self.registry_base_url = registry_base_url
        self.schema_base_url = schema_base_url

    def with_registry_url(self, url: str) -> "RegistryConfig":
        if self.schema_base_url == f"{self.registry_base_url}/schema":
            self.schema_base_url = f"{url}/schema"
        self.registry_base_url = url
        return self

    def with_schema_url(self, url: str) -> "RegistryConfig":
        self.schema_base_url = url
        return self


# =============================================================================
# Unified registry
# =============================================================================


class FabricRegistry:
    """Unified registry for cap definitions and media specs.

    Holds two in-memory caches (cached_caps, cached_specs) plus an
    extension index. The disk layout uses one root with `caps/` and
    `media/` subdirectories so the two domains stay distinguishable
    on-disk while sharing one HTTP client and one cache root.

    Atomic cap fetch: `get_cap` only caches a cap after every media
    URN it references has also been successfully fetched. If any
    referenced media URN cannot be resolved, the cap is NOT cached,
    NOT persisted to disk, and the error propagates to the caller.
    """

    def __init__(
        self,
        cache_dir: Path,
        config: RegistryConfig,
        client: Optional["httpx.AsyncClient"] = None,
    ):
        if not HTTPX_AVAILABLE and client is None:
            raise ImportError(
                "httpx is required for registry operations. Install with: pip install httpx"
            )

        self.cache_dir = cache_dir
        self.caps_cache_dir = cache_dir / "caps"
        self.media_cache_dir = cache_dir / "media"
        self.config = config
        self.client = client

        self.cached_caps: Dict[str, Cap] = {}
        self.cached_specs: Dict[str, StoredMediaSpec] = {}
        self.extension_index: Dict[str, List[str]] = {}

        self.cache_lock = threading.Lock()
        self._offline = False

    # -------------------------------------------------------------------------
    # Constructors
    # -------------------------------------------------------------------------

    @classmethod
    async def new(cls) -> "FabricRegistry":
        """Create a new FabricRegistry with default configuration."""
        return await cls.with_config(RegistryConfig())

    @classmethod
    async def with_config(cls, config: RegistryConfig) -> "FabricRegistry":
        """Create a new FabricRegistry with custom configuration."""
        cache_dir = cls._get_cache_dir()
        cache_dir.mkdir(parents=True, exist_ok=True)

        client = httpx.AsyncClient(timeout=10.0) if HTTPX_AVAILABLE else None

        registry = cls(cache_dir, config, client)
        registry._load_all_cached_caps()
        registry._load_all_cached_specs()
        return registry

    @staticmethod
    def _get_cache_dir() -> Path:
        if os.name == "nt":
            cache_base = Path(os.getenv("LOCALAPPDATA", os.path.expanduser("~/.cache")))
        elif os.name == "posix":
            cache_base = Path(os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache")))
        else:
            cache_base = Path.home() / ".cache"
        return cache_base / "capdag"

    # -------------------------------------------------------------------------
    # Disk-cache loaders
    # -------------------------------------------------------------------------

    def _load_all_cached_caps(self) -> None:
        if not self.caps_cache_dir.exists():
            return
        for cache_file in self.caps_cache_dir.glob("*.json"):
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                entry = CacheEntry.from_dict(data)
                if entry.is_expired():
                    cache_file.unlink(missing_ok=True)
                    continue
                normalized_urn = normalize_cap_urn(entry.definition.urn_string())
                with self.cache_lock:
                    self.cached_caps[normalized_urn] = entry.definition
            except Exception as e:
                print(f"[WARN] Failed to load cap cache file {cache_file}: {e}")
                cache_file.unlink(missing_ok=True)

    def _load_all_cached_specs(self) -> None:
        if not self.media_cache_dir.exists():
            return
        for cache_file in self.media_cache_dir.glob("*.json"):
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                entry = MediaCacheEntry.from_dict(data)
                if entry.is_expired():
                    cache_file.unlink(missing_ok=True)
                    continue
                normalized_urn = normalize_media_urn(entry.spec.urn)
                with self.cache_lock:
                    self.cached_specs[normalized_urn] = entry.spec
                    self._update_extension_index(entry.spec)
            except Exception as e:
                print(f"[WARN] Failed to load media cache file {cache_file}: {e}")
                cache_file.unlink(missing_ok=True)

    # -------------------------------------------------------------------------
    # Disk-cache writers
    # -------------------------------------------------------------------------

    def _cap_cache_file_path(self, urn: str) -> Path:
        normalized_urn = normalize_cap_urn(urn)
        digest = hashlib.sha256(normalized_urn.encode("utf-8")).hexdigest()
        return self.caps_cache_dir / f"{digest}.json"

    def _media_cache_file_path(self, urn: str) -> Path:
        normalized_urn = normalize_media_urn(urn)
        digest = hashlib.sha256(normalized_urn.encode("utf-8")).hexdigest()
        return self.media_cache_dir / f"{digest}.json"

    def _save_cap_to_cache(self, cap: Cap) -> None:
        self.caps_cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self._cap_cache_file_path(cap.urn_string())
        entry = CacheEntry(definition=cap, cached_at=int(time.time()), ttl_hours=CACHE_DURATION_HOURS)
        try:
            with open(cache_file, "w") as f:
                json.dump(entry.to_dict(), f, indent=2)
        except Exception as e:
            raise CacheError(f"Failed to write cap cache file: {e}")

    def _save_media_spec_to_cache(self, spec: StoredMediaSpec) -> None:
        self.media_cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self._media_cache_file_path(spec.urn)
        entry = MediaCacheEntry(spec=spec, cached_at=int(time.time()), ttl_hours=CACHE_DURATION_HOURS)
        try:
            with open(cache_file, "w") as f:
                json.dump(entry.to_dict(), f, indent=2)
        except Exception as e:
            raise CacheError(f"Failed to write media spec cache file: {e}")

    # -------------------------------------------------------------------------
    # Extension index
    # -------------------------------------------------------------------------

    def _update_extension_index(self, spec: StoredMediaSpec) -> None:
        for ext in spec.extensions:
            ext_lower = ext.lower()
            urns = self.extension_index.setdefault(ext_lower, [])
            if spec.urn not in urns:
                urns.append(spec.urn)

    # -------------------------------------------------------------------------
    # HTTP fetch
    # -------------------------------------------------------------------------

    async def _fetch_cap_from_registry(self, urn: str) -> Cap:
        if not HTTPX_AVAILABLE or self.client is None:
            raise HttpError("httpx not available - cannot fetch from registry")

        normalized_urn = normalize_cap_urn(urn)
        try:
            CapUrn.from_string(normalized_urn)
        except Exception as e:
            raise FabricRegistryError(f"Invalid cap URN '{normalized_urn}': {e}")

        digest = hashlib.sha256(normalized_urn.encode("utf-8")).hexdigest()
        url = f"{self.config.registry_base_url}/caps/{digest}"

        try:
            response = await self.client.get(url)
            if not response.is_success:
                raise NotFoundError(
                    f"Cap '{urn}' not found in registry (HTTP {response.status_code})"
                )
            return Cap.from_dict(response.json())
        except httpx.HTTPError as e:
            raise HttpError(f"Failed to fetch cap from registry: {e}")
        except json.JSONDecodeError as e:
            raise ParseError(f"Failed to parse registry response for cap '{urn}': {e}")

    async def _fetch_media_spec_from_registry(self, urn: str) -> StoredMediaSpec:
        if not HTTPX_AVAILABLE or self.client is None:
            raise HttpError("httpx not available - cannot fetch from registry")

        normalized_urn = normalize_media_urn(urn)
        try:
            MediaUrn.from_string(normalized_urn)
        except Exception as e:
            raise FabricRegistryError(f"Invalid media URN '{normalized_urn}': {e}")

        digest = hashlib.sha256(normalized_urn.encode("utf-8")).hexdigest()
        url = f"{self.config.registry_base_url}/media/{digest}"

        try:
            response = await self.client.get(url)
            if not response.is_success:
                raise NotFoundError(
                    f"Media spec '{urn}' not found in registry (HTTP {response.status_code})"
                )
            return StoredMediaSpec.from_dict(response.json())
        except httpx.HTTPError as e:
            raise HttpError(f"Failed to fetch media spec from registry: {e}")
        except (json.JSONDecodeError, KeyError) as e:
            raise ParseError(f"Failed to parse registry response for media '{urn}': {e}")

    # -------------------------------------------------------------------------
    # Atomic cap fetch — the core of the merged registry
    # -------------------------------------------------------------------------

    @staticmethod
    def _is_wildcard_media_urn(urn: str) -> bool:
        """Return True if `urn` is the bare `media:` identity URN.

        The wildcard URN is not a fetchable spec — it is the universal
        input/output marker. Skip it from the recursive fetch list of
        a cap so the cap can still be cached even if the registry has
        no entry for `media:`.
        """
        try:
            parsed = MediaUrn.from_string(urn)
        except Exception:
            return False
        return parsed.is_top()

    def _collect_referenced_media_urns(self, cap: Cap) -> List[str]:
        """Collect every media URN a cap definition references, skipping
        the bare `media:` wildcard. Order is deterministic (in-spec,
        out-spec, args, stdin sources, output) and de-duplicated."""
        seen: List[str] = []

        def push(urn: str) -> None:
            if not urn or self._is_wildcard_media_urn(urn):
                return
            normalized = normalize_media_urn(urn)
            if normalized not in seen:
                seen.append(normalized)

        push(cap.urn.in_spec())
        push(cap.urn.out_spec())
        for arg in cap.get_args():
            push(arg.media_urn)
            for source in arg.sources:
                if isinstance(source, StdinSource):
                    push(source.stdin)
        output = cap.get_output()
        if output is not None:
            push(output.media_urn)
        return seen

    async def _fetch_cap_atomic(self, urn: str) -> Cap:
        """Fetch a cap and every media URN it references atomically.

        Returns the cap on success and updates both in-memory caches
        and disk. On any failure (cap fetch or any referenced media
        spec fetch), the cap is NOT cached — the caller sees the
        propagated error.
        """
        cap = await self._fetch_cap_from_registry(urn)

        referenced = self._collect_referenced_media_urns(cap)
        for media_urn in referenced:
            with self.cache_lock:
                already_cached = media_urn in self.cached_specs
            if already_cached:
                continue
            spec = await self._fetch_media_spec_from_registry(media_urn)
            self._save_media_spec_to_cache(spec)
            with self.cache_lock:
                self.cached_specs[normalize_media_urn(spec.urn)] = spec
                self._update_extension_index(spec)

        # All referenced media specs landed — now cache the cap.
        self._save_cap_to_cache(cap)
        with self.cache_lock:
            self.cached_caps[normalize_cap_urn(cap.urn_string())] = cap
        return cap

    # -------------------------------------------------------------------------
    # Public cap API
    # -------------------------------------------------------------------------

    async def get_cap(self, urn: str) -> Cap:
        """Get a cap by URN. Hits in-memory cache, then network."""
        normalized_urn = normalize_cap_urn(urn)
        with self.cache_lock:
            cached = self.cached_caps.get(normalized_urn)
        if cached is not None:
            return cached

        if self._offline:
            raise NetworkBlockedError(
                f"Network access blocked while offline: cannot fetch cap {urn!r}"
            )

        return await self._fetch_cap_atomic(urn)

    async def get_caps(self, urns: List[str]) -> List[Cap]:
        return [await self.get_cap(u) for u in urns]

    async def get_cached_caps(self) -> List[Cap]:
        with self.cache_lock:
            return list(self.cached_caps.values())

    def get_cached_cap(self, urn: str) -> Optional[Cap]:
        """Synchronous in-memory cache probe; never touches the network."""
        normalized_urn = normalize_cap_urn(urn)
        with self.cache_lock:
            return self.cached_caps.get(normalized_urn)

    async def cap_exists(self, urn: str) -> bool:
        try:
            await self.get_cap(urn)
            return True
        except (NotFoundError, HttpError, ParseError):
            return False

    async def validate_cap(self, cap: Cap) -> None:
        """Validate a local cap against its canonical definition."""
        canonical_cap = await self.get_cap(cap.urn_string())
        if cap.command != canonical_cap.command:
            raise ValidationError(
                f"Command mismatch. Local: {cap.command}, Canonical: {canonical_cap.command}"
            )
        local_stdin = cap.get_stdin_media_urn()
        canonical_stdin = canonical_cap.get_stdin_media_urn()
        if local_stdin != canonical_stdin:
            raise ValidationError(
                f"stdin mismatch. Local: {local_stdin}, Canonical: {canonical_stdin}"
            )

    # -------------------------------------------------------------------------
    # Public media-spec API
    # -------------------------------------------------------------------------

    async def get_media_spec(self, urn: str) -> StoredMediaSpec:
        normalized_urn = normalize_media_urn(urn)
        with self.cache_lock:
            cached = self.cached_specs.get(normalized_urn)
        if cached is not None:
            return cached

        if self._offline:
            raise NetworkBlockedError(
                f"Network access blocked while offline: cannot fetch media spec {urn!r}"
            )

        spec = await self._fetch_media_spec_from_registry(urn)
        self._save_media_spec_to_cache(spec)
        with self.cache_lock:
            self.cached_specs[normalize_media_urn(spec.urn)] = spec
            self._update_extension_index(spec)
        return spec

    async def get_media_specs(self, urns: List[str]) -> List[StoredMediaSpec]:
        return [await self.get_media_spec(u) for u in urns]

    async def get_cached_media_specs(self) -> List[StoredMediaSpec]:
        with self.cache_lock:
            return list(self.cached_specs.values())

    def get_cached_media_spec(self, urn: str) -> Optional[StoredMediaSpec]:
        """Synchronous in-memory cache probe; never touches the network."""
        normalized_urn = normalize_media_urn(urn)
        with self.cache_lock:
            return self.cached_specs.get(normalized_urn)

    async def media_spec_exists(self, urn: str) -> bool:
        try:
            await self.get_media_spec(urn)
            return True
        except (NotFoundError, HttpError, ParseError):
            return False

    def media_urns_for_extension(self, extension: str) -> List[str]:
        """Look up media URNs registered for a file extension.

        Raises ExtensionNotFoundError if no spec is registered. The
        registry hydrates lazily through `get_media_spec` and through
        the atomic cap fetch — extensions only become known once the
        owning specs have landed in cache.
        """
        ext_lower = extension.lower()
        with self.cache_lock:
            urns = self.extension_index.get(ext_lower)
        if urns is None:
            raise ExtensionNotFoundError(
                f"No media spec registered for extension '{extension}'. "
                f"Ensure the media spec is defined in capfab/src/media/ with an 'extension' field."
            )
        return list(urns)

    def get_extension_mappings(self) -> List[tuple]:
        with self.cache_lock:
            return [(k, list(v)) for k, v in self.extension_index.items()]

    # -------------------------------------------------------------------------
    # Offline / cache control
    # -------------------------------------------------------------------------

    def set_offline(self, offline: bool) -> None:
        self._offline = offline

    def clear_cache(self) -> None:
        """Clear in-memory and on-disk caches for both caps and media specs."""
        import shutil

        with self.cache_lock:
            self.cached_caps.clear()
            self.cached_specs.clear()
            self.extension_index.clear()

        if self.cache_dir.exists():
            try:
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                raise CacheError(f"Failed to clear cache directory: {e}")

    # -------------------------------------------------------------------------
    # Identity cap (mandatory)
    # -------------------------------------------------------------------------

    def ensure_identity_cap(self) -> None:
        """Install the mandatory identity cap into the in-memory cap cache.

        Idempotent. The identity cap is mandatory in every capability
        set so the resolver's source-to-cap-arg matching can route
        through identity in any notation.
        """
        from capdag.standard.caps import identity_cap

        identity = identity_cap()
        normalized_urn = normalize_cap_urn(identity.urn_string())
        with self.cache_lock:
            if normalized_urn not in self.cached_caps:
                self.cached_caps[normalized_urn] = identity

    # -------------------------------------------------------------------------
    # Test helpers
    # -------------------------------------------------------------------------

    @classmethod
    def new_for_test(cls, cache_dir: Optional[Path] = None) -> "FabricRegistry":
        """Build an empty registry for tests.

        The mandatory identity cap is auto-installed so the resolver's
        source-to-cap-arg matching can route through identity in any
        notation, matching the production invariant.
        """
        if cache_dir is None:
            from tempfile import mkdtemp

            cache_dir = Path(mkdtemp(prefix="capdag-fabric-test-"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        client = httpx.AsyncClient(timeout=10.0) if HTTPX_AVAILABLE else None
        registry = cls(cache_dir, RegistryConfig(), client)
        registry.ensure_identity_cap()
        return registry

    @classmethod
    def new_for_test_with_config(
        cls, config: RegistryConfig, cache_dir: Optional[Path] = None
    ) -> "FabricRegistry":
        if cache_dir is None:
            from tempfile import mkdtemp

            cache_dir = Path(mkdtemp(prefix="capdag-fabric-test-"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        client = httpx.AsyncClient(timeout=10.0) if HTTPX_AVAILABLE else None
        registry = cls(cache_dir, config, client)
        registry.ensure_identity_cap()
        return registry

    def add_caps_to_cache(self, caps: List[Cap]) -> None:
        """Insert caps directly into the in-memory cache (test helper)."""
        with self.cache_lock:
            for cap in caps:
                self.cached_caps[normalize_cap_urn(cap.urn_string())] = cap

    def add_spec(self, spec: StoredMediaSpec) -> None:
        """Insert a media spec directly into the in-memory cache (test helper).

        Updates the extension index as a side effect so
        `media_urns_for_extension` finds the seeded spec.
        """
        with self.cache_lock:
            self.cached_specs[normalize_media_urn(spec.urn)] = spec
            self._update_extension_index(spec)
