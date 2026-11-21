"""Value-based media URN refinement."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from tagged_urn import ConstraintPresent

from capdag.urn.media_urn import MediaUrn


class ValueAdapterError(ValueError):
    """Why a value adapter could not be registered, chosen or believed.

    ``kind`` is one of ``bad-key`` (the key an adapter was registered under is
    no media URN), ``duplicate-key`` (an adapter is already registered under
    an equivalent key), ``ambiguous`` (the base falls under two most specific
    keys, neither of which refines the other), ``bad-refinement`` (the
    adapter's refinement is no media URN) and ``not-inside`` (the adapter's
    refinement does not conform to the base it refines)."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class ValueAdapter:
    """Refines a base media URN when the inspected value matches a predicate."""

    name: str
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
        return actual_base.with_tag(self.refined_marker_tag, ConstraintPresent()).to_string()
