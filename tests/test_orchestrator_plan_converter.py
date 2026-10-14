"""Tests for the steps of a plan as a graph an executor runs."""

import pytest

from capdag.cap.definition import CapArg, CapOutput, CliFlagSource
from capdag.cap.registry import FabricRegistry
from capdag.orchestrator.plan_converter import plan_to_resolved_graph, steps_to_resolved_graph
from capdag.orchestrator.types import (
    CapNotFoundError,
    InvalidGraphError,
    ResolvedGraph,
    ResolvedStep,
    StepInput,
    StepOutput,
    StepSource,
)
from capdag.planner.cardinality import InputCardinality
from capdag.planner.plan import ForEachSource, MachineNode, MachinePlan, MachinePlanEdge
from capdag.planner.policy import ON_ERROR_ABSENT, StepPolicy

from tests.definitions import complete_cap

EXTRACT = 'cap:in="media:document;ext=pdf";extract;out="media:enc=utf-8;ext=txt"'
SUMMARIZE = 'cap:in="media:enc=utf-8;ext=txt";summarize;out="media:enc=utf-8;summary"'
CONCAT = 'cap:in="media:enc=utf-8";concat;out="media:enc=utf-8;joined"'
SPLIT = 'cap:in="media:enc=utf-8;ext=txt";split;out="media:enc=utf-8;head"'
NOW = 'cap:in="media:void";now;out="media:stamp"'
CONTEXT = "media:context;enc=utf-8"
REST = "media:enc=utf-8;rest"


def _registry() -> FabricRegistry:
    registry = FabricRegistry.new_for_test()
    summarize = complete_cap(SUMMARIZE, "summarize", "summarize")
    summarize.add_arg(CapArg(CONTEXT, "context", False, [CliFlagSource("--context")]))
    concat = complete_cap(CONCAT, "concat", "concat")
    concat.args[0].is_sequence = True
    split = complete_cap(SPLIT, "split", "split")
    split.add_output(CapOutput(REST, "rest", "the rest"))
    registry.add_caps_to_cache([
        complete_cap(EXTRACT, "extract", "extract"),
        summarize,
        concat,
        split,
        complete_cap(NOW, "now", "now"),
    ])
    return registry


def _plan() -> MachinePlan:
    """doc → extract → summarize (context ← now) → out; extract also feeds
    split, whose `rest` output is taken; concat gathers summarize and rest."""
    plan = MachinePlan("convert")
    plan.add_node(MachineNode.input_slot("doc", "input", "media:document;ext=pdf", InputCardinality.SINGLE))
    plan.add_node(MachineNode.cap("extract", EXTRACT))
    plan.add_node(MachineNode.cap("summarize", SUMMARIZE))
    plan.add_node(MachineNode.cap("now", NOW))
    plan.add_node(MachineNode.cap("split", SPLIT))
    plan.add_node(MachineNode.cap_output("split.rest", "split", REST, "rest", False))
    plan.add_node(MachineNode.collect("both", ["summarize", "split.rest"], "media:enc=utf-8"))
    plan.add_node(MachineNode.cap("concat", CONCAT))
    plan.add_node(MachineNode.output("out", "result", "concat"))
    plan.add_edge(MachinePlanEdge.direct("doc", "extract"))
    plan.add_edge(MachinePlanEdge.direct("extract", "summarize"))
    plan.add_edge(MachinePlanEdge.arg("now", "summarize", CONTEXT))
    plan.add_edge(MachinePlanEdge.direct("extract", "split"))
    plan.add_edge(MachinePlanEdge.direct("split", "split.rest"))
    plan.add_edge(MachinePlanEdge.collection("summarize", "both"))
    plan.add_edge(MachinePlanEdge.collection("split.rest", "both"))
    plan.add_edge(MachinePlanEdge.direct("both", "concat"))
    plan.add_edge(MachinePlanEdge.direct("concat", "out"))
    plan.validate()
    return plan


def _step(graph: ResolvedGraph, node: str) -> ResolvedStep:
    found = [step for step in graph.steps if step.node == node]
    assert len(found) == 1, f"no step '{node}'"
    return found[0]


# TEST1161: every step of a plan becomes one step of the graph, keyed by its
# node; its main input is the stream its cap's `in=` names and a named arg the
# stream the edge names; a step nothing is wired into has no inputs; a gather
# is one input with its members in order; an output of a step that something
# takes is listed with the node it is stored at.
def test_1161_a_plan_converts_to_steps_with_their_inputs_and_outputs():
    graph = plan_to_resolved_graph(_plan(), _registry())
    assert len(graph.steps) == 5
    assert graph.graph_name == "convert"

    extract = _step(graph, "extract")
    assert extract.inputs == [
        StepInput(stream_urn="media:document;ext=pdf", source=StepSource.of_node("doc")),
    ]
    assert extract.outputs == []
    assert extract.out_media == "media:enc=utf-8;ext=txt"

    summarize = _step(graph, "summarize")
    assert summarize.inputs == [
        StepInput(stream_urn="media:enc=utf-8;ext=txt", source=StepSource.of_node("extract")),
        StepInput(stream_urn=CONTEXT, source=StepSource.of_node("now")),
    ]

    assert _step(graph, "now").inputs == [], "a source is sent no stream"

    split = _step(graph, "split")
    assert split.outputs == [StepOutput(output_media_urn=REST, node="split.rest")]
    assert split.produced_nodes() == ["split", "split.rest"]

    concat = _step(graph, "concat")
    assert concat.inputs == [
        StepInput(stream_urn="media:enc=utf-8", source=StepSource.gather(["summarize", "split.rest"])),
    ]
    assert concat.inputs[0].source.is_gather
    assert not extract.inputs[0].source.is_gather
    assert extract.inputs[0].source.node == "doc"
    with pytest.raises(ValueError):
        concat.inputs[0].source.node  # a gather is several nodes, not one
    assert concat.source_nodes() == ["summarize", "split.rest"]
    # One node sent as it is and a gather of that one node are two sources.
    assert StepSource.of_node("doc") != StepSource.gather(["doc"])

    # Every node a step reads or produces has its media; the plan's input is
    # there as what the graph is given.
    assert graph.nodes["doc"] == "media:document;ext=pdf"
    assert graph.nodes["split.rest"] == REST
    assert graph.nodes["concat"] == "media:enc=utf-8;joined"
    assert "both" not in graph.nodes, "a gather is an input, not a node of the graph"
    assert "out" not in graph.nodes

    # A step alone: what it produces has its media whether or not a step of
    # the graph reads it, and what it reads is what the graph is given.
    alone = steps_to_resolved_graph(_plan(), ["split"], _registry())
    assert alone.nodes == {
        "split": "media:enc=utf-8;head",
        "split.rest": REST,
        "extract": "media:enc=utf-8;ext=txt",
    }
    # And a step that reads a step's other output from outside the graph is
    # given it under that output's own type.
    gathering = steps_to_resolved_graph(_plan(), ["concat"], _registry())
    assert gathering.nodes == {
        "concat": "media:enc=utf-8;joined",
        "summarize": "media:enc=utf-8;summary",
        "split.rest": REST,
    }
    # The steps come in the order they were asked for.
    assert [step.node for step in steps_to_resolved_graph(_plan(), ["split", "extract"], _registry()).steps] \
        == ["split", "extract"]


# TEST770: a plan with a map is not one graph, and the refusal names the map;
# the steps of one scope of it are, with what they read from outside (an item,
# a step of the enclosing scope) as the graph's inputs.
def test_770_a_plan_with_a_map_is_run_scope_by_scope():
    plan = MachinePlan("mapped")
    plan.add_node(MachineNode.input_slot("docs", "input", "media:document;ext=pdf", InputCardinality.SEQUENCE))
    plan.add_node(MachineNode.cap("now", NOW))
    plan.add_node(MachineNode.for_each(
        "each", [ForEachSource(node="docs", item="doc")], ["doc", "extract", "summarize"],
    ))
    plan.add_node(MachineNode.item("doc", "each", "docs", "media:document;ext=pdf"))
    plan.add_node(MachineNode.cap("extract", EXTRACT))
    plan.add_node(MachineNode.cap("summarize", SUMMARIZE))
    plan.add_edge(MachinePlanEdge.direct("docs", "each"))
    plan.add_edge(MachinePlanEdge.iteration("each", "doc"))
    plan.add_edge(MachinePlanEdge.direct("doc", "extract"))
    plan.add_edge(MachinePlanEdge.direct("extract", "summarize"))
    plan.add_edge(MachinePlanEdge.arg("now", "summarize", CONTEXT))
    plan.validate()

    registry = _registry()
    with pytest.raises(InvalidGraphError) as refusal:
        plan_to_resolved_graph(plan, registry)
    assert "has a map ('each')" in refusal.value.message

    body = steps_to_resolved_graph(plan, ["extract", "summarize"], registry)
    assert len(body.steps) == 2
    assert _step(body, "extract").inputs[0].source == StepSource.of_node("doc")
    assert body.nodes["doc"] == "media:document;ext=pdf", "the item is what the body is given"
    assert body.nodes["now"] == "media:stamp", "a step of the enclosing scope is given whole"

    # Not a step, and not in the plan.
    for ids, expect in [
        (["each"], "'each' is not a step of plan 'mapped'"),
        (["nowhere"], "'nowhere' is not a node of plan 'mapped'"),
    ]:
        with pytest.raises(InvalidGraphError) as refusal:
            steps_to_resolved_graph(plan, ids, registry)
        assert refusal.value.message == expect


# TEST771: a plan that wires a step in a way no invocation can be given is
# refused by what is wrong: two sources on one input stream (two main inputs;
# the same arg named by two edges, however its URN is spelled), a map wired
# straight into a step, a cap the registry does not have.
def test_771_a_step_no_invocation_can_be_given_is_refused():
    registry = _registry()

    def refused(change, expect: str) -> None:
        plan = _plan()
        change(plan)
        with pytest.raises(InvalidGraphError) as refusal:
            plan_to_resolved_graph(plan, registry)
        assert expect in refusal.value.message, f"expected {expect!r} in: {refusal.value.message}"

    refused(
        lambda plan: plan.add_edge(MachinePlanEdge.direct("now", "summarize")),
        "step 'summarize' is wired twice on input stream 'media:enc=utf-8;ext=txt'",
    )
    refused(
        # The same arg, its tags in another order.
        lambda plan: plan.add_edge(MachinePlanEdge.arg("doc", "summarize", "media:enc=utf-8;context")),
        "step 'summarize' is wired twice on input stream",
    )
    refused(
        lambda plan: plan.add_edge(MachinePlanEdge.iteration("now", "summarize")),
        "step 'summarize' has an incoming Iteration edge from 'now'",
    )
    refused(
        lambda plan: plan.add_edge(MachinePlanEdge.collection("now", "summarize")),
        "step 'summarize' has an incoming Collection edge from 'now'",
    )
    refused(
        lambda plan: plan.add_edge(MachinePlanEdge.arg("out", "extract", CONTEXT)),
        "step 'extract' is wired from 'out', which holds no value",
    )
    refused(
        lambda plan: plan.add_edge(MachinePlanEdge.arg("doc", "extract", "not a urn")),
        "step 'extract': input stream URN 'not a urn' is not a media URN",
    )
    refused(
        lambda plan: plan.add_edge(MachinePlanEdge.arg("nowhere", "extract", CONTEXT)),
        "step 'extract' is wired from 'nowhere', which is not in the plan",
    )

    def gather_a_missing_node(plan: MachinePlan) -> None:
        plan.nodes["both"].node_type.input_nodes.append("nowhere")

    refused(gather_a_missing_node, "a step reads 'nowhere', which is not in the plan")

    def gather_an_output(plan: MachinePlan) -> None:
        plan.nodes["both"].node_type.input_nodes.append("out")

    refused(gather_an_output, "a step reads 'out', which holds no value (Output)")

    unknown = _plan()
    unknown.add_node(MachineNode.cap("mystery", 'cap:in="media:x";mystery;out="media:y"'))
    with pytest.raises(CapNotFoundError) as missing:
        plan_to_resolved_graph(unknown, registry)
    assert "mystery" in missing.value.cap_urn
    # A step the graph only reads from is looked up too.
    reading = _plan()
    reading.add_node(MachineNode.cap("mystery", 'cap:in="media:x";mystery;out="media:enc=utf-8;ext=txt"'))
    reading.edges[:] = [edge for edge in reading.edges if (edge.from_node, edge.to_node) != ("extract", "split")]
    reading.add_edge(MachinePlanEdge.direct("mystery", "split"))
    with pytest.raises(CapNotFoundError) as missing:
        steps_to_resolved_graph(reading, ["split"], registry)
    assert "mystery" in missing.value.cap_urn


# TEST953: a step's policy and its token go with it into the graph.
def test_953_a_step_keeps_its_token_and_policy():
    plan = _plan()
    policy = StepPolicy(retry=2, on_error=ON_ERROR_ABSENT)
    plan.nodes["extract"].node_type.policy = policy
    token = plan.nodes["extract"].node_type.token_id
    graph = plan_to_resolved_graph(plan, _registry())
    assert _step(graph, "extract").policy == policy
    assert _step(graph, "extract").token_id == token
    assert _step(graph, "summarize").policy.is_default()
    assert _step(graph, "summarize").token_id != token, "each step has its own"
