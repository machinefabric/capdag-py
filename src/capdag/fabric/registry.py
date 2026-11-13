"""Unified Fabric Registry — caps, media defs, aliases and dims.

Replaces the previous split between `cap.registry.FabricRegistry` (cap
definitions) and `media.registry.FabricRegistry` (media defs). Holds
one HTTP client, one disk cache folder, an in-memory dict per domain, and
the fabric's file types: which media definitions a file extension names
(:meth:`FabricRegistry.file_media_for_extension`), loaded from the whole
pinned manifest when a file's type is first asked.

On disk, under the folder of the manifest version the registry is pinned at
(``<os cache>/capdag/<charter slug>/v<N>/``), each definition is at
``<kind>/<sha256>/<defver>.json``, beside ``manifest.json``. Entries are
replaced whole and a corrupt one is an error naming its file: see
:mod:`capdag.fabric.cache`.

Atomic cap fetch: a cap is only cached after every media URN it
references has also been successfully fetched. If any referenced media
URN cannot be resolved, the cap is NOT cached, NOT persisted to disk,
and the caller sees the error.

A cap or media def is likewise cached only once every dim it names
(`dims`) is cached, at the version the manifest pins, with the value it
names. So a reader holding a cached definition can always read the
documentation of the dims it was built from (`get_cached_dim`).
"""

import asyncio
import errno
import hashlib
import json
from http import HTTPStatus
import logging
import os
import re
import shutil
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

from capdag.bifaci.charter import (
    CHARTER_FORMAT,
    Charter,
    CharterError,
    CharterFetchError,
    RegistryKind,
    fetch_charter,
    store_charter,
    stored_charter_for,
)
from capdag.cap.definition import Cap
from capdag.cap.validation import ValidationError as CapDefinitionError, validate_cap_definition
from capdag.fabric import cache
from capdag.fabric.dim import (
    DimError,
    DimRef,
    StoredDim,
    check_dim_refs,
    dim_refs_from_list,
    is_dim_name,
)
from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn


#: The anchor of MachineFabric's production fabric, used when nothing names
#: another. Only the anchor: where its objects are is read from its charter.
DEFAULT_FABRIC_ANCHOR = "https://fabric.capdag.com"
CACHE_DURATION_HOURS = 24

_log = logging.getLogger(__name__)


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
    """The registry's answer is that it does not hold the definition: the
    pinned manifest does not name it, or the registry answered 404 (or 410)
    for it. Nothing else is reported as a missing definition."""


#: Why a fetch from the registry brought back no body: the registry answered
#: with a status that is neither a success nor an answer that the object is
#: absent (404, 410).
FETCH_CAUSE_STATUS = "status"
#: The registry did not answer before the HTTP client's timeout.
FETCH_CAUSE_TIMED_OUT = "timed_out"
#: The request could not be made or its answer could not be read: the
#: connection was refused or broke off.
FETCH_CAUSE_TRANSPORT = "transport"


@dataclass(frozen=True)
class FetchCause:
    """Why a fetch from the registry brought back no body: ``kind`` is one of
    the ``FETCH_CAUSE_*`` values, with the HTTP ``status`` for a status and
    the ``detail`` of what happened on the connection for a transport
    failure."""

    kind: str
    status: Optional[int] = None
    detail: Optional[str] = None


class FetchFailedError(FabricRegistryError):
    """A fetch from the registry brought back no body: the registry refused
    it, or did not answer. The definition may well exist; what is known is
    only that this fetch failed, and the failure says what was fetched, from
    where, for which fabric manifest, and why."""

    def __init__(self, what: str, url: str, manifest_version: int, cause: FetchCause):
        self.what = what
        self.url = url
        self.manifest_version = manifest_version
        self.cause = cause
        super().__init__(self._describe())

    def _describe(self) -> str:
        what, url, version, cause = self.what, self.url, self.manifest_version, self.cause
        if cause.kind == FETCH_CAUSE_STATUS:
            try:
                reason = " " + HTTPStatus(cause.status).phrase
            except ValueError:
                reason = ""
            return (
                f"the registry refused the fetch of {what} for fabric manifest v{version}: "
                f"HTTP {cause.status}{reason} from {url}"
            )
        if cause.kind == FETCH_CAUSE_TIMED_OUT:
            return (
                f"the registry did not answer the fetch of {what} for fabric manifest "
                f"v{version}: the request to {url} timed out"
            )
        if cause.kind == FETCH_CAUSE_TRANSPORT:
            return (
                f"the fetch of {what} for fabric manifest v{version} from {url} failed: "
                f"{cause.detail}"
            )
        raise ValueError(f"unknown fetch cause kind {cause.kind!r}")


class PendingError(FabricRegistryError):
    """The pinned manifest names the definition, it is not in memory, and it
    has not been fetched: it is not at hand yet. Only a synchronous lookup,
    which never touches the network, says this."""


class ParseError(FabricRegistryError):
    """Failed to parse registry response."""


class FabricCharterError(FabricRegistryError):
    """The registry's charter could not be had, or was refused. Nothing the
    registry serves is used without it."""


class CacheError(FabricRegistryError):
    """Cache operation error."""


class ValidationError(FabricRegistryError):
    """Validation error."""


def checked_cap_definition(body: bytes, cap_urn: str) -> Cap:
    """Read a definition a registry served and hold it to the definition
    rules (RULE1-RULE22) before it is cached or returned: a definition is
    held to them by the side that receives it as well as the side that sends
    it. One that does not parse is a ParseError; one that parses and breaks a
    rule is a ValidationError naming the cap and the rule."""
    try:
        cap = Cap.from_dict(json.loads(body))
    except (ValueError, KeyError, TypeError) as e:
        raise ParseError(f"Failed to parse registry response for cap '{cap_urn}': {e}")
    try:
        validate_cap_definition(cap)
    except CapDefinitionError as e:
        raise ValidationError(
            f"the registry's definition of cap '{cap_urn}' breaks a definition rule: {e}"
        )
    return cap


class FileTypesError(FabricRegistryError):
    """The fabric's file media types could not be told: a manifest entry
    that is no media URN, or file media definitions that could not all be
    loaded. The message names each."""


# =============================================================================
# URN normalization
# =============================================================================


def normalize_cap_urn(urn: str) -> str:
    """Normalize a Cap URN to its canonical string form.

    A URN that fails to parse is malformed; this raises ``ParseError``
    rather than passing the raw string through. Swallowing the parse
    error here lets the lookup proceed and the failure resurfaces
    downstream as a misleading "not part of manifest" instead of the
    truth ("malformed cap URN: <parse error>"). The error is a normal,
    catchable ``FabricRegistryError`` — callers handle it gracefully
    (propagate on resolution paths, log + degrade on cache lookups and
    hydration); it must never escape uncaught and crash the app.
    """
    try:
        return CapUrn.from_string(urn).to_string()
    except Exception as e:
        raise ParseError(f"malformed cap URN '{urn}': {e}")


def normalize_media_urn(urn: str) -> str:
    """Normalize a Media URN to its canonical string form.

    A URN that fails to parse is malformed; this raises ``ParseError``
    rather than passing the raw string through (see
    :func:`normalize_cap_urn` for the rationale). The error is a normal,
    catchable ``FabricRegistryError`` that callers handle gracefully; it
    must never escape uncaught and crash the app.
    """
    try:
        return MediaUrn.from_string(urn).to_string()
    except Exception as e:
        raise ParseError(f"malformed media URN '{urn}': {e}")


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
        dims: Optional[List[DimRef]] = None,
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
        # The dims this media def was built from (see ``MediaDef.dims``).
        self.dims: List[DimRef] = list(dims or [])

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
        if self.dims:
            result["dims"] = [r.to_dict() for r in self.dims]
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
            dims=dim_refs_from_list(data.get("dims", []), f"media def '{data['urn']}'"),
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


def select_display_alias(names: Iterable[str]) -> Optional[str]:
    """Pick the display alias from a set of alias names that all target the
    same URN: the SHORTEST name, ties broken alphabetically. Returns ``None``
    for an empty set.

    The ordering is total and deterministic: ``(len, name)`` lexicographic. So
    ``png`` beats ``png-image`` (shorter), and between equal-length ``a16`` /
    ``a09`` the alphabetical-smaller ``a09`` wins. Stable across processes for a
    given alias set, which is what makes aliased UI/notation reproducible.
    """
    best: Optional[str] = None
    for name in names:
        if best is None or (len(name), name) < (len(best), best):
            best = name
    return best


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
# Dims
# =============================================================================


class DimCacheEntry:
    """On-disk cache entry for a dim."""

    def __init__(self, dim: StoredDim, cached_at: int, ttl_hours: int):
        self.dim = dim
        self.cached_at = cached_at
        self.ttl_hours = ttl_hours

    def to_dict(self) -> Dict:
        return {
            "dim": self.dim.to_dict(),
            "cached_at": self.cached_at,
            "ttl_hours": self.ttl_hours,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DimCacheEntry":
        return cls(
            dim=StoredDim.from_dict(data["dim"]),
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
    object; manifests at version >= 1 name every cap URN, media URN, alias
    name and dim name in the snapshot paired with its per-definition
    version.

    ``dims`` maps a dim name to its per-definition version; the body (the
    dim's title, documentation and values) lives at
    ``dims/<sha256-of-name>/<defver>.json``. Every dim a cap or media def of
    the snapshot names is there. Required on the wire: a manifest without it
    is not one this library reads."""

    version: int
    previous: int
    caps: Dict[str, int] = field(default_factory=dict)
    media: Dict[str, int] = field(default_factory=dict)
    aliases: Dict[str, int] = field(default_factory=dict)
    dims: Dict[str, int] = field(default_factory=dict)

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
            "dims": dict(self.dims),
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Manifest":
        if "dims" not in data:
            raise ValueError(
                f"manifest v{data.get('version')} is missing field `dims`: every manifest "
                f"this library reads names the dims of its snapshot"
            )
        dims = data["dims"]
        if not isinstance(dims, dict):
            raise ValueError(f"manifest field `dims` is not an object: {dims!r}")
        return cls(
            version=data["version"],
            previous=data["previous"],
            caps=dict(data.get("caps", {})),
            media=dict(data.get("media", {})),
            aliases=dict(data.get("aliases", {})),
            dims=dict(dims),
        )


# =============================================================================
# Configuration
# =============================================================================


class RegistryConfig:
    """What a fabric registry client is asked to use.

    The ANCHOR names the registry and is all a client is told; where its
    manifest and definitions are, and the folder its cache lives in, come from
    the registry's charter (:class:`FabricLocations`). Sources, in priority
    order: the constructor argument or :meth:`with_anchor`, then
    ``CDG_FABRIC_REGISTRY_URL``, then MachineFabric's production fabric.
    """

    def __init__(self, anchor: Optional[str] = None):
        if anchor is None:
            anchor = os.getenv("CDG_FABRIC_REGISTRY_URL") or DEFAULT_FABRIC_ANCHOR
        self.anchor = anchor

    def with_anchor(self, anchor: str) -> "RegistryConfig":
        self.anchor = anchor
        return self


class FabricLocations:
    """Where a fabric registry's objects are, as its charter states them.

    Built once from a charter whose shape check guarantees each template uses
    exactly the placeholders filled here — so filling one cannot fail, and
    nothing in the client composes a fabric URL any other way."""

    def __init__(self, manifest: str, definition: str):
        self._manifest = manifest
        self._definition = definition

    @classmethod
    def from_charter(cls, charter: Charter) -> "FabricLocations":
        if charter.kind is not RegistryKind.FABRIC:
            raise FabricCharterError(
                f"{charter.anchor} is chartered as a {charter.kind.value} registry, not a fabric"
            )
        for name in ("manifest", "definition"):
            if name not in charter.locations:
                raise FabricCharterError(
                    f"the fabric charter of {charter.anchor} declares no '{name}' location"
                )
        return cls(charter.locations["manifest"], charter.locations["definition"])

    def manifest(self, version: int) -> str:
        """The URL of manifest ``version``."""
        return self._manifest.replace("{manifest_version}", str(version))

    def definition(self, kind: str, urn_hash: str, version: int) -> str:
        """The URL of one definition: ``kind`` is caps, media, aliases or dims."""
        return (
            self._definition.replace("{kind}", kind)
            .replace("{urn_hash}", urn_hash)
            .replace("{version}", str(version))
        )


def publisher_layout_charter(anchor: str) -> Charter:
    """The charter of a fabric published at ``anchor`` the way the publisher
    lays a fabric out (``fabric/src/fabric.js``). For a registry that is never
    fetched: the test constructors, and tests of where things are."""
    return Charter(
        format=CHARTER_FORMAT,
        anchor=anchor,
        kind=RegistryKind.FABRIC,
        slug="test-fabric",
        environment="prod",
        locations={
            "manifest": f"{anchor}/manifest/{{manifest_version}}.json",
            "latest": f"{anchor}/manifest/latest.json",
            "definition": f"{anchor}/{{kind}}/{{urn_hash}}/{{version}}.json",
        },
        issued_at=0,
        not_after=None,
    )


def _definition_url_and_cache_path(
    cache_dir: Path, locations: FabricLocations, kind: str, key: str, defver: int
) -> Tuple[str, Path]:
    """The URL of one definition at ``defver``, from the charter's
    ``definition`` location, and the cache file it is kept in. Used by both
    the fetch path and the on-disk cache-path resolver so the two never drift
    apart. ``key`` is what the kind hashes: the normalized URN for caps and
    media, the name for aliases and dims."""
    return (
        locations.definition(kind, cache.key_hash(key), defver),
        cache.entry_path(cache_dir, kind, key, defver),
    )


async def _resolve_charter(
    client: Optional["httpx.AsyncClient"], capdag_cache: Path, anchor: str
) -> Charter:
    """The charter of the fabric registry at ``anchor``.

    A fabric's contents carry no signature, so no content environment is
    expected of its charter: any chartered fabric can be resolved against,
    and what keeps one client's registries on one fabric is each cartridge
    registry's charter naming it.

    The stored one, when a folder under ``capdag_cache`` holds a charter for
    this anchor — so an offline client keeps its fabric. Else the charter is
    fetched from the anchor and stored in the folder its slug names. Mirrors
    Rust ``resolve_charter`` (which also verifies the signature; see
    ``bifaci/charter.py``)."""
    found = stored_charter_for(capdag_cache, anchor, RegistryKind.FABRIC)
    if found is not None:
        return found[1]
    if client is None:
        raise HttpError("httpx not available - cannot fetch the fabric charter")
    try:
        fetched = await fetch_charter(client, anchor, RegistryKind.FABRIC)
    except CharterFetchError as e:
        raise FabricCharterError(
            f"the fabric registry {anchor} has no charter this client can use: {e}"
        ) from e
    folder = capdag_cache / fetched.charter.slug
    try:
        store_charter(fetched, folder)
    except (OSError, CharterError) as e:
        raise CacheError(f"Failed to store the charter of {anchor} in {folder}: {e}") from e
    return fetched.charter


def checked_dim(body: bytes, name: str, defver: int) -> StoredDim:
    """A dim body as a registry served it, for the dim ``name`` at
    ``defver``: parsed (unknown fields refused), named and versioned as
    requested, and holding (:meth:`StoredDim.validate`). A body that does not
    parse, or names another dim or version, is a ParseError; one that does
    not hold is a ValidationError."""
    try:
        dim = StoredDim.from_dict(json.loads(body))
    except (ValueError, KeyError, TypeError) as e:
        raise ParseError(f"Failed to parse dim '{name}': {e}")
    if dim.name != name:
        raise ParseError(
            f"dim object name '{dim.name}' does not match requested name '{name}'"
        )
    if dim.version != defver:
        raise ParseError(
            f"dim '{dim.name}' object reports version {dim.version} but manifest pins defver {defver}"
        )
    try:
        dim.validate()
    except DimError as e:
        raise ValidationError(str(e))
    return dim


def _dims_resolve_in(dims: List[DimRef], cached: Dict[str, StoredDim]) -> bool:
    """Whether every dim ``dims`` names is in ``cached`` with the value it
    names."""
    for r in dims:
        dim = cached.get(r.dim)
        if dim is None or dim.value(r.value) is None:
            return False
    return True


def _retain_pinned(
    manifest: "Manifest",
    manifest_version: int,
    caps: Dict[str, Cap],
    specs: Dict[str, StoredMediaDef],
    aliases: Dict[str, StoredAlias],
    dims: Dict[str, StoredDim],
) -> None:
    """Keep, of what was loaded from the disk cache, only what the pinned
    manifest names at the version it names, and only definitions whose dims
    all survive with them. At v0 the manifest is empty and caps and media are
    all retained; aliases and dims are versioned-regime concepts and are all
    dropped.

    A definition whose dims did not survive is dropped here and fetched
    again, with its dims, when it is next asked for — so a cached definition
    always has its dims cached. The dicts are filtered in place."""

    def keep_only(d: Dict[str, Any], keep) -> None:
        for key in [k for k, v in d.items() if not keep(k, v)]:
            del d[key]

    if manifest_version >= 1:
        keep_only(caps, lambda urn, cap: manifest.caps.get(urn, 0) == cap.version)
        keep_only(specs, lambda urn, spec: manifest.media.get(urn, 0) == spec.version)
        keep_only(aliases, lambda name, alias: manifest.aliases.get(name, 0) == alias.version)
        keep_only(dims, lambda name, dim: manifest.dims.get(name, 0) == dim.version)
    else:
        aliases.clear()
        dims.clear()
    keep_only(caps, lambda _urn, cap: _dims_resolve_in(cap.dims, dims))
    keep_only(specs, lambda _urn, spec: _dims_resolve_in(spec.dims, dims))


def _validate_fetched_alias(alias: "StoredAlias", expected_name: str, expected_defver: int) -> None:
    """An alias body is the alias ``expected_name`` at ``expected_defver``,
    and its target is a cap or media URN. A body that names another alias or
    version is a ParseError; a target that is neither kind of URN is a
    ValidationError."""
    if alias.name != expected_name:
        raise ParseError(
            f"alias object name '{alias.name}' does not match requested name "
            f"'{expected_name}'"
        )
    if alias.version != expected_defver:
        raise ParseError(
            f"alias '{alias.name}' object reports version {alias.version} "
            f"but manifest pins defver {expected_defver}"
        )
    if classify_alias_target(alias.target) is None:
        raise ValidationError(
            f"alias '{alias.name}' target '{alias.target}' is neither a cap nor a media URN"
        )


# =============================================================================
# Disk cache: clearing
# =============================================================================


def clear_cache_folder(version_folder: Path) -> None:
    """Empty the cache folder of one manifest version, ``version_folder``, and
    remove the folders the layout before per-version folders kept beside it.

    The cache is SHARED, and the processes that clear it run at the same time:
    a test run starts many cartridge builds within milliseconds of each other
    and every one of them refreshes this folder. Removing the tree and putting
    it back is not safe between peers — one process deleting an ancestor while
    another is creating into it is how a build fails with ``No such file or
    directory`` on a path it had just made.

    So a kind's folder is never removed, only its contents, and every step
    tolerates a peer having done the same thing first. The end state is the
    same — an empty cache — and no peer is ever left with the tree missing
    underneath it. The manifest, and any temporary file a killed writer left,
    are removed from the version's folder; other versions' folders and the
    stored charter are left as they are."""
    for kind in cache.KIND_FOLDERS:
        directory = version_folder / kind
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise CacheError(f"Failed to create cache directory {directory}: {e}") from e
        _remove_contents(directory)
    # What is left at the top of the version's folder: the manifest, and
    # temporary files. The kinds' folders themselves stay.
    try:
        top = list(version_folder.iterdir())
    except FileNotFoundError:
        return
    except OSError as e:
        raise CacheError(f"Failed to read cache directory {version_folder}: {e}") from e
    for path in top:
        if not path.is_dir():
            _remove_shared(path)
    registry_folder = version_folder.parent
    for legacy in cache.LEGACY_FOLDERS:
        path = registry_folder / legacy
        if path.is_dir():
            _remove_shared(path)


def _remove_contents(directory: Path) -> None:
    """Remove everything in ``directory``, which peers are clearing and
    filling at the same time (:func:`_remove_shared`)."""
    try:
        entries = list(directory.iterdir())
    # A peer removed it between the create and the read. It is empty by any
    # reading, which is what was wanted.
    except FileNotFoundError:
        return
    except OSError as e:
        raise CacheError(f"Failed to read cache directory {directory}: {e}") from e
    for entry in entries:
        _remove_shared(entry)


def _remove_shared(path: Path) -> None:
    """Remove one file or folder of the shared cache, which a peer may be
    removing or refilling at the same moment."""
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
    # Already gone: a peer clearing the same cache got there first, which is
    # the outcome either way.
    except FileNotFoundError:
        pass
    except OSError as e:
        # Refilled underneath us, or deleted by a peer at this moment: neither
        # is a failure of this clear. The entries now there were put there by
        # a peer that has just refreshed them, so they are exactly what a
        # refresh was for.
        if _is_busy(e) or _deleted_by_a_peer(path, e):
            return
        raise CacheError(f"Failed to remove {path}: {e}") from e


def _is_busy(error: OSError) -> bool:
    """Whether an error means "somebody else is using this right now".

    One process removing a directory another is writing into is answered
    differently by each platform — ``ENOTEMPTY`` or ``EBUSY`` on Unix,
    ``ERROR_DIR_NOT_EMPTY`` (145) or ``ERROR_SHARING_VIOLATION`` (32) on
    Windows — and none says the clear failed."""
    if error.errno in (errno.ENOTEMPTY, errno.EBUSY):
        return True
    return getattr(error, "winerror", None) in (145, 32)


def _deleted_by_a_peer(path: Path, error: OSError) -> bool:
    """Whether a removal refused with "access denied" was a PEER deleting the
    same entry.

    Windows answers every open of a file that is being deleted — a second
    delete included — with access denied until the deleting process's last
    handle closes; Unix reports the same race as "not found". Access denied
    is also what a genuine permission problem says, so the entry is asked for
    afterwards: gone within a short bound means a peer took it, still there
    means it really cannot be removed and that is reported."""
    if sys.platform != "win32" or not isinstance(error, PermissionError):
        return False
    for _ in range(50):
        if not os.path.lexists(path):
            return True
        time.sleep(0.01)
    return False


# =============================================================================
# Disk cache: loading
# =============================================================================


@dataclass
class PinnedEntries:
    """The definitions a manifest version's cache folder holds at the versions
    its manifest pins, keyed as the registry keys them in memory."""

    caps: Dict[str, Cap] = field(default_factory=dict)
    media: Dict[str, "StoredMediaDef"] = field(default_factory=dict)
    aliases: Dict[str, "StoredAlias"] = field(default_factory=dict)
    dims: Dict[str, StoredDim] = field(default_factory=dict)


def _identity_mismatch(found: str, found_defver: int, key: str, defver: int) -> str:
    return (
        f"it holds '{found}' at defver {found_defver}, "
        f"where '{key}' at defver {defver} belongs"
    )


def load_pinned_entries(cache_dir: Path, manifest: "Manifest") -> PinnedEntries:
    """Read, from the cache folder ``cache_dir`` of manifest ``manifest``,
    every definition the manifest pins that is cached: each from the one file
    its key and pinned defver name, so nothing at another defver, and nothing
    another manifest version cached, is ever read.

    An entry that is not there is not cached. One that is there and cannot be
    read, does not parse, or is not the definition and defver its path names
    is corrupt, and a CacheError naming the file. Two rules drop an entry and
    leave it to be fetched anew, naming its file in the log:

    - a defver-0 cap or media def older than its time to live (defver 0 is
      the flat, mutable regime);
    - a cap or dim that breaks the definition rules was written by a capdag
      with other rules (``capdag/docs/10-validation-rules.md``)."""
    entries = PinnedEntries()
    for urn, defver in manifest.caps.items():
        path = cache.entry_path(cache_dir, "caps", urn, defver)
        cap_entry = cache.read_entry(path, "cap", CacheEntry.from_dict)
        if cap_entry is None:
            continue
        try:
            cached_urn = normalize_cap_urn(cap_entry.definition.urn_string())
        except ParseError as e:
            raise cache.corrupt(path, "cap", str(e)) from e
        if cached_urn != urn or cap_entry.definition.version != defver:
            raise cache.corrupt(
                path,
                "cap",
                _identity_mismatch(cached_urn, cap_entry.definition.version, urn, defver),
            )
        if defver == 0 and cap_entry.is_expired():
            _log.info("the cached cap %s is past its time to live", path)
            continue
        try:
            validate_cap_definition(cap_entry.definition)
        except CapDefinitionError as e:
            _log.warning("dropping the cached cap %s: %s", path, e)
            path.unlink(missing_ok=True)
            continue
        entries.caps[cached_urn] = cap_entry.definition
    for urn, defver in manifest.media.items():
        path = cache.entry_path(cache_dir, "media", urn, defver)
        media_entry = cache.read_entry(path, "media def", MediaCacheEntry.from_dict)
        if media_entry is None:
            continue
        try:
            cached_urn = normalize_media_urn(media_entry.spec.urn)
        except ParseError as e:
            raise cache.corrupt(path, "media def", str(e)) from e
        if cached_urn != urn or media_entry.spec.version != defver:
            raise cache.corrupt(
                path,
                "media def",
                _identity_mismatch(cached_urn, media_entry.spec.version, urn, defver),
            )
        if defver == 0 and media_entry.is_expired():
            _log.info("the cached media def %s is past its time to live", path)
            continue
        entries.media[cached_urn] = media_entry.spec
    for name, defver in manifest.aliases.items():
        path = cache.entry_path(cache_dir, "aliases", name, defver)
        alias_entry = cache.read_entry(path, "alias", AliasCacheEntry.from_dict)
        if alias_entry is None:
            continue
        try:
            _validate_fetched_alias(alias_entry.alias, name, defver)
        except FabricRegistryError as e:
            raise cache.corrupt(path, "alias", str(e)) from e
        entries.aliases[alias_entry.alias.name] = alias_entry.alias
    for name, defver in manifest.dims.items():
        path = cache.entry_path(cache_dir, "dims", name, defver)
        dim_entry = cache.read_entry(path, "dim", DimCacheEntry.from_dict)
        if dim_entry is None:
            continue
        if dim_entry.dim.name != name or dim_entry.dim.version != defver:
            raise cache.corrupt(
                path,
                "dim",
                _identity_mismatch(dim_entry.dim.name, dim_entry.dim.version, name, defver),
            )
        try:
            dim_entry.dim.validate()
        except DimError as e:
            _log.warning("dropping the cached dim %s: %s", path, e)
            path.unlink(missing_ok=True)
            continue
        entries.dims[dim_entry.dim.name] = dim_entry.dim
    return entries


# =============================================================================
# File types
# =============================================================================


#: How many file media definitions are fetched at once when the file media
#: index loads on a cold cache.
FILE_MEDIA_FETCHES_AT_ONCE = 16


def derive_file_types(manifest: Manifest) -> List[Tuple[str, int]]:
    """The media definitions of ``manifest`` that are file types: those whose
    URN carries the ``ext=`` file-type tag, each with its pinned defver, in
    URN order. A manifest entry that is no media URN is a FileTypesError
    naming the manifest version and the entry."""
    file_types: List[Tuple[str, int]] = []
    for urn, defver in manifest.media.items():
        try:
            parsed = MediaUrn.from_string(urn)
        except Exception as e:
            raise FileTypesError(
                f"manifest v{manifest.version} names '{urn}' as a media definition, "
                f"and it is no media URN: {e}"
            ) from e
        if parsed.get_tag("ext") is not None:
            file_types.append((urn, defver))
    file_types.sort()
    return file_types


@dataclass(frozen=True)
class KeptFileTypes:
    """The file types a manifest names, as they are kept beside it
    (:data:`cache.FILE_TYPES_FILE`): worked out from the manifest file whose
    bytes hash to ``manifest_sha256``. On disk ``file_types`` is a list of
    ``[URN, defver]`` pairs."""

    manifest_sha256: str
    file_types: List[Tuple[str, int]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "manifest_sha256": self.manifest_sha256,
            "file_types": [[urn, defver] for urn, defver in self.file_types],
        }

    @classmethod
    def from_dict(cls, data: Any) -> "KeptFileTypes":
        if not isinstance(data, dict):
            raise ValueError(f"kept file types are not an object: {data!r}")
        manifest_sha256 = data["manifest_sha256"]
        if not isinstance(manifest_sha256, str):
            raise ValueError(f"field `manifest_sha256` is not a string: {manifest_sha256!r}")
        pairs = data["file_types"]
        if not isinstance(pairs, list):
            raise ValueError(f"field `file_types` is not an array: {pairs!r}")
        file_types: List[Tuple[str, int]] = []
        for pair in pairs:
            if (
                not isinstance(pair, list)
                or len(pair) != 2
                or not isinstance(pair[0], str)
                or not isinstance(pair[1], int)
                or isinstance(pair[1], bool)
                or pair[1] < 0
            ):
                raise ValueError(f"field `file_types` holds {pair!r}, which is no [URN, defver] pair")
            file_types.append((pair[0], pair[1]))
        return cls(manifest_sha256=manifest_sha256, file_types=file_types)


def file_types_of(
    cache_dir: Path, manifest_file: Optional[Path], manifest: Manifest
) -> List[Tuple[str, int]]:
    """The file types of ``manifest``, in the cache folder ``cache_dir`` of
    its version. ``manifest_file`` is the cached manifest file ``manifest``
    was read from, ``None`` for a manifest made in memory.

    Working them out parses every media URN the manifest names (32,890 in
    manifest 13), which a command that reads a file would otherwise pay on
    every run. So they are kept beside the manifest file, with the hash of
    its bytes, and read back while that file is unchanged; a manifest fetched
    again has other bytes and its file types are worked out afresh. Kept file
    types that cannot be read are a CacheError naming their file. A manifest
    with no file keeps nothing."""
    if manifest_file is None:
        return derive_file_types(manifest)
    try:
        data = manifest_file.read_bytes()
    except OSError as e:
        raise CacheError(f"the cached manifest {manifest_file} cannot be read: {e}") from e
    manifest_sha256 = hashlib.sha256(data).hexdigest()
    kept_file = cache_dir / cache.FILE_TYPES_FILE
    kept = cache.read_entry(kept_file, "file types", KeptFileTypes.from_dict)
    if kept is not None and kept.manifest_sha256 == manifest_sha256:
        return list(kept.file_types)
    file_types = derive_file_types(manifest)
    cache.store_entry(
        kept_file,
        KeptFileTypes(manifest_sha256=manifest_sha256, file_types=file_types).to_dict(),
        "file types",
    )
    return file_types


# =============================================================================
# Unified registry
# =============================================================================


async def _fetch_object(
    client: Optional["httpx.AsyncClient"], url: str, what: str, manifest_version: int
) -> bytes:
    """The body of one registry object — ``what`` at ``url``, fetched for
    fabric manifest ``manifest_version``.

    A success is the body. 404 or 410 is the registry's answer that it does
    not hold the object, and only that is a NotFoundError. Any other status,
    and a fetch that got no answer, is a FetchFailedError saying the URL, the
    status or what happened on the connection, and the manifest version: a
    refused fetch is never reported as a missing definition."""
    if not HTTPX_AVAILABLE or client is None:
        raise HttpError(f"httpx not available - cannot fetch {what}")
    try:
        response = await client.get(url)
        body = response.content
    except httpx.TimeoutException:
        raise FetchFailedError(what, url, manifest_version, FetchCause(FETCH_CAUSE_TIMED_OUT))
    except httpx.HTTPError as e:
        detail = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
        raise FetchFailedError(
            what, url, manifest_version, FetchCause(FETCH_CAUSE_TRANSPORT, detail=detail)
        )
    if response.is_success:
        return body
    if response.status_code in (404, 410):
        raise NotFoundError(
            f"the registry has no {what} for fabric manifest v{manifest_version} "
            f"(HTTP {response.status_code} from {url})"
        )
    raise FetchFailedError(
        what, url, manifest_version, FetchCause(FETCH_CAUSE_STATUS, status=response.status_code)
    )


class FabricRegistry:
    """Unified registry for cap definitions and media defs.

    Holds an in-memory cache per domain, and the index of the fabric's file
    types by extension once a file's type has been asked
    (:meth:`file_media_for_extension`). On disk it keeps the cache folder of
    the manifest version it is pinned at (:mod:`capdag.fabric.cache`).

    Atomic cap fetch: `get_cap` only caches a cap after every media
    URN it references has also been successfully fetched. If any
    referenced media URN cannot be resolved, the cap is NOT cached,
    NOT persisted to disk, and the error propagates to the caller.
    """

    def __init__(
        self,
        cache_dir: Path,
        config: RegistryConfig,
        charter: Charter,
        client: Optional["httpx.AsyncClient"] = None,
        manifest_version: int = 1,
        manifest: Optional[Manifest] = None,
        manifest_file: Optional[Path] = None,
    ):
        if not HTTPX_AVAILABLE and client is None:
            raise ImportError(
                "httpx is required for registry operations. Install with: pip install httpx"
            )

        #: The cache folder of the manifest version this registry is pinned
        #: at, ``<os cache>/capdag/<charter slug>/v<N>``. Definitions live at
        #: ``<kind>/<sha>/<defver>.json`` and the manifest at
        #: ``manifest.json`` (:mod:`capdag.fabric.cache`).
        self.cache_dir = cache_dir
        self.config = config
        #: The registry's charter: its slug names the registry's folder, and
        #: its locations are where every object is fetched from.
        self.charter = charter
        self.locations = FabricLocations.from_charter(charter)
        self.client = client

        self.cached_caps: Dict[str, Cap] = {}
        self.cached_specs: Dict[str, StoredMediaDef] = {}
        self.cached_aliases: Dict[str, StoredAlias] = {}
        # Dim name -> StoredDim, filtered to the pinned manifest's defvers.
        self.cached_dims: Dict[str, StoredDim] = {}
        #: Lower-case extension -> the file media definitions that list it,
        #: in URN order; loaded from the whole manifest when a file's type
        #: is first asked (:meth:`file_media_for_extension`).
        self._file_media: Optional[Dict[str, List[StoredMediaDef]]] = None
        #: Held while the file media index loads, so it loads once.
        self._file_media_loading = asyncio.Lock()

        # Manifest pin, >= 1: every URN lookup resolves to a (urn, defver)
        # pair via the manifest before fetching.
        self.manifest_version = manifest_version
        self.manifest = manifest if manifest is not None else Manifest.empty(manifest_version)
        #: The cached manifest file ``manifest`` was read from: the file
        #: types it names are kept beside it (:func:`file_types_of`). ``None``
        #: for a manifest made in memory, and once a test helper has changed
        #: ``manifest``'s media.
        self.manifest_file = manifest_file

        self.cache_lock = threading.Lock()
        self._offline = False
        #: What the last failed fetch of each definition came to, keyed by
        #: (kind, name, defver), until a fetch of it succeeds. A synchronous
        #: lookup says this rather than "not fetched yet" when the registry
        #: already answered.
        self._fetch_failures: Dict[Tuple[str, str, int], FabricRegistryError] = {}

    # -------------------------------------------------------------------------
    # Constructors
    # -------------------------------------------------------------------------

    @staticmethod
    def _baked_manifest_version() -> int:
        """The workspace-pinned fabric manifest version. Mirrors Rust's
        compile-time-baked ``capdag::FABRIC_MANIFEST_VERSION``; in Python it
        is read from ``MFR_FABRIC_MANIFEST_VERSION`` (the same env var the
        build exports). Its absence is a hard failure: there is no version
        to fall back to."""
        raw = os.getenv("MFR_FABRIC_MANIFEST_VERSION")
        if raw is None or raw == "":
            raise ValidationError(
                "the fabric manifest version is not set. A workspace build reads "
                "MFR_FABRIC_MANIFEST_VERSION, which the workspace build tool exports "
                "from fabric/manifest-version.txt"
            )
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

        The registry's charter is resolved first — the one stored in the cache
        when one is stored for this anchor, else fetched from the anchor — and
        everything after it is read from the charter: the registry's folder is
        its slug, the cache is that folder's ``v<manifest_version>``, and the
        manifest is fetched from its location. The constructor
        blocks on the network when either is not cached. A version below 1
        names no manifest and is refused.
        """
        if manifest_version < 1:
            raise ValidationError(
                f"fabric manifest version {manifest_version} names no manifest; "
                "a registry is pinned at 1 or later"
            )
        client = httpx.AsyncClient(timeout=10.0) if HTTPX_AVAILABLE else None
        capdag_cache = cls._capdag_cache_root()
        charter = await _resolve_charter(client, capdag_cache, config.anchor)
        locations = FabricLocations.from_charter(charter)
        cache_dir = cache.version_dir(capdag_cache / charter.slug, manifest_version)
        for kind in cache.KIND_FOLDERS:
            directory = cache_dir / kind
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                raise CacheError(f"Failed to create cache directory {directory}: {e}") from e

        manifest = await cls._load_or_fetch_manifest(
            cache_dir, client, locations, manifest_version
        )

        registry = cls(
            cache_dir,
            config,
            charter,
            client,
            manifest_version,
            manifest,
            manifest_file=cache_dir / cache.MANIFEST_FILE,
        )
        # Only what the manifest pins is read; keep, of that, only definitions
        # whose dims survive with them.
        pinned = load_pinned_entries(cache_dir, manifest)
        with registry.cache_lock:
            registry.cached_caps = pinned.caps
            registry.cached_specs = pinned.media
            registry.cached_aliases = pinned.aliases
            registry.cached_dims = pinned.dims
            _retain_pinned(
                manifest,
                manifest_version,
                registry.cached_caps,
                registry.cached_specs,
                registry.cached_aliases,
                registry.cached_dims,
            )
        registry.ensure_identity_cap()
        return registry

    @staticmethod
    async def _load_or_fetch_manifest(
        cache_dir: Path,
        client: Optional["httpx.AsyncClient"],
        locations: FabricLocations,
        version: int,
    ) -> Manifest:
        """Manifest bootstrap, in the cache folder ``cache_dir`` of manifest
        ``version``. Tries the cached manifest first; falls back to a network
        GET. A cached manifest that does not parse, or is another version's,
        is corrupt: a CacheError naming its file, never refetched over."""
        cache_file = cache_dir / cache.MANIFEST_FILE
        m = cache.read_entry(cache_file, "manifest", Manifest.from_dict)
        if m is not None:
            if m.version != version:
                raise cache.corrupt(
                    cache_file,
                    "manifest",
                    f"it is manifest {m.version}, in the folder of manifest {version}",
                )
            return m

        url = locations.manifest(version)
        body = (await _fetch_object(client, url, f"manifest v{version}", version)).decode("utf-8")
        try:
            manifest = Manifest.from_dict(json.loads(body))
        except (ValueError, KeyError) as e:
            raise ParseError(f"Failed to parse manifest v{version}: {e}")
        if manifest.version != version:
            raise ParseError(
                f"Manifest fetched as v{version} reports version {manifest.version}"
            )
        cache.write_atomically(cache_file, body.encode("utf-8"))
        return manifest

    @staticmethod
    def _capdag_cache_root() -> Path:
        """The directory every registry's cache folder lives under:
        ``<os-cache>/capdag``. A registry's own folder is its charter's slug,
        so two registries never share one, whatever their URLs look like — a
        cache populated from one fabric can never satisfy lookups against
        another, which serves DIFFERENT bytes for the same URN and version."""
        if os.name == "nt":
            cache_base = Path(os.getenv("LOCALAPPDATA", os.path.expanduser("~/.cache")))
        elif os.name == "posix":
            cache_base = Path(os.getenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache")))
        else:
            cache_base = Path.home() / ".cache"
        return cache_base / "capdag"

    # -------------------------------------------------------------------------
    # Disk-cache writers
    # -------------------------------------------------------------------------

    def _cap_cache_file_path(self, urn: str, defver: int) -> Path:
        _, cache_file = _definition_url_and_cache_path(
            self.cache_dir, self.locations, "caps", normalize_cap_urn(urn), defver
        )
        return cache_file

    def _media_cache_file_path(self, urn: str, defver: int) -> Path:
        _, cache_file = _definition_url_and_cache_path(
            self.cache_dir, self.locations, "media", normalize_media_urn(urn), defver
        )
        return cache_file

    def _alias_cache_file_path(self, normalized_name: str, defver: int) -> Path:
        _, cache_file = _definition_url_and_cache_path(
            self.cache_dir, self.locations, "aliases", normalized_name, defver
        )
        return cache_file

    def _save_cap_to_cache(self, cap: Cap) -> None:
        cache_file = self._cap_cache_file_path(cap.urn_string(), cap.version)
        entry = CacheEntry(definition=cap, cached_at=int(time.time()), ttl_hours=CACHE_DURATION_HOURS)
        cache.store_entry(cache_file, entry.to_dict(), "cap")

    def _save_media_def_to_cache(self, spec: StoredMediaDef) -> None:
        cache_file = self._media_cache_file_path(spec.urn, spec.version)
        entry = MediaCacheEntry(spec=spec, cached_at=int(time.time()), ttl_hours=CACHE_DURATION_HOURS)
        cache.store_entry(cache_file, entry.to_dict(), "media def")

    def _save_alias_to_cache(self, alias: StoredAlias) -> None:
        cache_file = self._alias_cache_file_path(alias.name, alias.version)
        entry = AliasCacheEntry(alias=alias, cached_at=int(time.time()), ttl_hours=CACHE_DURATION_HOURS)
        cache.store_entry(cache_file, entry.to_dict(), "alias")

    def _save_dim_to_cache(self, dim: StoredDim) -> None:
        _, cache_file = _definition_url_and_cache_path(
            self.cache_dir, self.locations, "dims", dim.name, dim.version
        )
        entry = DimCacheEntry(dim=dim, cached_at=int(time.time()), ttl_hours=CACHE_DURATION_HOURS)
        cache.store_entry(cache_file, entry.to_dict(), "dim")

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

        url, _ = _definition_url_and_cache_path(
            self.cache_dir, self.locations, "caps", normalized_urn, defver
        )
        body = await _fetch_object(
            self.client, url, f"cap '{normalized_urn}' (defver {defver})", self.manifest_version
        )
        return checked_cap_definition(body, normalized_urn)

    async def _fetch_media_def_from_registry(self, urn: str, defver: int) -> StoredMediaDef:
        if not HTTPX_AVAILABLE or self.client is None:
            raise HttpError("httpx not available - cannot fetch from registry")

        normalized_urn = normalize_media_urn(urn)
        try:
            MediaUrn.from_string(normalized_urn)
        except Exception as e:
            raise FabricRegistryError(f"Invalid media URN '{normalized_urn}': {e}")

        url, _ = _definition_url_and_cache_path(
            self.cache_dir, self.locations, "media", normalized_urn, defver
        )
        body = await _fetch_object(
            self.client, url, f"media def '{normalized_urn}' (defver {defver})", self.manifest_version
        )
        try:
            return StoredMediaDef.from_dict(json.loads(body))
        except (ValueError, KeyError, TypeError) as e:
            raise ParseError(f"Failed to parse registry response for media '{urn}': {e}")

    async def _fetch_alias_from_registry(self, normalized_name: str, defver: int) -> StoredAlias:
        if not HTTPX_AVAILABLE or self.client is None:
            raise HttpError("httpx not available - cannot fetch from registry")
        if defver < 1:
            raise NotFoundError(
                f"alias '{normalized_name}' has non-positive defver {defver}; "
                f"aliases are versioned-only"
            )
        url, _ = _definition_url_and_cache_path(
            self.cache_dir, self.locations, "aliases", normalized_name, defver
        )
        body = await _fetch_object(
            self.client, url, f"alias '{normalized_name}' (defver {defver})", self.manifest_version
        )
        try:
            alias = StoredAlias.from_dict(json.loads(body))
        except (json.JSONDecodeError, KeyError) as e:
            raise ParseError(f"Failed to parse alias '{normalized_name}': {e}")
        # The fetched body must match what was requested, and the target must
        # classify as a cap or media URN — a mismatched object is a hard error.
        _validate_fetched_alias(alias, normalized_name, defver)
        return alias

    async def _fetch_one_dim(self, name: str, defver: int) -> StoredDim:
        """Fetch a single dim body at its pinned defver, check it
        (:func:`checked_dim`), and cache it in memory and on disk. A registry
        that serves another object is a hard error, never silently
        accepted."""
        if self._offline:
            raise NetworkBlockedError(f"offline: cannot fetch dim '{name}'")
        if defver < 1:
            raise NotFoundError(
                f"dim '{name}' has non-positive defver {defver}; dims are versioned-only"
            )
        if not HTTPX_AVAILABLE or self.client is None:
            raise HttpError("httpx not available - cannot fetch from registry")
        url, _ = _definition_url_and_cache_path(self.cache_dir, self.locations, "dims", name, defver)
        body = await _fetch_object(
            self.client, url, f"dim '{name}' (defver {defver})", self.manifest_version
        )
        dim = checked_dim(body, name, defver)
        self._save_dim_to_cache(dim)
        with self.cache_lock:
            self.cached_dims[dim.name] = dim
        return dim

    async def _ensure_dims_cached(self, owner: str, dims: List[DimRef]) -> None:
        """Make sure every dim a definition names is cached, fetching the
        ones that are not at the defver the manifest pins, and that each
        names a value the dim declares. ``owner`` names the definition in
        errors. Nothing about the definition itself is cached here: its
        fetcher caches it only once this succeeds."""
        try:
            check_dim_refs(dims)
        except ValueError as e:
            raise ValidationError(f"{owner} dims: {e}")
        for r in dims:
            with self.cache_lock:
                dim = self.cached_dims.get(r.dim)
            if dim is None:
                if self.manifest_version == 0:
                    raise NotFoundError(
                        f"{owner} names dim '{r.dim}', but the registry is pinned at v0 "
                        f"(dims are a versioned-regime concept)"
                    )
                defver = self.manifest.dims.get(r.dim)
                if defver is None:
                    raise NotFoundError(
                        f"{owner} names dim '{r.dim}', which is not in manifest "
                        f"v{self.manifest_version}"
                    )
                # The dim's own failure, as it is: a refused fetch stays a
                # refused fetch, and only the registry's 404 is a NotFoundError.
                dim = await self._fetch_one_dim(r.dim, defver)
            if dim.value(r.value) is None:
                raise ValidationError(
                    f"{owner} names value '{r.value}' of dim '{r.dim}', which the dim "
                    f"does not declare"
                )

    # -------------------------------------------------------------------------
    # Defver resolution (manifest pin)
    # -------------------------------------------------------------------------

    def _cap_defver(self, normalized_urn: str) -> int:
        """Resolve a normalized cap URN to its defver under the pinned
        manifest. At v0 → 0. At v >= 1 the URN must be in the manifest's caps
        map; absence is a hard NotFoundError (no fallback to another version)."""
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

    def _dim_defver(self, name: str) -> int:
        """Resolve a dim name to its defver under the pinned manifest. Dims
        exist only in the versioned regime: at v0 any dim lookup is a hard
        NotFound. At v >= 1 the name must be in the manifest's dims map."""
        if self.manifest_version == 0:
            raise NotFoundError(
                f"dim '{name}' cannot resolve: registry is pinned at v0 "
                f"(dims are a versioned-regime concept)"
            )
        defver = self.manifest.dims.get(name)
        if defver is None:
            raise NotFoundError(
                f"dim '{name}' is not part of manifest v{self.manifest_version}"
            )
        return defver

    def cap_defver_for(self, urn: str) -> int:
        return self._cap_defver(normalize_cap_urn(urn))

    def media_defver_for(self, urn: str) -> int:
        return self._media_defver(normalize_media_urn(urn))

    def alias_defver_for(self, name: str) -> int:
        return self._alias_defver(normalize_alias_name(name))

    def dim_defver_for(self, name: str) -> int:
        """Look up a dim name's pinned defver under this registry's manifest
        without fetching the body."""
        return self._dim_defver(name)

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
        out-spec, each arg and what it accepts, every output) and
        de-duplicated."""
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
            # What the arg accepts: its stdin source's URN, or its `accepts`.
            push(arg.accepted_urn())
        for output in cap.get_outputs():
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
        return await self._noting(
            ("cap", normalized_urn, defver), self._fetch_cap_and_footprint(urn, normalized_urn, defver)
        )

    async def _noting(self, key: Tuple[str, str, int], fetch) -> Any:
        """Await ``fetch`` and keep what it came to for ``key``: a failure is
        remembered for the synchronous lookups, and a success forgets the
        failure before it."""
        try:
            result = await fetch
        except FabricRegistryError as e:
            with self.cache_lock:
                self._fetch_failures[key] = e
            raise
        with self.cache_lock:
            self._fetch_failures.pop(key, None)
        return result

    def _not_at_hand(self, key: Tuple[str, str, int], what: str, url: str) -> FabricRegistryError:
        """Why a definition the manifest names is not in memory: what its last
        fetch came to, or PendingError when it has not been fetched."""
        with self.cache_lock:
            last = self._fetch_failures.get(key)
        if last is not None:
            return last
        return PendingError(
            f"{what} is named by manifest v{self.manifest_version} and has not been "
            f"fetched from {url}"
        )

    async def _fetch_cap_and_footprint(self, urn: str, normalized_urn: str, defver: int) -> Cap:
        cap = await self._fetch_cap_from_registry(urn, defver)

        referenced = self._collect_referenced_media_urns(cap)
        for media_urn in referenced:
            with self.cache_lock:
                already_cached = media_urn in self.cached_specs
            if already_cached:
                continue
            await self._fetch_media_def_atomic(media_urn)

        # Every dim the cap names, at its pinned version, with the value named.
        await self._ensure_dims_cached(f"cap '{normalized_urn}'", cap.dims)

        # All referenced media defs and dims landed — now cache the cap.
        self._save_cap_to_cache(cap)
        with self.cache_lock:
            self.cached_caps[normalize_cap_urn(cap.urn_string())] = cap
        return cap

    async def _fetch_media_def_atomic(self, urn: str) -> StoredMediaDef:
        """Fetch a media def at its pinned defver and cache it only once
        every dim it names is cached (see ``_ensure_dims_cached``)."""
        normalized_urn = normalize_media_urn(urn)
        defver = self._media_defver(normalized_urn)
        return await self._noting(
            ("media", normalized_urn, defver),
            self._fetch_media_def_and_dims(urn, normalized_urn, defver),
        )

    async def _fetch_media_def_and_dims(
        self, urn: str, normalized_urn: str, defver: int
    ) -> StoredMediaDef:
        spec = await self._fetch_media_def_from_registry(urn, defver)
        await self._ensure_dims_cached(f"media def '{normalized_urn}'", spec.dims)
        self._save_media_def_to_cache(spec)
        with self.cache_lock:
            self.cached_specs[normalize_media_urn(spec.urn)] = spec
        return spec

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
        # The manifest answers first: a cap it does not name is absent,
        # offline or not.
        self._cap_defver(normalized_urn)

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

    def get_cached_cap(self, urn: str) -> Cap:
        """Synchronous in-memory lookup; never touches the network.

        The cap, or raises why it is not at hand: NotFoundError when the
        registry's answer is that it has no such cap (the pinned manifest does
        not name it, or its fetch was answered 404); FetchFailedError when its
        last fetch was refused or got no answer, with the URL, the status and
        the manifest version; PendingError when it has not been fetched; and
        ParseError when the URN does not parse."""
        normalized_urn = normalize_cap_urn(urn)
        with self.cache_lock:
            cached = self.cached_caps.get(normalized_urn)
        if cached is not None:
            return cached
        defver = self._cap_defver(normalized_urn)
        url, _ = _definition_url_and_cache_path(
            self.cache_dir, self.locations, "caps", normalized_urn, defver
        )
        raise self._not_at_hand(
            ("cap", normalized_urn, defver), f"cap '{normalized_urn}' (defver {defver})", url
        )

    async def cap_exists(self, urn: str) -> bool:
        """Whether the registry holds the cap (cached or online): False only
        when its answer is that it has none. A fetch that was refused or got
        no answer says nothing about whether the cap exists, and raises."""
        try:
            await self.get_cap(urn)
            return True
        except (NotFoundError, ParseError):
            return False

    async def validate_cap(self, cap: Cap) -> None:
        """Validate a local cap against its canonical definition."""
        canonical_cap = await self.get_cap(cap.urn_string())
        canonical_alias_set = set(canonical_cap.aliases)
        unknown = [a for a in cap.aliases if a not in canonical_alias_set]
        if unknown:
            raise ValidationError(
                f"Alias mismatch: {unknown} not among the fabric cap's aliases {canonical_cap.aliases}"
            )
        if cap.is_abstract != canonical_cap.is_abstract:
            raise ValidationError(
                f"Abstract-flag mismatch. Local: {cap.is_abstract}, Canonical: {canonical_cap.is_abstract}"
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
        # The manifest answers first: a media def it does not name is absent,
        # offline or not.
        self._media_defver(normalized_urn)

        if self._offline:
            raise NetworkBlockedError(
                f"Network access blocked while offline: cannot fetch media def {urn!r}"
            )

        return await self._fetch_media_def_atomic(urn)

    async def get_media_defs(self, urns: List[str]) -> List[StoredMediaDef]:
        return [await self.get_media_def(u) for u in urns]

    async def get_cached_media_defs(self) -> List[StoredMediaDef]:
        with self.cache_lock:
            return list(self.cached_specs.values())

    def get_cached_media_def(self, urn: str) -> StoredMediaDef:
        """Synchronous in-memory lookup; never touches the network: the media
        def, or raises why it is not at hand, as ``get_cached_cap`` says."""
        normalized_urn = normalize_media_urn(urn)
        with self.cache_lock:
            cached = self.cached_specs.get(normalized_urn)
        if cached is not None:
            return cached
        defver = self._media_defver(normalized_urn)
        url, _ = _definition_url_and_cache_path(
            self.cache_dir, self.locations, "media", normalized_urn, defver
        )
        raise self._not_at_hand(
            ("media", normalized_urn, defver),
            f"media def '{normalized_urn}' (defver {defver})",
            url,
        )

    async def media_def_exists(self, urn: str) -> bool:
        """Whether the registry holds the media def (cached or online), as
        ``cap_exists`` answers it."""
        try:
            await self.get_media_def(urn)
            return True
        except (NotFoundError, ParseError):
            return False

    async def file_media_for_extension(self, extension: str) -> List[StoredMediaDef]:
        """The file media types a file with this extension can be: every
        definition in the pinned manifest whose URN carries the ``ext=``
        file-type tag and whose ``extensions`` list the extension (any case),
        in URN order. Empty when the fabric declares no file type for it.

        The first call loads every file media definition the manifest names
        (those not cached yet are fetched at once, 16 at a time, and kept in
        this manifest version's cache); later calls answer from memory. A
        definition that cannot be had fails the call with a FileTypesError
        naming each one and why: an answer from part of the fabric's file
        types would be a wrong answer."""
        index = await self._file_media_index()
        return list(index.get(extension.lower(), []))

    async def _file_media_index(self) -> Dict[str, List[StoredMediaDef]]:
        with self.cache_lock:
            loaded = self._file_media
        if loaded is not None:
            return loaded
        async with self._file_media_loading:
            with self.cache_lock:
                loaded = self._file_media
                if loaded is not None:
                    return loaded
                file_types = file_types_of(self.cache_dir, self.manifest_file, self.manifest)
                defs: List[StoredMediaDef] = []
                missing: List[Tuple[str, int]] = []
                for urn, defver in file_types:
                    cached = self.cached_specs.get(urn)
                    if cached is not None:
                        defs.append(cached)
                    else:
                        missing.append((urn, defver))

            gate = asyncio.Semaphore(FILE_MEDIA_FETCHES_AT_ONCE)

            async def fetch(urn: str, defver: int) -> StoredMediaDef:
                async with gate:
                    if self._offline:
                        raise NetworkBlockedError(
                            f"Network access blocked while offline: cannot fetch media def {urn!r}"
                        )
                    return await self._noting(
                        ("media", urn, defver), self._fetch_media_def_and_dims(urn, urn, defver)
                    )

            results = await asyncio.gather(
                *(fetch(urn, defver) for urn, defver in missing), return_exceptions=True
            )
            failures: List[str] = []
            for (urn, _), result in zip(missing, results):
                if isinstance(result, FabricRegistryError):
                    failures.append(f"{urn}: {result}")
                elif isinstance(result, BaseException):
                    # Anything but a registry's answer is a defect, raised as
                    # it is.
                    raise result
                else:
                    defs.append(result)
            if failures:
                failures.sort()
                raise FileTypesError(
                    f"{len(failures)} of the {len(failures) + len(defs)} file media types of "
                    f"manifest v{self.manifest_version} could not be loaded, so no file's type "
                    f"can be told from its extension: {'; '.join(failures)}"
                )

            index: Dict[str, List[StoredMediaDef]] = {}
            for spec in defs:
                for ext in spec.extensions:
                    index.setdefault(ext.lower(), []).append(spec)
            for ext, specs in index.items():
                by_urn: Dict[str, StoredMediaDef] = {}
                for spec in specs:
                    by_urn.setdefault(spec.urn, spec)
                index[ext] = [by_urn[urn] for urn in sorted(by_urn)]
            with self.cache_lock:
                self._file_media = index
            return index

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
        # The manifest answers first: an alias it does not name is absent,
        # offline or not.
        defver = self._alias_defver(normalized)
        if self._offline:
            raise NetworkBlockedError(
                f"Network access blocked while offline: cannot fetch alias {name!r}"
            )
        alias = await self._noting(
            ("alias", normalized, defver), self._fetch_alias_from_registry(normalized, defver)
        )
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
        """Synchronous, in-memory-only alias resolution.

        The target URN when the alias is in memory. None when the registry
        has no alias by this name: the pinned manifest does not name it, or
        the name is not one an alias can have. An alias the manifest names
        that is not in memory raises: what its last fetch came to (a refusal
        is reported as itself), or PendingError when it has not been fetched
        — it exists, so it is never reported as undefined."""
        try:
            normalized = normalize_alias_name(name)
        except ValueError:
            return None
        with self.cache_lock:
            alias = self.cached_aliases.get(normalized)
        if alias is not None:
            return alias.target
        try:
            defver = self._alias_defver(normalized)
        except NotFoundError:
            return None
        url, _ = _definition_url_and_cache_path(
            self.cache_dir, self.locations, "aliases", normalized, defver
        )
        raise self._not_at_hand(
            ("alias", normalized, defver), f"alias '{normalized}' (defver {defver})", url
        )

    # -------------------------------------------------------------------------
    # Public dim API
    # -------------------------------------------------------------------------

    async def get_dim(self, name: str) -> StoredDim:
        """Fetch a dim's definition — its title, documentation and values,
        each value with its own — by name (cache-first, then network), at the
        version the pinned manifest names. A string that is no dim name is a
        ValidationError; a name the manifest does not list is a NotFoundError,
        decided before any fetch."""
        if not is_dim_name(name):
            raise ValidationError(f"'{name}' is not a dim name")
        cached = self.get_cached_dim(name)
        if cached is not None:
            return cached
        defver = self._dim_defver(name)
        return await self._fetch_one_dim(name, defver)

    def get_cached_dim(self, name: str) -> Optional[StoredDim]:
        """Synchronous, in-memory-only dim lookup. Every dim a cached cap or
        media def names is cached with it, so a reader holding a definition
        from this registry finds its dims here."""
        with self.cache_lock:
            return self.cached_dims.get(name)

    # -------------------------------------------------------------------------
    # Offline / cache control
    # -------------------------------------------------------------------------

    def set_offline(self, offline: bool) -> None:
        self._offline = offline

    def clear_cache(self) -> None:
        """Invalidate every cache of this registry's manifest version: the
        in-memory maps and its whole folder on disk, INCLUDING the manifest.
        After this a freshly constructed registry re-fetches the manifest and
        every body from the network. The folders of the layout before
        per-version folders are removed with it (:func:`clear_cache_folder`)."""
        with self.cache_lock:
            self.cached_caps.clear()
            self.cached_specs.clear()
            self.cached_aliases.clear()
            self.cached_dims.clear()
            self._file_media = None
        clear_cache_folder(self.cache_dir)

    @classmethod
    async def clear_cache_of(cls, config: RegistryConfig, manifest_version: int) -> Path:
        """Clear the disk cache of manifest ``manifest_version`` of the
        registry ``config`` names, without opening a registry on it — so a
        cache holding a corrupt entry, which a registry refuses to open, can
        still be cleared. The registry's charter is the stored one, else
        fetched, as a registry finds it. Answers the folder cleared."""
        capdag_cache = cls._capdag_cache_root()
        if HTTPX_AVAILABLE:
            async with httpx.AsyncClient(timeout=10.0) as client:
                charter = await _resolve_charter(client, capdag_cache, config.anchor)
        else:
            charter = await _resolve_charter(None, capdag_cache, config.anchor)
        cache_dir = cache.version_dir(capdag_cache / charter.slug, manifest_version)
        clear_cache_folder(cache_dir)
        return cache_dir

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
        try:
            normalized_urn = normalize_cap_urn(identity.urn_string())
        except ParseError as e:
            # The identity cap URN is a built-in constant and should always
            # parse; if it ever does not, log an error and skip caching
            # identity rather than crashing registry construction.
            _log.error("ensure_identity_cap: skipping identity seed: %s", e)
            return
        with self.cache_lock:
            if normalized_urn not in self.cached_caps:
                self.cached_caps[normalized_urn] = identity
            if self.manifest_version >= 1:
                self.manifest.caps[normalized_urn] = self.manifest_version

    # -------------------------------------------------------------------------
    # Test helpers
    # -------------------------------------------------------------------------

    @classmethod
    def new_for_test(cls, registry_dir: Optional[Path] = None) -> "FabricRegistry":
        """Build an empty registry for tests, pinned at manifest 1, caching
        in ``v1`` of ``registry_dir`` (a fresh temporary folder when none is
        given).

        The mandatory identity cap is auto-installed so the resolver's
        source-to-cap-arg matching can route through identity in any
        notation, matching the production invariant.
        """
        cache_dir = cls._test_cache_dir(registry_dir, 1)
        client = httpx.AsyncClient(timeout=10.0) if HTTPX_AVAILABLE else None
        # Pin at v1 with an empty manifest so test helpers flow caps/media/
        # aliases into the manifest at their declared version (mirrors Rust).
        config = RegistryConfig()
        registry = cls(
            cache_dir, config, publisher_layout_charter(config.anchor), client, 1, Manifest.empty(1)
        )
        registry.ensure_identity_cap()
        return registry

    @staticmethod
    def _test_cache_dir(registry_dir: Optional[Path], manifest_version: int) -> Path:
        """The cache folder of manifest ``manifest_version`` under the test
        registry folder ``registry_dir``, made with its kinds' folders."""
        if registry_dir is None:
            from tempfile import mkdtemp

            registry_dir = Path(mkdtemp(prefix="capdag-fabric-test-"))
        cache_dir = cache.version_dir(registry_dir, manifest_version)
        for kind in cache.KIND_FOLDERS:
            (cache_dir / kind).mkdir(parents=True, exist_ok=True)
        return cache_dir

    @classmethod
    def new_for_test_with_config(
        cls, config: RegistryConfig, registry_dir: Optional[Path] = None
    ) -> "FabricRegistry":
        """:meth:`new_for_test` with ``config``."""
        return cls.new_for_test_with_config_and_version(config, 1, registry_dir)

    @classmethod
    def new_for_test_with_config_and_version(
        cls,
        config: RegistryConfig,
        manifest_version: int,
        registry_dir: Optional[Path] = None,
    ) -> "FabricRegistry":
        """A test registry with ``config``, pinned at ``manifest_version``
        with an empty manifest made in memory, caching in ``v<N>`` of
        ``registry_dir`` (a fresh temporary folder when none is given). It
        fetches from the publisher's layout at ``config``'s anchor."""
        cache_dir = cls._test_cache_dir(registry_dir, manifest_version)
        client = httpx.AsyncClient(timeout=10.0) if HTTPX_AVAILABLE else None
        registry = cls(
            cache_dir,
            config,
            publisher_layout_charter(config.anchor),
            client,
            manifest_version,
            Manifest.empty(manifest_version),
        )
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
                try:
                    normalized = normalize_cap_urn(cap.urn_string())
                except ParseError as e:
                    # Skip a cap with a malformed URN: log and continue the
                    # batch. Never cache under a raw key, never crash.
                    _log.warning("add_caps_to_cache: skipping cap: %s", e)
                    continue
                self.cached_caps[normalized] = cap
                if self.manifest_version >= 1:
                    self.manifest.caps[normalized] = cap.version

    def list_media_in_manifest_for_test(self, urn: str, defver: int) -> None:
        """Name a media definition in the manifest without caching it: a test
        registry then fetches it from the registry's location when it is
        first needed (test helper)."""
        normalized = normalize_media_urn(urn)
        with self.cache_lock:
            self.manifest.media[normalized] = defver
            # The manifest is no longer the file it was read from.
            self.manifest_file = None

    def add_spec(self, spec: StoredMediaDef) -> None:
        """Insert a media def directly into the in-memory cache (test helper).

        Records the spec in the manifest. A spec whose version is 0 is
        stamped to the pinned manifest version.
        """
        with self.cache_lock:
            if spec.version == 0 and self.manifest_version >= 1:
                spec.version = self.manifest_version
            try:
                normalized = normalize_media_urn(spec.urn)
            except ParseError as e:
                # Skip a spec with a malformed URN: log and no-op. Never
                # cache under a raw key, never crash.
                _log.warning("add_spec: skipping media def: %s", e)
                return
            self.cached_specs[normalized] = spec
            if self.manifest_version >= 1:
                self.manifest.media[normalized] = spec.version
                # The manifest is no longer the file it was read from.
                self.manifest_file = None

    def display_alias_for_urn(self, urn: str) -> Optional[str]:
        """Reverse-resolve a cap or media URN to its display alias name.

        The query URN is canonicalised by kind first (cap vs media, via the
        same classifier the alias publisher uses for targets), so a
        non-canonical query (different tag order, redundant whitespace) that
        would otherwise miss still resolves. A URN that is neither a cap nor a
        media URN, or that fails to parse, returns ``None`` (it cannot have an
        alias).

        When multiple aliases target the same URN, the winner is the SHORTEST
        name, ties broken alphabetically (see :func:`select_display_alias`).
        This is deterministic and stable across processes for a given alias
        set.
        """
        # Canonicalise by kind. classify_alias_target keys off the prefix and
        # is the same classifier the alias publisher uses for targets, so a
        # query and a stored target canonicalise identically.
        kind = classify_alias_target(urn)
        if kind is None:
            return None
        try:
            if kind == ALIAS_TARGET_CAP:
                canonical = normalize_cap_urn(urn)
            else:
                canonical = normalize_media_urn(urn)
        except FabricRegistryError:
            return None
        with self.cache_lock:
            names = [
                alias.name
                for alias in self.cached_aliases.values()
                if alias.target == canonical
            ]
        return select_display_alias(names)

    def cached_cap_aliases(self) -> List[Tuple[str, str]]:
        """All cached aliases whose target is a CAP URN, as ``(name, cap_urn)``
        pairs. Used by the notation editor to offer registered cap aliases as
        wiring completions. Order is unspecified (the caller sorts/filters).
        Synchronous, cache-only — relies on the startup alias prefetch having
        warmed the cache.
        """
        with self.cache_lock:
            return [
                (alias.name, alias.target)
                for alias in self.cached_aliases.values()
                if classify_alias_target(alias.target) == ALIAS_TARGET_CAP
            ]

    def insert_cached_alias_for_test(self, alias: StoredAlias) -> None:
        """Insert an alias directly into the in-memory cache and register its
        defver in the manifest, bypassing the network (test helper)."""
        with self.cache_lock:
            self.cached_aliases[alias.name] = alias
            if self.manifest_version >= 1:
                self.manifest.aliases[alias.name] = alias.version

    def insert_cached_dim_for_test(self, dim: StoredDim) -> None:
        """Insert a dim directly into the in-memory cache and register its
        defver in the manifest, bypassing the network (test helper). Mirrors
        ``insert_cached_alias_for_test``."""
        with self.cache_lock:
            self.cached_dims[dim.name] = dim
            if self.manifest_version >= 1:
                self.manifest.dims[dim.name] = dim.version
