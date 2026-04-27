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
        """Convert to JSON-serializable dict"""
        result: Dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "channel": self.channel,
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
        """Parse from dict. Channel is required — there is no default;
        a manifest without `channel` is a build/publish-pipeline bug
        we want to surface immediately."""
        manifest = cls(
            name=data["name"],
            version=data["version"],
            channel=data["channel"],
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
