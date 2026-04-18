"""Value-based media URN refinement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from capdag.urn.media_urn import MediaUrn


@dataclass(frozen=True)
class ValueAdapter:
    """Refines a base media URN when the inspected value matches a predicate."""

    base_media_urn: str
    refined_marker_tag: str
    value_matches: Callable[[str], bool]

    def refine(self, base_media_urn: str, value: str) -> Optional[str]:
        """Return a refined URN when both base URN and value match."""
        adapter_base = MediaUrn.from_string(self.base_media_urn)
        actual_base = MediaUrn.from_string(base_media_urn)
        if not actual_base.conforms_to(adapter_base):
            return None
        if not self.value_matches(value):
            return None
        return actual_base.with_tag(self.refined_marker_tag, "*").to_string()
