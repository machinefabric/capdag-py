"""Plan builder — what the steps of a resolved path need to be given.

This module provides MachinePlanBuilder, which takes a Strand (from the live
capfab) and says, step by step, which arguments a run must supply.

Key types:
- ArgumentResolution: how an argument will be resolved at execution time
- ArgumentInfo: full argument metadata for one cap arg
- StepArgumentRequirements: all argument info for one step in a path
- PathArgumentRequirements: all argument info for an entire path
- MachinePlanBuilder: analyzes the argument requirements of paths
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from capdag.cap.definition import Cap
from capdag.fabric.registry import FabricRegistry
from capdag.media.spec import resolve_media_urn
from capdag.urn.media_urn import MediaUrn
from capdag.planner.error import InvalidPathError, NotFoundError, FabricRegistryError
from capdag.planner.live_cap_fab import Strand, StrandStep


class ArgumentResolution(Enum):
    """How an argument will be resolved at execution time."""
    FROM_INPUT_FILE = "from_input_file"
    FROM_PREVIOUS_OUTPUT = "from_previous_output"
    HAS_DEFAULT = "has_default"
    REQUIRES_USER_INPUT = "requires_user_input"


class ArgumentInfo:
    """Full argument metadata for one cap argument."""

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
        # in= spec. Populated from CapArg.is_main_input during
        # step-argument-requirements assembly. Mirrors Rust
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
    """Argument requirements for one step in a path.

    ``token_id`` is the planner-minted ``StrandStep.token_id`` of the step these
    requirements describe — the ONLY address an argument value is ever bound to.
    A token exists because a plan exists; it is never derived from a position, a
    notation string, or anything else. Positions cannot address a step because a
    strand is a DAG: parallel branches merging downstream have no ordinal, and
    two identical caps on separate branches differ only by token.
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


class PathArgumentRequirements:
    """Argument requirements for an entire path."""

    __slots__ = ("source_media_urn", "target_media_urn", "steps", "can_execute_without_input")

    def __init__(
        self,
        source_media_urn: str,
        target_media_urn: str,
        steps: List[StepArgumentRequirements],
        can_execute_without_input: bool,
    ) -> None:
        self.source_media_urn = source_media_urn
        self.target_media_urn = target_media_urn
        self.steps = steps
        self.can_execute_without_input = can_execute_without_input

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_media_urn": self.source_media_urn,
            "target_media_urn": self.target_media_urn,
            "steps": [s.to_dict() for s in self.steps],
            "can_execute_without_input": self.can_execute_without_input,
        }

    def __repr__(self) -> str:
        return (
            f"PathArgumentRequirements(steps={len(self.steps)}, "
            f"can_execute={self.can_execute_without_input})"
        )


class MachinePlanBuilder:
    """Analyzes resolved paths against the registry's cap definitions.

    Takes a Strand (from live capfab) and reports the argument requirements
    of each of its steps.
    """

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

    async def analyze_path_arguments(
        self,
        path: Strand,
    ) -> PathArgumentRequirements:
        """Analyze all argument requirements for a path."""
        try:
            caps = await self._fabric_registry.get_cached_caps()
        except Exception as e:
            raise FabricRegistryError(f"Failed to get cached caps: {e}")

        step_requirements: List[StepArgumentRequirements] = []
        cap_step_index = 0

        for step in path.steps:
            cap_urn = step.get_cap_urn()
            if cap_urn is None:
                continue

            cap_urn_str = str(cap_urn)
            # A cap step without a token is not addressable, so no argument
            # could ever be delivered to it. Every step a planner creates is
            # minted with one, which means an empty token here can only come
            # from deserializing something that was never a plan. Refuse it at
            # the boundary rather than emitting requirements the caller cannot
            # bind a value to.
            if not step.token_id:
                raise InvalidPathError(
                    f"strand step for cap '{cap_urn_str}' carries no token_id; "
                    "argument requirements are addressed by token and cannot be "
                    "built for an unidentified step"
                )
            cap = next((c for c in caps if str(c.urn) == cap_urn_str), None)
            if cap is None:
                raise NotFoundError(f"Cap not found: {cap_urn_str}")

            in_spec = cap.urn.in_spec()
            out_spec = cap.urn.out_spec()
            # Parse the cap's in= spec once for main-input detection. A
            # spec that fails to parse yields None, and no arg can be the
            # main input of an unparseable in=.
            try:
                in_spec_urn: Optional[MediaUrn] = MediaUrn.from_string(in_spec)
            except Exception:
                in_spec_urn = None
            arguments: List[ArgumentInfo] = []
            slots: List[ArgumentInfo] = []

            for arg in cap.get_args():
                resolution = self._determine_resolution_with_io_check(
                    arg.media_urn, in_spec, out_spec,
                    cap_step_index, arg.required, arg.default_value,
                )

                # Resolve media validation through the registry. Caps no
                # longer carry inline media definitions.
                validation_json: Optional[Any] = None
                try:
                    resolved_spec = await resolve_media_urn(
                        arg.media_urn,
                        self._fabric_registry,
                    )
                    if resolved_spec.validation is not None:
                        validation_json = self._validation_to_json(resolved_spec.validation)
                except Exception:
                    pass

                arg_info = ArgumentInfo(
                    name=arg.media_urn,
                    media_urn=arg.media_urn,
                    description=arg.arg_description or "",
                    resolution=resolution,
                    default_value=arg.default_value,
                    is_required=arg.required,
                    validation=validation_json,
                    is_main_input=(
                        in_spec_urn is not None and arg.is_main_input(in_spec_urn)
                    ),
                )

                is_io_arg = resolution in (
                    ArgumentResolution.FROM_INPUT_FILE,
                    ArgumentResolution.FROM_PREVIOUS_OUTPUT,
                )
                if not is_io_arg:
                    slots.append(arg_info)

                arguments.append(arg_info)

            step_requirements.append(StepArgumentRequirements(
                cap_urn=cap_urn_str,
                token_id=step.token_id,
                title=step.title(),
                arguments=arguments,
                slots=slots,
            ))
            cap_step_index += 1

        return PathArgumentRequirements(
            source_media_urn=str(path.source_media_urn),
            target_media_urn=str(path.target_media_urn),
            steps=step_requirements,
            can_execute_without_input=all(len(s.slots) == 0 for s in step_requirements),
        )

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

    def _determine_resolution_with_io_check(
        self,
        media_urn: str,
        in_spec: str,
        out_spec: str,
        step_index: int,
        _is_required: bool,
        default_value: Optional[Any],
    ) -> ArgumentResolution:
        """Determine how an argument will be resolved.

        Priority: I/O match → file-path type → default → user input.
        """
        # 1. Input spec match
        if media_urn == in_spec:
            if step_index == 0:
                return ArgumentResolution.FROM_INPUT_FILE
            return ArgumentResolution.FROM_PREVIOUS_OUTPUT

        # 2. Output spec match
        if media_urn == out_spec:
            return ArgumentResolution.FROM_PREVIOUS_OUTPUT

        # 3. File-path type
        try:
            mu = MediaUrn.from_string(media_urn)
            if mu.is_file_path():
                if step_index == 0:
                    return ArgumentResolution.FROM_INPUT_FILE
                return ArgumentResolution.FROM_PREVIOUS_OUTPUT
        except Exception:
            pass

        # 4. Default or user input
        if default_value is not None:
            return ArgumentResolution.HAS_DEFAULT
        return ArgumentResolution.REQUIRES_USER_INPUT

    def determine_resolution_with_io_check(
        self,
        media_urn: str,
        in_spec: str,
        out_spec: str,
        step_index: int,
        is_required: bool,
        default_value: Optional[Any],
    ) -> ArgumentResolution:
        """Public alias matching the reference API used by parity tests."""
        return self._determine_resolution_with_io_check(
            media_urn,
            in_spec,
            out_spec,
            step_index,
            is_required,
            default_value,
        )
