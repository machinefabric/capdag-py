"""Cartridge repository models and cache service.

Fetches and caches cartridge registry data from configured cartridge repositories.
Provides cartridge suggestions when a cap is unavailable but a cartridge exists
that could provide it.

Wire schema is v5.0: cartridges are partitioned by channel under
`channels.<channel>.cartridges.<id>`. Each cartridge advertises its caps
in `cap_groups` (snake_case key on the wire). There is no flat `caps`
field. URN matching goes through `CapUrn.from_string` and the predicate
methods (`is_equivalent`, `conforms_to`); raw string equality on URNs is
forbidden.
"""

from __future__ import annotations

import json
import sys
from enum import Enum
from functools import cmp_to_key
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Tuple

from capdag.urn.cap_urn import CapUrn


class CartridgeChannel(str, Enum):
    """Distribution channel for a cartridge entry. Mirrors capdag's
    `CartridgeChannel` and the registry's `channels.<channel>` keys.

    `RELEASE` is the user-facing channel; `NIGHTLY` is the in-flight
    channel. The value is the lowercase string used in the wire format.
    """
    RELEASE = "release"
    NIGHTLY = "nightly"


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
    """Distribution file info (package). `url` is the absolute URL of
    the package — every consumer downloads from that URL directly.
    There is no derived URL pattern any more.

    `format` is the installer format ("pkg" macOS, "deb"/"rpm" Linux,
    "msi"/"exe" Windows). It defaults to "" so the legacy singular
    `package` object (which carries no `format`) round-trips through
    this same struct."""

    name: str
    sha256: str
    size: int
    url: str
    format: str = ""

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeDistributionInfo":
        return cls(
            name=raw["name"],
            sha256=raw["sha256"],
            size=int(raw["size"]),
            url=raw["url"],
            format=str(raw.get("format", "")),
        )


def host_platform() -> str:
    """The platform string ``{os}-{arch}`` of the interpreter that calls
    this, in the exact form the registry uses (``darwin-arm64``,
    ``darwin-x86_64``, ``linux-x86_64``, ``windows-x86_64``).

    Derived from the running platform — the binary literally runs here, so
    this is the authoritative host string for compatibility resolution.
    Single source of truth: every consumer that needs "what am I running
    on?" calls this rather than re-deriving the os/arch mapping.

    `aarch64`/`arm64` are both normalized to `arm64`; an `x86_64`/`amd64`
    machine reports `x86_64`. The os maps macOS→darwin, otherwise the
    lowercase platform system name.
    """
    import platform as _platform

    system = _platform.system().lower()
    if system == "darwin":
        os_name = "darwin"
    elif system == "linux":
        os_name = "linux"
    elif system == "windows":
        os_name = "windows"
    else:
        os_name = system
    machine = _platform.machine().lower()
    if machine in ("aarch64", "arm64"):
        arch = "arm64"
    elif machine in ("x86_64", "amd64"):
        arch = "x86_64"
    else:
        arch = machine
    return f"{os_name}-{arch}"


class CompatStatus(str, Enum):
    """Host-compatibility status of a registry cartridge, resolved against
    a specific host platform string. Mirrors capdag's `CompatStatus` and
    the proto `CartridgeCompatibilityStatus`."""

    # The latest version has a build for this host platform — install as-is.
    COMPATIBLE = "compatible"
    # The latest version has no host build, but an older version does;
    # `resolved_version` names that older version. Install it, mark outdated.
    COMPATIBLE_OUTDATED = "compatible_outdated"
    # No version has a build for this host platform. Nothing to install.
    INCOMPATIBLE = "incompatible"


@dataclass
class CartridgeCompatibilityResolution:
    """The resolved verdict the engine attaches to an available cartridge:
    which version/package the host should install (if any) and a human
    reason when it is not the latest-and-greatest."""

    status: CompatStatus
    host_platform: str
    # Newest version that has a build for this host (None when Incompatible).
    resolved_version: Optional[str]
    # Host-preferred installer package within `resolved_version` (None when
    # Incompatible).
    resolved_package: Optional["CartridgeDistributionInfo"]
    # Explanation, set whenever status is not Compatible.
    reason: Optional[str]


@dataclass
class CartridgeBuild:
    """A platform-specific build of a cartridge version.

    `packages[]` lists every installer format the build ships. The
    legacy singular `package` is read only as a fallback when
    `packages[]` is absent, so a registry not yet republished with the
    dual-write keeps installing."""

    platform: str
    packages: List[CartridgeDistributionInfo] = field(default_factory=list)
    package: Optional[CartridgeDistributionInfo] = None

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeBuild":
        packages_raw = raw.get("packages", [])
        package_raw = raw.get("package")
        return cls(
            platform=raw["platform"],
            packages=[CartridgeDistributionInfo.from_dict(item) for item in packages_raw],
            package=CartridgeDistributionInfo.from_dict(package_raw) if package_raw is not None else None,
        )

    def primary_package(self) -> Optional[CartridgeDistributionInfo]:
        """The installer package the host should use, preferring the
        platform's native format. Falls back to the legacy singular
        `package` when `packages[]` is empty (pre-dual-write manifests).
        Returns ``None`` only when the build ships no installer at all."""
        os = self.platform.split("-")[0] if self.platform else ""
        preference: List[str]
        if os == "darwin":
            preference = ["pkg"]
        elif os == "linux":
            preference = ["deb", "rpm"]
        elif os == "windows":
            preference = ["msi", "exe"]
        else:
            preference = []
        for fmt in preference:
            for pkg in self.packages:
                if pkg.format == fmt:
                    return pkg
        if self.packages:
            return self.packages[0]
        return self.package


@dataclass
class CartridgeVersionData:
    """A cartridge version's data (v5.0 schema).

    `notes_url` is the absolute URL of the version's release-notes
    Markdown file, when one was uploaded at publish time. Optional —
    cartridges historically did not ship per-version notes.
    """

    release_date: str
    changelog: List[str] = field(default_factory=list)
    min_app_version: str = ""
    builds: List[CartridgeBuild] = field(default_factory=list)
    notes_url: Optional[str] = None

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeVersionData":
        return cls(
            release_date=raw["releaseDate"],
            changelog=list(raw.get("changelog", [])),
            min_app_version=_null_as_empty_string(raw.get("minAppVersion")),
            builds=[CartridgeBuild.from_dict(item) for item in raw.get("builds", [])],
            notes_url=raw.get("notesUrl"),
        )


@dataclass
class CartridgeInfo:
    """A cartridge entry as returned by /api/cartridges.

    The cartridge's capability surface lives in `cap_groups`. There is no
    flat `caps` list and no `homepage` field. `iter_caps()` walks every
    cap across every group in declaration order.

    `channel` is set by the transformer when flattening the channel-
    partitioned registry — every entry knows which channel it lives in.
    """
    id: str
    name: str
    channel: CartridgeChannel
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
    # Registry URL this entry was fetched from. Verbatim string — never
    # trimmed, normalized, or re-derived. Identity comparison is byte
    # equality. Defaults to "" for entries constructed without a known
    # registry (e.g. unit fixtures).
    registry_url: str = ""

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeInfo":
        versions_raw = raw.get("versions", {})
        channel_raw = raw.get("channel")
        if channel_raw not in ("release", "nightly"):
            raise ValueError(
                f"CartridgeInfo {raw.get('id', '?')}: invalid or missing channel {channel_raw!r}"
            )
        return cls(
            id=raw["id"],
            name=raw["name"],
            channel=CartridgeChannel(channel_raw),
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
            registry_url=_null_as_empty_string(raw.get("registryUrl")),
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

    def _build_for_host(self, version: str, host_platform: str) -> Optional[CartridgeBuild]:
        """Find this cartridge's build for `host_platform` within a
        given version, if any."""
        version_data = self.versions.get(version)
        if version_data is None:
            return None
        for build in version_data.builds:
            if build.platform == host_platform:
                return build
        return None

    def resolve_for_host(self, host_platform: str) -> "CartridgeCompatibilityResolution":
        """Resolve which version/package this host should install,
        scanning versions newest-first (`available_versions` is the
        authoritative newest-first ordering). The newest version with a
        host build wins:

          * it IS the latest version → Compatible
          * it is older than the latest → CompatibleOutdated
          * no version has a host build → Incompatible

        "Latest" is `self.version`, not `available_versions[0]`. They
        must agree; if they do not, that is a registry transformer bug,
        and the host build found at `self.version` still classifies as
        Compatible while any other found version classifies as
        CompatibleOutdated. We do not paper over a `self.version` with
        no host build by silently calling it latest.
        """
        latest = self.version

        for ver in self.available_versions:
            build = self._build_for_host(ver, host_platform)
            if build is None:
                continue
            # primary_package() returns None only when the build ships no
            # installer at all — a build entry with an empty packages[]
            # and no legacy package. That is a malformed registry build;
            # skip it rather than resolve to a version the host cannot
            # actually download, and keep scanning older versions.
            pkg = build.primary_package()
            if pkg is None:
                continue
            if ver == latest:
                return CartridgeCompatibilityResolution(
                    status=CompatStatus.COMPATIBLE,
                    host_platform=host_platform,
                    resolved_version=ver,
                    resolved_package=pkg,
                    reason=None,
                )
            return CartridgeCompatibilityResolution(
                status=CompatStatus.COMPATIBLE_OUTDATED,
                host_platform=host_platform,
                resolved_version=ver,
                resolved_package=pkg,
                reason=(
                    f"Latest {latest} has no {host_platform} build; "
                    f"newest compatible is {ver}"
                ),
            )

        return CartridgeCompatibilityResolution(
            status=CompatStatus.INCOMPATIBLE,
            host_platform=host_platform,
            resolved_version=None,
            resolved_package=None,
            reason=f"No installable {host_platform} build available in any version",
        )

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
    channel: CartridgeChannel


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
class CartridgeChannelEntries:
    """One channel's cartridges map. Always present in the parent
    registry, possibly empty."""
    cartridges: Dict[str, CartridgeRegistryEntry] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeChannelEntries":
        cartridges_raw = raw.get("cartridges", {})
        if not isinstance(cartridges_raw, dict):
            raise ValueError("CartridgeChannelEntries.cartridges must be an object")
        return cls(cartridges={
            key: CartridgeRegistryEntry.from_dict(value)
            for key, value in cartridges_raw.items()
        })


@dataclass
class CartridgeRegistryChannels:
    """Per-channel partitioning of the registry. Both channels are
    always present (possibly empty)."""
    release: CartridgeChannelEntries
    nightly: CartridgeChannelEntries

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeRegistryChannels":
        if "release" not in raw or "nightly" not in raw:
            raise ValueError("Registry channels must contain both 'release' and 'nightly'")
        return cls(
            release=CartridgeChannelEntries.from_dict(raw["release"]),
            nightly=CartridgeChannelEntries.from_dict(raw["nightly"]),
        )


@dataclass
class CartridgeRegistry:
    """The v5.0 cartridge registry (channel-partitioned schema)."""
    schema_version: str
    last_updated: str
    channels: CartridgeRegistryChannels

    @classmethod
    def from_dict(cls, raw: dict) -> "CartridgeRegistry":
        return cls(
            schema_version=raw["schemaVersion"],
            last_updated=raw["lastUpdated"],
            channels=CartridgeRegistryChannels.from_dict(raw["channels"]),
        )

    @classmethod
    def from_json(cls, payload: str) -> "CartridgeRegistry":
        return cls.from_dict(json.loads(payload))


@dataclass
class _CartridgeRepoCache:
    """Cached cartridge data keyed by `(channel, id)` so the same id can
    independently coexist in both channels with different metadata."""
    cartridges: Dict[Tuple[CartridgeChannel, str], CartridgeInfo]
    cap_to_cartridges: Dict[str, List[Tuple[CartridgeChannel, str]]]
    last_updated: float
    repo_url: str


class CartridgeRepoError(ValueError):
    pass


class CartridgeRepoServer:
    """Transforms a validated v5.0 channel-partitioned registry into
    flat API responses, preserving channel provenance."""

    def __init__(self, registry: CartridgeRegistry):
        if registry.schema_version != "5.0":
            raise CartridgeRepoError(
                f"Unsupported registry schema version: {registry.schema_version}. Required: 5.0"
            )
        self.registry = registry

    @staticmethod
    def _validate_version_data(
        cartridge_id: str,
        channel: CartridgeChannel,
        version: str,
        version_data: CartridgeVersionData,
    ) -> None:
        if not version_data.builds:
            raise CartridgeRepoError(
                f"Cartridge {cartridge_id} ({channel.value}) v{version}: no builds"
            )
        for index, build in enumerate(version_data.builds):
            if not build.platform:
                raise CartridgeRepoError(
                    f"Cartridge {cartridge_id} ({channel.value}) v{version}: build[{index}] missing platform"
                )
            primary = build.primary_package()
            if primary is None or not primary.name:
                raise CartridgeRepoError(
                    f"Cartridge {cartridge_id} ({channel.value}) v{version}: build[{index}] ({build.platform}) missing package.name"
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

    def _channel_entries(self, channel: CartridgeChannel) -> Dict[str, CartridgeRegistryEntry]:
        if channel is CartridgeChannel.RELEASE:
            return self.registry.channels.release.cartridges
        if channel is CartridgeChannel.NIGHTLY:
            return self.registry.channels.nightly.cartridges
        raise CartridgeRepoError(f"Invalid channel {channel!r}")

    def _entry_to_cartridge_info(
        self,
        channel: CartridgeChannel,
        cartridge_id: str,
        entry: CartridgeRegistryEntry,
    ) -> CartridgeInfo:
        latest_version = entry.latest_version
        version_data = entry.versions.get(latest_version)
        if version_data is None:
            raise CartridgeRepoError(
                f"Cartridge {cartridge_id} ({channel.value}): latestVersion {latest_version} not found in versions"
            )
        self._validate_version_data(cartridge_id, channel, latest_version, version_data)
        available_versions = sorted(
            entry.versions.keys(),
            key=cmp_to_key(lambda a, b: self._compare_versions(b, a)),
        )
        return CartridgeInfo(
            id=cartridge_id,
            name=entry.name,
            channel=channel,
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

    def transform_to_cartridge_array(self) -> List[CartridgeInfo]:
        """Walk both channels and emit a flat list of CartridgeInfo —
        release entries first, then nightly."""
        out: List[CartridgeInfo] = []
        for channel in (CartridgeChannel.RELEASE, CartridgeChannel.NIGHTLY):
            for cartridge_id, entry in self._channel_entries(channel).items():
                out.append(self._entry_to_cartridge_info(channel, cartridge_id, entry))
        return out

    def get_cartridges(self) -> CartridgeRegistryResponse:
        return CartridgeRegistryResponse(cartridges=self.transform_to_cartridge_array())

    def get_cartridge_by_id(
        self,
        channel: CartridgeChannel,
        cartridge_id: str,
    ) -> Optional[CartridgeInfo]:
        """Get a cartridge by `(channel, id)`. Channel is required —
        the same id can independently exist in both channels."""
        entries = self._channel_entries(channel)
        entry = entries.get(cartridge_id)
        if entry is None:
            return None
        return self._entry_to_cartridge_info(channel, cartridge_id, entry)

    def search_cartridges(self, query: str) -> List[CartridgeInfo]:
        """Match query against cartridge name/description/tags and cap
        titles across both channels. Cap URN strings are NOT
        substring-matched: a cap URN is a tagged identifier, not
        free-form text. Use get_cartridges_by_cap for cap lookups."""
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
        """Return cartridges that provide a cap conforming to the
        requested URN.

        The request URN is parsed via CapUrn.from_string. Each declared
        cartridge cap is parsed and matched with `conforms_to`: cap
        dispatch is the partial-order question "does the declared cap
        conform to the requested pattern?". Only `in` and `out` tags
        are functionally meaningful — the `op` tag has no role. A
        malformed input URN raises; a malformed declared URN raises
        too (registry corruption is not a fallback condition).
        """
        requested = CapUrn.from_string(cap_urn)
        result: List[CartridgeInfo] = []
        for cartridge in self.transform_to_cartridge_array():
            for cap in cartridge.iter_caps():
                declared = CapUrn.from_string(cap.urn)
                if declared.conforms_to(requested):
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
        """Index the registry response into the cache, keyed by
        `(channel, id)`.

        The cap-to-cartridges index keys on the *normalized* tagged-URN
        form of each cap URN (parse via CapUrn.from_string, then take
        str()), with `(channel, id)` references so suggestions preserve
        channel provenance. A cap URN that fails to parse is a registry
        corruption: we raise CartridgeRepoError rather than silently
        keep the malformed string in the index.
        """
        cartridges: Dict[Tuple[CartridgeChannel, str], CartridgeInfo] = {}
        cap_to_cartridges: Dict[str, List[Tuple[CartridgeChannel, str]]] = {}

        for cartridge_info in registry.cartridges:
            key = (cartridge_info.channel, cartridge_info.id)
            for cap in cartridge_info.iter_caps():
                try:
                    parsed = CapUrn.from_string(cap.urn)
                except Exception as exc:
                    raise CartridgeRepoError(
                        f"cartridge {cartridge_info.id} ({cartridge_info.channel.value}): "
                        f"invalid cap URN {cap.urn!r}: {exc}"
                    ) from exc
                normalized = str(parsed)
                cap_to_cartridges.setdefault(normalized, []).append(key)
            cartridges[key] = cartridge_info

        self._caches[repo_url] = _CartridgeRepoCache(
            cartridges=cartridges,
            cap_to_cartridges=cap_to_cartridges,
            last_updated=time.time(),
            repo_url=repo_url,
        )

    def get_all_cartridges(self) -> List[Tuple[CartridgeChannel, str, CartridgeInfo]]:
        """Return every cached cartridge as a `(channel, id, info)`
        tuple. Channel is first-class so consumers don't have to look
        it up separately."""
        result: List[Tuple[CartridgeChannel, str, CartridgeInfo]] = []
        for cache in self._caches.values():
            for (channel, cartridge_id), cartridge in cache.cartridges.items():
                result.append((channel, cartridge_id, cartridge))
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

    def get_cartridge(
        self,
        channel: CartridgeChannel,
        cartridge_id: str,
    ) -> Optional[CartridgeInfo]:
        """Get a cartridge by `(channel, id)`. Channel is required —
        the same id can independently exist in both channels with
        separate metadata/versions."""
        key = (channel, cartridge_id)
        for cache in self._caches.values():
            if key in cache.cartridges:
                return cache.cartridges[key]
        return None

    def get_suggestions_for_cap(self, cap_urn: str) -> List[CartridgeSuggestion]:
        """Return suggestions for a cap URN that isn't currently
        available locally.

        `cap_urn` is parsed via CapUrn.from_string; the parsed-and-
        re-serialized form is the canonical key into the cap-to-
        cartridges index. Each candidate's caps are matched on
        `is_equivalent` (suggestion lookup is exact-match URN). A
        malformed input URN logs to stderr and returns no suggestions
        rather than masking the error.
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
            for key in cache.cap_to_cartridges.get(normalized, []):
                cartridge = cache.cartridges[key]
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
                channel, cartridge_id = key
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
                        channel=channel,
                    )
                )
        return suggestions
