"""Tests for planner execution plan structures."""

import json

import pytest

from capdag.planner.argument_binding import ArgumentBindings
from capdag.planner.cardinality import InputCardinality
from capdag.planner.plan import (
    EdgeType,
    ExecutionNodeType,
    MachineNode,
    MachinePlan,
    MachinePlanEdge,
    MachineResult,
    MergeStrategy,
    NodeExecutionResult,
)
from capdag.planner.error import InternalError


# TEST728: Tests MachineNode helper methods for identifying node types (cap, fan-out, fan-in) Verifies is_cap(), is_fan_out(), is_fan_in(), and cap_urn() correctly classify node types
def test_728_cap_node_helpers():
    cap_node = MachineNode.cap("test", "cap:test")
    assert cap_node.is_cap()
    assert not cap_node.is_fan_out()
    assert not cap_node.is_fan_in()
    assert cap_node.get_cap_urn() == "cap:test"

    foreach_node = MachineNode.for_each("foreach", "input", "body", "body")
    assert not foreach_node.is_cap()
    assert foreach_node.is_fan_out()
    assert not foreach_node.is_fan_in()
    assert foreach_node.get_cap_urn() is None

    collect_node = MachineNode.collect("collect", ["a"])
    assert not collect_node.is_cap()
    assert not collect_node.is_fan_out()
    assert collect_node.is_fan_in()


# TEST729: Tests creation and classification of different edge types (Direct, Iteration, Collection, JsonField) Verifies that edge constructors produce correct EdgeType variants
def test_729_edge_types():
    assert MachinePlanEdge.direct("a", "b").edge_type.kind == EdgeType.DIRECT
    assert MachinePlanEdge.iteration("foreach", "body").edge_type.kind == EdgeType.ITERATION
    assert MachinePlanEdge.collection("body", "collect").edge_type.kind == EdgeType.COLLECTION
    json_field = MachinePlanEdge.json_field("a", "b", "data")
    assert json_field.edge_type.kind == EdgeType.JSON_FIELD
    assert json_field.edge_type.field == "data"


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
    plan = MachinePlan.linear_chain(["cap:only"], "media:pdf", "media:image;png", ["source_file"])
    assert len(plan.nodes) == 3
    assert len(plan.edges) == 2
    plan.validate()


# TEST738: Tests linear_chain() with empty capability list Verifies that an empty chain produces a plan with zero nodes and edges
def test_738_linear_chain_empty():
    plan = MachinePlan.linear_chain([], "media:pdf", "media:image;png", [])
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


# TEST742: Tests EdgeType enum serialization and deserialization to/from JSON Verifies that edge types like Direct and JsonField correctly round-trip through serde_json
def test_742_edge_type_serialization():
    payload = json.dumps(EdgeType.direct().to_dict())
    assert payload == '"direct"'
    direct = EdgeType.from_dict(json.loads(payload))
    assert direct.kind == EdgeType.DIRECT

    json_field_payload = json.dumps(EdgeType.json_field("data").to_dict())
    assert "json_field" in json_field_payload
    assert "data" in json_field_payload


# TEST743: Tests ExecutionNodeType enum serialization and deserialization to/from JSON Verifies that node types like Cap and ForEach correctly serialize with their fields
def test_743_execution_node_type_serialization():
    cap_node = ExecutionNodeType.cap("cap:test", ArgumentBindings())
    payload = json.dumps(cap_node.to_dict())
    assert "cap" in payload
    assert "cap:test" in payload

    foreach_node = ExecutionNodeType.for_each("input", "body", "body")
    foreach_payload = json.dumps(foreach_node.to_dict())
    assert "for_each" in foreach_payload


# TEST744: Tests MachinePlan serialization and deserialization to/from JSON Verifies that complete plans with nodes and edges correctly round-trip through JSON
def test_744_plan_serialization():
    plan = MachinePlan.single_cap("cap:test", "media:pdf", "media:image;png", "input_file")
    payload = json.dumps(plan.to_dict())
    assert "cap:test" in payload
    assert "input_slot" in payload
    assert "output" in payload
    round_trip = MachinePlan.from_dict(json.loads(payload))
    assert len(round_trip.nodes) == len(plan.nodes)
    assert len(round_trip.edges) == len(plan.edges)


# TEST745: Tests MergeStrategy enum serialization to JSON Verifies that merge strategies like Concat and ZipWith serialize to correct string values
def test_745_merge_strategy_serialization():
    assert json.dumps(MergeStrategy.CONCAT.value) == '"concat"'
    assert json.dumps(MergeStrategy.ZIP_WITH.value) == '"zip_with"'


# TEST746: Tests creation of Output node type that references a source node Verifies that MachineNode::output() correctly constructs an Output node with name and source
def test_746_cap_node_output():
    output = MachineNode.output("out", "result", "source")
    assert output.node_type.kind == ExecutionNodeType.OUTPUT
    assert output.node_type.output_name == "result"
    assert output.node_type.source_node == "source"


# TEST747: Tests creation and validation of Merge node that combines multiple inputs Verifies that Merge nodes with multiple input nodes and a strategy can be added to plans
def test_747_cap_node_merge():
    plan = MachinePlan("merge_test")
    merge_node = MachineNode(
        "merge",
        ExecutionNodeType.merge(["a", "b"], MergeStrategy.CONCAT),
        description="Merge outputs",
    )
    plan.nodes["a"] = MachineNode.cap("a", "cap:a")
    plan.nodes["b"] = MachineNode.cap("b", "cap:b")
    plan.nodes["merge"] = merge_node
    plan.edges.append(MachinePlanEdge.direct("a", "merge"))
    plan.edges.append(MachinePlanEdge.direct("b", "merge"))
    plan.validate()


# TEST748: Tests creation of Split node that distributes input to multiple outputs Verifies that Split nodes correctly specify an input node and output count
def test_748_cap_node_split():
    split_node = MachineNode(
        "split",
        ExecutionNodeType.split("input", 3),
        description="Split input",
    )
    assert split_node.node_type.kind == ExecutionNodeType.SPLIT
    assert split_node.node_type.input_node == "input"
    assert split_node.node_type.output_count == 3


# TEST749: Tests get_node() method for looking up nodes by ID in a plan Verifies that existing nodes are found and non-existent nodes return None
def test_749_get_node():
    plan = MachinePlan.single_cap("cap:test", "media:pdf", "media:image;png", "doc_path")
    assert plan.get_node("cap_0") is not None
    assert plan.get_node("input_slot") is not None
    assert plan.get_node("output") is not None
    assert plan.get_node("nonexistent") is None


def _build_foreach_plan_with_collect():
    plan = MachinePlan("ForEach test plan")
    plan.add_node(MachineNode.input_slot("input_slot", "input", "media:pdf", InputCardinality.SINGLE))
    plan.add_node(MachineNode.cap("cap_0", 'cap:in=media:pdf;out="media:pdf-page;list"'))
    plan.add_node(MachineNode.for_each("foreach_0", "cap_0", "body_cap_0", "body_cap_1"))
    plan.add_node(MachineNode.cap("body_cap_0", 'cap:in=media:pdf-page;out="media:text;textable"'))
    plan.add_node(
        MachineNode.cap(
            "body_cap_1",
            'cap:in="media:text;textable";out="media:decision;json;record;textable"',
        )
    )
    collect_node = MachineNode.collect("collect_0", ["body_cap_1"])
    collect_node.node_type = ExecutionNodeType.collect(
        ["body_cap_1"], "media:decision;json;record;textable"
    )
    plan.add_node(collect_node)
    plan.add_node(
        MachineNode.cap(
            "cap_post",
            'cap:in="media:decision;json;record;textable";out="media:json;textable"',
        )
    )
    plan.add_node(MachineNode.output("output", "result", "cap_post"))
    plan.add_edge(MachinePlanEdge.direct("input_slot", "cap_0"))
    plan.add_edge(MachinePlanEdge.direct("cap_0", "foreach_0"))
    plan.add_edge(MachinePlanEdge.iteration("foreach_0", "body_cap_0"))
    plan.add_edge(MachinePlanEdge.direct("body_cap_0", "body_cap_1"))
    plan.add_edge(MachinePlanEdge.collection("body_cap_1", "collect_0"))
    plan.add_edge(MachinePlanEdge.direct("collect_0", "cap_post"))
    plan.add_edge(MachinePlanEdge.direct("cap_post", "output"))
    return plan


def _build_foreach_plan_unclosed():
    plan = MachinePlan("Unclosed ForEach test plan")
    plan.add_node(MachineNode.input_slot("input_slot", "input", "media:pdf", InputCardinality.SINGLE))
    plan.add_node(MachineNode.cap("cap_0", 'cap:in=media:pdf;out="media:pdf-page;list"'))
    plan.add_node(MachineNode.for_each("foreach_0", "cap_0", "body_cap_0", "body_cap_0"))
    plan.add_node(
        MachineNode.cap(
            "body_cap_0",
            'cap:in=media:pdf-page;out="media:decision;json;record;textable"',
        )
    )
    plan.add_node(MachineNode.output("output", "result", "body_cap_0"))
    plan.add_edge(MachinePlanEdge.direct("input_slot", "cap_0"))
    plan.add_edge(MachinePlanEdge.direct("cap_0", "foreach_0"))
    plan.add_edge(MachinePlanEdge.iteration("foreach_0", "body_cap_0"))
    plan.add_edge(MachinePlanEdge.direct("body_cap_0", "output"))
    return plan


# TEST754: extract_prefix_to with nonexistent node returns error
def test_754_extract_prefix_nonexistent():
    with pytest.raises(InternalError):
        _build_foreach_plan_with_collect().extract_prefix_to("nonexistent")


# TEST755: extract_foreach_body extracts body as standalone plan
def test_755_extract_foreach_body():
    body = _build_foreach_plan_with_collect().extract_foreach_body("foreach_0", "media:pdf-page")
    assert len(body.nodes) == 4
    assert body.get_node("foreach_0_body_input") is not None
    assert body.get_node("body_cap_0") is not None
    assert body.get_node("body_cap_1") is not None
    assert body.get_node("foreach_0_body_output") is not None
    assert len(body.entry_nodes) == 1
    assert len(body.output_nodes) == 1
    body.validate()
    assert not body.has_foreach()
    assert body.get_node("foreach_0_body_input").node_type.expected_media_urn == "media:pdf-page"
    assert body.get_node("foreach_0_body_input").node_type.cardinality == InputCardinality.SINGLE
    assert len(body.topological_order()) == 4


# TEST756: extract_foreach_body for unclosed ForEach (single body cap)
def test_756_extract_foreach_body_unclosed():
    body = _build_foreach_plan_unclosed().extract_foreach_body("foreach_0", "media:pdf-page")
    assert len(body.nodes) == 3
    assert body.get_node("foreach_0_body_input") is not None
    assert body.get_node("body_cap_0") is not None
    assert body.get_node("foreach_0_body_output") is not None
    body.validate()
    assert not body.has_foreach()


# TEST757: extract_foreach_body fails for non-ForEach node
def test_757_extract_foreach_body_wrong_type():
    with pytest.raises(InternalError, match="not a ForEach node"):
        _build_foreach_plan_with_collect().extract_foreach_body("cap_0", "media:pdf-page")


# TEST758: extract_suffix_from extracts collect → cap_post → output
def test_758_extract_suffix_from():
    suffix = _build_foreach_plan_with_collect().extract_suffix_from(
        "collect_0", "media:decision;json;record;textable"
    )
    assert len(suffix.nodes) == 3
    assert suffix.get_node("collect_0_suffix_input") is not None
    assert suffix.get_node("cap_post") is not None
    assert suffix.get_node("output") is not None
    assert len(suffix.entry_nodes) == 1
    assert len(suffix.output_nodes) == 1
    suffix.validate()
    assert not suffix.has_foreach()


# TEST759: extract_suffix_from fails for nonexistent node
def test_759_extract_suffix_nonexistent():
    with pytest.raises(InternalError):
        _build_foreach_plan_with_collect().extract_suffix_from("nonexistent", "media:whatever")


# TEST760: Full decomposition roundtrip — prefix + body + suffix cover all cap nodes
def test_760_decomposition_covers_all_caps():
    plan = _build_foreach_plan_with_collect()
    original_caps = {node.id for node in plan.nodes.values() if node.is_cap()}
    assert len(original_caps) == 4
    prefix = plan.extract_prefix_to("cap_0")
    body = plan.extract_foreach_body("foreach_0", "media:pdf-page")
    suffix = plan.extract_suffix_from("collect_0", "media:decision;json;record;textable")
    combined_caps = {node.id for node in prefix.nodes.values() if node.is_cap()}
    combined_caps.update(node.id for node in body.nodes.values() if node.is_cap())
    combined_caps.update(node.id for node in suffix.nodes.values() if node.is_cap())
    assert combined_caps == original_caps


# TEST761: Prefix sub-plan can be topologically sorted (is a valid DAG)
def test_761_prefix_is_dag():
    prefix = _build_foreach_plan_with_collect().extract_prefix_to("cap_0")
    prefix.topological_order()


# TEST762: Body sub-plan can be topologically sorted (is a valid DAG)
def test_762_body_is_dag():
    body = _build_foreach_plan_with_collect().extract_foreach_body("foreach_0", "media:pdf-page")
    body.topological_order()


# TEST763: Suffix sub-plan can be topologically sorted (is a valid DAG)
def test_763_suffix_is_dag():
    suffix = _build_foreach_plan_with_collect().extract_suffix_from(
        "collect_0", "media:decision;json;record;textable"
    )
    suffix.topological_order()


# TEST764: extract_prefix_to with InputSlot as target (trivial prefix)
def test_764_extract_prefix_to_input_slot():
    prefix = _build_foreach_plan_with_collect().extract_prefix_to("input_slot")
    assert len(prefix.nodes) == 2
    prefix.validate()


# TEST934: find_first_foreach detects ForEach in a plan
def test_934_find_first_foreach():
    plan = _build_foreach_plan_with_collect()
    assert plan.find_first_foreach() == "foreach_0"


# TEST935: find_first_foreach returns None for linear plans
def test_935_find_first_foreach_linear():
    plan = MachinePlan.linear_chain(["cap:a", "cap:b"], "media:pdf", "media:image;png", ["input_a", "input_b"])
    assert plan.find_first_foreach() is None


# TEST936: has_foreach detects ForEach nodes
def test_936_has_foreach():
    foreach_plan = _build_foreach_plan_with_collect()
    assert foreach_plan.has_foreach()

    linear_plan = MachinePlan.linear_chain(["cap:a"], "media:pdf", "media:image;png", ["input_a"])
    assert not linear_plan.has_foreach()

    standalone_collect_plan = MachinePlan("collect_only")
    standalone_collect_plan.add_node(
        MachineNode.input_slot("input", "input", "media:textable", InputCardinality.SINGLE)
    )
    standalone_collect_plan.add_node(
        MachineNode.cap("cap_0", "cap:in=media:textable;summarize;out=media:summary")
    )
    collect_node = MachineNode.collect("collect_0", ["cap_0"])
    collect_node.node_type = ExecutionNodeType.collect(["cap_0"], "media:list;summary")
    standalone_collect_plan.add_node(collect_node)
    standalone_collect_plan.add_node(MachineNode.output("output", "result", "collect_0"))
    assert not standalone_collect_plan.has_foreach()


# TEST937: extract_prefix_to extracts input_slot -> cap_0 as a standalone plan
def test_937_extract_prefix_to():
    prefix = _build_foreach_plan_with_collect().extract_prefix_to("cap_0")
    assert len(prefix.nodes) == 3
    assert prefix.get_node("input_slot") is not None
    assert prefix.get_node("cap_0") is not None
    assert prefix.get_node("cap_0_prefix_output") is not None
    assert len(prefix.entry_nodes) == 1
    assert len(prefix.output_nodes) == 1
    prefix.validate()
    assert len(prefix.topological_order()) == 3


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
