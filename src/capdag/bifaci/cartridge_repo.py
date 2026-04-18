"""Cartridge repository models and cache service.

Fetches and caches cartridge registry data from configured cartridge repositories.
Provides cartridge suggestions when a cap is unavailable but a cartridge exists
that could provide it.
"""

from __future__ import annotations

import json
from functools import cmp_to_key
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional


def _null_as_empty_string(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    raise ValueError(f"expected string or null, got {type(value).__name__}")


@dataclass
class CartridgeCapSummary:
    urn: str
    title: str
    description: str = ""

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeCapSummary":
        return cls(
            urn=raw["urn"],
            title=raw["title"],
            description=_null_as_empty_string(raw.get("description")),
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
    id: str
    name: str
    version: str = ""
    description: str = ""
    author: str = ""
    homepage: str = ""
    team_id: str = ""
    signed_at: str = ""
    min_app_version: str = ""
    page_url: str = ""
    categories: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    caps: List[CartridgeCapSummary] = field(default_factory=list)
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
            homepage=_null_as_empty_string(raw.get("homepage")),
            team_id=_null_as_empty_string(raw.get("teamId")),
            signed_at=_null_as_empty_string(raw.get("signedAt")),
            min_app_version=_null_as_empty_string(raw.get("minAppVersion")),
            page_url=_null_as_empty_string(raw.get("pageUrl")),
            categories=list(raw.get("categories", [])),
            tags=list(raw.get("tags", [])),
            caps=[CartridgeCapSummary.from_dict(item) for item in raw.get("caps", [])],
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
    name: str
    description: str
    author: str
    page_url: str = ""
    team_id: str = ""
    min_app_version: str = ""
    caps: List[CartridgeCapSummary] = field(default_factory=list)
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
            caps=[CartridgeCapSummary.from_dict(item) for item in raw.get("caps", [])],
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
                    homepage="",
                    team_id=entry.team_id,
                    signed_at=version_data.release_date,
                    min_app_version=version_data.min_app_version or entry.min_app_version,
                    page_url=entry.page_url,
                    categories=list(entry.categories),
                    tags=list(entry.tags),
                    caps=list(entry.caps),
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
        lower_query = query.lower()
        return [
            cartridge
            for cartridge in self.transform_to_cartridge_array()
            if lower_query in cartridge.name.lower()
            or lower_query in cartridge.description.lower()
            or any(lower_query in tag.lower() for tag in cartridge.tags)
            or any(
                lower_query in cap.urn.lower() or lower_query in cap.title.lower()
                for cap in cartridge.caps
            )
        ]

    def get_cartridges_by_category(self, category: str) -> List[CartridgeInfo]:
        return [
            cartridge
            for cartridge in self.transform_to_cartridge_array()
            if category in cartridge.categories
        ]

    def get_cartridges_by_cap(self, cap_urn: str) -> List[CartridgeInfo]:
        return [
            cartridge
            for cartridge in self.transform_to_cartridge_array()
            if any(cap.urn == cap_urn for cap in cartridge.caps)
        ]


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
        cartridges: Dict[str, CartridgeInfo] = {}
        cap_to_cartridges: Dict[str, List[str]] = {}

        for cartridge_info in registry.cartridges:
            cartridge_id = cartridge_info.id
            for cap in cartridge_info.caps:
                cap_to_cartridges.setdefault(cap.urn, []).append(cartridge_id)
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
        suggestions: List[CartridgeSuggestion] = []
        for cache in self._caches.values():
            for cartridge_id in cache.cap_to_cartridges.get(cap_urn, []):
                cartridge = cache.cartridges[cartridge_id]
                cap_info = next((cap for cap in cartridge.caps if cap.urn == cap_urn), None)
                if cap_info is None:
                    continue
                page_url = cartridge.page_url or cache.repo_url
                suggestions.append(
                    CartridgeSuggestion(
                        cartridge_id=cartridge_id,
                        cartridge_name=cartridge.name,
                        cartridge_description=cartridge.description,
                        cap_urn=cap_urn,
                        cap_title=cap_info.title,
                        latest_version=cartridge.version,
                        repo_url=cache.repo_url,
                        page_url=page_url,
                    )
                )
        return suggestions
