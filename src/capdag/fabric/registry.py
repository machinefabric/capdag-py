"""Unified Fabric Registry — merged cap and media-def lookup/cache.

Replaces the previous split between `cap.registry.FabricRegistry` (cap
definitions) and `media.registry.FabricRegistry` (media defs). Holds
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
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

from capdag.bifaci.cartridge_slug import slug_for
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
    """Cap or media def not found in registry."""


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


class StoredMediaDef:
    """Stored media def format (matches registry API response)."""

    def __init__(
        self,
        urn: str,
        media_type: str,
        title: str,
        version: int = 0,
        profile_uri: Optional[str] = None,
        schema: Optional[Any] = None,
        description: Optional[str] = None,
        documentation: Optional[str] = None,
        validation: Optional[Dict] = None,
        metadata: Optional[Any] = None,
        extensions: Optional[List[str]] = None,
    ):
        self.urn = urn
        # Per-definition version. 0 ⇒ v0 (frozen flat-path); >= 1 ⇒ pinned at
        # media/<sha256-of-urn>/<version>.json and referenced by a manifest.
        self.version = version
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
        if self.version != 0:
            result["version"] = self.version
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
    def from_dict(cls, data: Dict) -> "StoredMediaDef":
        return cls(
            urn=data["urn"],
            media_type=data["media_type"],
            title=data["title"],
            version=int(data.get("version", 0)),
            profile_uri=data.get("profile_uri"),
            schema=data.get("schema"),
            description=data.get("description"),
            documentation=data.get("documentation"),
            validation=data.get("validation"),
            metadata=data.get("metadata"),
            extensions=data.get("extensions", []),
        )


class MediaCacheEntry:
    """On-disk cache entry for a media def."""

    def __init__(self, spec: StoredMediaDef, cached_at: int, ttl_hours: int):
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
            spec=StoredMediaDef.from_dict(data["spec"]),
            cached_at=data["cached_at"],
            ttl_hours=data["ttl_hours"],
        )


# =============================================================================
# Aliases
# =============================================================================


# Alias target kinds. An alias resolves to exactly one cap or media URN.
ALIAS_TARGET_CAP = "cap"
ALIAS_TARGET_MEDIA = "media"

_ALIAS_NAME_RE = re.compile(r"^[a-z0-9._-]+$")


def token_is_urn(token: str) -> bool:
    """A contiguous token "looks like a URN" iff it contains a colon. Every
    tagged URN has the shape ``prefix:...``; the presence of ':' is the
    unambiguous discriminator between a URN and an alias name."""
    return ":" in token


def is_alias_token(token: str) -> bool:
    """Complement of :func:`token_is_urn` — a colon-free token is an alias
    candidate (still subject to :func:`normalize_alias_name` validation)."""
    return not token_is_urn(token)


def normalize_alias_name(name: str) -> str:
    """Normalize and validate an alias name. Lowercases the input, then
    requires it to be non-empty, contain no ':' (so it can never look like a
    tagged URN), contain no whitespace, and match ``[a-z0-9._-]+``. Returns
    the canonical lowercased name or raises ``ValueError`` — no lenient path.
    """
    if not name:
        raise ValueError("alias name is empty")
    if ":" in name:
        raise ValueError(
            f"alias name '{name}' contains ':' — aliases must never look like a tagged URN"
        )
    if any(ch.isspace() for ch in name):
        raise ValueError(f"alias name '{name}' contains whitespace")
    lowered = name.lower()
    if not _ALIAS_NAME_RE.match(lowered):
        raise ValueError(
            f"alias name '{name}' contains invalid characters; "
            f"allowed: lowercase letters, digits, '.', '_', '-'"
        )
    return lowered


def classify_alias_target(target: str) -> Optional[str]:
    """Classify an alias target URN by prefix. Returns ALIAS_TARGET_CAP,
    ALIAS_TARGET_MEDIA, or None (not a cap/media URN)."""
    try:
        CapUrn.from_string(target)
        return ALIAS_TARGET_CAP
    except Exception:
        pass
    try:
        MediaUrn.from_string(target)
        return ALIAS_TARGET_MEDIA
    except Exception:
        pass
    return None


class StoredAlias:
    """Stored alias definition. Mirrors ``fabric/alias.schema.json`` on the
    wire and is the body cached at ``aliases/<sha256-of-name>/<defver>.json``.
    """

    def __init__(self, name: str, target: str, version: int):
        self.name = name
        self.target = target
        self.version = version

    def to_dict(self) -> Dict:
        return {"name": self.name, "target": self.target, "version": self.version}

    @classmethod
    def from_dict(cls, data: Dict) -> "StoredAlias":
        return cls(
            name=data["name"],
            target=data["target"],
            version=data["version"],
        )

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, StoredAlias)
            and self.name == other.name
            and self.target == other.target
            and self.version == other.version
        )


class AliasCacheEntry:
    """On-disk cache entry for an alias."""

    def __init__(self, alias: StoredAlias, cached_at: int, ttl_hours: int):
        self.alias = alias
        self.cached_at = cached_at
        self.ttl_hours = ttl_hours

    def is_expired(self) -> bool:
        return int(time.time()) > self.cached_at + (self.ttl_hours * 3600)

    def to_dict(self) -> Dict:
        return {
            "alias": self.alias.to_dict(),
            "cached_at": self.cached_at,
            "ttl_hours": self.ttl_hours,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "AliasCacheEntry":
        return cls(
            alias=StoredAlias.from_dict(data["alias"]),
            cached_at=data["cached_at"],
            ttl_hours=data["ttl_hours"],
        )


# =============================================================================
# Manifest (registry snapshot)
# =============================================================================


@dataclass
class Manifest:
    """A versioned registry snapshot. Mirrors ``fabric/manifest.schema.json``
    on the wire. v0 (the implicit pre-versioning state) has no manifest
    object; manifests at version >= 1 name every cap URN, media URN, and
    alias name in the snapshot paired with its per-definition version."""

    version: int
    previous: int
    caps: Dict[str, int] = field(default_factory=dict)
    media: Dict[str, int] = field(default_factory=dict)
    aliases: Dict[str, int] = field(default_factory=dict)

    @classmethod
    def empty(cls, version: int) -> "Manifest":
        return cls(version=version, previous=max(0, version - 1))

    def to_dict(self) -> Dict:
        return {
            "version": self.version,
            "previous": self.previous,
            "caps": dict(self.caps),
            "media": dict(self.media),
            "aliases": dict(self.aliases),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Manifest":
        return cls(
            version=data["version"],
            previous=data["previous"],
            caps=dict(data.get("caps", {})),
            media=dict(data.get("media", {})),
            aliases=dict(data.get("aliases", {})),
        )


# =============================================================================
# Configuration
# =============================================================================


class RegistryConfig:
    """Configuration for the unified fabric registry.

    Resolution order:
    1. Explicit constructor argument.
    2. Environment variable (`CDG_FABRIC_REGISTRY_URL`, `CDG_SCHEMA_BASE_URL`).
    3. Default values.
    """

    def __init__(
        self,
        registry_base_url: Optional[str] = None,
        schema_base_url: Optional[str] = None,
    ):
        if registry_base_url is None:
            registry_base_url = os.getenv(
                "CDG_FABRIC_REGISTRY_URL", DEFAULT_REGISTRY_BASE_URL
            )

        if schema_base_url is None:
            schema_base_url = os.getenv(
                "CDG_SCHEMA_BASE_URL", f"{registry_base_url}/schema"
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
    """Unified registry for cap definitions and media defs.

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
        manifest_version: int = 0,
        manifest: Optional[Manifest] = None,
    ):
        if not HTTPX_AVAILABLE and client is None:
            raise ImportError(
                "httpx is required for registry operations. Install with: pip install httpx"
            )

        self.cache_dir = cache_dir
        self.caps_cache_dir = cache_dir / "caps"
        self.media_cache_dir = cache_dir / "media"
        self.aliases_cache_dir = cache_dir / "aliases"
        self.config = config
        self.client = client

        self.cached_caps: Dict[str, Cap] = {}
        self.cached_specs: Dict[str, StoredMediaDef] = {}
        self.cached_aliases: Dict[str, StoredAlias] = {}
        self.extension_index: Dict[str, List[str]] = {}

        # Manifest pin. manifest_version == 0 is legacy v0 / flat-path mode
        # (no manifest consulted). >= 1 is manifest-driven: every URN lookup
        # resolves to a (urn, defver) pair via the manifest before fetching.
        self.manifest_version = manifest_version
        self.manifest = manifest if manifest is not None else Manifest.empty(manifest_version)

        self.cache_lock = threading.Lock()
        self._offline = False

    # -------------------------------------------------------------------------
    # Constructors
    # -------------------------------------------------------------------------

    @staticmethod
    def _baked_manifest_version() -> int:
        """The workspace-pinned fabric manifest version. Mirrors Rust's
        compile-time-baked ``capdag::FABRIC_MANIFEST_VERSION``; in Python it
        is read from ``MFR_FABRIC_MANIFEST_VERSION`` (the same env var the
        build exports). Absent ⇒ 0 (legacy v0 / flat-path mode)."""
        raw = os.getenv("MFR_FABRIC_MANIFEST_VERSION")
        if raw is None or raw == "":
            return 0
        try:
            return int(raw)
        except ValueError:
            raise FabricRegistryError(
                f"MFR_FABRIC_MANIFEST_VERSION must be an integer, got {raw!r}"
            )

    @classmethod
    async def new(cls) -> "FabricRegistry":
        """Create a new FabricRegistry with default configuration, pinned at
        the workspace-baked manifest version."""
        return await cls.with_config(RegistryConfig())

    @classmethod
    async def with_config(cls, config: RegistryConfig) -> "FabricRegistry":
        """Create a new FabricRegistry with custom configuration, pinned at
        the workspace-baked manifest version."""
        return await cls.with_config_and_manifest_version(
            config, cls._baked_manifest_version()
        )

    @classmethod
    async def with_config_and_manifest_version(
        cls, config: RegistryConfig, manifest_version: int
    ) -> "FabricRegistry":
        """Full constructor: custom config + explicit pinned manifest version.

        ``manifest_version == 0`` ⇒ legacy v0 / flat-path mode (no manifest
        fetch). ``>= 1`` ⇒ manifest-driven: the constructor loads
        ``manifest/<N>.json`` from the local cache, else blocks on a network
        fetch. If neither can provide it, raises ``NotFoundError`` — there is
        no fallback to v0.
        """
        cache_dir = cls._get_cache_dir(config.registry_base_url)
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "caps").mkdir(parents=True, exist_ok=True)
        (cache_dir / "media").mkdir(parents=True, exist_ok=True)
        (cache_dir / "aliases").mkdir(parents=True, exist_ok=True)
        (cache_dir / "manifests").mkdir(parents=True, exist_ok=True)

        client = httpx.AsyncClient(timeout=10.0) if HTTPX_AVAILABLE else None

        if manifest_version == 0:
            manifest = Manifest.empty(0)
        else:
            manifest = await cls._load_or_fetch_manifest(
                cache_dir / "manifests", client, config, manifest_version
            )

        registry = cls(cache_dir, config, client, manifest_version, manifest)
        registry._load_all_cached_caps()
        registry._load_all_cached_specs()
        registry._load_all_cached_aliases()
        # Filter loaded caches to the pinned manifest's defvers (v >= 1).
        if manifest_version >= 1:
            with registry.cache_lock:
                registry.cached_caps = {
                    urn: cap
                    for urn, cap in registry.cached_caps.items()
                    if manifest.caps.get(urn, 0) == cap.version
                }
                registry.cached_specs = {
                    urn: spec
                    for urn, spec in registry.cached_specs.items()
                    if manifest.media.get(urn, 0) == spec.version
                }
                registry.cached_aliases = {
                    name: alias
                    for name, alias in registry.cached_aliases.items()
                    if manifest.aliases.get(name, 0) == alias.version
                }
                registry.extension_index = {}
                for spec in registry.cached_specs.values():
                    registry._update_extension_index(spec)
        else:
            with registry.cache_lock:
                registry.cached_aliases = {}
        registry.ensure_identity_cap()
        return registry

    @staticmethod
    async def _load_or_fetch_manifest(
        manifests_dir: Path,
        client: Optional["httpx.AsyncClient"],
        config: RegistryConfig,
        version: int,
    ) -> Manifest:
        cache_file = manifests_dir / f"{version}.json"
        if cache_file.exists():
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                m = Manifest.from_dict(data)
                if m.version != version:
                    raise ParseError(
                        f"Cached manifest at {cache_file} reports version {m.version} "
                        f"but file is {version}.json"
                    )
                return m
            except (json.JSONDecodeError, KeyError):
                cache_file.unlink(missing_ok=True)

        if not HTTPX_AVAILABLE or client is None:
            raise HttpError("httpx not available - cannot fetch manifest")
        url = f"{config.registry_base_url}/manifest/{version}.json"
        try:
            response = await client.get(url)
        except httpx.HTTPError as e:
            raise HttpError(f"Failed to fetch manifest v{version} at {url}: {e}")
        if not response.is_success:
            raise NotFoundError(
                f"Manifest v{version} not found in registry (HTTP {response.status_code}) at {url}"
            )
        body = response.text
        try:
            manifest = Manifest.from_dict(json.loads(body))
        except (json.JSONDecodeError, KeyError) as e:
            raise ParseError(f"Failed to parse manifest v{version}: {e}")
        if manifest.version != version:
            raise ParseError(
                f"Manifest fetched as v{version} reports version {manifest.version}"
            )
        try:
            with open(cache_file, "w") as f:
                f.write(body)
        except Exception as e:
            raise CacheError(f"Failed to write manifest cache to {cache_file}: {e}")
        return manifest

    @staticmethod
    def _get_cache_dir(registry_base_url: str) -> Path:
        """On-disk cache root, namespaced per registry origin.

        The cache root is ``<os-cache>/capdag/<slug>`` where ``slug`` is
        ``slug_for(registry_base_url)`` — the SAME slug scheme the cartridge
        registry layout uses (truncated sha256 hex of the URL). Without this
        per-origin namespace a cache populated from one registry (e.g.
        https://fabric.capdag.com) would be reused to satisfy a lookup against
        a different registry (e.g. https://fabric-staging.capdag.com), which
        serves DIFFERENT bytes for the same URN/version — silently resolving
        against the wrong snapshot. Same origin → stable root, so caching hits;
        distinct origins → distinct roots.
        """
        if os.name == "nt":
            cache_base = Path(os.getenv("LOCALAPPDATA", os.path.expanduser("~/.cache")))
        elif os.name == "posix":
            cache_base = Path(os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache")))
        else:
            cache_base = Path.home() / ".cache"
        return cache_base / "capdag" / slug_for(registry_base_url)

    # -------------------------------------------------------------------------
    # Disk-cache loaders
    # -------------------------------------------------------------------------

    def _load_all_cached_caps(self) -> None:
        """Walk the cap cache dir recursively, picking up both v0 flat files
        (caps/<sha>.json) and v >= 1 versioned files (caps/<sha>/<defver>.json).
        TTL applies only to v0 entries — versioned entries are immutable."""
        if not self.caps_cache_dir.exists():
            return
        for cache_file in self.caps_cache_dir.rglob("*.json"):
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                entry = CacheEntry.from_dict(data)
                if entry.definition.version == 0 and entry.is_expired():
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
        for cache_file in self.media_cache_dir.rglob("*.json"):
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                entry = MediaCacheEntry.from_dict(data)
                if entry.spec.version == 0 and entry.is_expired():
                    cache_file.unlink(missing_ok=True)
                    continue
                normalized_urn = normalize_media_urn(entry.spec.urn)
                with self.cache_lock:
                    self.cached_specs[normalized_urn] = entry.spec
                    self._update_extension_index(entry.spec)
            except Exception as e:
                print(f"[WARN] Failed to load media cache file {cache_file}: {e}")
                cache_file.unlink(missing_ok=True)

    def _load_all_cached_aliases(self) -> None:
        """Walk the alias cache dir (aliases/<sha>/<defver>.json). Aliases are
        versioned-only — no v0 flat path, no TTL expiry."""
        if not self.aliases_cache_dir.exists():
            return
        for cache_file in self.aliases_cache_dir.rglob("*.json"):
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                entry = AliasCacheEntry.from_dict(data)
                with self.cache_lock:
                    self.cached_aliases[entry.alias.name] = entry.alias
            except Exception as e:
                print(f"[WARN] Failed to load alias cache file {cache_file}: {e}")
                cache_file.unlink(missing_ok=True)

    # -------------------------------------------------------------------------
    # Disk-cache writers
    # -------------------------------------------------------------------------

    def _cap_cache_file_path(self, urn: str, defver: int) -> Path:
        normalized_urn = normalize_cap_urn(urn)
        digest = hashlib.sha256(normalized_urn.encode("utf-8")).hexdigest()
        if defver == 0:
            return self.caps_cache_dir / f"{digest}.json"
        return self.caps_cache_dir / digest / f"{defver}.json"

    def _media_cache_file_path(self, urn: str, defver: int) -> Path:
        normalized_urn = normalize_media_urn(urn)
        digest = hashlib.sha256(normalized_urn.encode("utf-8")).hexdigest()
        if defver == 0:
            return self.media_cache_dir / f"{digest}.json"
        return self.media_cache_dir / digest / f"{defver}.json"

    def _alias_cache_file_path(self, normalized_name: str, defver: int) -> Path:
        digest = hashlib.sha256(normalized_name.encode("utf-8")).hexdigest()
        return self.aliases_cache_dir / digest / f"{defver}.json"

    def _save_cap_to_cache(self, cap: Cap) -> None:
        cache_file = self._cap_cache_file_path(cap.urn_string(), cap.version)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        entry = CacheEntry(definition=cap, cached_at=int(time.time()), ttl_hours=CACHE_DURATION_HOURS)
        try:
            with open(cache_file, "w") as f:
                json.dump(entry.to_dict(), f, indent=2)
        except Exception as e:
            raise CacheError(f"Failed to write cap cache file: {e}")

    def _save_media_def_to_cache(self, spec: StoredMediaDef) -> None:
        cache_file = self._media_cache_file_path(spec.urn, spec.version)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        entry = MediaCacheEntry(spec=spec, cached_at=int(time.time()), ttl_hours=CACHE_DURATION_HOURS)
        try:
            with open(cache_file, "w") as f:
                json.dump(entry.to_dict(), f, indent=2)
        except Exception as e:
            raise CacheError(f"Failed to write media def cache file: {e}")

    def _save_alias_to_cache(self, alias: StoredAlias) -> None:
        cache_file = self._alias_cache_file_path(alias.name, alias.version)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        entry = AliasCacheEntry(alias=alias, cached_at=int(time.time()), ttl_hours=CACHE_DURATION_HOURS)
        try:
            with open(cache_file, "w") as f:
                json.dump(entry.to_dict(), f, indent=2)
        except Exception as e:
            raise CacheError(f"Failed to write alias cache file: {e}")

    # -------------------------------------------------------------------------
    # Extension index
    # -------------------------------------------------------------------------

    def _update_extension_index(self, spec: StoredMediaDef) -> None:
        for ext in spec.extensions:
            ext_lower = ext.lower()
            urns = self.extension_index.setdefault(ext_lower, [])
            if spec.urn not in urns:
                urns.append(spec.urn)

    # -------------------------------------------------------------------------
    # HTTP fetch
    # -------------------------------------------------------------------------

    async def _fetch_cap_from_registry(self, urn: str, defver: int) -> Cap:
        if not HTTPX_AVAILABLE or self.client is None:
            raise HttpError("httpx not available - cannot fetch from registry")

        normalized_urn = normalize_cap_urn(urn)
        try:
            CapUrn.from_string(normalized_urn)
        except Exception as e:
            raise FabricRegistryError(f"Invalid cap URN '{normalized_urn}': {e}")

        digest = hashlib.sha256(normalized_urn.encode("utf-8")).hexdigest()
        if defver == 0:
            url = f"{self.config.registry_base_url}/caps/{digest}"
        else:
            url = f"{self.config.registry_base_url}/caps/{digest}/{defver}.json"

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

    async def _fetch_media_def_from_registry(self, urn: str, defver: int) -> StoredMediaDef:
        if not HTTPX_AVAILABLE or self.client is None:
            raise HttpError("httpx not available - cannot fetch from registry")

        normalized_urn = normalize_media_urn(urn)
        try:
            MediaUrn.from_string(normalized_urn)
        except Exception as e:
            raise FabricRegistryError(f"Invalid media URN '{normalized_urn}': {e}")

        digest = hashlib.sha256(normalized_urn.encode("utf-8")).hexdigest()
        if defver == 0:
            url = f"{self.config.registry_base_url}/media/{digest}"
        else:
            url = f"{self.config.registry_base_url}/media/{digest}/{defver}.json"

        try:
            response = await self.client.get(url)
            if not response.is_success:
                raise NotFoundError(
                    f"Media def '{urn}' not found in registry (HTTP {response.status_code})"
                )
            return StoredMediaDef.from_dict(response.json())
        except httpx.HTTPError as e:
            raise HttpError(f"Failed to fetch media def from registry: {e}")
        except (json.JSONDecodeError, KeyError) as e:
            raise ParseError(f"Failed to parse registry response for media '{urn}': {e}")

    async def _fetch_alias_from_registry(self, normalized_name: str, defver: int) -> StoredAlias:
        if not HTTPX_AVAILABLE or self.client is None:
            raise HttpError("httpx not available - cannot fetch from registry")
        if defver < 1:
            raise NotFoundError(
                f"alias '{normalized_name}' has non-positive defver {defver}; "
                f"aliases are versioned-only"
            )
        digest = hashlib.sha256(normalized_name.encode("utf-8")).hexdigest()
        url = f"{self.config.registry_base_url}/aliases/{digest}/{defver}.json"
        try:
            response = await self.client.get(url)
            if not response.is_success:
                raise NotFoundError(
                    f"alias '{normalized_name}' not found in registry "
                    f"(HTTP {response.status_code}) at {url}"
                )
            alias = StoredAlias.from_dict(response.json())
        except httpx.HTTPError as e:
            raise HttpError(f"Failed to fetch alias '{normalized_name}': {e}")
        except (json.JSONDecodeError, KeyError) as e:
            raise ParseError(f"Failed to parse alias '{normalized_name}': {e}")
        # The fetched body must match what was requested, and the target must
        # classify as a cap or media URN — a mismatched object is a hard error.
        if alias.name != normalized_name:
            raise ParseError(
                f"alias object name '{alias.name}' does not match requested name "
                f"'{normalized_name}'"
            )
        if alias.version != defver:
            raise ParseError(
                f"alias '{alias.name}' object reports version {alias.version} "
                f"but manifest pins defver {defver}"
            )
        if classify_alias_target(alias.target) is None:
            raise ValidationError(
                f"alias '{alias.name}' target '{alias.target}' is neither a cap nor a media URN"
            )
        return alias

    # -------------------------------------------------------------------------
    # Defver resolution (manifest pin)
    # -------------------------------------------------------------------------

    def _cap_defver(self, normalized_urn: str) -> int:
        """Resolve a normalized cap URN to its defver under the pinned
        manifest. At v0 → 0. At v >= 1 the URN must be in the manifest's caps
        map; absence is a hard NotFoundError (no fallback to flat paths)."""
        if self.manifest_version == 0:
            return 0
        defver = self.manifest.caps.get(normalized_urn)
        if defver is None:
            raise NotFoundError(
                f"cap '{normalized_urn}' is not part of manifest v{self.manifest_version}"
            )
        return defver

    def _media_defver(self, normalized_urn: str) -> int:
        if self.manifest_version == 0:
            return 0
        # The bare `media:` wildcard is a sentinel with no published spec.
        if normalized_urn == "media:":
            return 0
        defver = self.manifest.media.get(normalized_urn)
        if defver is None:
            raise NotFoundError(
                f"media def '{normalized_urn}' is not part of manifest v{self.manifest_version}"
            )
        return defver

    def _alias_defver(self, normalized_name: str) -> int:
        """Resolve a normalized alias name to its defver. Aliases exist only
        in the versioned regime: at v0 any alias lookup is a hard NotFound."""
        if self.manifest_version == 0:
            raise NotFoundError(
                f"alias '{normalized_name}' cannot resolve: registry is pinned at v0 "
                f"(aliases are a versioned-regime concept)"
            )
        defver = self.manifest.aliases.get(normalized_name)
        if defver is None:
            raise NotFoundError(
                f"alias '{normalized_name}' is not part of manifest v{self.manifest_version}"
            )
        return defver

    def cap_defver_for(self, urn: str) -> int:
        return self._cap_defver(normalize_cap_urn(urn))

    def media_defver_for(self, urn: str) -> int:
        return self._media_defver(normalize_media_urn(urn))

    def alias_defver_for(self, name: str) -> int:
        return self._alias_defver(normalize_alias_name(name))

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
        normalized_urn = normalize_cap_urn(urn)
        defver = self._cap_defver(normalized_urn)
        cap = await self._fetch_cap_from_registry(urn, defver)

        referenced = self._collect_referenced_media_urns(cap)
        for media_urn in referenced:
            with self.cache_lock:
                already_cached = media_urn in self.cached_specs
            if already_cached:
                continue
            media_defver = self._media_defver(media_urn)
            spec = await self._fetch_media_def_from_registry(media_urn, media_defver)
            self._save_media_def_to_cache(spec)
            with self.cache_lock:
                self.cached_specs[normalize_media_urn(spec.urn)] = spec
                self._update_extension_index(spec)

        # All referenced media defs landed — now cache the cap.
        self._save_cap_to_cache(cap)
        with self.cache_lock:
            self.cached_caps[normalize_cap_urn(cap.urn_string())] = cap
        return cap

    # -------------------------------------------------------------------------
    # Public cap API
    # -------------------------------------------------------------------------

    async def get_cap(self, urn: str) -> Cap:
        """Get a cap by URN or alias. Hits in-memory cache, then network.

        ``urn`` may be a cap URN (``cap:...``) or an alias (a colon-free
        token). An alias is resolved first; because this is the typed cap
        boundary, an alias whose target is not a cap URN is a hard error.
        """
        if is_alias_token(urn):
            target = await self.resolve_alias_typed(urn, ALIAS_TARGET_CAP)
            return await self.get_cap(target)

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
    # Public media-def API
    # -------------------------------------------------------------------------

    async def get_media_def(self, urn: str) -> StoredMediaDef:
        """Get a media def by URN or alias.

        ``urn`` may be a media URN (``media:...``) or an alias (a colon-free
        token). An alias is resolved first; because this is the typed media
        boundary, an alias whose target is not a media URN is a hard error.
        """
        if is_alias_token(urn):
            target = await self.resolve_alias_typed(urn, ALIAS_TARGET_MEDIA)
            return await self.get_media_def(target)

        normalized_urn = normalize_media_urn(urn)
        with self.cache_lock:
            cached = self.cached_specs.get(normalized_urn)
        if cached is not None:
            return cached

        if self._offline:
            raise NetworkBlockedError(
                f"Network access blocked while offline: cannot fetch media def {urn!r}"
            )

        defver = self._media_defver(normalized_urn)
        spec = await self._fetch_media_def_from_registry(urn, defver)
        self._save_media_def_to_cache(spec)
        with self.cache_lock:
            self.cached_specs[normalize_media_urn(spec.urn)] = spec
            self._update_extension_index(spec)
        return spec

    async def get_media_defs(self, urns: List[str]) -> List[StoredMediaDef]:
        return [await self.get_media_def(u) for u in urns]

    async def get_cached_media_defs(self) -> List[StoredMediaDef]:
        with self.cache_lock:
            return list(self.cached_specs.values())

    def get_cached_media_def(self, urn: str) -> Optional[StoredMediaDef]:
        """Synchronous in-memory cache probe; never touches the network."""
        normalized_urn = normalize_media_urn(urn)
        with self.cache_lock:
            return self.cached_specs.get(normalized_urn)

    async def media_def_exists(self, urn: str) -> bool:
        try:
            await self.get_media_def(urn)
            return True
        except (NotFoundError, HttpError, ParseError):
            return False

    def media_urns_for_extension(self, extension: str) -> List[str]:
        """Look up media URNs registered for a file extension.

        Raises ExtensionNotFoundError if no spec is registered. The
        registry hydrates lazily through `get_media_def` and through
        the atomic cap fetch — extensions only become known once the
        owning specs have landed in cache.
        """
        ext_lower = extension.lower()
        with self.cache_lock:
            urns = self.extension_index.get(ext_lower)
        if urns is None:
            raise ExtensionNotFoundError(
                f"No media def registered for extension '{extension}'. "
                f"Ensure the media def is defined in capfab/src/media/ with an 'extension' field."
            )
        return list(urns)

    def get_extension_mappings(self) -> List[tuple]:
        with self.cache_lock:
            return [(k, list(v)) for k, v in self.extension_index.items()]

    # -------------------------------------------------------------------------
    # Public alias API
    # -------------------------------------------------------------------------

    async def get_alias(self, name: str) -> StoredAlias:
        """Fetch the full StoredAlias for a name (cache-first, then network).
        The name is normalized; a malformed name is a hard ValidationError."""
        try:
            normalized = normalize_alias_name(name)
        except ValueError as e:
            raise ValidationError(f"invalid alias name: {e}")
        with self.cache_lock:
            cached = self.cached_aliases.get(normalized)
        if cached is not None:
            return cached
        if self._offline:
            raise NetworkBlockedError(
                f"Network access blocked while offline: cannot fetch alias {name!r}"
            )
        defver = self._alias_defver(normalized)
        alias = await self._fetch_alias_from_registry(normalized, defver)
        self._save_alias_to_cache(alias)
        with self.cache_lock:
            self.cached_aliases[alias.name] = alias
        return alias

    async def resolve_alias(self, name: str) -> str:
        """Resolve an alias to the cap or media URN it points at (untyped):
        returns whatever the alias targets."""
        alias = await self.get_alias(name)
        return alias.target

    async def resolve_alias_typed(self, name: str, expected: Optional[str]) -> str:
        """Resolve an alias and assert its target kind. If ``expected`` is
        ALIAS_TARGET_CAP/ALIAS_TARGET_MEDIA and the resolved target is the
        other kind, fail hard. ``None`` accepts either kind."""
        alias = await self.get_alias(name)
        actual = classify_alias_target(alias.target)
        if actual is None:
            raise ValidationError(
                f"alias '{alias.name}' target '{alias.target}' is neither a cap nor a media URN"
            )
        if expected is not None and actual != expected:
            raise ValidationError(
                f"alias '{alias.name}' resolves to a {actual} URN ('{alias.target}') "
                f"but a {expected} was required here"
            )
        return alias.target

    def resolve_alias_cached(self, name: str) -> Optional[str]:
        """Synchronous, in-memory-only alias resolution. Returns the target
        URN if the alias is already cached, else None. Returns None (not an
        error) for a malformed name so callers treat 'not a valid alias' and
        'not cached' uniformly as 'no resolution'."""
        try:
            normalized = normalize_alias_name(name)
        except ValueError:
            return None
        with self.cache_lock:
            alias = self.cached_aliases.get(normalized)
        return alias.target if alias is not None else None

    # -------------------------------------------------------------------------
    # Offline / cache control
    # -------------------------------------------------------------------------

    def set_offline(self, offline: bool) -> None:
        self._offline = offline

    def clear_cache(self) -> None:
        """Clear in-memory and on-disk caches for caps, media defs, aliases."""
        import shutil

        with self.cache_lock:
            self.cached_caps.clear()
            self.cached_specs.clear()
            self.cached_aliases.clear()
            self.extension_index.clear()

        if self.cache_dir.exists():
            try:
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                for sub in ("caps", "media", "aliases", "manifests"):
                    (self.cache_dir / sub).mkdir(parents=True, exist_ok=True)
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
        # STANDARD_CAPS travel with the manifest: their per-def version is the
        # registry's pinned manifest version (mirrors Rust).
        if self.manifest_version >= 1:
            identity.version = self.manifest_version
        normalized_urn = normalize_cap_urn(identity.urn_string())
        with self.cache_lock:
            if normalized_urn not in self.cached_caps:
                self.cached_caps[normalized_urn] = identity
            if self.manifest_version >= 1:
                self.manifest.caps[normalized_urn] = self.manifest_version

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
        # Pin at v1 with an empty manifest so test helpers flow caps/media/
        # aliases into the manifest at their declared version (mirrors Rust).
        registry = cls(cache_dir, RegistryConfig(), client, 1, Manifest.empty(1))
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
        registry = cls(cache_dir, config, client, 1, Manifest.empty(1))
        registry.ensure_identity_cap()
        return registry

    def add_caps_to_cache(self, caps: List[Cap]) -> None:
        """Insert caps directly into the in-memory cache (test helper).

        Records each cap in the manifest at its version. A cap whose version
        is 0 is stamped to the pinned manifest version (matching Rust's
        'test forgot to set it' handling)."""
        with self.cache_lock:
            for cap in caps:
                if cap.version == 0 and self.manifest_version >= 1:
                    cap.version = self.manifest_version
                normalized = normalize_cap_urn(cap.urn_string())
                self.cached_caps[normalized] = cap
                if self.manifest_version >= 1:
                    self.manifest.caps[normalized] = cap.version

    def add_spec(self, spec: StoredMediaDef) -> None:
        """Insert a media def directly into the in-memory cache (test helper).

        Updates the extension index and records the spec in the manifest.
        A spec whose version is 0 is stamped to the pinned manifest version.
        """
        with self.cache_lock:
            if spec.version == 0 and self.manifest_version >= 1:
                spec.version = self.manifest_version
            normalized = normalize_media_urn(spec.urn)
            self.cached_specs[normalized] = spec
            self._update_extension_index(spec)
            if self.manifest_version >= 1:
                self.manifest.media[normalized] = spec.version

    def insert_cached_alias_for_test(self, alias: StoredAlias) -> None:
        """Insert an alias directly into the in-memory cache and register its
        defver in the manifest, bypassing the network (test helper)."""
        with self.cache_lock:
            self.cached_aliases[alias.name] = alias
            if self.manifest_version >= 1:
                self.manifest.aliases[alias.name] = alias.version
