"""Plan executor — executes cap execution plans.

This module provides MachineExecutor which takes a MachinePlan
and executes it node-by-node in topological order.
Mirrors Rust's planner/executor.rs exactly.

Key types:
- CapExecutor: protocol for executing individual caps
- CapSettingsProvider: protocol for providing cap settings
- MachineExecutor: executes a complete plan
- apply_edge_type(): applies edge transformations to data
- extract_json_path(): navigates JSON by dot-separated paths
"""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from capdag.cap.caller import CapArgumentValue
from capdag.cap.definition import Cap, StdinSource
from capdag.planner.argument_binding import (
    ArgumentBinding, ArgumentBindings, ArgumentResolutionContext,
    ArgumentSource, CapInputFile, resolve_binding,
)
from capdag.planner.error import InternalError, ExecutionError
from capdag.planner.plan import (
    MachineResult, MachinePlanEdge, MachinePlan, MachineNode,
    EdgeType, ExecutionNodeType, NodeExecutionResult,
)
from capdag.urn.media_urn import MEDIA_FILE_PATH


class CapExecutor(ABC):
    """Protocol for executing individual caps."""

    @abstractmethod
    async def execute_cap(
        self,
        cap_urn: str,
        arguments: List[CapArgumentValue],
        preferred_cap: Optional[str] = None,
    ) -> bytes:
        """Execute a cap and return raw output bytes."""
        ...

    @abstractmethod
    async def has_cap(self, cap_urn: str) -> bool:
        """Check if a cap is available."""
        ...

    @abstractmethod
    async def get_cap(self, cap_urn: str) -> Cap:
        """Get the cap definition."""
        ...


class CapSettingsProvider(ABC):
    """Protocol for providing cap settings overrides."""

    @abstractmethod
    async def get_settings(self, cap_urn: str) -> Dict[str, Any]:
        """Get settings for a specific cap. Returns media_urn -> value map."""
        ...


class MachineExecutor:
    """Executes a MachinePlan node-by-node in topological order."""

    def __init__(
        self,
        executor: CapExecutor,
        plan: MachinePlan,
        input_files: List[CapInputFile],
    ) -> None:
        self._executor = executor
        self._plan = plan
        self._input_files = input_files
        self._slot_values: Dict[str, bytes] = {}
        self._settings_provider: Optional[CapSettingsProvider] = None

    def with_slot_values(self, slot_values: Dict[str, bytes]) -> MachineExecutor:
        self._slot_values = slot_values
        return self

    def with_settings_provider(self, provider: CapSettingsProvider) -> MachineExecutor:
        self._settings_provider = provider
        return self

    async def execute(self) -> MachineResult:
        """Execute the plan and return results."""
        start = time.monotonic()

        self._plan.validate()
        order = self._plan.topological_order()

        node_results: Dict[str, NodeExecutionResult] = {}
        node_outputs: Dict[str, Any] = {}

        for node in order:
            try:
                exec_result, output_val = await self._execute_node(
                    node, node_results, node_outputs)
            except Exception as e:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                return MachineResult(
                    success=False,
                    node_results=node_results,
                    error=str(e),
                    total_duration_ms=elapsed_ms,
                )

            node_results[node.id] = exec_result
            if output_val is not None:
                node_outputs[node.id] = output_val

            if not exec_result.success:
                elapsed_ms = int((time.monotonic() - start) * 1000)
                return MachineResult(
                    success=False,
                    node_results=node_results,
                    error=exec_result.error,
                    total_duration_ms=elapsed_ms,
                )

        # Collect outputs from output nodes
        outputs: Dict[str, Any] = {}
        for output_node_id in self._plan.output_nodes:
            output_node = self._plan.get_node(output_node_id)
            if output_node is not None and output_node.node_type.kind == ExecutionNodeType.OUTPUT:
                source = output_node.node_type.source_node
                if source in node_outputs:
                    outputs[output_node.node_type.output_name] = node_outputs[source]

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return MachineResult(
            success=True,
            node_results=node_results,
            outputs=outputs,
            total_duration_ms=elapsed_ms,
        )

    async def _execute_node(
        self,
        node: MachineNode,
        _node_results: Dict[str, NodeExecutionResult],
        node_outputs: Dict[str, Any],
    ) -> tuple:
        """Execute a single node. Returns (NodeExecutionResult, Optional[output_value])."""
        start = time.monotonic()
        kind = node.node_type.kind

        if kind == ExecutionNodeType.CAP:
            return await self._execute_cap_node(
                node.id,
                node.node_type.cap_urn,
                node.node_type.arg_bindings,
                node.node_type.preferred_cap,
                node_outputs,
            )

        elif kind == ExecutionNodeType.INPUT_SLOT:
            if len(self._input_files) == 1:
                output = {
                    "file_path": self._input_files[0].file_path,
                    "media_urn": self._input_files[0].media_urn,
                }
            else:
                output = [
                    {"file_path": f.file_path, "media_urn": f.media_urn}
                    for f in self._input_files
                ]
            duration_ms = int((time.monotonic() - start) * 1000)
            return (
                NodeExecutionResult(
                    node_id=node.id, success=True,
                    text_output=json.dumps(output),
                    duration_ms=duration_ms,
                ),
                output,
            )

        elif kind == ExecutionNodeType.OUTPUT:
            source_node = node.node_type.source_node
            output = node_outputs.get(source_node)
            duration_ms = int((time.monotonic() - start) * 1000)
            return (
                NodeExecutionResult(
                    node_id=node.id, success=True,
                    duration_ms=duration_ms,
                ),
                output,
            )

        elif kind == ExecutionNodeType.FOR_EACH:
            input_node = node.node_type.input_node
            body_entry = node.node_type.body_entry
            body_exit = node.node_type.body_exit
            input_val = node_outputs.get(input_node)
            if isinstance(input_val, list):
                items = input_val
            elif input_val is not None:
                items = [input_val]
            else:
                items = []
            output = {
                "iteration_count": len(items),
                "items": items,
                "body_entry": body_entry,
                "body_exit": body_exit,
            }
            duration_ms = int((time.monotonic() - start) * 1000)
            return (
                NodeExecutionResult(
                    node_id=node.id, success=True,
                    duration_ms=duration_ms,
                ),
                output,
            )

        elif kind == ExecutionNodeType.COLLECT:
            input_nodes = node.node_type.input_nodes
            collected: List[Any] = []
            for inp_id in input_nodes:
                val = node_outputs.get(inp_id)
                if val is None:
                    continue
                if isinstance(val, list):
                    collected.extend(val)
                else:
                    collected.append(val)
            output = {"collected": collected, "count": len(collected)}
            duration_ms = int((time.monotonic() - start) * 1000)
            return (
                NodeExecutionResult(
                    node_id=node.id, success=True,
                    duration_ms=duration_ms,
                ),
                output,
            )

        elif kind == ExecutionNodeType.MERGE:
            input_nodes = node.node_type.input_nodes
            merged = [node_outputs.get(inp_id) for inp_id in input_nodes if inp_id in node_outputs]
            output = {
                "merged": merged,
                "strategy": node.node_type.merge_strategy.value,
            }
            duration_ms = int((time.monotonic() - start) * 1000)
            return (
                NodeExecutionResult(
                    node_id=node.id, success=True,
                    duration_ms=duration_ms,
                ),
                output,
            )

        elif kind == ExecutionNodeType.SPLIT:
            input_node = node.node_type.input_node
            input_val = node_outputs.get(input_node)
            output = {
                "input": input_val,
                "output_count": node.node_type.output_count,
            }
            duration_ms = int((time.monotonic() - start) * 1000)
            return (
                NodeExecutionResult(
                    node_id=node.id, success=True,
                    duration_ms=duration_ms,
                ),
                output,
            )

        elif kind == ExecutionNodeType.WRAP_IN_LIST:
            # Find predecessor via incoming edge
            predecessor_output = None
            for edge in self._plan.edges:
                if edge.to_node == node.id:
                    predecessor_output = node_outputs.get(edge.from_node)
                    break
            duration_ms = int((time.monotonic() - start) * 1000)
            return (
                NodeExecutionResult(
                    node_id=node.id, success=True,
                    duration_ms=duration_ms,
                ),
                predecessor_output,
            )

        else:
            raise InternalError(f"Unknown node type: {kind}")

    async def _execute_cap_node(
        self,
        node_id: str,
        cap_urn: str,
        arg_bindings: ArgumentBindings,
        preferred_cap: Optional[str],
        node_outputs: Dict[str, Any],
    ) -> tuple:
        """Execute a Cap node with argument binding and resolution."""
        start = time.monotonic()

        # Check availability
        if not await self._executor.has_cap(cap_urn):
            duration_ms = int((time.monotonic() - start) * 1000)
            return (
                NodeExecutionResult(
                    node_id=node_id, success=False,
                    error=f"No capability available for '{cap_urn}'",
                    duration_ms=duration_ms,
                ),
                None,
            )

        # Get cap definition
        cap_def = await self._executor.get_cap(cap_urn)
        cap_args = cap_def.get_args()

        # Build arg defaults and required maps
        arg_defaults: Dict[str, Any] = {}
        arg_required: Dict[str, bool] = {}
        for arg in cap_args:
            if arg.default_value is not None:
                arg_defaults[arg.media_urn] = arg.default_value
            arg_required[arg.media_urn] = arg.required

        # Load cap settings from provider
        cap_settings_map: Optional[Dict[str, Dict[str, Any]]] = None
        if self._settings_provider is not None:
            try:
                settings = await self._settings_provider.get_settings(cap_urn)
                if settings:
                    cap_settings_map = {cap_urn: settings}
            except Exception:
                pass

        # Build resolution context
        context = ArgumentResolutionContext(
            input_files=self._input_files,
            current_file_index=0,
            previous_outputs=node_outputs,
            plan_metadata=self._plan.metadata,
            cap_settings=cap_settings_map,
            slot_values=self._slot_values if self._slot_values else None,
        )

        # Resolve each binding
        arguments: List[CapArgumentValue] = []
        for name, binding in arg_bindings.bindings.items():
            is_required = arg_required.get(name, False)
            try:
                resolved = resolve_binding(
                    binding, context, cap_urn, node_id,
                    arg_defaults.get(name), is_required,
                )
            except Exception as e:
                raise InternalError(
                    f"Failed to resolve argument '{name}' for cap '{cap_urn}': {e}"
                )

            if resolved is not None:
                arg_media_urn = (
                    MEDIA_FILE_PATH
                    if resolved.source == ArgumentSource.INPUT_FILE
                    else name
                )
                arguments.append(CapArgumentValue(arg_media_urn, resolved.value))

        # Implicit stdin injection
        stdin_arg_already_bound = any(
            any(isinstance(s, StdinSource) for s in arg.sources)
            and arg.media_urn in arg_bindings.bindings
            for arg in cap_args
        )
        has_file_path_binding = any(
            b.kind == ArgumentBinding.INPUT_FILE_PATH
            for b in arg_bindings.bindings.values()
        )

        if (self._input_files
                and cap_def.accepts_stdin()
                and not stdin_arg_already_bound
                and not has_file_path_binding):
            input_file = self._input_files[0]
            stdin_media_urn = cap_def.get_stdin_media_urn() or input_file.media_urn
            with open(input_file.file_path, "rb") as f:
                data = f.read()
            arguments.append(CapArgumentValue(stdin_media_urn, data))

        # Execute
        try:
            response_bytes = await self._executor.execute_cap(
                cap_urn, arguments, preferred_cap)
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            return (
                NodeExecutionResult(
                    node_id=node_id, success=False,
                    error=str(e),
                    duration_ms=duration_ms,
                ),
                None,
            )

        # Process result
        duration_ms = int((time.monotonic() - start) * 1000)
        text_output: Optional[str] = None
        try:
            text_output = response_bytes.decode("utf-8")
        except UnicodeDecodeError:
            pass

        # Try to parse as JSON, fall back to text wrapper
        output_json: Any
        if text_output is not None:
            try:
                output_json = json.loads(text_output)
            except json.JSONDecodeError:
                output_json = {"text": text_output}
        else:
            output_json = {"text": None}

        return (
            NodeExecutionResult(
                node_id=node_id, success=True,
                binary_output=response_bytes,
                text_output=text_output,
                duration_ms=duration_ms,
            ),
            output_json,
        )


def apply_edge_type(source_output: Any, edge_type: EdgeType) -> Any:
    """Apply an edge type transformation to source output."""
    if edge_type.kind == EdgeType.DIRECT:
        return source_output
    elif edge_type.kind == EdgeType.JSON_FIELD:
        if not isinstance(source_output, dict) or edge_type.field not in source_output:
            raise InternalError(f"Field '{edge_type.field}' not found in source output")
        return source_output[edge_type.field]
    elif edge_type.kind == EdgeType.JSON_PATH:
        return extract_json_path(source_output, edge_type.path)
    elif edge_type.kind == EdgeType.ITERATION:
        return source_output
    elif edge_type.kind == EdgeType.COLLECTION:
        return source_output
    else:
        raise InternalError(f"Unknown edge type: {edge_type.kind}")


def extract_json_path(json_val: Any, path: str) -> Any:
    """Navigate JSON by dot-separated path with optional array indexing.

    Supports paths like "items.0.name" or "data[2].field".
    """
    current = json_val
    for segment in path.split("."):
        if "[" in segment:
            field_name, rest = segment.split("[", 1)
            index_str = rest.rstrip("]")
            try:
                index = int(index_str)
            except ValueError:
                raise InternalError(f"Invalid array index: {index_str}")

            if field_name:
                if not isinstance(current, dict) or field_name not in current:
                    raise InternalError(f"Field '{field_name}' not found in path")
                current = current[field_name]

            if not isinstance(current, list) or index >= len(current):
                raise InternalError(f"Array index {index} out of bounds")
            current = current[index]
        else:
            if not isinstance(current, dict) or segment not in current:
                raise InternalError(f"Field '{segment}' not found in path")
            current = current[segment]

    return current
