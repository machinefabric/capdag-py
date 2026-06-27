"""Orchestrator executor — progress mapping primitives.

Mirrors Rust's orchestrator/executor.rs progress subdivision logic.

A ``CapProgressFn`` is a callable with signature
``(progress: float, cap_urn: str, msg: str) -> None`` where ``progress``
is in [0.0, 1.0].
"""

from __future__ import annotations

from typing import Callable

# Callback for reporting per-cap progress.
# Parameters: (progress 0.0-1.0, cap URN string, human-readable message)
CapProgressFn = Callable[[float, str, str], None]


def _clamp(value: float, low: float, high: float) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return value


def map_progress(child_progress: float, base: float, weight: float) -> float:
    """Map child progress [0.0, 1.0] into parent range [base, base + weight].

    This is the canonical progress mapping formula. Every place in the system
    that subdivides progress must use this function — no ad-hoc derivations.

    All child progress values are clamped to [0.0, 1.0] before mapping.
    The mapped result is ``base + clamp(child_progress, 0.0, 1.0) * weight``.
    """
    return base + _clamp(child_progress, 0.0, 1.0) * weight


class ProgressMapper:
    """Wraps a ``CapProgressFn`` with a progress range subdivision."""

    def __init__(self, parent: CapProgressFn, base: float, weight: float) -> None:
        """Create a mapper that maps child [0.0, 1.0] into parent [base, base + weight]."""
        self.base = base
        self.weight = weight
        self.parent = parent

    def report(self, child_progress: float, cap_urn: str, msg: str) -> None:
        """Report child progress. The value is clamped to [0.0, 1.0] and mapped."""
        overall = map_progress(child_progress, self.base, self.weight)
        self.parent(overall, cap_urn, msg)

    def as_cap_progress_fn(self) -> CapProgressFn:
        """Convert into a ``CapProgressFn`` for passing to APIs that expect one."""

        def _fn(p: float, cap_urn: str, msg: str) -> None:
            self.report(p, cap_urn, msg)

        return _fn

    def sub_mapper(self, sub_base: float, sub_weight: float) -> "ProgressMapper":
        """Create a sub-mapper that maps a child range within this mapper's range.

        Example: if this mapper maps to [0.2, 0.8] (base=0.2, weight=0.6),
        and you create a sub-mapper with sub_base=0.5, sub_weight=0.5,
        the sub-mapper maps to [0.5, 0.8] in the parent's coordinate space.
        """
        return ProgressMapper(
            self.parent,
            self.base + sub_base * self.weight,
            sub_weight * self.weight,
        )
