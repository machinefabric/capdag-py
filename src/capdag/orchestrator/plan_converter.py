"""Steps of a MachinePlan as a ResolvedGraph.

The plan is node-centric: steps, the values they read and produce, the maps
they run in. An executor runs a ResolvedGraph: steps with their cap
definitions, each saying which nodes its input streams are sent from and which
nodes its outputs are stored at. This module is the bridge. Mirrors the
reference's ``orchestrator/plan_converter.rs``.

A graph holds only steps. What else a plan has is read through them:

- an edge into a step is one of its inputs — the cap's ``in=`` stream for a
  Direct edge, the named arg's stream for an Arg edge;
- a Collect wired into a step is that input's gather: its members, in order;
- a CapOutput of a step is an output of it that something takes.

Maps are not in a graph at all: a map's body runs once per item, and the steps
of one scope are asked for at a time (:func:`steps_to_resolved_graph`). A node
a graph's steps read and none of them produces is an input of the graph,
whatever it is in the plan — an input slot, an item, a step of another scope.

All cap lookups use ``get_cached_cap``: caps must be in the registry cache
before a plan is converted.
"""

from __future__ import annotations

from typing import Dict, List

from capdag.fabric.registry import FabricRegistry
from capdag.planner.plan import EdgeType, ExecutionNodeType, MachinePlan
from capdag.urn.media_urn import MediaUrn

from capdag.orchestrator.types import (
    CapNotFoundError,
    InvalidGraphError,
    ResolvedGraph,
    ResolvedStep,
    StepInput,
    StepOutput,
    StepSource,
)

# How a refusal names an edge kind and a node kind.
_EDGE_KIND_LABELS = {
    EdgeType.DIRECT: "Direct",
    EdgeType.ARG: "Arg",
    EdgeType.ITERATION: "Iteration",
    EdgeType.COLLECTION: "Collection",
}
_NODE_KIND_LABELS = {
    ExecutionNodeType.CAP: "Cap",
    ExecutionNodeType.CAP_OUTPUT: "CapOutput",
    ExecutionNodeType.FOR_EACH: "ForEach",
    ExecutionNodeType.ITEM: "Item",
    ExecutionNodeType.COLLECT: "Collect",
    ExecutionNodeType.INPUT_SLOT: "InputSlot",
    ExecutionNodeType.OUTPUT: "Output",
}


def _cached_cap(registry: FabricRegistry, cap_urn: str):
    cap = registry.get_cached_cap(cap_urn)
    if cap is None:
        raise CapNotFoundError(cap_urn)
    return cap


def steps_to_resolved_graph(
    plan: MachinePlan,
    step_ids: List[str],
    registry: FabricRegistry,
) -> ResolvedGraph:
    """The steps ``step_ids`` of ``plan`` (ids of its Cap nodes) as a graph.

    Raises:
        InvalidGraphError: an id is not a step of the plan, or the plan wires
            a step in a way no invocation can be given — two sources on one
            stream, or a map wired straight into a step.
        CapNotFoundError: a step's cap is not in the registry cache.
    """
    nodes: Dict[str, str] = {}
    steps: List[ResolvedStep] = []

    # A step's other taken outputs: the CapOutput nodes that name it.
    outputs_of: Dict[str, List[StepOutput]] = {}
    for node_id in sorted(plan.nodes):
        nt = plan.nodes[node_id].node_type
        if nt.kind == ExecutionNodeType.CAP_OUTPUT:
            outputs_of.setdefault(nt.cap_node, []).append(
                StepOutput(output_media_urn=nt.output_media_urn, node=node_id)
            )

    for step_id in step_ids:
        node = plan.nodes.get(step_id)
        if node is None:
            raise InvalidGraphError(f"'{step_id}' is not a node of plan '{plan.name}'")
        if node.node_type.kind != ExecutionNodeType.CAP:
            raise InvalidGraphError(f"'{step_id}' is not a step of plan '{plan.name}'")
        cap_urn = node.node_type.cap_urn
        cap = _cached_cap(registry, cap_urn)

        # The streams the step is sent, in the order the plan wires them.
        inputs: List[StepInput] = []
        taken: List[MediaUrn] = []
        for edge in plan.edges:
            if edge.to_node != step_id:
                continue
            kind = edge.edge_type.kind
            if kind == EdgeType.DIRECT:
                stream_urn = str(cap.urn.in_spec())
            elif kind == EdgeType.ARG:
                stream_urn = edge.edge_type.arg_urn
            else:
                raise InvalidGraphError(
                    f"step '{step_id}' has an incoming {_EDGE_KIND_LABELS[kind]} edge from "
                    f"'{edge.from_node}' — a step is wired by its main input and its args only"
                )
            source_node = plan.nodes.get(edge.from_node)
            if source_node is None:
                raise InvalidGraphError(
                    f"step '{step_id}' is wired from '{edge.from_node}', which is not in the plan"
                )
            source_kind = source_node.node_type.kind
            if source_kind == ExecutionNodeType.COLLECT:
                source = StepSource.gather(source_node.node_type.input_nodes)
            elif source_kind in (ExecutionNodeType.FOR_EACH, ExecutionNodeType.OUTPUT):
                raise InvalidGraphError(
                    f"step '{step_id}' is wired from '{edge.from_node}', which holds no value"
                )
            else:
                source = StepSource.of_node(edge.from_node)
            try:
                stream = MediaUrn.from_string(stream_urn)
            except Exception as error:
                raise InvalidGraphError(
                    f"step '{step_id}': input stream URN '{stream_urn}' is not a media URN: {error}"
                ) from error
            if any(other.is_equivalent(stream) for other in taken):
                raise InvalidGraphError(
                    f"step '{step_id}' is wired twice on input stream '{stream_urn}' — one stream "
                    f"has one source; several values into one arg are a gather"
                )
            taken.append(stream)
            inputs.append(StepInput(stream_urn=stream_urn, source=source))

        out_media = str(cap.urn.out_spec())
        nodes[step_id] = out_media
        outputs = list(outputs_of.get(step_id, []))
        for output in outputs:
            nodes[output.node] = output.output_media_urn
        steps.append(ResolvedStep(
            token_id=node.node_type.token_id,
            node=step_id,
            cap_urn=cap_urn,
            cap=cap,
            inputs=inputs,
            outputs=outputs,
            out_media=out_media,
            policy=node.node_type.policy,
        ))

    # The nodes the graph is given: what its steps read and none produces.
    for step in steps:
        for source in step.source_nodes():
            if source in nodes:
                continue
            source_node = plan.nodes.get(source)
            if source_node is None:
                raise InvalidGraphError(f"a step reads '{source}', which is not in the plan")
            nt = source_node.node_type
            if nt.kind == ExecutionNodeType.INPUT_SLOT:
                nodes[source] = nt.expected_media_urn
            elif nt.kind == ExecutionNodeType.ITEM:
                nodes[source] = nt.media_urn
            elif nt.kind == ExecutionNodeType.CAP_OUTPUT:
                nodes[source] = nt.output_media_urn
            elif nt.kind == ExecutionNodeType.CAP:
                nodes[source] = str(_cached_cap(registry, nt.cap_urn).urn.out_spec())
            else:
                raise InvalidGraphError(
                    f"a step reads '{source}', which holds no value ({_NODE_KIND_LABELS[nt.kind]})"
                )

    return ResolvedGraph(nodes=nodes, steps=steps, graph_name=plan.name)


def plan_to_resolved_graph(
    plan: MachinePlan,
    registry: FabricRegistry,
) -> ResolvedGraph:
    """Every step of a plan that has no map, as one graph.

    A plan with a map is not one graph: its body runs once per item. Asking
    for it here is refused, naming the map.
    """
    step_ids: List[str] = []
    for node_id in sorted(plan.nodes):
        kind = plan.nodes[node_id].node_type.kind
        if kind == ExecutionNodeType.CAP:
            step_ids.append(node_id)
        elif kind == ExecutionNodeType.FOR_EACH:
            raise InvalidGraphError(
                f"plan '{plan.name}' has a map ('{node_id}'): its body runs once per item and is "
                f"not one graph — run its scopes one at a time"
            )
    return steps_to_resolved_graph(plan, step_ids, registry)
