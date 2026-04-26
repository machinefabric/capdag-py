"""Cartridge repository models and cache service.

Fetches and caches cartridge registry data from configured cartridge repositories.
Provides cartridge suggestions when a cap is unavailable but a cartridge exists
that could provide it.

Wire schema is v4.0: each cartridge advertises its caps in `cap_groups`
(snake_case key on the wire). There is no flat `caps` field. URN matching
goes through `CapUrn.from_string` and `is_equivalent`; raw string equality
on URNs is forbidden.
"""

from __future__ import annotations

import json
import sys
from functools import cmp_to_key
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

from capdag.urn.cap_urn import CapUrn


def _null_as_empty_string(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    raise ValueError(f"expected string or null, got {type(value).__name__}")


@dataclass
class RegistryArgSource:
    """One source for a registry cap argument. Exactly one of stdin /
    position / cli_flag is populated by the producer."""
    stdin: Optional[str] = None
    position: Optional[int] = None
    cli_flag: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: dict) -> "RegistryArgSource":
        return cls(
            stdin=raw.get("stdin"),
            position=raw.get("position"),
            cli_flag=raw.get("cli_flag"),
        )


@dataclass
class RegistryCapArg:
    """One argument descriptor on a registry cap."""
    media_urn: str
    required: bool
    is_sequence: bool = False
    sources: List[RegistryArgSource] = field(default_factory=list)
    arg_description: Optional[str] = None
    default_value: Any = None

    @classmethod
    def from_dict(cls, raw: dict) -> "RegistryCapArg":
        return cls(
            media_urn=raw["media_urn"],
            required=bool(raw.get("required", False)),
            is_sequence=bool(raw.get("is_sequence", False)),
            sources=[RegistryArgSource.from_dict(s) for s in raw.get("sources", [])],
            arg_description=raw.get("arg_description"),
            default_value=raw.get("default_value"),
        )


@dataclass
class RegistryCapOutput:
    """Output descriptor on a registry cap."""
    media_urn: str
    is_sequence: bool = False
    output_description: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: dict) -> "RegistryCapOutput":
        return cls(
            media_urn=raw["media_urn"],
            is_sequence=bool(raw.get("is_sequence", False)),
            output_description=raw.get("output_description"),
        )


@dataclass
class RegistryCap:
    """A single capability advertised by a cartridge in the registry."""
    urn: str
    title: str
    command: str
    cap_description: Optional[str] = None
    args: Optional[List[RegistryCapArg]] = None
    output: Optional[RegistryCapOutput] = None

    @classmethod
    def from_dict(cls, raw: dict) -> "RegistryCap":
        return cls(
            urn=raw["urn"],
            title=raw["title"],
            command=raw["command"],
            cap_description=raw.get("cap_description"),
            args=[RegistryCapArg.from_dict(a) for a in raw["args"]] if "args" in raw else None,
            output=RegistryCapOutput.from_dict(raw["output"]) if "output" in raw else None,
        )


@dataclass
class RegistryCapGroup:
    """A bundle of caps + adapter URNs registered atomically by a
    cartridge."""
    name: str
    caps: List[RegistryCap] = field(default_factory=list)
    adapter_urns: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> "RegistryCapGroup":
        return cls(
            name=raw["name"],
            caps=[RegistryCap.from_dict(c) for c in raw.get("caps", [])],
            adapter_urns=list(raw.get("adapter_urns", [])),
        )


@dataclass
class CartridgeDistributionInfo:
    name: str
    sha256: str
    size: int

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeDistributionInfo":
        return cls(
            name=raw["name"],
            sha256=raw["sha256"],
            size=int(raw["size"]),
        )


@dataclass
class CartridgeBuild:
    platform: str
    package: CartridgeDistributionInfo

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeBuild":
        return cls(
            platform=raw["platform"],
            package=CartridgeDistributionInfo.from_dict(raw["package"]),
        )


@dataclass
class CartridgeVersionData:
    release_date: str
    changelog: List[str] = field(default_factory=list)
    min_app_version: str = ""
    builds: List[CartridgeBuild] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeVersionData":
        return cls(
            release_date=raw["releaseDate"],
            changelog=list(raw.get("changelog", [])),
            min_app_version=_null_as_empty_string(raw.get("minAppVersion")),
            builds=[CartridgeBuild.from_dict(item) for item in raw.get("builds", [])],
        )


@dataclass
class CartridgeInfo:
    """A cartridge entry as returned by /api/cartridges.

    The cartridge's capability surface lives in `cap_groups`. There is no
    flat `caps` list and no `homepage` field. `iter_caps()` walks every
    cap across every group in declaration order.
    """
    id: str
    name: str
    version: str = ""
    description: str = ""
    author: str = ""
    team_id: str = ""
    signed_at: str = ""
    min_app_version: str = ""
    page_url: str = ""
    categories: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    cap_groups: List[RegistryCapGroup] = field(default_factory=list)
    versions: Dict[str, CartridgeVersionData] = field(default_factory=dict)
    available_versions: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeInfo":
        versions_raw = raw.get("versions", {})
        return cls(
            id=raw["id"],
            name=raw["name"],
            version=_null_as_empty_string(raw.get("version")),
            description=_null_as_empty_string(raw.get("description")),
            author=_null_as_empty_string(raw.get("author")),
            team_id=_null_as_empty_string(raw.get("teamId")),
            signed_at=_null_as_empty_string(raw.get("signedAt")),
            min_app_version=_null_as_empty_string(raw.get("minAppVersion")),
            page_url=_null_as_empty_string(raw.get("pageUrl")),
            categories=list(raw.get("categories", [])),
            tags=list(raw.get("tags", [])),
            cap_groups=[RegistryCapGroup.from_dict(item) for item in raw.get("cap_groups", [])],
            versions={key: CartridgeVersionData.from_dict(value) for key, value in versions_raw.items()},
            available_versions=list(raw.get("availableVersions", [])),
        )

    @classmethod
    def from_json(cls, payload: str) -> "CartridgeInfo":
        return cls.from_dict(json.loads(payload))

    def is_signed(self) -> bool:
        return bool(self.team_id and self.signed_at)

    def build_for_platform(self, platform: str) -> Optional[CartridgeBuild]:
        version = self.versions.get(self.version)
        if version is None:
            return None
        for build in version.builds:
            if build.platform == platform:
                return build
        return None

    def available_platforms(self) -> List[str]:
        platforms = sorted(
            {
                build.platform
                for version in self.versions.values()
                for build in version.builds
            }
        )
        return platforms

    def iter_caps(self) -> Iterator[RegistryCap]:
        """Yield every cap across every cap group in declaration order."""
        for group in self.cap_groups:
            for cap in group.caps:
                yield cap


@dataclass
class CartridgeRegistryResponse:
    cartridges: List[CartridgeInfo]

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeRegistryResponse":
        return cls(
            cartridges=[CartridgeInfo.from_dict(item) for item in raw["cartridges"]]
        )

    @classmethod
    def from_json(cls, payload: str) -> "CartridgeRegistryResponse":
        return cls.from_dict(json.loads(payload))


@dataclass
class CartridgeSuggestion:
    cartridge_id: str
    cartridge_name: str
    cartridge_description: str
    cap_urn: str
    cap_title: str
    latest_version: str
    repo_url: str
    page_url: str


@dataclass
class CartridgeRegistryEntry:
    """A cartridge entry in the v4.0 source-of-truth registry.

    Capability surface lives in `cap_groups`; there is no flat `caps`
    list. The transformer in `CartridgeRepoServer` converts each entry
    into a `CartridgeInfo` for the API response.
    """
    name: str
    description: str
    author: str
    page_url: str = ""
    team_id: str = ""
    min_app_version: str = ""
    cap_groups: List[RegistryCapGroup] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    latest_version: str = ""
    versions: Dict[str, CartridgeVersionData] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeRegistryEntry":
        versions_raw = raw.get("versions", {})
        return cls(
            name=raw["name"],
            description=raw["description"],
            author=raw["author"],
            page_url=_null_as_empty_string(raw.get("pageUrl")),
            team_id=_null_as_empty_string(raw.get("teamId")),
            min_app_version=_null_as_empty_string(raw.get("minAppVersion")),
            cap_groups=[RegistryCapGroup.from_dict(item) for item in raw.get("cap_groups", [])],
            categories=list(raw.get("categories", [])),
            tags=list(raw.get("tags", [])),
            latest_version=raw["latestVersion"],
            versions={key: CartridgeVersionData.from_dict(value) for key, value in versions_raw.items()},
        )


@dataclass
class CartridgeRegistry:
    schema_version: str
    last_updated: str
    cartridges: Dict[str, CartridgeRegistryEntry]

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeRegistry":
        return cls(
            schema_version=raw["schemaVersion"],
            last_updated=raw["lastUpdated"],
            cartridges={
                key: CartridgeRegistryEntry.from_dict(value)
                for key, value in raw["cartridges"].items()
            },
        )

    @classmethod
    def from_json(cls, payload: str) -> "CartridgeRegistry":
        return cls.from_dict(json.loads(payload))


@dataclass
class _CartridgeRepoCache:
    cartridges: Dict[str, CartridgeInfo]
    cap_to_cartridges: Dict[str, List[str]]
    last_updated: float
    repo_url: str


class CartridgeRepoError(ValueError):
    pass


class CartridgeRepoServer:
    """Transforms validated nested registry data into flat API responses."""

    def __init__(self, registry: CartridgeRegistry):
        if registry.schema_version != "4.0":
            raise CartridgeRepoError(
                f"Unsupported registry schema version: {registry.schema_version}. Required: 4.0"
            )
        self.registry = registry

    @staticmethod
    def _validate_version_data(
        cartridge_id: str,
        version: str,
        version_data: CartridgeVersionData,
    ) -> None:
        if not version_data.builds:
            raise CartridgeRepoError(f"Cartridge {cartridge_id} v{version}: no builds")
        for index, build in enumerate(version_data.builds):
            if not build.platform:
                raise CartridgeRepoError(
                    f"Cartridge {cartridge_id} v{version}: build[{index}] missing platform"
                )
            if not build.package.name:
                raise CartridgeRepoError(
                    f"Cartridge {cartridge_id} v{version}: build[{index}] ({build.platform}) missing package.name"
                )

    @staticmethod
    def _compare_versions(a: str, b: str) -> int:
        parts_a = [int(part) for part in a.split(".") if part.isdigit()]
        parts_b = [int(part) for part in b.split(".") if part.isdigit()]
        max_len = max(len(parts_a), len(parts_b))
        for index in range(max_len):
            num_a = parts_a[index] if index < len(parts_a) else 0
            num_b = parts_b[index] if index < len(parts_b) else 0
            if num_a < num_b:
                return -1
            if num_a > num_b:
                return 1
        return 0

    def transform_to_cartridge_array(self) -> List[CartridgeInfo]:
        cartridges: List[CartridgeInfo] = []
        for cartridge_id, entry in self.registry.cartridges.items():
            latest_version = entry.latest_version
            version_data = entry.versions.get(latest_version)
            if version_data is None:
                raise CartridgeRepoError(
                    f"Cartridge {cartridge_id}: latest version {latest_version} not found in versions"
                )

            self._validate_version_data(cartridge_id, latest_version, version_data)
            available_versions = sorted(
                entry.versions.keys(),
                key=cmp_to_key(lambda a, b: self._compare_versions(b, a)),
            )

            cartridges.append(
                CartridgeInfo(
                    id=cartridge_id,
                    name=entry.name,
                    version=latest_version,
                    description=entry.description,
                    author=entry.author,
                    team_id=entry.team_id,
                    signed_at=version_data.release_date,
                    min_app_version=version_data.min_app_version or entry.min_app_version,
                    page_url=entry.page_url,
                    categories=list(entry.categories),
                    tags=list(entry.tags),
                    cap_groups=list(entry.cap_groups),
                    versions=dict(entry.versions),
                    available_versions=available_versions,
                )
            )
        return cartridges

    def get_cartridges(self) -> CartridgeRegistryResponse:
        return CartridgeRegistryResponse(cartridges=self.transform_to_cartridge_array())

    def get_cartridge_by_id(self, cartridge_id: str) -> Optional[CartridgeInfo]:
        for cartridge in self.transform_to_cartridge_array():
            if cartridge.id == cartridge_id:
                return cartridge
        return None

    def search_cartridges(self, query: str) -> List[CartridgeInfo]:
        """Match query against cartridge name/description/tags and cap
        titles. Cap URN strings are NOT substring-matched: a cap URN is a
        tagged identifier, not free-form text. Use get_cartridges_by_cap
        for cap lookups."""
        lower_query = query.lower()
        return [
            cartridge
            for cartridge in self.transform_to_cartridge_array()
            if lower_query in cartridge.name.lower()
            or lower_query in cartridge.description.lower()
            or any(lower_query in tag.lower() for tag in cartridge.tags)
            or any(
                lower_query in cap.title.lower()
                for cap in cartridge.iter_caps()
            )
        ]

    def get_cartridges_by_category(self, category: str) -> List[CartridgeInfo]:
        return [
            cartridge
            for cartridge in self.transform_to_cartridge_array()
            if category in cartridge.categories
        ]

    def get_cartridges_by_cap(self, cap_urn: str) -> List[CartridgeInfo]:
        """Return cartridges that provide a cap equivalent to `cap_urn`.

        Both the request URN and each candidate cap URN are parsed via
        CapUrn.from_string and matched with `is_equivalent` so caps
        declared in any tag order resolve. A malformed input URN raises
        — there is no fallback that compares the raw strings.
        """
        requested = CapUrn.from_string(cap_urn)
        result: List[CartridgeInfo] = []
        for cartridge in self.transform_to_cartridge_array():
            for cap in cartridge.iter_caps():
                try:
                    parsed = CapUrn.from_string(cap.urn)
                except Exception:
                    continue
                if parsed.is_equivalent(requested):
                    result.append(cartridge)
                    break
        return result


class CartridgeRepo:
    """Cache service for cartridge repository metadata."""

    def __init__(self, cache_ttl_seconds: int):
        self.cache_ttl_seconds = cache_ttl_seconds
        self._caches: Dict[str, _CartridgeRepoCache] = {}
        self._offline = False

    def set_offline(self, offline: bool) -> None:
        self._offline = offline

    def _is_cache_stale(self, cache: _CartridgeRepoCache) -> bool:
        return (time.time() - cache.last_updated) > self.cache_ttl_seconds

    def update_cache(self, repo_url: str, registry: CartridgeRegistryResponse) -> None:
        """Index the registry response into the cache.

        The cap-to-cartridges index keys on the *normalized* tagged-URN
        form of each cap URN (parse via CapUrn.from_string, then take
        str()). A cap URN that fails to parse is a registry corruption:
        we raise CartridgeRepoError rather than silently keep the
        malformed string in the index.
        """
        cartridges: Dict[str, CartridgeInfo] = {}
        cap_to_cartridges: Dict[str, List[str]] = {}

        for cartridge_info in registry.cartridges:
            cartridge_id = cartridge_info.id
            for cap in cartridge_info.iter_caps():
                try:
                    parsed = CapUrn.from_string(cap.urn)
                except Exception as exc:
                    raise CartridgeRepoError(
                        f"cartridge {cartridge_id}: invalid cap URN {cap.urn!r}: {exc}"
                    ) from exc
                normalized = str(parsed)
                cap_to_cartridges.setdefault(normalized, []).append(cartridge_id)
            cartridges[cartridge_id] = cartridge_info

        self._caches[repo_url] = _CartridgeRepoCache(
            cartridges=cartridges,
            cap_to_cartridges=cap_to_cartridges,
            last_updated=time.time(),
            repo_url=repo_url,
        )

    def get_all_cartridges(self) -> List[tuple[str, CartridgeInfo]]:
        result: List[tuple[str, CartridgeInfo]] = []
        for cache in self._caches.values():
            for cartridge_id, cartridge in cache.cartridges.items():
                result.append((cartridge_id, cartridge))
        return result

    def get_all_available_caps(self) -> List[str]:
        caps = {
            cap
            for cache in self._caches.values()
            for cap in cache.cap_to_cartridges.keys()
        }
        return sorted(caps)

    def needs_sync(self, repo_urls: List[str]) -> bool:
        for repo_url in repo_urls:
            cache = self._caches.get(repo_url)
            if cache is None or self._is_cache_stale(cache):
                return True
        return False

    def get_cartridge(self, cartridge_id: str) -> Optional[CartridgeInfo]:
        for cache in self._caches.values():
            if cartridge_id in cache.cartridges:
                return cache.cartridges[cartridge_id]
        return None

    def get_suggestions_for_cap(self, cap_urn: str) -> List[CartridgeSuggestion]:
        """Return suggestions for a cap URN that isn't currently
        available locally.

        `cap_urn` is parsed via CapUrn.from_string; the parsed-and-
        re-serialized form is the canonical key into the cap-to-
        cartridges index. Inside each candidate cartridge we walk caps
        via iter_caps() and match each on is_equivalent. A malformed
        input URN logs to stderr and returns no suggestions rather than
        masking the error.
        """
        try:
            requested = CapUrn.from_string(cap_urn)
        except Exception as exc:
            print(
                f"get_suggestions_for_cap: invalid cap URN {cap_urn!r}: {exc}",
                file=sys.stderr,
            )
            return []
        normalized = str(requested)

        suggestions: List[CartridgeSuggestion] = []
        for cache in self._caches.values():
            for cartridge_id in cache.cap_to_cartridges.get(normalized, []):
                cartridge = cache.cartridges[cartridge_id]
                cap_info: Optional[RegistryCap] = None
                for cap in cartridge.iter_caps():
                    try:
                        parsed = CapUrn.from_string(cap.urn)
                    except Exception:
                        continue
                    if parsed.is_equivalent(requested):
                        cap_info = cap
                        break
                if cap_info is None:
                    continue
                page_url = cartridge.page_url or cache.repo_url
                suggestions.append(
                    CartridgeSuggestion(
                        cartridge_id=cartridge_id,
                        cartridge_name=cartridge.name,
                        cartridge_description=cartridge.description,
                        cap_urn=normalized,
                        cap_title=cap_info.title,
                        latest_version=cartridge.version,
                        repo_url=cache.repo_url,
                        page_url=page_url,
                    )
                )
        return suggestions
