"""Plan builder — constructs execution plans from resolved paths.

This module provides MachinePlanBuilder which takes a Strand
(from the live cap graph) and builds a MachinePlan DAG.
Mirrors Rust's planner/plan_builder.rs exactly.

Key types:
- ArgumentResolution: how an argument will be resolved at execution time
- ArgumentInfo: full argument metadata for one cap arg
- StepArgumentRequirements: all argument info for one step in a path
- PathArgumentRequirements: all argument info for an entire path
- MachinePlanBuilder: builds execution plans from paths
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from capdag.cap.definition import Cap, StdinSource
from capdag.cap.registry import CapRegistry
from capdag.media.registry import MediaUrnRegistry
from capdag.media.spec import resolve_media_urn
from capdag.urn.media_urn import MediaUrn
from capdag.planner.argument_binding import ArgumentBinding, ArgumentBindings
from capdag.planner.cardinality import InputCardinality
from capdag.planner.error import (
    InternalError, InvalidPathError, NotFoundError, RegistryError,
)
from capdag.planner.live_cap_graph import Strand, StrandStep, StrandStepType
from capdag.planner.plan import MachinePlanEdge, MachinePlan, MachineNode


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
        "default_value", "is_required", "validation",
    )

    def __init__(
        self,
        name: str,
        media_urn: str,
        description: str,
        resolution: ArgumentResolution,
        default_value: Optional[Any] = None,
        is_required: bool = True,
        validation: Optional[Any] = None,
    ) -> None:
        self.name = name
        self.media_urn = media_urn
        self.description = description
        self.resolution = resolution
        self.default_value = default_value
        self.is_required = is_required
        self.validation = validation

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "media_urn": self.media_urn,
            "description": self.description,
            "resolution": self.resolution.value,
            "is_required": self.is_required,
        }
        if self.default_value is not None:
            d["default_value"] = self.default_value
        if self.validation is not None:
            d["validation"] = self.validation
        return d

    def __repr__(self) -> str:
        return f"ArgumentInfo(name={self.name!r}, resolution={self.resolution.value})"


class StepArgumentRequirements:
    """Argument requirements for one step in a path."""

    __slots__ = ("cap_urn", "step_index", "title", "arguments", "slots")

    def __init__(
        self,
        cap_urn: str,
        step_index: int,
        title: str,
        arguments: List[ArgumentInfo],
        slots: List[ArgumentInfo],
    ) -> None:
        self.cap_urn = cap_urn
        self.step_index = step_index
        self.title = title
        self.arguments = arguments
        self.slots = slots

    def to_dict(self) -> Dict[str, Any]:
        return {
            "cap_urn": self.cap_urn,
            "step_index": self.step_index,
            "title": self.title,
            "arguments": [a.to_dict() for a in self.arguments],
            "slots": [s.to_dict() for s in self.slots],
        }

    def __repr__(self) -> str:
        return f"StepArgumentRequirements(cap_urn={self.cap_urn!r}, slots={len(self.slots)})"


class PathArgumentRequirements:
    """Argument requirements for an entire path."""

    __slots__ = ("source_spec", "target_spec", "steps", "can_execute_without_input")

    def __init__(
        self,
        source_spec: str,
        target_spec: str,
        steps: List[StepArgumentRequirements],
        can_execute_without_input: bool,
    ) -> None:
        self.source_spec = source_spec
        self.target_spec = target_spec
        self.steps = steps
        self.can_execute_without_input = can_execute_without_input

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_spec": self.source_spec,
            "target_spec": self.target_spec,
            "steps": [s.to_dict() for s in self.steps],
            "can_execute_without_input": self.can_execute_without_input,
        }

    def __repr__(self) -> str:
        return (
            f"PathArgumentRequirements(steps={len(self.steps)}, "
            f"can_execute={self.can_execute_without_input})"
        )


class MachinePlanBuilder:
    """Builds execution plans from resolved paths.

    Takes a Strand (from live cap graph) and constructs
    a MachinePlan DAG ready for execution.
    """

    def __init__(self, cap_registry: CapRegistry, media_registry: MediaUrnRegistry) -> None:
        self._cap_registry = cap_registry
        self._media_registry = media_registry

    @staticmethod
    def _find_file_path_arg(cap: Cap) -> Optional[str]:
        """Find the first argument that is a file-path type media URN."""
        for arg in cap.get_args():
            try:
                media_urn = MediaUrn.from_string(arg.media_urn)
                if media_urn.is_any_file_path():
                    return arg.media_urn
            except Exception:
                continue
        return None

    @staticmethod
    def _is_file_path_stdin_chainable(cap: Cap) -> bool:
        """Check if the cap's file-path arg accepts stdin with matching in_spec."""
        in_spec = cap.urn.in_spec()
        for arg in cap.get_args():
            try:
                media_urn = MediaUrn.from_string(arg.media_urn)
                if not media_urn.is_any_file_path():
                    continue
            except Exception:
                continue

            for source in arg.sources:
                if isinstance(source, StdinSource):
                    if source.stdin_media_urn() == in_spec:
                        return True
        return False

    async def build_plan_from_path(
        self,
        name: str,
        path: Strand,
        input_cardinality: InputCardinality,
    ) -> MachinePlan:
        """Build an execution plan from a resolved path."""
        plan = MachinePlan(name)

        try:
            caps = await self._cap_registry.get_cached_caps()
        except Exception as e:
            raise RegistryError(f"Failed to get cached caps: {e}")

        # Build file-path info: cap_urn -> (file_path_arg_name, stdin_chainable)
        file_path_info: Dict[str, Tuple[Optional[str], bool]] = {}
        for step in path.steps:
            cap_urn = step.cap_urn()
            if cap_urn is None:
                continue
            cap_urn_str = str(cap_urn)
            cap = next((c for c in caps if str(c.urn) == cap_urn_str), None)
            if cap is not None:
                file_path_info[cap_urn_str] = (
                    self._find_file_path_arg(cap),
                    self._is_file_path_stdin_chainable(cap),
                )

        source_spec_str = str(path.source_spec)
        input_slot_id = "input_slot"
        plan.add_node(MachineNode.input_slot(input_slot_id, "input", source_spec_str, input_cardinality))

        prev_node_id = input_slot_id
        cap_step_count = 0
        inside_foreach_body: Optional[Tuple[int, str]] = None  # (foreach_step_index, foreach_node_id)
        body_entry: Optional[str] = None
        body_exit: Optional[str] = None

        for i, step in enumerate(path.steps):
            node_id = f"step_{i}"

            if step.step_type.kind == StrandStepType.CAP:
                cap_urn_str = str(step.step_type.cap_urn_val)
                bindings = ArgumentBindings()

                cap = next((c for c in caps if str(c.urn) == cap_urn_str), None)
                in_spec = cap.urn.in_spec() if cap else ""
                out_spec = cap.urn.out_spec() if cap else ""
                is_inside_body = inside_foreach_body is not None

                # File-path arg binding
                info = file_path_info.get(cap_urn_str)
                if info is not None:
                    arg_name, stdin_chainable = info
                    if arg_name is not None:
                        if cap_step_count == 0 and not is_inside_body:
                            bindings.add_file_path(arg_name)
                        elif stdin_chainable:
                            bindings.add(
                                arg_name,
                                ArgumentBinding.previous_output(prev_node_id),
                            )
                        else:
                            bindings.add_file_path(arg_name)

                # Slot bindings for non-I/O args
                if cap is not None:
                    for arg in cap.get_args():
                        if arg.media_urn == in_spec or arg.media_urn == out_spec:
                            continue
                        try:
                            mu = MediaUrn.from_string(arg.media_urn)
                            if mu.is_any_file_path():
                                continue
                        except Exception:
                            pass
                        if arg.media_urn in bindings.bindings:
                            continue
                        bindings.add(
                            arg.media_urn,
                            ArgumentBinding.slot(arg.media_urn),
                        )

                plan.add_node(MachineNode.cap_with_bindings(node_id, cap_urn_str, bindings))
                plan.add_edge(MachinePlanEdge.direct(prev_node_id, node_id))

                if is_inside_body:
                    if body_entry is None:
                        body_entry = node_id
                    body_exit = node_id
                else:
                    cap_step_count += 1

            elif step.step_type.kind == StrandStepType.FOR_EACH:
                # If already inside a ForEach body (nested), finalize the outer ForEach
                if inside_foreach_body is not None:
                    outer_foreach_idx, outer_foreach_node_id = inside_foreach_body
                    outer_entry = body_entry if body_entry is not None else prev_node_id
                    outer_exit = body_exit if body_exit is not None else prev_node_id
                    outer_foreach_input = (
                        input_slot_id if outer_foreach_idx == 0
                        else f"step_{outer_foreach_idx - 1}"
                    )

                    if body_entry is None:
                        raise InvalidPathError(
                            f"Nested ForEach at step[{i}] but outer ForEach at "
                            f"step[{outer_foreach_idx}] ('{outer_foreach_node_id}') has no body caps."
                        )
                    if outer_foreach_input == outer_entry:
                        raise InvalidPathError(
                            f"Outer ForEach at step[{outer_foreach_idx}] "
                            f"('{outer_foreach_node_id}') would create a cycle"
                        )

                    plan.add_node(MachineNode.for_each(
                        outer_foreach_node_id, outer_foreach_input, outer_entry, outer_exit))
                    plan.add_edge(MachinePlanEdge.direct(outer_foreach_input, outer_foreach_node_id))
                    plan.add_edge(MachinePlanEdge.iteration(outer_foreach_node_id, outer_entry))
                    prev_node_id = outer_exit

                inside_foreach_body = (i, node_id)
                body_entry = None
                body_exit = None
                continue  # skip prev_node_id = node_id

            elif step.step_type.kind == StrandStepType.COLLECT:
                if inside_foreach_body is not None:
                    foreach_idx, foreach_node_id = inside_foreach_body
                    entry = body_entry if body_entry is not None else prev_node_id
                    exit_node = body_exit if body_exit is not None else prev_node_id
                    foreach_input = (
                        input_slot_id if foreach_idx == 0
                        else f"step_{foreach_idx - 1}"
                    )

                    plan.add_node(MachineNode.for_each(
                        foreach_node_id, foreach_input, entry, exit_node))
                    plan.add_edge(MachinePlanEdge.direct(foreach_input, foreach_node_id))
                    plan.add_edge(MachinePlanEdge.iteration(foreach_node_id, entry))

                    plan.add_node(MachineNode.collect(node_id, [exit_node]))
                    plan.add_edge(MachinePlanEdge.collection(exit_node, node_id))

                    inside_foreach_body = None
                    body_entry = None
                    body_exit = None
                else:
                    raise InvalidPathError("Collect step without matching ForEach")

            elif step.step_type.kind == StrandStepType.WRAP_IN_LIST:
                plan.add_node(MachineNode.wrap_in_list(
                    node_id,
                    str(step.step_type.item_spec),
                    str(step.step_type.list_spec),
                ))
                plan.add_edge(MachinePlanEdge.direct(prev_node_id, node_id))

            prev_node_id = node_id

        # Handle unclosed ForEach at end of loop
        if inside_foreach_body is not None:
            foreach_idx, foreach_node_id = inside_foreach_body
            has_body_entry = body_entry is not None
            entry = body_entry if body_entry is not None else prev_node_id
            exit_node = body_exit if body_exit is not None else prev_node_id
            foreach_input = (
                input_slot_id if foreach_idx == 0
                else f"step_{foreach_idx - 1}"
            )

            if has_body_entry:
                if foreach_input == entry:
                    raise InvalidPathError(
                        f"ForEach at step[{foreach_idx}] ('{foreach_node_id}') "
                        f"would create a cycle"
                    )
                plan.add_node(MachineNode.for_each(
                    foreach_node_id, foreach_input, entry, exit_node))
                plan.add_edge(MachinePlanEdge.direct(foreach_input, foreach_node_id))
                plan.add_edge(MachinePlanEdge.iteration(foreach_node_id, entry))
                prev_node_id = exit_node

        # Output node
        plan.add_node(MachineNode.output("output", "result", prev_node_id))
        plan.add_edge(MachinePlanEdge.direct(prev_node_id, "output"))

        # Metadata
        plan.metadata = {
            "source_spec": source_spec_str,
            "target_spec": str(path.target_spec),
        }

        # Validate
        plan.validate()
        try:
            plan.topological_order()
        except InternalError as e:
            raise InvalidPathError(f"Plan has cycle: {e.message}")

        return plan

    async def analyze_path_arguments(
        self,
        path: Strand,
    ) -> PathArgumentRequirements:
        """Analyze all argument requirements for a path."""
        try:
            caps = await self._cap_registry.get_cached_caps()
        except Exception as e:
            raise RegistryError(f"Failed to get cached caps: {e}")

        step_requirements: List[StepArgumentRequirements] = []
        cap_step_index = 0

        for i, step in enumerate(path.steps):
            cap_urn = step.cap_urn()
            if cap_urn is None:
                continue

            cap_urn_str = str(cap_urn)
            cap = next((c for c in caps if str(c.urn) == cap_urn_str), None)
            if cap is None:
                raise NotFoundError(f"Cap not found: {cap_urn_str}")

            in_spec = cap.urn.in_spec()
            out_spec = cap.urn.out_spec()
            arguments: List[ArgumentInfo] = []
            slots: List[ArgumentInfo] = []

            for arg in cap.get_args():
                resolution = self._determine_resolution_with_io_check(
                    arg.media_urn, in_spec, out_spec,
                    cap_step_index, arg.required, arg.default_value,
                )

                # Resolve media validation
                validation_json: Optional[Any] = None
                try:
                    resolved_spec = await resolve_media_urn(
                        arg.media_urn,
                        cap.media_specs if cap.media_specs else None,
                        self._media_registry,
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
                step_index=i,
                title=step.title(),
                arguments=arguments,
                slots=slots,
            ))
            cap_step_index += 1

        return PathArgumentRequirements(
            source_spec=str(path.source_spec),
            target_spec=str(path.target_spec),
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
            if mu.is_any_file_path():
                if step_index == 0:
                    return ArgumentResolution.FROM_INPUT_FILE
                return ArgumentResolution.FROM_PREVIOUS_OUTPUT
        except Exception:
            pass

        # 4. Default or user input
        if default_value is not None:
            return ArgumentResolution.HAS_DEFAULT
        return ArgumentResolution.REQUIRES_USER_INPUT
