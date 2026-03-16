"""Execution plan data structures for cap chains.

This module defines the DAG-based execution plan that represents
a sequence of cap operations. Mirrors Rust's planner/plan.rs exactly.

Key types:
- ExecutionNodeType: discriminated union of node kinds (Cap, ForEach, Collect, etc.)
- CapNode: a node in the execution plan
- EdgeType: how data flows between nodes
- CapEdge: a directed edge in the plan
- CapExecutionPlan: the complete execution DAG
- NodeExecutionResult / CapChainExecutionResult: execution output
"""

from __future__ import annotations

from collections import deque
from enum import Enum
from typing import Any, Dict, List, Optional

from capdag.planner.argument_binding import ArgumentBindings, ArgumentBinding
from capdag.planner.cardinality import InputCardinality
from capdag.planner.error import InternalError, InvalidPathError


# NodeId is just a string alias
NodeId = str


class MergeStrategy(Enum):
    """Strategy for merging multiple inputs."""
    CONCAT = "concat"
    ZIP_WITH = "zip_with"
    FIRST_SUCCESS = "first_success"
    ALL_SUCCESSFUL = "all_successful"


class ExecutionNodeType:
    """Discriminated union of execution node types.

    Uses a `kind` field to distinguish variants, matching Rust's
    serde(tag = "node_type") representation.
    """

    # Kind constants
    CAP = "cap"
    FOR_EACH = "for_each"
    COLLECT = "collect"
    MERGE = "merge"
    SPLIT = "split"
    WRAP_IN_LIST = "wrap_in_list"
    INPUT_SLOT = "input_slot"
    OUTPUT = "output"

    __slots__ = ("kind", "_data")

    def __init__(self, kind: str, data: Dict[str, Any]) -> None:
        self.kind = kind
        self._data = data

    # --- Factory methods ---

    @staticmethod
    def cap(cap_urn: str, arg_bindings: Optional[ArgumentBindings] = None,
            preferred_cap: Optional[str] = None) -> ExecutionNodeType:
        return ExecutionNodeType(ExecutionNodeType.CAP, {
            "cap_urn": cap_urn,
            "arg_bindings": arg_bindings or ArgumentBindings(),
            "preferred_cap": preferred_cap,
        })

    @staticmethod
    def for_each(input_node: str, body_entry: str, body_exit: str) -> ExecutionNodeType:
        return ExecutionNodeType(ExecutionNodeType.FOR_EACH, {
            "input_node": input_node,
            "body_entry": body_entry,
            "body_exit": body_exit,
        })

    @staticmethod
    def collect(input_nodes: List[str], output_media_urn: Optional[str] = None) -> ExecutionNodeType:
        return ExecutionNodeType(ExecutionNodeType.COLLECT, {
            "input_nodes": input_nodes,
            "output_media_urn": output_media_urn,
        })

    @staticmethod
    def merge(input_nodes: List[str], merge_strategy: MergeStrategy = MergeStrategy.CONCAT) -> ExecutionNodeType:
        return ExecutionNodeType(ExecutionNodeType.MERGE, {
            "input_nodes": input_nodes,
            "merge_strategy": merge_strategy,
        })

    @staticmethod
    def split(input_node: str, output_count: int) -> ExecutionNodeType:
        return ExecutionNodeType(ExecutionNodeType.SPLIT, {
            "input_node": input_node,
            "output_count": output_count,
        })

    @staticmethod
    def wrap_in_list(item_media_urn: str, list_media_urn: str) -> ExecutionNodeType:
        return ExecutionNodeType(ExecutionNodeType.WRAP_IN_LIST, {
            "item_media_urn": item_media_urn,
            "list_media_urn": list_media_urn,
        })

    @staticmethod
    def input_slot(slot_name: str, expected_media_urn: str,
                   cardinality: InputCardinality = InputCardinality.SINGLE) -> ExecutionNodeType:
        return ExecutionNodeType(ExecutionNodeType.INPUT_SLOT, {
            "slot_name": slot_name,
            "expected_media_urn": expected_media_urn,
            "cardinality": cardinality,
        })

    @staticmethod
    def output(output_name: str, source_node: str) -> ExecutionNodeType:
        return ExecutionNodeType(ExecutionNodeType.OUTPUT, {
            "output_name": output_name,
            "source_node": source_node,
        })

    # --- Data accessors ---

    @property
    def cap_urn(self) -> str:
        return self._data["cap_urn"]

    @property
    def arg_bindings(self) -> ArgumentBindings:
        return self._data["arg_bindings"]

    @property
    def preferred_cap(self) -> Optional[str]:
        return self._data.get("preferred_cap")

    @property
    def input_node(self) -> str:
        return self._data["input_node"]

    @property
    def body_entry(self) -> str:
        return self._data["body_entry"]

    @property
    def body_exit(self) -> str:
        return self._data["body_exit"]

    @property
    def input_nodes(self) -> List[str]:
        return self._data["input_nodes"]

    @property
    def output_media_urn(self) -> Optional[str]:
        return self._data.get("output_media_urn")

    @property
    def merge_strategy(self) -> MergeStrategy:
        return self._data["merge_strategy"]

    @property
    def output_count(self) -> int:
        return self._data["output_count"]

    @property
    def item_media_urn(self) -> str:
        return self._data["item_media_urn"]

    @property
    def list_media_urn(self) -> str:
        return self._data["list_media_urn"]

    @property
    def slot_name(self) -> str:
        return self._data["slot_name"]

    @property
    def expected_media_urn(self) -> str:
        return self._data["expected_media_urn"]

    @property
    def cardinality(self) -> InputCardinality:
        return self._data["cardinality"]

    @property
    def output_name(self) -> str:
        return self._data["output_name"]

    @property
    def source_node(self) -> str:
        return self._data["source_node"]

    # --- Serialization ---

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {"node_type": self.kind}
        for k, v in self._data.items():
            if v is None:
                continue
            if isinstance(v, ArgumentBindings):
                d[k] = v.to_dict()
            elif isinstance(v, InputCardinality):
                d[k] = v.value
            elif isinstance(v, MergeStrategy):
                d[k] = v.value
            else:
                d[k] = v
        return d

    def __repr__(self) -> str:
        return f"ExecutionNodeType({self.kind!r})"


class CapNode:
    """A node in the execution plan."""

    __slots__ = ("id", "node_type", "description")

    def __init__(self, id: str, node_type: ExecutionNodeType,
                 description: Optional[str] = None) -> None:
        self.id = id
        self.node_type = node_type
        self.description = description

    # --- Static constructors ---

    @staticmethod
    def cap(id: str, cap_urn: str) -> CapNode:
        return CapNode(id, ExecutionNodeType.cap(cap_urn))

    @staticmethod
    def cap_with_bindings(id: str, cap_urn: str, bindings: ArgumentBindings) -> CapNode:
        return CapNode(id, ExecutionNodeType.cap(cap_urn, bindings))

    @staticmethod
    def cap_with_preference(id: str, cap_urn: str, bindings: ArgumentBindings,
                            preferred_cap: Optional[str] = None) -> CapNode:
        return CapNode(id, ExecutionNodeType.cap(cap_urn, bindings, preferred_cap))

    @staticmethod
    def for_each(id: str, input_node: str, body_entry: str, body_exit: str) -> CapNode:
        return CapNode(
            id, ExecutionNodeType.for_each(input_node, body_entry, body_exit),
            description="Fan-out: process each item in vector",
        )

    @staticmethod
    def collect(id: str, input_nodes: List[str]) -> CapNode:
        return CapNode(
            id, ExecutionNodeType.collect(input_nodes),
            description="Fan-in: collect results into vector",
        )

    @staticmethod
    def wrap_in_list(id: str, item_media_urn: str, list_media_urn: str) -> CapNode:
        return CapNode(
            id, ExecutionNodeType.wrap_in_list(item_media_urn, list_media_urn),
            description="WrapInList: wrap scalar in list-of-one",
        )

    @staticmethod
    def input_slot(id: str, slot_name: str, media_urn: str,
                   cardinality: InputCardinality = InputCardinality.SINGLE) -> CapNode:
        return CapNode(
            id, ExecutionNodeType.input_slot(slot_name, media_urn, cardinality),
            description=f"Input: {slot_name}",
        )

    @staticmethod
    def output(id: str, output_name: str, source_node: str) -> CapNode:
        return CapNode(
            id, ExecutionNodeType.output(output_name, source_node),
            description=f"Output: {output_name}",
        )

    # --- Query methods ---

    def is_cap(self) -> bool:
        return self.node_type.kind == ExecutionNodeType.CAP

    def is_fan_out(self) -> bool:
        return self.node_type.kind == ExecutionNodeType.FOR_EACH

    def is_fan_in(self) -> bool:
        return self.node_type.kind == ExecutionNodeType.COLLECT

    def get_cap_urn(self) -> Optional[str]:
        if self.node_type.kind == ExecutionNodeType.CAP:
            return self.node_type.cap_urn
        return None

    def get_preferred_cap(self) -> Optional[str]:
        if self.node_type.kind == ExecutionNodeType.CAP:
            return self.node_type.preferred_cap
        return None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.id,
            "node_type": self.node_type.to_dict(),
        }
        if self.description is not None:
            d["description"] = self.description
        return d

    def __repr__(self) -> str:
        return f"CapNode(id={self.id!r}, type={self.node_type.kind!r})"


class EdgeType:
    """How data flows between nodes."""

    DIRECT = "direct"
    JSON_FIELD = "json_field"
    JSON_PATH = "json_path"
    ITERATION = "iteration"
    COLLECTION = "collection"

    __slots__ = ("kind", "_data")

    def __init__(self, kind: str, data: Optional[Dict[str, str]] = None) -> None:
        self.kind = kind
        self._data = data or {}

    @staticmethod
    def direct() -> EdgeType:
        return EdgeType(EdgeType.DIRECT)

    @staticmethod
    def json_field(field: str) -> EdgeType:
        return EdgeType(EdgeType.JSON_FIELD, {"field": field})

    @staticmethod
    def json_path(path: str) -> EdgeType:
        return EdgeType(EdgeType.JSON_PATH, {"path": path})

    @staticmethod
    def iteration() -> EdgeType:
        return EdgeType(EdgeType.ITERATION)

    @staticmethod
    def collection() -> EdgeType:
        return EdgeType(EdgeType.COLLECTION)

    @property
    def field(self) -> str:
        return self._data["field"]

    @property
    def path(self) -> str:
        return self._data["path"]

    def to_dict(self) -> Any:
        if self._data:
            d: Dict[str, Any] = {"type": self.kind}
            d.update(self._data)
            return d
        return self.kind

    def __repr__(self) -> str:
        if self._data:
            return f"EdgeType({self.kind!r}, {self._data!r})"
        return f"EdgeType({self.kind!r})"


class CapEdge:
    """A directed edge in the execution plan."""

    __slots__ = ("from_node", "to_node", "edge_type")

    def __init__(self, from_node: str, to_node: str,
                 edge_type: Optional[EdgeType] = None) -> None:
        self.from_node = from_node
        self.to_node = to_node
        self.edge_type = edge_type or EdgeType.direct()

    @staticmethod
    def direct(from_node: str, to_node: str) -> CapEdge:
        return CapEdge(from_node, to_node, EdgeType.direct())

    @staticmethod
    def iteration(from_node: str, to_node: str) -> CapEdge:
        return CapEdge(from_node, to_node, EdgeType.iteration())

    @staticmethod
    def collection(from_node: str, to_node: str) -> CapEdge:
        return CapEdge(from_node, to_node, EdgeType.collection())

    @staticmethod
    def json_field(from_node: str, to_node: str, field: str) -> CapEdge:
        return CapEdge(from_node, to_node, EdgeType.json_field(field))

    @staticmethod
    def json_path(from_node: str, to_node: str, path: str) -> CapEdge:
        return CapEdge(from_node, to_node, EdgeType.json_path(path))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_node": self.from_node,
            "to_node": self.to_node,
            "edge_type": self.edge_type.to_dict(),
        }

    def __repr__(self) -> str:
        return f"CapEdge({self.from_node!r} -> {self.to_node!r}, {self.edge_type!r})"


class CapExecutionPlan:
    """Complete execution plan DAG.

    Manages nodes, edges, entry points, and output nodes.
    Supports validation, topological ordering, and sub-plan extraction.
    """

    __slots__ = ("name", "nodes", "edges", "entry_nodes", "output_nodes", "metadata")

    def __init__(self, name: str) -> None:
        self.name = name
        self.nodes: Dict[str, CapNode] = {}
        self.edges: List[CapEdge] = []
        self.entry_nodes: List[str] = []
        self.output_nodes: List[str] = []
        self.metadata: Optional[Dict[str, Any]] = None

    def add_node(self, node: CapNode) -> None:
        """Add a node. InputSlot nodes are auto-registered as entry nodes,
        Output nodes as output nodes."""
        node_id = node.id
        self.nodes[node_id] = node
        if node.node_type.kind == ExecutionNodeType.INPUT_SLOT:
            self.entry_nodes.append(node_id)
        elif node.node_type.kind == ExecutionNodeType.OUTPUT:
            self.output_nodes.append(node_id)

    def add_edge(self, edge: CapEdge) -> None:
        self.edges.append(edge)

    def get_node(self, id: str) -> Optional[CapNode]:
        return self.nodes.get(id)

    def validate(self) -> None:
        """Validate plan structure. Raises InternalError on invalid references."""
        for edge in self.edges:
            if edge.from_node not in self.nodes:
                raise InternalError(f"Edge from_node '{edge.from_node}' not found in plan")
            if edge.to_node not in self.nodes:
                raise InternalError(f"Edge to_node '{edge.to_node}' not found in plan")
        for entry_id in self.entry_nodes:
            if entry_id not in self.nodes:
                raise InternalError(f"Entry node '{entry_id}' not found in plan")
        for output_id in self.output_nodes:
            if output_id not in self.nodes:
                raise InternalError(f"Output node '{output_id}' not found in plan")

    def topological_order(self) -> List[CapNode]:
        """Return nodes in topological order using Kahn's algorithm.
        Raises InternalError if cycle detected."""
        in_degree: Dict[str, int] = {nid: 0 for nid in self.nodes}
        adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}

        for edge in self.edges:
            if edge.to_node in in_degree:
                in_degree[edge.to_node] += 1
            if edge.from_node in adj:
                adj[edge.from_node].append(edge.to_node)

        queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
        result: List[CapNode] = []

        while queue:
            nid = queue.popleft()
            node = self.nodes.get(nid)
            if node is not None:
                result.append(node)
            for neighbor in adj.get(nid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self.nodes):
            raise InternalError("Cycle detected in execution plan")
        return result

    @staticmethod
    def single_cap(cap_urn: str, input_media: str, _output_media: str,
                   file_path_arg_name: str) -> CapExecutionPlan:
        """Create a simple 3-node plan: input → cap → output."""
        plan = CapExecutionPlan(f"single_{cap_urn}")
        plan.add_node(CapNode.input_slot("input_slot", "input", input_media, InputCardinality.SINGLE))

        bindings = ArgumentBindings()
        bindings.add_file_path(file_path_arg_name)
        plan.add_node(CapNode.cap_with_bindings("cap_0", cap_urn, bindings))
        plan.add_node(CapNode.output("output", "result", "cap_0"))

        plan.add_edge(CapEdge.direct("input_slot", "cap_0"))
        plan.add_edge(CapEdge.direct("cap_0", "output"))
        return plan

    @staticmethod
    def linear_chain(cap_urns: List[str], input_media: str, _output_media: str,
                     file_path_arg_names: List[str]) -> CapExecutionPlan:
        """Create a linear chain plan: input → cap_0 → cap_1 → ... → output."""
        plan = CapExecutionPlan("linear_chain")
        if not cap_urns:
            return plan

        plan.add_node(CapNode.input_slot("input_slot", "input", input_media, InputCardinality.SINGLE))

        prev_id = "input_slot"
        for i, urn in enumerate(cap_urns):
            node_id = f"cap_{i}"
            bindings = ArgumentBindings()
            if i < len(file_path_arg_names):
                bindings.add_file_path(file_path_arg_names[i])
            plan.add_node(CapNode.cap_with_bindings(node_id, urn, bindings))
            plan.add_edge(CapEdge.direct(prev_id, node_id))
            prev_id = node_id

        plan.add_node(CapNode.output("output", "result", prev_id))
        plan.add_edge(CapEdge.direct(prev_id, "output"))
        return plan

    def find_first_foreach(self) -> Optional[str]:
        """Find the first ForEach node in topological order."""
        try:
            order = self.topological_order()
        except InternalError:
            return None
        for node in order:
            if node.node_type.kind == ExecutionNodeType.FOR_EACH:
                return node.id
        return None

    def has_foreach_or_collect(self) -> bool:
        """Check if any node is ForEach or Collect."""
        return any(
            n.node_type.kind in (ExecutionNodeType.FOR_EACH, ExecutionNodeType.COLLECT)
            for n in self.nodes.values()
        )

    def extract_prefix_to(self, target_node_id: str) -> CapExecutionPlan:
        """Extract ancestor subgraph up to and including target_node_id."""
        if target_node_id not in self.nodes:
            raise InternalError(f"Target node '{target_node_id}' not found in plan")

        # BFS backward from target
        reverse_adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for edge in self.edges:
            if edge.to_node in reverse_adj:
                reverse_adj[edge.to_node].append(edge.from_node)

        ancestors: set = set()
        queue = deque([target_node_id])
        while queue:
            nid = queue.popleft()
            if nid in ancestors:
                continue
            ancestors.add(nid)
            for pred in reverse_adj.get(nid, []):
                if pred not in ancestors:
                    queue.append(pred)

        sub_plan = CapExecutionPlan(f"{self.name}_prefix")
        for nid in ancestors:
            node = self.nodes[nid]
            # Skip original Output nodes
            if node.node_type.kind == ExecutionNodeType.OUTPUT:
                continue
            sub_plan.add_node(node)

        for edge in self.edges:
            if edge.from_node in ancestors and edge.to_node in ancestors:
                from_node = self.nodes[edge.from_node]
                to_node = self.nodes[edge.to_node]
                if (from_node.node_type.kind != ExecutionNodeType.OUTPUT and
                        to_node.node_type.kind != ExecutionNodeType.OUTPUT):
                    sub_plan.add_edge(edge)

        # Add synthetic output
        output_id = f"{target_node_id}_prefix_output"
        sub_plan.add_node(CapNode.output(output_id, "prefix_result", target_node_id))
        sub_plan.add_edge(CapEdge.direct(target_node_id, output_id))

        sub_plan.validate()
        return sub_plan

    def extract_foreach_body(self, foreach_node_id: str,
                             item_media_urn: str) -> CapExecutionPlan:
        """Extract the body of a ForEach node as a standalone plan."""
        node = self.nodes.get(foreach_node_id)
        if node is None:
            raise InternalError(f"ForEach node '{foreach_node_id}' not found in plan")
        if node.node_type.kind != ExecutionNodeType.FOR_EACH:
            raise InternalError(f"Node '{foreach_node_id}' is not a ForEach node")

        body_entry = node.node_type.body_entry
        body_exit = node.node_type.body_exit

        # BFS forward from body_entry, stopping at body_exit
        forward_adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for edge in self.edges:
            if edge.from_node in forward_adj:
                forward_adj[edge.from_node].append(edge.to_node)

        body_nodes: set = set()
        queue = deque([body_entry])
        while queue:
            nid = queue.popleft()
            if nid in body_nodes:
                continue
            body_nodes.add(nid)
            if nid == body_exit:
                continue  # don't traverse past body_exit
            orig_node = self.nodes.get(nid)
            if orig_node and orig_node.node_type.kind in (ExecutionNodeType.OUTPUT, ExecutionNodeType.COLLECT):
                continue
            for succ in forward_adj.get(nid, []):
                if succ not in body_nodes:
                    queue.append(succ)

        # Force body_exit into set
        body_nodes.add(body_exit)

        body_plan = CapExecutionPlan(f"{self.name}_foreach_body")

        # Synthetic input slot
        input_id = f"{foreach_node_id}_body_input"
        body_plan.add_node(CapNode.input_slot(input_id, "item_input", item_media_urn, InputCardinality.SINGLE))

        # Add body nodes
        for nid in body_nodes:
            body_node = self.nodes.get(nid)
            if body_node is not None:
                body_plan.add_node(body_node)

        # Edge from synthetic input to body_entry
        body_plan.add_edge(CapEdge.direct(input_id, body_entry))

        # Copy edges within body, skipping Iteration and Collection
        for edge in self.edges:
            if edge.from_node in body_nodes and edge.to_node in body_nodes:
                if edge.edge_type.kind in (EdgeType.ITERATION, EdgeType.COLLECTION):
                    continue
                body_plan.add_edge(edge)

        # Synthetic output
        output_id = f"{foreach_node_id}_body_output"
        body_plan.add_node(CapNode.output(output_id, "item_result", body_exit))
        body_plan.add_edge(CapEdge.direct(body_exit, output_id))

        body_plan.validate()
        return body_plan

    def extract_suffix_from(self, source_node_id: str,
                            source_media_urn: str) -> CapExecutionPlan:
        """Extract all descendants of source_node_id as a standalone plan."""
        if source_node_id not in self.nodes:
            raise InternalError(f"Source node '{source_node_id}' not found in plan")

        # BFS forward from source
        forward_adj: Dict[str, List[str]] = {nid: [] for nid in self.nodes}
        for edge in self.edges:
            if edge.from_node in forward_adj:
                forward_adj[edge.from_node].append(edge.to_node)

        descendants: set = set()
        queue = deque([source_node_id])
        while queue:
            nid = queue.popleft()
            if nid in descendants:
                continue
            descendants.add(nid)
            for succ in forward_adj.get(nid, []):
                if succ not in descendants:
                    queue.append(succ)

        sub_plan = CapExecutionPlan(f"{self.name}_suffix")

        # Synthetic input slot replacing source_node
        input_id = f"{source_node_id}_suffix_input"
        sub_plan.add_node(CapNode.input_slot(
            input_id, "collected_input", source_media_urn, InputCardinality.SINGLE))

        # Add descendant nodes (excluding source and original InputSlot nodes)
        for nid in descendants:
            if nid == source_node_id:
                continue
            desc_node = self.nodes.get(nid)
            if desc_node is not None and desc_node.node_type.kind != ExecutionNodeType.INPUT_SLOT:
                sub_plan.add_node(desc_node)

        # Remap edges
        for edge in self.edges:
            if edge.from_node == source_node_id and edge.to_node in descendants:
                # Replace source with synthetic input
                sub_plan.add_edge(CapEdge.direct(input_id, edge.to_node))
            elif (edge.from_node in descendants and edge.to_node in descendants
                  and edge.from_node != source_node_id):
                sub_plan.add_edge(edge)

        sub_plan.validate()
        return sub_plan

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "name": self.name,
            "nodes": {nid: n.to_dict() for nid, n in self.nodes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "entry_nodes": self.entry_nodes,
            "output_nodes": self.output_nodes,
        }
        if self.metadata is not None:
            d["metadata"] = self.metadata
        return d

    def __repr__(self) -> str:
        return (
            f"CapExecutionPlan(name={self.name!r}, "
            f"nodes={len(self.nodes)}, edges={len(self.edges)})"
        )


class NodeExecutionResult:
    """Result of executing a single node."""

    __slots__ = ("node_id", "success", "binary_output", "text_output", "error", "duration_ms")

    def __init__(
        self,
        node_id: str,
        success: bool,
        binary_output: Optional[bytes] = None,
        text_output: Optional[str] = None,
        error: Optional[str] = None,
        duration_ms: int = 0,
    ) -> None:
        self.node_id = node_id
        self.success = success
        self.binary_output = binary_output
        self.text_output = text_output
        self.error = error
        self.duration_ms = duration_ms

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "node_id": self.node_id,
            "success": self.success,
            "duration_ms": self.duration_ms,
        }
        if self.text_output is not None:
            d["text_output"] = self.text_output
        if self.error is not None:
            d["error"] = self.error
        # binary_output is not included in dict (too large / not JSON-safe)
        return d

    def __repr__(self) -> str:
        return f"NodeExecutionResult(node_id={self.node_id!r}, success={self.success})"


class CapChainExecutionResult:
    """Result of executing a complete cap chain."""

    __slots__ = ("success", "node_results", "outputs", "error", "total_duration_ms")

    def __init__(
        self,
        success: bool,
        node_results: Optional[Dict[str, NodeExecutionResult]] = None,
        outputs: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        total_duration_ms: int = 0,
    ) -> None:
        self.success = success
        self.node_results = node_results or {}
        self.outputs = outputs or {}
        self.error = error
        self.total_duration_ms = total_duration_ms

    def primary_output(self) -> Optional[Any]:
        """Get the first output value (non-deterministic ordering)."""
        for v in self.outputs.values():
            return v
        return None

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "success": self.success,
            "node_results": {nid: r.to_dict() for nid, r in self.node_results.items()},
            "outputs": self.outputs,
            "total_duration_ms": self.total_duration_ms,
        }
        if self.error is not None:
            d["error"] = self.error
        return d

    def __repr__(self) -> str:
        return (
            f"CapChainExecutionResult(success={self.success}, "
            f"outputs={len(self.outputs)})"
        )
