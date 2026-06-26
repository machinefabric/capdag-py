"""Unified cap-based manifest interface

This module defines the unified manifest interface with standardized cap-based declarations.
"""

import json
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from capdag.cap.definition import Cap


@dataclass
class CapGroup:
    """A cap group bundles caps and adapter URNs as an atomic registration unit.

    If any adapter in the group creates ambiguity with an already-registered adapter,
    the entire group is rejected — none of its caps or adapters get registered.
    """

    name: str
    """Group name (for diagnostics and error messages)"""

    caps: List[Cap]
    """Caps in this group"""

    adapter_urns: List[str] = field(default_factory=list)
    """Media URNs this group's adapter handles.
    These are matched via conforms_to during registration — they are not patterns,
    they are declared URNs checked for overlap with existing registrations.
    """

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "name": self.name,
            "caps": [cap.to_dict() for cap in self.caps],
        }
        if self.adapter_urns:
            result["adapter_urns"] = self.adapter_urns
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapGroup":
        return cls(
            name=data["name"],
            caps=[Cap.from_dict(c) for c in data.get("caps", [])],
            adapter_urns=data.get("adapter_urns", []),
        )


def default_group(caps: List[Cap]) -> CapGroup:
    """Wrap caps in a default cap group with no adapter URNs."""
    return CapGroup(name="default", caps=caps)


def registry_url_from_build_env(raw: Optional[str]) -> Optional[str]:
    """Validate ``MFR_CARTRIDGE_REGISTRY_URL`` and return the baked registry URL.

    Valid states:

    - ``None``  => dev build; registry identity is absent and the build
      must use the on-disk ``dev/`` slot.
    - ``Some(s)`` where ``s`` is non-empty => published-registry build.

    Invalid state:

    - ``Some("")`` => caller exported the variable with an empty value.
      This is neither a dev build nor a valid registry identity, and it
      must fail hard so the build cannot silently hash the empty string
      into a fake registry slug. In Rust this is a compile-time
      ``panic!``; here it is a hard ``ValueError`` — there is no
      fallback to a dev build.
    """
    if raw is None:
        return None
    if len(raw) == 0:
        raise ValueError(
            "MFR_CARTRIDGE_REGISTRY_URL must be unset for dev builds or set to a "
            "non-empty registry URL for published builds; empty string is invalid"
        )
    return raw


class CapManifest:
    """Unified cap manifest for component output

    `(name, version, channel)` is the cartridge's full identity.
    Channel is part of the cartridge's identity and is baked in at
    compile/package time (Python cartridges read it from the
    `MFR_CARTRIDGE_CHANNEL` env var at packaging time, mirroring the
    Rust SDK's `env!()` pattern).

    A manifest includes:
    - Component metadata (name, version, channel, description)
    - Cap groups (bundles of caps + adapter URNs)
    - Optional author and page URL
    """

    def __init__(
        self,
        name: str,
        version: str,
        channel: str,
        registry_url: Optional[str],
        description: str,
        cap_groups: List[CapGroup],
    ):
        if channel not in ("release", "nightly"):
            raise ValueError(
                f"CapManifest channel must be 'release' or 'nightly', got '{channel}'"
            )
        self.name = name
        self.version = version
        self.channel = channel
        # Verbatim registry URL the cartridge was built for. ``None``
        # ⇔ dev build (cartridge.sh was invoked without ``--registry``;
        # MFR_CARTRIDGE_REGISTRY_URL env var was unset at compile time).
        self.registry_url = registry_url
        self.description = description
        self.cap_groups = cap_groups
        self.author: Optional[str] = None
        self.page_url: Optional[str] = None

    def all_caps(self) -> List[Cap]:
        """Returns all caps from all cap groups."""
        result = []
        for group in self.cap_groups:
            result.extend(group.caps)
        return result

    def with_author(self, author: str) -> "CapManifest":
        """Set the author of the component"""
        self.author = author
        return self

    def with_page_url(self, page_url: str) -> "CapManifest":
        """Set the page URL for the component"""
        self.page_url = page_url
        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict.

        ``registry_url`` is always emitted (as JSON null for dev
        builds), never elided — the consumer's required-but-nullable
        check would reject an absent key.
        """
        result: Dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "channel": self.channel,
            "registry_url": self.registry_url,
            "description": self.description,
            "cap_groups": [g.to_dict() for g in self.cap_groups],
        }

        if self.author is not None:
            result["author"] = self.author

        if self.page_url is not None:
            result["page_url"] = self.page_url

        return result

    def to_json(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CapManifest":
        """Parse from dict. ``channel`` and ``registry_url`` are both
        required (``registry_url`` may be null) — a manifest without
        either key is a build/publish-pipeline bug we surface
        immediately. Old-schema cartridge SDKs that omit
        ``registry_url`` get rejected here."""
        if "registry_url" not in data:
            raise ValueError(
                "CapManifest is missing required `registry_url` field. "
                "It must be present, with value null for dev builds or "
                "a URL string for registry builds."
            )
        manifest = cls(
            name=data["name"],
            version=data["version"],
            channel=data["channel"],
            registry_url=data["registry_url"],
            description=data["description"],
            cap_groups=[CapGroup.from_dict(g) for g in data["cap_groups"]],
        )

        if "author" in data:
            manifest.author = data["author"]

        if "page_url" in data:
            manifest.page_url = data["page_url"]

        return manifest

    @classmethod
    def from_json(cls, json_str: str) -> "CapManifest":
        """Parse from JSON string"""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def validate(self) -> None:
        """Validate that this manifest has CAP_IDENTITY.
        Checks caps within cap_groups.

        Raises ValueError if identity cap is missing.
        """
        from capdag.urn.cap_urn import CapUrn
        from capdag.standard.caps import CAP_IDENTITY

        identity_urn = CapUrn.from_string(CAP_IDENTITY)
        has_identity = any(identity_urn.conforms_to(cap.urn) for cap in self.all_caps())
        if not has_identity:
            raise ValueError(f"Manifest missing required CAP_IDENTITY ({CAP_IDENTITY})")

    def ensure_identity(self) -> "CapManifest":
        """Ensure CAP_IDENTITY is present in this manifest. Adds it if missing.

        Returns self for method chaining.
        """
        from capdag.urn.cap_urn import CapUrn
        from capdag.standard.caps import CAP_IDENTITY

        identity_urn = CapUrn.from_string(CAP_IDENTITY)
        has_identity = any(identity_urn.conforms_to(cap.urn) for cap in self.all_caps())

        if not has_identity:
            identity_cap = Cap(
                urn=identity_urn,
                title="Identity",
                command="identity"
            )
            self.cap_groups.insert(0, default_group([identity_cap]))

        return self
