"""Convert MachinePlan to ResolvedGraph.

Bridges the planner's MachinePlan (node-centric) to the
orchestrator's ResolvedGraph (edge-centric) format for execution.
Mirrors Rust's orchestrator/plan_converter.rs exactly.

Conversion strategy:
- InputSlot nodes become source data nodes
- Cap nodes become edges from their input source to their output target
- Output nodes mark terminal data nodes
- Standalone Collect nodes (output_media_urn set) are transparent pass-throughs
- ForEach-paired Collect nodes (no output_media_urn) are rejected
- ForEach/Merge/Split nodes are rejected — the caller must
  decompose ForEach plans into sub-plans before conversion

All cap lookups use get_cached_cap: caps must be pre-loaded into the registry
cache before calling this function.
"""

from __future__ import annotations

from typing import Dict, List

from capdag.cap.registry import CapRegistry
from capdag.planner.plan import MachinePlan, ExecutionNodeType

from capdag.orchestrator.types import (
    CapNotFoundError,
    InvalidGraphError,
    ResolvedEdge,
    ResolvedGraph,
)


async def plan_to_resolved_graph(
    plan: MachinePlan,
    registry: CapRegistry,
) -> ResolvedGraph:
    """Convert a MachinePlan to a ResolvedGraph for execution.

    Transforms the node-centric plan (where caps are nodes) into the
    edge-centric graph (where caps are edge labels) that execute_dag expects.

    Args:
        plan: The execution plan from the planner.
        registry: Cap registry — caps must be pre-loaded in cache.

    Returns:
        A ResolvedGraph suitable for execute_dag.

    Raises:
        InvalidGraphError: If the plan contains ForEach/Merge/Split nodes, or a
            ForEach-paired Collect (output_media_urn is None).
        CapNotFoundError: If a cap URN cannot be resolved in the cache.
    """
    def lookup_cap(cap_urn: str):
        cap = registry.get_cached_cap(cap_urn)
        if cap is None:
            raise CapNotFoundError(f"Cap not found in registry cache: {cap_urn!r}")
        return cap

    nodes: Dict[str, str] = {}
    resolved_edges: List[ResolvedEdge] = []

    # First pass: identify all data nodes and their media URNs
    for node_id, node in plan.nodes.items():
        nt = node.node_type

        if nt.kind == ExecutionNodeType.INPUT_SLOT:
            nodes[node_id] = nt.expected_media_urn

        elif nt.kind == ExecutionNodeType.CAP:
            cap = lookup_cap(nt.cap_urn)
            out_media = str(cap.urn.out_spec())
            nodes[node_id] = out_media

        elif nt.kind == ExecutionNodeType.OUTPUT:
            source = plan.nodes.get(nt.source_node)
            if source is not None and source.node_type.kind == ExecutionNodeType.CAP:
                cap = lookup_cap(source.node_type.cap_urn)
                nodes[node_id] = str(cap.urn.out_spec())

        elif nt.kind == ExecutionNodeType.COLLECT:
            output_media_urn = nt.output_media_urn
            if output_media_urn is not None:
                # Standalone Collect (scalar→list): pass-through at execution time.
                # The data flows unchanged, only the type annotation changes.
                # Register the node with the list media URN so downstream edges
                # can find data at it.
                nodes[node_id] = output_media_urn
            else:
                # ForEach-paired Collect without output_media_urn should not reach
                # plan_converter — the plan should have been decomposed first.
                raise InvalidGraphError(
                    f"Plan contains ForEach-paired Collect node '{node_id}'. Decompose the plan "
                    f"using extract_prefix_to/extract_foreach_body/extract_suffix_from "
                    f"before converting to ResolvedGraph."
                )

        elif nt.kind == ExecutionNodeType.FOR_EACH:
            raise InvalidGraphError(
                f"Plan contains ForEach node '{node_id}'. Decompose the plan using "
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

    # Build a map from standalone Collect nodes to their input predecessors.
    # Standalone Collect is a pass-through: data at the predecessor flows through unchanged.
    # When an edge's from_node is a standalone Collect, we resolve it to the actual data source.
    collect_predecessors: Dict[str, str] = {}
    for edge in plan.edges:
        to_node = plan.nodes.get(edge.to_node)
        if to_node is not None:
            nt = to_node.node_type
            if nt.kind == ExecutionNodeType.COLLECT and nt.output_media_urn is not None:
                collect_predecessors[edge.to_node] = edge.from_node

    # Second pass: convert edges that lead INTO Cap nodes into ResolvedEdges
    for edge in plan.edges:
        to_node = plan.nodes.get(edge.to_node)
        if to_node is None:
            raise CapNotFoundError(f"Node '{edge.to_node}' not found in plan")

        # Only create ResolvedEdges for edges that point to Cap nodes
        if to_node.node_type.kind == ExecutionNodeType.CAP:
            cap_urn = to_node.node_type.cap_urn
            cap = lookup_cap(cap_urn)
            in_media = str(cap.urn.in_spec())
            out_media = str(cap.urn.out_spec())

            # If the source is a standalone Collect node, resolve through to the
            # actual data source. Standalone Collect is transparent — data at the
            # predecessor flows unchanged through it.
            from_node = collect_predecessors.get(edge.from_node, edge.from_node)

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
