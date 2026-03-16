"""Convert CapExecutionPlan to ResolvedGraph.

Bridges the planner's CapExecutionPlan (node-centric) to the
orchestrator's ResolvedGraph (edge-centric) format for execution.
Mirrors Rust's orchestrator/plan_converter.rs exactly.

Conversion strategy:
- InputSlot nodes become source data nodes
- Cap nodes become edges from their input source to their output target
- Output nodes mark terminal data nodes
- WrapInList nodes are transparent pass-throughs
- ForEach/Collect/Merge/Split nodes are rejected — the caller must
  decompose ForEach plans into sub-plans before conversion
"""

from __future__ import annotations

from typing import Dict, List

from capdag.planner.plan import CapExecutionPlan, ExecutionNodeType

from capdag.orchestrator.types import (
    CapRegistryTrait,
    ParseOrchestrationError,
    CapNotFoundError,
    InvalidGraphError,
    ResolvedEdge,
    ResolvedGraph,
)


async def plan_to_resolved_graph(
    plan: CapExecutionPlan,
    registry: CapRegistryTrait,
) -> ResolvedGraph:
    """Convert a CapExecutionPlan to a ResolvedGraph for execution.

    Transforms the node-centric plan (where caps are nodes) into the
    edge-centric graph (where caps are edge labels) that execute_dag expects.

    Args:
        plan: The execution plan from the planner.
        registry: Cap registry for resolving full Cap definitions.

    Returns:
        A ResolvedGraph suitable for execute_dag.

    Raises:
        InvalidGraphError: If the plan contains ForEach/Collect/Merge/Split nodes.
        CapNotFoundError: If a cap URN cannot be resolved.
    """
    nodes: Dict[str, str] = {}
    resolved_edges: List[ResolvedEdge] = []

    # First pass: identify all data nodes and their media URNs
    for node_id, node in plan.nodes.items():
        nt = node.node_type

        if nt.kind == ExecutionNodeType.INPUT_SLOT:
            nodes[node_id] = nt.expected_media_urn

        elif nt.kind == ExecutionNodeType.CAP:
            cap = await registry.lookup(nt.cap_urn)
            out_media = str(cap.urn.out_spec())
            nodes[node_id] = out_media

        elif nt.kind == ExecutionNodeType.OUTPUT:
            source = plan.nodes.get(nt.source_node)
            if source is not None and source.node_type.kind == ExecutionNodeType.CAP:
                cap = await registry.lookup(source.node_type.cap_urn)
                nodes[node_id] = str(cap.urn.out_spec())

        elif nt.kind == ExecutionNodeType.WRAP_IN_LIST:
            nodes[node_id] = nt.list_media_urn

        elif nt.kind == ExecutionNodeType.FOR_EACH:
            raise InvalidGraphError(
                f"Plan contains ForEach node '{node_id}'. Decompose the plan using "
                f"extract_prefix_to/extract_foreach_body/extract_suffix_from "
                f"before converting to ResolvedGraph."
            )

        elif nt.kind == ExecutionNodeType.COLLECT:
            raise InvalidGraphError(
                f"Plan contains Collect node '{node_id}'. Decompose the plan using "
                f"extract_prefix_to/extract_foreach_body/extract_suffix_from "
                f"before converting to ResolvedGraph."
            )

        elif nt.kind == ExecutionNodeType.MERGE:
            raise InvalidGraphError(
                f"Plan contains Merge node '{node_id}' which is not yet supported for execution."
            )

        elif nt.kind == ExecutionNodeType.SPLIT:
            raise InvalidGraphError(
                f"Plan contains Split node '{node_id}' which is not yet supported for execution."
            )

    # Build a map from WrapInList nodes to their input predecessors.
    # WrapInList is a pass-through: data at the predecessor flows through unchanged.
    wrap_predecessors: Dict[str, str] = {}
    for edge in plan.edges:
        to_node = plan.nodes.get(edge.to_node)
        if to_node is not None and to_node.node_type.kind == ExecutionNodeType.WRAP_IN_LIST:
            wrap_predecessors[edge.to_node] = edge.from_node

    # Second pass: convert edges that lead INTO Cap nodes into ResolvedEdges
    for edge in plan.edges:
        to_node = plan.nodes.get(edge.to_node)
        if to_node is None:
            raise CapNotFoundError(f"Node '{edge.to_node}' not found in plan")

        # Only create ResolvedEdges for edges that point to Cap nodes
        if to_node.node_type.kind == ExecutionNodeType.CAP:
            cap_urn = to_node.node_type.cap_urn
            cap = await registry.lookup(cap_urn)
            in_media = str(cap.urn.in_spec())
            out_media = str(cap.urn.out_spec())

            # If the source is a WrapInList node, resolve through to the actual
            # data source. WrapInList is transparent.
            from_node = edge.from_node
            if from_node in wrap_predecessors:
                from_node = wrap_predecessors[from_node]

            resolved_edges.append(ResolvedEdge(
                from_node=from_node,
                to_node=edge.to_node,
                cap_urn=cap_urn,
                cap=cap,
                in_media=in_media,
                out_media=out_media,
            ))

    return ResolvedGraph(
        nodes=nodes,
        edges=resolved_edges,
        graph_name=plan.name,
    )
