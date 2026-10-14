"""What the steps of a plan are given, and by what.

The model of a plan's argument requirements, mirroring the reference's
``planner::plan_builder``. The analysis that produces it reads a plan, and
plans are built by the reference only (15.2): this module carries the model
and the helpers the reference shares with it.

Key types:
- ArgumentResolution: where an argument gets its value in a run
- ArgumentInfo: full argument metadata for one cap arg
- StepArgumentRequirements: all argument info for one step of a plan
- PlanArgumentRequirements: all argument info for a whole plan
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from capdag.cap.definition import Cap
from capdag.fabric.registry import FabricRegistry


class ArgumentResolution(Enum):
    """Where a step's argument gets its value in a run of a plan."""
    # Wired from an input of the machine (through a map's item or a gather of
    # inputs, when it is reached through one).
    FROM_INPUT = "from_input"
    # Wired from what another step produces.
    FROM_STEP = "from_step"
    # Bound to a constant the machine writes.
    CONSTANT = "constant"
    # Not bound by the machine; its definition gives a default.
    HAS_DEFAULT = "has_default"
    # Not bound by the machine and no default: the run supplies it.
    REQUIRES_USER_INPUT = "requires_user_input"

    def is_bound(self) -> bool:
        """Whether the machine itself binds the arg. A bound arg takes no value
        from the run."""
        return self in (
            ArgumentResolution.FROM_INPUT,
            ArgumentResolution.FROM_STEP,
            ArgumentResolution.CONSTANT,
        )


class ArgumentInfo:
    """Full argument metadata for one cap argument. ``name`` is the arg's name in
    its cap definition: a label, unique within the cap."""

    __slots__ = (
        "name", "media_urn", "description", "resolution",
        "default_value", "is_required", "is_sequence", "is_main_input",
        "validation",
    )

    def __init__(
        self,
        name: str,
        media_urn: str,
        description: str,
        resolution: ArgumentResolution,
        default_value: Optional[Any] = None,
        is_required: bool = True,
        is_sequence: bool = False,
        validation: Optional[Any] = None,
        is_main_input: bool = False,
    ) -> None:
        self.name = name
        self.media_urn = media_urn
        self.description = description
        self.resolution = resolution
        self.default_value = default_value
        self.is_required = is_required
        self.is_sequence = is_sequence
        # Whether this argument is the cap's MAIN input: it declares a
        # Stdin source whose URN is tagged-URN-equivalent to the cap URN's
        # in= spec. Mirrors Rust
        # planner::plan_builder::ArgumentInfo::is_main_input.
        self.is_main_input = is_main_input
        self.validation = validation

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "media_urn": self.media_urn,
            "description": self.description,
            "resolution": self.resolution.value,
            "is_required": self.is_required,
            "is_sequence": self.is_sequence,
            "is_main_input": self.is_main_input,
        }
        if self.default_value is not None:
            d["default_value"] = self.default_value
        if self.validation is not None:
            d["validation"] = self.validation
        return d

    def __repr__(self) -> str:
        return f"ArgumentInfo(name={self.name!r}, resolution={self.resolution.value})"


class StepArgumentRequirements:
    """Argument requirements for one step of a plan.

    ``token_id`` is the token of the plan's cap node these requirements describe
    — the ONLY address an argument value is ever bound to. A token exists
    because a plan exists; it is never derived from a position, a notation
    string, or anything else. Positions cannot address a step because a plan is
    a DAG: parallel branches merging downstream have no ordinal, and two
    identical caps on separate branches differ only by token. ``slots`` are the
    arguments the machine does not bind: the ones a run may give a value (and
    must, when they have no default).
    """

    __slots__ = ("cap_urn", "token_id", "title", "arguments", "slots")

    def __init__(
        self,
        cap_urn: str,
        token_id: str,
        title: str,
        arguments: List[ArgumentInfo],
        slots: List[ArgumentInfo],
    ) -> None:
        self.cap_urn = cap_urn
        self.token_id = token_id
        self.title = title
        self.arguments = arguments
        self.slots = slots

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cap_urn": self.cap_urn,
            "token_id": self.token_id,
            "title": self.title,
            "arguments": [a.to_dict() for a in self.arguments],
            "slots": [s.to_dict() for s in self.slots],
        }

    def __repr__(self) -> str:
        return f"StepArgumentRequirements(cap_urn={self.cap_urn!r}, slots={len(self.slots)})"


class PlanArgumentRequirements:
    """Argument requirements for a whole plan: one entry per cap node, in the
    plan's topological order. ``can_execute_without_input`` says whether a run
    needs no value from the user: every required arg the machine leaves
    unbound has a default."""

    __slots__ = ("steps", "can_execute_without_input")

    def __init__(
        self,
        steps: List[StepArgumentRequirements],
        can_execute_without_input: bool,
    ) -> None:
        self.steps = steps
        self.can_execute_without_input = can_execute_without_input

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "can_execute_without_input": self.can_execute_without_input,
        }

    def __repr__(self) -> str:
        return (
            f"PlanArgumentRequirements(steps={len(self.steps)}, "
            f"can_execute={self.can_execute_without_input})"
        )


class MachinePlanBuilder:
    """The helpers the reference's plan builder shares with this mirror:
    duplicate-cap detection and the presentation of media validation."""

    def __init__(self, fabric_registry: FabricRegistry) -> None:
        self._fabric_registry = fabric_registry

    @staticmethod
    def check_for_duplicate_caps(caps: List[Cap]) -> int:
        """Simulate graph-building duplicate detection logic from the reference implementation."""
        seen_edges = set()
        edge_count = 0

        for cap in caps:
            input_spec = str(cap.urn.in_spec())
            output_spec = str(cap.urn.out_spec())

            if not input_spec or not output_spec:
                continue

            cap_urn = str(cap.urn)
            edge_key = (input_spec, cap_urn)
            if edge_key in seen_edges:
                raise ValueError(
                    f"Duplicate cap_urn detected: {cap_urn} (input_spec: {input_spec})"
                )
            seen_edges.add(edge_key)
            edge_count += 1

        return edge_count

    @classmethod
    def new_for_test(cls, fabric_registry: FabricRegistry) -> "MachinePlanBuilder":
        """Create a test builder backed by the supplied unified registry."""
        return cls(fabric_registry)

    @staticmethod
    def _validation_to_json(validation: Any) -> Optional[Any]:
        """Convert MediaValidation to JSON if it has constraints."""
        if validation is None:
            return None
        has_constraints = (
            getattr(validation, 'min', None) is not None or
            getattr(validation, 'max', None) is not None or
            getattr(validation, 'min_length', None) is not None or
            getattr(validation, 'max_length', None) is not None or
            getattr(validation, 'pattern', None) is not None or
            getattr(validation, 'allowed_values', None) is not None
        )
        if not has_constraints:
            return None
        d: Dict[str, Any] = {}
        for attr in ('min', 'max', 'min_length', 'max_length', 'pattern', 'allowed_values'):
            val = getattr(validation, attr, None)
            if val is not None:
                d[attr] = val
        return d

    @staticmethod
    def validation_to_json(validation: Any) -> Optional[Any]:
        """Public alias matching the reference API used by parity tests."""
        return MachinePlanBuilder._validation_to_json(validation)
