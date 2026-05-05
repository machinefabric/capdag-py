"""Tests for orchestrator plan conversion parity with Rust."""

import pytest

from capdag.cap.definition import Cap, CapArg, CapOutput, StdinSource
from capdag.cap.registry import CapRegistry
from capdag.orchestrator.plan_converter import plan_to_resolved_graph
from capdag.planner.cardinality import InputCardinality
from capdag.planner.plan import ExecutionNodeType, MachineNode, MachinePlan, MachinePlanEdge
from capdag.urn.cap_urn import CapUrn


def _build_cap(cap_urn_str: str, title: str) -> Cap:
    urn = CapUrn.from_string(cap_urn_str)
    in_media = str(urn.in_spec())
    out_media = str(urn.out_spec())

    cap = Cap.with_description(urn, title, title.lower().replace(" ", "_"), f"{title} cap")
    cap.add_arg(
        CapArg(
            media_urn=in_media,
            required=True,
            sources=[StdinSource(in_media)],
        )
    )
    cap.set_output(CapOutput(out_media, f"{title} output"))
    return cap


def _registry_with_caps(cap_urns: list[str]) -> CapRegistry:
    registry = CapRegistry.new_for_test()
    registry.add_caps_to_cache(
        [_build_cap(cap_urn, f"Test Cap {index}") for index, cap_urn in enumerate(cap_urns)]
    )
    return registry


# TEST770: plan_to_resolved_graph rejects plans containing ForEach nodes
@pytest.mark.asyncio
async def test_770_rejects_foreach():
    registry = _registry_with_caps(
        [
            "cap:in=media:pdf;disbind;out=media:pdf-page",
            "cap:in=media:pdf-page;process;out=media:text",
        ]
    )

    plan = MachinePlan("foreach_plan")
    plan.add_node(
        MachineNode.input_slot(
            "input",
            "input",
            "media:pdf",
            InputCardinality.SINGLE,
        )
    )
    plan.add_node(MachineNode.cap("cap_0", "cap:in=media:pdf;disbind;out=media:pdf-page"))
    plan.add_node(MachineNode.for_each("foreach_0", "cap_0", "cap_1", "cap_1"))
    plan.add_node(MachineNode.cap("cap_1", "cap:in=media:pdf-page;process;out=media:text"))
    plan.add_node(MachineNode.output("output", "result", "cap_1"))

    plan.add_edge(MachinePlanEdge.direct("input", "cap_0"))
    plan.add_edge(MachinePlanEdge.direct("cap_0", "foreach_0"))
    plan.add_edge(MachinePlanEdge.iteration("foreach_0", "cap_1"))
    plan.add_edge(MachinePlanEdge.direct("cap_1", "output"))

    with pytest.raises(Exception, match="ForEach node"):
        await plan_to_resolved_graph(plan, registry)


# TEST1161: Converting a simple linear plan produces resolved edges for the cap-to-cap chain.
@pytest.mark.asyncio
async def test_1161_simple_linear_chain_conversion():
    registry = _registry_with_caps(
        [
            "cap:in=media:pdf;extract;out=media:text",
            "cap:in=media:text;summarize;out=media:summary",
        ]
    )

    plan = MachinePlan("test_chain")
    plan.add_node(MachineNode.input_slot("input", "input", "media:pdf", InputCardinality.SINGLE))
    plan.add_node(MachineNode.cap("cap_0", "cap:in=media:pdf;extract;out=media:text"))
    plan.add_node(MachineNode.cap("cap_1", "cap:in=media:text;summarize;out=media:summary"))
    plan.add_node(MachineNode.output("output", "result", "cap_1"))

    plan.add_edge(MachinePlanEdge.direct("input", "cap_0"))
    plan.add_edge(MachinePlanEdge.direct("cap_0", "cap_1"))
    plan.add_edge(MachinePlanEdge.direct("cap_1", "output"))

    graph = await plan_to_resolved_graph(plan, registry)

    assert graph.graph_name == "test_chain"
    assert graph.nodes["input"] == "media:pdf"
    assert graph.nodes["cap_0"] == "media:text"
    assert graph.nodes["cap_1"] == "media:summary"
    assert len(graph.edges) == 2
    assert graph.edges[0].from_node == "input"
    assert graph.edges[0].to_node == "cap_0"
    assert graph.edges[1].from_node == "cap_0"
    assert graph.edges[1].to_node == "cap_1"


# TEST771: plan_to_resolved_graph rejects plans containing Collect nodes
@pytest.mark.asyncio
async def test_771_rejects_collect():
    registry = _registry_with_caps(
        [
            "cap:in=media:pdf;disbind;out=media:pdf-page",
            "cap:in=media:pdf-page;process;out=media:text",
        ]
    )

    plan = MachinePlan("collect_plan")
    plan.add_node(
        MachineNode.input_slot(
            "input",
            "input",
            "media:pdf",
            InputCardinality.SINGLE,
        )
    )
    plan.add_node(MachineNode.cap("cap_0", "cap:in=media:pdf;disbind;out=media:pdf-page"))
    plan.add_node(MachineNode.for_each("foreach_0", "cap_0", "cap_1", "cap_1"))
    plan.add_node(MachineNode.cap("cap_1", "cap:in=media:pdf-page;process;out=media:text"))
    plan.add_node(MachineNode.collect("collect_0", ["cap_1"]))
    plan.add_node(MachineNode.output("output", "result", "collect_0"))

    plan.add_edge(MachinePlanEdge.direct("input", "cap_0"))
    plan.add_edge(MachinePlanEdge.direct("cap_0", "foreach_0"))
    plan.add_edge(MachinePlanEdge.iteration("foreach_0", "cap_1"))
    plan.add_edge(MachinePlanEdge.collection("cap_1", "collect_0"))
    plan.add_edge(MachinePlanEdge.direct("collect_0", "output"))

    with pytest.raises(Exception) as exc_info:
        await plan_to_resolved_graph(plan, registry)

    message = str(exc_info.value)
    assert "ForEach node" in message or "Collect node" in message


# TEST953: Linear plans (no ForEach/Collect) still convert successfully
@pytest.mark.asyncio
async def test_953_linear_plan_still_works():
    registry = _registry_with_caps(["cap:in=media:pdf;extract;out=media:text"])

    plan = MachinePlan("linear_plan")
    plan.add_node(
        MachineNode.input_slot(
            "input",
            "input",
            "media:pdf",
            InputCardinality.SINGLE,
        )
    )
    plan.add_node(MachineNode.cap("cap_0", "cap:in=media:pdf;extract;out=media:text"))
    plan.add_node(MachineNode.output("output", "result", "cap_0"))

    plan.add_edge(MachinePlanEdge.direct("input", "cap_0"))
    plan.add_edge(MachinePlanEdge.direct("cap_0", "output"))

    graph = await plan_to_resolved_graph(plan, registry)

    assert graph.graph_name == "linear_plan"
    assert len(graph.edges) == 1
    assert graph.edges[0].from_node == "input"
    assert graph.edges[0].to_node == "cap_0"
    assert graph.edges[0].cap_urn == "cap:in=media:pdf;extract;out=media:text"


# TEST954: Standalone Collect nodes are handled as pass-through
@pytest.mark.asyncio
async def test_954_standalone_collect_passthrough():
    registry = _registry_with_caps(
        [
            'cap:in=media:pdf;extract;out="media:text;textable"',
            'cap:in="media:list;text;textable";embed;out="media:embedding-vector;record;textable"',
        ]
    )

    plan = MachinePlan("collect_plan")
    plan.add_node(
        MachineNode.input_slot(
            "input",
            "input",
            "media:pdf",
            InputCardinality.SINGLE,
        )
    )
    plan.add_node(
        MachineNode.cap(
            "cap_0",
            'cap:in=media:pdf;extract;out="media:text;textable"',
        )
    )

    collect_node = MachineNode.collect("collect_0", ["cap_0"])
    collect_node.node_type = ExecutionNodeType.collect(
        ["cap_0"],
        output_media_urn="media:list;text;textable",
    )
    collect_node.description = "Collect: scalar to list-of-one"
    plan.add_node(collect_node)

    plan.add_node(
        MachineNode.cap(
            "cap_1",
            'cap:in="media:list;text;textable";embed;out="media:embedding-vector;record;textable"',
        )
    )
    plan.add_node(MachineNode.output("output", "result", "cap_1"))

    plan.add_edge(MachinePlanEdge.direct("input", "cap_0"))
    plan.add_edge(MachinePlanEdge.direct("cap_0", "collect_0"))
    plan.add_edge(MachinePlanEdge.direct("collect_0", "cap_1"))
    plan.add_edge(MachinePlanEdge.direct("cap_1", "output"))

    graph = await plan_to_resolved_graph(plan, registry)

    edge_pairs = {(edge.from_node, edge.to_node) for edge in graph.edges}
    assert len(graph.edges) == 2
    assert ("input", "cap_0") in edge_pairs
    assert ("cap_0", "cap_1") in edge_pairs
    assert not any(
        from_node == "collect_0" or to_node == "collect_0"
        for from_node, to_node in edge_pairs
    )
    assert not plan.has_foreach()
