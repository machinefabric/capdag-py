"""Tests for planner execution plan structures."""

import json

import pytest

from capdag.planner.argument_binding import ArgumentBindings
from capdag.planner.cardinality import InputCardinality
from capdag.planner.plan import (
    EdgeType,
    ExecutionNodeType,
    ForEachSource,
    MachineNode,
    MachinePlan,
    MachinePlanEdge,
    MachineResult,
    MapRun,
    NodeExecutionResult,
    BodyOutcome,
)
from capdag.planner.error import InternalError
from capdag.planner.live_cap_fab import StepToken
from capdag.planner.policy import ON_ERROR_ABSENT, ON_ERROR_FAIL, StepPolicy


# TEST6525: Body outcomes preserve explicit null attribution coordinates and preview fields in JSON.
def test_6525_body_outcome_serialization_preserves_attribution_shape():
    outcome = BodyOutcome(body_index=0, foreach_token_id=None, success=True)
    encoded = outcome.to_dict()

    assert "foreach_token_id" in encoded and encoded["foreach_token_id"] is None
    assert "failed_token_id" in encoded and encoded["failed_token_id"] is None
    assert "failed_arg_urn" in encoded and encoded["failed_arg_urn"] is None
    assert "item_preview_text" in encoded and encoded["item_preview_text"] is None
    assert encoded["item_byte_count"] == 0

    # What is written is read back, and a coordinate left out is not an
    # outcome: each is required, though it may be null.
    assert BodyOutcome.from_dict(json.loads(json.dumps(encoded))).to_dict() == encoded
    for coordinate in ["foreach_token_id", "failed_token_id", "failed_arg_urn"]:
        missing = {key: value for key, value in encoded.items() if key != coordinate}
        with pytest.raises(ValueError, match=coordinate):
            BodyOutcome.from_dict(missing)

    with pytest.raises(ValueError, match="linear BodyOutcome must use body_index 0"):
        BodyOutcome(body_index=1, foreach_token_id=None, success=True)
    with pytest.raises(ValueError, match="linear BodyOutcome must use body_index 0"):
        BodyOutcome.from_dict({**encoded, "body_index": 1})

    # The runs a body is inside are written as a list, empty for a body of
    # the machine's own map; a linear outcome is inside no map.
    assert encoded["enclosing"] == []
    outer = MapRun(foreach_token_id=StepToken.parse("tok-outer"), body_index=2)
    with pytest.raises(ValueError, match="a linear BodyOutcome is inside no map"):
        BodyOutcome(body_index=0, foreach_token_id=None, success=True, enclosing=[outer])
    with pytest.raises(ValueError, match="a linear BodyOutcome is inside no map"):
        BodyOutcome.from_dict({**encoded, "enclosing": [outer.to_dict()]})

    foreach = BodyOutcome(
        body_index=3,
        foreach_token_id="tok-foreach",
        success=True,
    )
    assert foreach.to_dict()["foreach_token_id"] == "tok-foreach"
    assert foreach.to_dict()["body_index"] == 3
    decoded = BodyOutcome.from_dict(json.loads(json.dumps(foreach.to_dict())))
    assert (decoded.body_index, decoded.foreach_token_id, decoded.enclosing) == (3, "tok-foreach", [])
    # An outcome written before a body could be inside another map says so by
    # leaving the list out.
    without = {key: value for key, value in foreach.to_dict().items() if key != "enclosing"}
    assert BodyOutcome.from_dict(without).enclosing == []

    # A body of a map opened inside another names the run it is inside.
    nested = BodyOutcome(body_index=3, foreach_token_id="tok-foreach", success=True, enclosing=[outer])
    assert nested.to_dict()["enclosing"] == [{"foreach_token_id": "tok-outer", "body_index": 2}]
    assert BodyOutcome.from_dict(json.loads(json.dumps(nested.to_dict()))).enclosing == [outer]
    # A run that names no map is not a run.
    for not_a_run in [{"body_index": 2}, {"foreach_token_id": "", "body_index": 2},
                      {"foreach_token_id": "tok-outer"}, {"foreach_token_id": "tok-outer", "body_index": -1}]:
        with pytest.raises(ValueError):
            MapRun.from_dict(not_a_run)


# TEST728: Tests MachineNode helper methods for identifying node types (cap, fan-out, fan-in) Verifies is_cap(), is_fan_out(), is_fan_in(), and cap_urn() correctly classify node types
def test_728_cap_node_helpers():
    cap_node = MachineNode.cap("test", "cap:test")
    assert cap_node.is_cap()
    assert not cap_node.is_fan_out()
    assert not cap_node.is_fan_in()
    assert cap_node.get_cap_urn() == "cap:test"

    foreach_node = MachineNode.for_each(
        "foreach", [ForEachSource(node="input", item="item")], ["item", "body"]
    )
    assert not foreach_node.is_cap()
    assert foreach_node.is_fan_out()
    assert not foreach_node.is_fan_in()
    assert foreach_node.get_cap_urn() is None

    collect_node = MachineNode.collect("collect", ["a"], "media:")
    assert not collect_node.is_cap()
    assert not collect_node.is_fan_out()
    assert collect_node.is_fan_in()


# TEST729: Tests creation and classification of different edge types (Direct, Iteration, Collection, Arg) Verifies that edge constructors produce correct EdgeType variants
def test_729_edge_types():
    direct = MachinePlanEdge.direct("a", "b")
    assert direct.edge_type.kind == EdgeType.DIRECT
    assert MachinePlanEdge.iteration("foreach", "body").edge_type.kind == EdgeType.ITERATION
    assert MachinePlanEdge.collection("body", "collect").edge_type.kind == EdgeType.COLLECTION
    arg = MachinePlanEdge.arg("a", "b", "media:data")
    assert arg.edge_type.kind == EdgeType.ARG
    assert arg.edge_type.arg_urn == "media:data"
    assert direct.edge_type.arg_urn is None, "only an arg edge names an argument"


# TEST734: Tests topological sort detects self-referencing cycles (A→A) Verifies that self-loops are recognized as cycles and produce an error
def test_734_topological_order_self_loop():
    plan = MachinePlan("self_loop")
    plan.nodes["A"] = MachineNode.cap("A", "cap:a")
    plan.edges.append(MachinePlanEdge.direct("A", "A"))
    with pytest.raises(InternalError, match="Cycle detected"):
        plan.topological_order()


# TEST735: Tests topological sort handles graphs with multiple independent starting nodes Verifies that parallel entry points (A→C, B→C) both precede their merge point in ordering
def test_735_topological_order_multiple_entry_points():
    plan = MachinePlan("multi_entry")
    for name in ["A", "B", "C", "D"]:
        plan.nodes[name] = MachineNode.cap(name, f"cap:{name.lower()}")
    plan.edges.extend(
        [
            MachinePlanEdge.direct("A", "C"),
            MachinePlanEdge.direct("B", "C"),
            MachinePlanEdge.direct("C", "D"),
        ]
    )
    order = plan.topological_order()
    positions = {node.id: index for index, node in enumerate(order)}
    assert len(order) == 4
    assert positions["A"] < positions["C"]
    assert positions["B"] < positions["C"]
    assert positions["C"] < positions["D"]


# TEST736: Tests topological sort on a complex multi-path DAG with 6 nodes Verifies that all dependency constraints are satisfied in a graph with multiple converging paths
def test_736_topological_order_complex_dag():
    plan = MachinePlan("complex")
    for name in ["A", "B", "C", "D", "E", "F"]:
        plan.nodes[name] = MachineNode.cap(name, f"cap:{name.lower()}")
    plan.edges.extend(
        [
            MachinePlanEdge.direct("A", "B"),
            MachinePlanEdge.direct("A", "C"),
            MachinePlanEdge.direct("B", "D"),
            MachinePlanEdge.direct("B", "E"),
            MachinePlanEdge.direct("C", "E"),
            MachinePlanEdge.direct("D", "F"),
            MachinePlanEdge.direct("E", "F"),
        ]
    )
    order = plan.topological_order()
    pos = {node.id: index for index, node in enumerate(order)}
    assert len(order) == 6
    assert pos["A"] == 0
    assert pos["F"] == 5
    assert pos["B"] < pos["D"] < pos["F"]
    assert pos["B"] < pos["E"] < pos["F"]
    assert pos["C"] < pos["E"]


# TEST737: Tests linear_chain() with exactly one capability Verifies that a single-element chain produces a valid plan with input_slot, cap, and output
def test_737_linear_chain_single_cap():
    plan = MachinePlan.linear_chain(["cap:only"], "media:document;ext=pdf", "media:ext=png;image", ["source_file"])
    assert len(plan.nodes) == 3
    assert len(plan.edges) == 2
    plan.validate()


# TEST738: Tests linear_chain() with empty capability list Verifies that an empty chain produces a plan with zero nodes and edges
def test_738_linear_chain_empty():
    plan = MachinePlan.linear_chain([], "media:document;ext=pdf", "media:ext=png;image", [])
    assert len(plan.nodes) == 0
    assert len(plan.edges) == 0


# TEST739: Tests NodeExecutionResult structure for successful node execution Verifies that success status, outputs (binary and text), and error fields work correctly
def test_739_node_execution_result_success():
    result = NodeExecutionResult(
        node_id="node_0",
        success=True,
        binary_output=b"\x01\x02\x03",
        error=None,
        duration_ms=50,
    )
    assert result.success
    assert result.binary_output is not None
    assert result.error is None


# TEST742: Tests EdgeType enum serialization and deserialization to/from JSON Verifies that every edge type round-trips by its name, and that a kind this library does not carry is refused
def test_742_edge_type_serialization():
    payload = json.dumps(EdgeType.direct().to_dict())
    assert payload == '"direct"'
    direct = EdgeType.from_dict(json.loads(payload))
    assert direct.kind == EdgeType.DIRECT

    for written, edge_type in [
        ('"direct"', EdgeType.direct()),
        ('"iteration"', EdgeType.iteration()),
        ('"collection"', EdgeType.collection()),
        ('{"arg": {"arg_urn": "media:data"}}', EdgeType.arg("media:data")),
    ]:
        assert json.dumps(edge_type.to_dict()) == written
        assert EdgeType.from_dict(json.loads(written)) == edge_type, written
    # Two arg edges are the same edge type when they name the same arg.
    assert EdgeType.arg("media:data") != EdgeType.arg("media:other")
    assert EdgeType.arg("media:data") != EdgeType.direct()
    # An arg edge that names no argument is not one.
    with pytest.raises(ValueError):
        EdgeType.from_dict({"arg": {}})

    # An edge carries the whole value: a part of it is not something an edge
    # can be asked for, in either of the forms that once said so — and a kind
    # nothing has is no kind, whatever it carries.
    for retired in ['{"json_field":{"field":"data"}}', '{"json_path":{"path":"a.b"}}',
                    '"json_field"', '"sideways"', '"arg"', '{"sideways":{"arg_urn":"media:data"}}',
                    '{"type":"json_field","field":"data"}']:
        with pytest.raises(ValueError):
            EdgeType.from_dict(json.loads(retired))


def _token(text: str) -> StepToken:
    return StepToken.parse(text)


# TEST743: Tests ExecutionNodeType enum serialization and deserialization to/from JSON Verifies that node types like Cap and ForEach correctly serialize with their fields
def test_743_execution_node_type_serialization():
    def back(node: ExecutionNodeType) -> ExecutionNodeType:
        return ExecutionNodeType.from_dict(json.loads(json.dumps(node.to_dict())))

    cap_node = ExecutionNodeType.cap("cap:test", ArgumentBindings(), token_id=_token("tok-cap-test"))
    written = cap_node.to_dict()
    assert written["node_type"] == "cap"
    assert written["cap_urn"] == "cap:test"
    assert written["token_id"] == "tok-cap-test", "a step node carries its identity"
    assert "policy" not in written, "the default policy is not written"
    assert back(cap_node).token_id == cap_node.token_id
    # A step that wrote a policy carries it.
    cap_node.policy = StepPolicy(retry=2, on_error=ON_ERROR_ABSENT)
    assert cap_node.to_dict()["policy"] == {"retry": 2, "on_error": "absent"}
    assert back(cap_node).policy == cap_node.policy
    # A policy is written whole: retries alone still say what a failure does.
    assert StepPolicy(retry=1).to_dict() == {"retry": 1, "on_error": "fail"}
    assert StepPolicy.from_dict({"retry": 3}) == StepPolicy(retry=3, on_error=ON_ERROR_FAIL), \
        "a field left out is its default"

    foreach_node = ExecutionNodeType.for_each(
        [ForEachSource(node="input", item="item")], ["item", "body"], token_id=_token("tok-foreach")
    )
    assert foreach_node.to_dict() == {
        "node_type": "for_each",
        "token_id": "tok-foreach",
        "sources": [{"node": "input", "item": "item"}],
        "body": ["item", "body"],
    }
    assert back(foreach_node) == foreach_node
    assert back(foreach_node).sources == [ForEachSource(node="input", item="item")]

    output_node = MachineNode.cap_output("o", "tok-cap-test", "media:residuals", "residuals", False).node_type
    assert output_node.to_dict() == {
        "node_type": "cap_output",
        "cap_node": "tok-cap-test",
        "output_media_urn": "media:residuals",
        "output_name": "residuals",
        "carries_input": False,
    }
    assert back(output_node) == output_node
    carrying = MachineNode.cap_output("o", "route", "media:dropped", "no", True).node_type
    assert back(carrying).carries_input is True

    item_node = MachineNode.item("item", "each", "input", "media:page").node_type
    assert item_node.to_dict() == {
        "node_type": "item", "foreach": "each", "source": "input", "media_urn": "media:page",
    }
    assert back(item_node) == item_node

    gather = MachineNode.collect("g", ["a", "b"], "media:summary").node_type
    assert gather.to_dict() == {
        "node_type": "collect", "input_nodes": ["a", "b"], "output_media_urn": "media:summary",
    }
    assert back(gather) == gather

    # A node type nothing produces is not read, nor is a node missing a field
    # its kind has, nor a map in the shape it once had.
    for refused in [
        '{"node_type":"merge","input_nodes":["a"],"merge_strategy":"concat"}',
        '{"node_type":"split","input_node":"a","output_count":2}',
        '{"node_type":"for_each","input_node":"a","body_entry":"b","body_exit":"b"}',
        '{"node_type":"for_each","token_id":"t","sources":[{"node":"a","item":"i"}]}',
        '{"node_type":"for_each","token_id":"t","sources":[{"node":"a"}],"body":[]}',
        '{"node_type":"collect","input_nodes":["a"]}',
        '{"node_type":"cap","cap_urn":"cap:test"}',
        '{"node_type":"cap","token_id":"","cap_urn":"cap:test"}',
        '{"node_type":"cap","token_id":"t","cap_urn":"cap:test","policy":{"on_error":"shrug"}}',
        '{"node_type":"item","foreach":"each","source":"input"}',
        '{"cap_urn":"cap:test"}',
    ]:
        with pytest.raises(ValueError):
            ExecutionNodeType.from_dict(json.loads(refused))


# TEST744: Tests MachinePlan serialization and deserialization to/from JSON Verifies that complete plans with nodes and edges correctly round-trip through JSON
def test_744_plan_serialization():
    plan = MachinePlan.single_cap("cap:test", "media:document;ext=pdf", "media:ext=png;image", "input_file")
    payload = json.dumps(plan.to_dict())
    assert "cap:test" in payload
    assert "input_slot" in payload
    assert "output" in payload
    round_trip = MachinePlan.from_dict(json.loads(payload))
    assert len(round_trip.nodes) == len(plan.nodes)
    assert len(round_trip.edges) == len(plan.edges)


# TEST746: Tests creation of Output node type that references a source node Verifies that MachineNode::output() correctly constructs an Output node with name and source
def test_746_cap_node_output():
    output = MachineNode.output("out", "result", "source")
    assert output.node_type.kind == ExecutionNodeType.OUTPUT
    assert output.node_type.output_name == "result"
    assert output.node_type.source_node == "source"


# TEST749: Tests get_node() method for looking up nodes by ID in a plan Verifies that existing nodes are found and non-existent nodes return None
def test_749_get_node():
    plan = MachinePlan.single_cap("cap:test", "media:document;ext=pdf", "media:ext=png;image", "doc_path")
    assert plan.get_node("cap_0") is not None
    assert plan.get_node("input_slot") is not None
    assert plan.get_node("output") is not None
    assert plan.get_node("nonexistent") is None


def _build_foreach_plan() -> MachinePlan:
    """A plan with a map and a fold after it: input_slot → cap_0 (a sequence)
    → map over it [ body_cap_0 → body_cap_1 ] → cap_post (takes the sequence
    of body_cap_1 over the runs) → output."""
    plan = MachinePlan("ForEach test plan")
    plan.add_node(MachineNode.input_slot("input_slot", "input", "media:document;ext=pdf", InputCardinality.SINGLE))
    plan.add_node(MachineNode.cap("cap_0", 'cap:in="media:document;ext=pdf";out="media:pdf-page;list"'))
    plan.add_node(MachineNode.for_each(
        "foreach_0",
        [ForEachSource(node="cap_0", item="foreach_0_item_0")],
        ["foreach_0_item_0", "body_cap_0", "body_cap_1"],
    ))
    plan.add_node(MachineNode.item("foreach_0_item_0", "foreach_0", "cap_0", "media:pdf-page"))
    plan.add_node(MachineNode.cap("body_cap_0", 'cap:in=media:pdf-page;out="media:enc=utf-8;text"'))
    plan.add_node(MachineNode.cap("body_cap_1", 'cap:in="media:enc=utf-8;text";out="media:decision;fmt=json;record"'))
    plan.add_node(MachineNode.cap("cap_post", 'cap:in="media:decision;fmt=json;record";out="media:fmt=json"'))
    plan.add_node(MachineNode.output("output", "result", "cap_post"))

    plan.add_edge(MachinePlanEdge.direct("input_slot", "cap_0"))
    plan.add_edge(MachinePlanEdge.direct("cap_0", "foreach_0"))
    plan.add_edge(MachinePlanEdge.iteration("foreach_0", "foreach_0_item_0"))
    plan.add_edge(MachinePlanEdge.direct("foreach_0_item_0", "body_cap_0"))
    plan.add_edge(MachinePlanEdge.direct("body_cap_0", "body_cap_1"))
    plan.add_edge(MachinePlanEdge.direct("body_cap_1", "cap_post"))
    plan.add_edge(MachinePlanEdge.direct("cap_post", "output"))
    return plan


# TEST936: has_foreach detects a map, and a gather alone is not one.
def test_936_has_foreach():
    foreach_plan = _build_foreach_plan()
    foreach_plan.validate()
    assert foreach_plan.has_foreach()

    linear_plan = MachinePlan.linear_chain(["cap:a"], "media:document;ext=pdf", "media:ext=png;image", ["input_a"])
    assert not linear_plan.has_foreach()

    gather_plan = MachinePlan("gather_only")
    gather_plan.add_node(MachineNode.input_slot("input", "input", "media:enc=utf-8", InputCardinality.SINGLE))
    gather_plan.add_node(MachineNode.cap("cap_0", 'cap:in="media:enc=utf-8";summarize;out=media:summary'))
    gather_plan.add_node(MachineNode.collect("collect_0", ["cap_0"], "media:summary"))
    gather_plan.add_node(MachineNode.output("output", "result", "collect_0"))
    gather_plan.validate()
    assert not gather_plan.has_foreach()


# TEST12753: a plan says which map each node runs in — the map whose body
# lists it — and which nodes are inside a map at any depth.
def test_12753_a_plan_says_which_map_a_node_runs_in():
    plan = _build_foreach_plan()
    enclosing = plan.enclosing_maps()
    assert enclosing["body_cap_0"] == "foreach_0"
    assert enclosing["body_cap_1"] == "foreach_0"
    assert enclosing["foreach_0_item_0"] == "foreach_0"
    for outside in ["input_slot", "cap_0", "foreach_0", "cap_post", "output"]:
        assert outside not in enclosing, f"{outside} is the machine's own"

    # A map opened inside the body: its nodes are inside the outer map, and
    # the outer body lists the inner map, not the inner body.
    plan.add_node(MachineNode.for_each(
        "foreach_1",
        [ForEachSource(node="body_cap_0", item="foreach_1_item_0")],
        ["foreach_1_item_0", "inner_cap"],
    ))
    plan.add_node(MachineNode.item("foreach_1_item_0", "foreach_1", "body_cap_0", "media:enc=utf-8;text"))
    plan.add_node(MachineNode.cap("inner_cap", 'cap:in="media:enc=utf-8;text";out=media:word'))
    plan.nodes["foreach_0"].node_type.body.append("foreach_1")
    plan.validate()
    enclosing = plan.enclosing_maps()
    assert enclosing["inner_cap"] == "foreach_1"
    assert enclosing["foreach_1"] == "foreach_0"
    assert plan.map_members("foreach_0") == {
        "body_cap_0", "body_cap_1", "foreach_0_item_0", "foreach_1", "foreach_1_item_0", "inner_cap",
    }
    assert plan.map_members("foreach_1") == {"foreach_1_item_0", "inner_cap"}
    assert plan.map_members("cap_0") == set(), "a step is no map"


# TEST12754: a plan whose nodes name what is not there, or name it as what it
# is not, is refused: a map that iterates nothing, an item its map does not
# list, a node in two bodies, an output node of something that is not a step,
# a gather of a missing node.
def test_12754_a_plan_that_names_what_is_not_there_is_refused():
    def refused(change, expect: str) -> None:
        plan = _build_foreach_plan()
        change(plan)
        with pytest.raises(InternalError) as error:
            plan.validate()
        assert expect in str(error.value), f"expected {expect!r} in: {error.value}"

    def the_map(plan: MachinePlan) -> ExecutionNodeType:
        return plan.nodes["foreach_0"].node_type

    def relist(plan: MachinePlan, node: str, item: str) -> None:
        the_map(plan).sources[0] = ForEachSource(node=node, item=item)

    refused(lambda plan: the_map(plan).sources.clear(), "map 'foreach_0' iterates nothing")
    refused(lambda plan: plan.add_node(MachineNode.for_each("lonely", [], [])), "map 'lonely' iterates nothing")
    refused(lambda plan: relist(plan, "cap_0", "body_cap_0"), "which is not that")
    refused(lambda plan: relist(plan, "nowhere", "foreach_0_item_0"),
            "node 'foreach_0' names source 'nowhere', which is not in the plan")
    refused(lambda plan: relist(plan, "cap_0", "nowhere"),
            "node 'foreach_0' names item 'nowhere', which is not in the plan")
    # The item it lists is an item — of another source, or of another map.
    refused(lambda plan: relist(plan, "input_slot", "foreach_0_item_0"),
            "map 'foreach_0' lists 'foreach_0_item_0' as its item of 'input_slot', which is not that")
    refused(
        lambda plan: plan.add_node(MachineNode.for_each(
            "second", [ForEachSource(node="cap_0", item="foreach_0_item_0")], ["foreach_0_item_0"],
        )),
        "map 'second' lists 'foreach_0_item_0' as its item of 'cap_0', which is not that",
    )

    def drop_item_from_body(plan: MachinePlan) -> None:
        the_map(plan).body[:] = ["body_cap_0", "body_cap_1"]

    refused(drop_item_from_body, "does not list its item 'foreach_0_item_0' in its body")

    def second_map_over_a_body_node(plan: MachinePlan) -> None:
        plan.add_node(MachineNode.for_each(
            "second", [ForEachSource(node="cap_0", item="second_item")], ["second_item", "body_cap_1"],
        ))
        plan.add_node(MachineNode.item("second_item", "second", "cap_0", "media:pdf-page"))

    refused(second_map_over_a_body_node, "node 'body_cap_1' is in the body of two maps ('foreach_0' and 'second')")
    refused(lambda plan: the_map(plan).body.append("foreach_0"), "map 'foreach_0' lists itself in its body")
    refused(lambda plan: plan.add_node(MachineNode.cap_output("o", "input_slot", "media:x", "x", False)),
            "names 'input_slot' as its step, which is not a step")
    refused(lambda plan: plan.add_node(MachineNode.cap_output("o", "nowhere", "media:x", "x", False)),
            "node 'o' names step 'nowhere', which is not in the plan")
    refused(lambda plan: plan.add_node(MachineNode.collect("g", ["nowhere"], "media:")),
            "node 'g' names gathered node 'nowhere', which is not in the plan")
    refused(lambda plan: plan.add_node(MachineNode.output("o2", "result", "nowhere")),
            "node 'o2' names source 'nowhere', which is not in the plan")
    refused(lambda plan: plan.add_node(MachineNode.item("stray", "foreach_0", "cap_0", "media:pdf-page")),
            "item node 'stray' names map 'foreach_0'")
    refused(lambda plan: plan.add_node(MachineNode.item("stray", "cap_0", "input_slot", "media:pdf-page")),
            "item node 'stray' names map 'cap_0'")
    refused(lambda plan: plan.add_node(MachineNode.item("stray", "nowhere", "cap_0", "media:pdf-page")),
            "node 'stray' names map 'nowhere', which is not in the plan")
    refused(lambda plan: the_map(plan).body.append("nowhere"),
            "node 'foreach_0' names body node 'nowhere', which is not in the plan")

    # An item its map lists for another source: nodes are checked in the order
    # of their ids, so it is the item — which comes first — that is named.
    def an_item_of_another_source(plan: MachinePlan) -> None:
        plan.add_node(MachineNode.for_each(
            "second", [ForEachSource(node="cap_0", item="an_item")], ["an_item"],
        ))
        plan.add_node(MachineNode.item("an_item", "second", "input_slot", "media:pdf-page"))

    refused(an_item_of_another_source,
            "item node 'an_item' names map 'second' and source 'input_slot', and that map does not list it so")

    # A step's other output, of a step: accepted.
    plan = _build_foreach_plan()
    plan.add_node(MachineNode.cap_output("o", "cap_0", "media:x", "x", False))
    plan.validate()


# TEST927: Tests MachineResult structure for successful execution outcomes Verifies that success status, outputs, and primary_output() accessor work correctly
def test_927_execution_result():
    result = MachineResult(
        success=True,
        outputs={"output": {"result": "success"}},
        total_duration_ms=100,
    )
    assert result.success
    assert result.primary_output() is not None


# TEST924: Tests plan validation detects edges pointing to non-existent nodes Verifies that validate() returns an error when an edge references a missing to_node
def test_924_validate_invalid_edge():
    plan = MachinePlan("invalid")
    plan.nodes["node_0"] = MachineNode.cap("node_0", "cap:test")
    plan.edges.append(MachinePlanEdge.direct("node_0", "nonexistent"))
    with pytest.raises(InternalError, match="Edge to_node 'nonexistent' not found"):
        plan.validate()


# TEST925: Tests topological sort correctly orders a diamond-shaped DAG (A->B,C->D) Verifies that nodes with multiple paths respect dependency constraints (A first, D last)
def test_925_topological_order_diamond():
    plan = MachinePlan("diamond")
    for name in ["A", "B", "C", "D"]:
        plan.nodes[name] = MachineNode.cap(name, f"cap:{name.lower()}")
    plan.edges.extend(
        [
            MachinePlanEdge.direct("A", "B"),
            MachinePlanEdge.direct("A", "C"),
            MachinePlanEdge.direct("B", "D"),
            MachinePlanEdge.direct("C", "D"),
        ]
    )
    order = plan.topological_order()
    assert len(order) == 4
    assert order[0].id == "A"
    assert order[3].id == "D"


# TEST926: Tests topological sort detects and rejects cyclic dependencies (A->B->C->A) Verifies that circular references produce a "Cycle detected" error
def test_926_topological_order_detects_cycle():
    plan = MachinePlan("cyclic")
    for name in ["A", "B", "C"]:
        plan.nodes[name] = MachineNode.cap(name, f"cap:{name.lower()}")
    plan.edges.extend(
        [
            MachinePlanEdge.direct("A", "B"),
            MachinePlanEdge.direct("B", "C"),
            MachinePlanEdge.direct("C", "A"),
        ]
    )
    with pytest.raises(InternalError, match="Cycle detected"):
        plan.topological_order()


# TEST928: Tests plan validation detects edges originating from non-existent nodes Verifies that validate() returns an error when an edge references a missing from_node
def test_928_validate_invalid_from_node():
    plan = MachinePlan("invalid")
    plan.nodes["node_0"] = MachineNode.cap("node_0", "cap:test")
    plan.edges.append(MachinePlanEdge.direct("nonexistent", "node_0"))
    with pytest.raises(InternalError, match="Edge from_node 'nonexistent' not found"):
        plan.validate()


# TEST929: Tests plan validation detects invalid entry node references Verifies that validate() returns an error when entry_nodes contains a non-existent node ID
def test_929_validate_invalid_entry_node():
    plan = MachinePlan("invalid_entry")
    plan.nodes["cap_0"] = MachineNode.cap("cap_0", "cap:test")
    plan.entry_nodes.append("nonexistent_entry")
    with pytest.raises(InternalError, match="Entry node 'nonexistent_entry' not found"):
        plan.validate()


# TEST930: Tests plan validation detects invalid output node references Verifies that validate() returns an error when output_nodes contains a non-existent node ID
def test_930_validate_invalid_output_node():
    plan = MachinePlan("invalid_output")
    plan.nodes["cap_0"] = MachineNode.cap("cap_0", "cap:test")
    plan.output_nodes.append("nonexistent_output")
    with pytest.raises(InternalError, match="Output node 'nonexistent_output' not found"):
        plan.validate()


# TEST931: Tests NodeExecutionResult structure for failed node execution Verifies that failure status, error message, and absence of outputs are correctly represented
def test_931_node_execution_result_failure():
    result = NodeExecutionResult(
        node_id="node_0",
        success=False,
        binary_output=None,
        error="Cap execution failed",
        duration_ms=10,
    )
    assert not result.success
    assert result.binary_output is None
    assert result.error == "Cap execution failed"


# TEST932: Tests MachineResult structure for failed chain execution Verifies that failure status, error message, and absence of outputs are correctly represented
def test_932_execution_result_failure():
    result = MachineResult(
        success=False,
        outputs={},
        error="Chain failed",
        total_duration_ms=100,
    )
    assert not result.success
    assert result.error == "Chain failed"
    assert result.primary_output() is None
