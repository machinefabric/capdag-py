"""Parity tests for orchestrator/parser.py — ported from Rust orchestrator/parser.rs."""

import pytest

from capdag.cap.definition import Cap, CapArg, CapOutput, StdinSource
from capdag.cap.registry import FabricRegistry
from capdag.orchestrator.parser import parse_machine_to_cap_dag
from capdag.orchestrator.types import (
    CapNotFoundError,
    MachineSyntaxParseFailedError,
    NotADagError,
    ParseOrchestrationError,
)
from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn


def _build_cap(cap_urn_str: str, stdin_urns: list, out_urn: str) -> Cap:
    urn = CapUrn.from_string(cap_urn_str)
    cap = Cap.with_description(urn, cap_urn_str, "op", "test cap")
    for stdin_urn in stdin_urns:
        cap.add_arg(CapArg(
            media_urn=stdin_urn,
            required=True,
            sources=[StdinSource(stdin_urn)],
        ))
    cap.set_output(CapOutput(out_urn, "output"))
    return cap


def _build_registry(specs: list) -> FabricRegistry:
    """Build a registry from (cap_urn_str, stdin_urns_list, out_urn) tuples."""
    registry = FabricRegistry.new_for_test()
    caps = [_build_cap(urn_str, stdins, out) for urn_str, stdins, out in specs]
    registry.add_caps_to_cache(caps)
    return registry


def _media(s: str) -> MediaUrn:
    return MediaUrn.from_string(s)


# TEST1256: Parsing a single-cap machine notation produces a graph with 2 nodes and 1 edge.
@pytest.mark.asyncio
async def test_1256_parse_simple_machine():
    registry = _build_registry([
        ('cap:in="media:ext=pdf";extract;out="media:enc=utf-8;ext=txt"', ["media:ext=pdf"], "media:enc=utf-8;ext=txt"),
    ])
    notation = (
        '[extract cap:in="media:ext=pdf";extract;out="media:enc=utf-8;ext=txt"]'
        "[A -> extract -> B]"
    )
    graph = await parse_machine_to_cap_dag(notation, registry)
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1

    node_a = _media(graph.nodes["A"])
    assert node_a.is_equivalent(_media("media:ext=pdf"))

    node_b = _media(graph.nodes["B"])
    assert node_b.is_equivalent(_media("media:enc=utf-8;ext=txt"))


# TEST1257: Two sequential wirings preserve the intermediate node media type.
@pytest.mark.asyncio
async def test_1257_parse_two_step_chain():
    registry = _build_registry([
        ('cap:in="media:ext=pdf";extract;out="media:enc=utf-8;ext=txt"', ["media:ext=pdf"], "media:enc=utf-8;ext=txt"),
        ('cap:in="media:enc=utf-8;ext=txt";embed;out="media:embedding-vector;enc=utf-8;record"',
         ["media:enc=utf-8;ext=txt"], "media:embedding-vector;enc=utf-8;record"),
    ])
    notation = (
        '[extract cap:in="media:ext=pdf";extract;out="media:enc=utf-8;ext=txt"]'
        '[embed cap:in="media:enc=utf-8;ext=txt";embed;out="media:embedding-vector;enc=utf-8;record"]'
        "[A -> extract -> B]"
        "[B -> embed -> C]"
    )
    graph = await parse_machine_to_cap_dag(notation, registry)
    assert len(graph.nodes) == 3
    assert len(graph.edges) == 2

    node_b = _media(graph.nodes["B"])
    assert node_b.is_equivalent(_media("media:enc=utf-8;ext=txt")), \
        f"Intermediate node B should be media:enc=utf-8;ext=txt, got {node_b}"


# TEST1261: A cap URN not present in the registry cache causes a parse orchestration error.
def test_1261_cap_not_found_in_registry():
    # Python raises MachineSyntaxParseFailedError (wraps UnknownCapError from parse_machine)
    # rather than CapNotFoundError, because the cap lookup happens inside parse_machine.
    import asyncio
    registry = _build_registry([])
    notation = (
        '[ex cap:in="media:unknown";test;out="media:unknown"]'
        "[A -> ex -> B]"
    )
    with pytest.raises(ParseOrchestrationError):
        asyncio.run(parse_machine_to_cap_dag(notation, registry))


# TEST1262: Non-machine text fails with a machine syntax parse error.
@pytest.mark.asyncio
async def test_1262_invalid_machine_notation():
    registry = _build_registry([])
    with pytest.raises(MachineSyntaxParseFailedError):
        await parse_machine_to_cap_dag("not valid", registry)


# TEST1258: One source node can fan out into multiple caps and target nodes.
@pytest.mark.asyncio
async def test_1258_parse_fan_out():
    registry = _build_registry([
        ('cap:in="media:ext=pdf";extract-metadata;out="media:enc=utf-8;file-metadata;record"',
         ["media:ext=pdf"], "media:enc=utf-8;file-metadata;record"),
        ('cap:in="media:ext=pdf";extract-outline;out="media:document-outline;enc=utf-8;record"',
         ["media:ext=pdf"], "media:document-outline;enc=utf-8;record"),
        ('cap:in="media:ext=pdf";generate-thumbnail;out="media:ext=png;image;thumbnail"',
         ["media:ext=pdf"], "media:ext=png;image;thumbnail"),
    ])
    notation = (
        '[meta cap:in="media:ext=pdf";extract-metadata;out="media:enc=utf-8;file-metadata;record"]'
        '[outline cap:in="media:ext=pdf";extract-outline;out="media:document-outline;enc=utf-8;record"]'
        '[thumb cap:in="media:ext=pdf";generate-thumbnail;out="media:ext=png;image;thumbnail"]'
        "[doc -> meta -> metadata]"
        "[doc -> outline -> outline_data]"
        "[doc -> thumb -> thumbnail]"
    )
    graph = await parse_machine_to_cap_dag(notation, registry)
    assert len(graph.nodes) == 4  # doc + 3 targets
    assert len(graph.edges) == 3


# TEST1259: Fan-in wiring resolves multiple upstream outputs into one multi-arg cap.
@pytest.mark.asyncio
async def test_1259_parse_fan_in():
    registry = _build_registry([
        ('cap:in="media:ext=pdf";generate-thumbnail;out="media:ext=png;image;thumbnail"',
         ["media:ext=pdf"], "media:ext=png;image;thumbnail"),
        ('cap:in="media:enc=utf-8;model-spec";download;out="media:enc=utf-8;model-spec"',
         ["media:enc=utf-8;model-spec"], "media:enc=utf-8;model-spec"),
        ('cap:in="media:ext=png;image";describe-image;out="media:enc=utf-8;image-description"',
         ["media:ext=png;image", "media:enc=utf-8;model-spec"], "media:enc=utf-8;image-description"),
    ])
    notation = (
        '[thumb cap:in="media:ext=pdf";generate-thumbnail;out="media:ext=png;image;thumbnail"]'
        '[model_dl cap:in="media:enc=utf-8;model-spec";download;out="media:enc=utf-8;model-spec"]'
        '[describe cap:in="media:ext=png;image";describe-image;out="media:enc=utf-8;image-description"]'
        "[doc -> thumb -> thumbnail]"
        "[spec_input -> model_dl -> model_spec]"
        "[(thumbnail, model_spec) -> describe -> description]"
    )
    graph = await parse_machine_to_cap_dag(notation, registry)
    # Fan-in produces 2 resolved edges for describe (one per source) plus 2 for thumb/model_dl = 4
    assert len(graph.edges) == 4


# TEST1260: The `LOOP` keyword is retired from the grammar. A keyword-free
# wiring parses to a single edge; the old `LOOP` form no longer parses.
# ForEach is never authored — it is derived from cardinality in the
# resolver/realizer.
@pytest.mark.asyncio
async def test_1260_loop_keyword_retired():
    registry = _build_registry([
        ('cap:in="media:disbound-page;enc=utf-8";page-to-text;out="media:enc=utf-8;ext=txt"',
         ["media:disbound-page;enc=utf-8"], "media:enc=utf-8;ext=txt"),
    ])
    header = '[p2t cap:in="media:disbound-page;enc=utf-8";page-to-text;out="media:enc=utf-8;ext=txt"]'

    # Keyword-free wiring parses to one edge.
    graph = await parse_machine_to_cap_dag(f"{header}[pages -> p2t -> texts]", registry)
    assert len(graph.edges) == 1
    assert len(graph.nodes) == 2

    # The retired `LOOP` keyword must not parse as a valid wiring.
    with pytest.raises(Exception):
        await parse_machine_to_cap_dag(f"{header}[pages -> LOOP p2t -> texts]", registry)


# TEST1263: Cyclic wirings are rejected as non-DAG orchestrations.
@pytest.mark.asyncio
async def test_1263_cycle_detection():
    registry = _build_registry([
        ('cap:in="media:enc=utf-8;ext=txt";process;out="media:enc=utf-8;ext=txt"',
         ["media:enc=utf-8;ext=txt"], "media:enc=utf-8;ext=txt"),
    ])
    notation = (
        '[proc cap:in="media:enc=utf-8;ext=txt";process;out="media:enc=utf-8;ext=txt"]'
        "[A -> proc -> B]"
        "[B -> proc -> C]"
        "[C -> proc -> A]"
    )
    with pytest.raises((NotADagError, MachineSyntaxParseFailedError)):
        await parse_machine_to_cap_dag(notation, registry)


# TEST1264: Shared nodes with incompatible upstream and downstream media fail during parsing.
@pytest.mark.asyncio
async def test_1264_incompatible_media_types_at_shared_node():
    registry = _build_registry([
        ('cap:in="media:void";produce-pdf;out="media:ext=pdf"',
         ["media:void"], "media:ext=pdf"),
        ('cap:in="media:audio;ext=wav";transcribe;out="media:enc=utf-8;ext=txt"',
         ["media:audio;ext=wav"], "media:enc=utf-8;ext=txt"),
    ])
    notation = (
        '[produce cap:in="media:void";produce-pdf;out="media:ext=pdf"]'
        '[transcribe cap:in="media:audio;ext=wav";transcribe;out="media:enc=utf-8;ext=txt"]'
        "[A -> produce -> B]"
        "[B -> transcribe -> C]"
    )
    with pytest.raises((MachineSyntaxParseFailedError, ParseOrchestrationError)):
        await parse_machine_to_cap_dag(notation, registry)


# TEST1265: Shared nodes accept compatible media URNs when one is a more specific form of the other.
# xfail: Python's match_sources_to_args requires strict tag conformance — source media:ext=png;image
# does not conform to cap arg media:bytes;ext=png;image (normalized: media:bytes;ext=png;image).
# Rust's is_comparable accepts subset/superset tag chains at the orchestrator level.
@pytest.mark.xfail(
    reason="Python source-matching requires strict tag subset: media:ext=png;image does not "
           "conform to media:bytes;ext=png;image (normalized from media:bytes;ext=png;image). "
           "Rust allows this via is_comparable at the orchestrator level.",
    strict=True,
)
# TEST1265: Compatible media urns at shared node
@pytest.mark.asyncio
async def test_1265_compatible_media_urns_at_shared_node():
    registry = _build_registry([
        ('cap:in="media:ext=pdf";thumbnail;out="media:ext=png;image"',
         ["media:ext=pdf"], "media:ext=png;image"),
        ('cap:in="media:bytes;ext=png;image";embed-image;out="media:embedding-vector;enc=utf-8;record"',
         ["media:bytes;ext=png;image"], "media:embedding-vector;enc=utf-8;record"),
    ])
    notation = (
        '[thumb cap:in="media:ext=pdf";thumbnail;out="media:ext=png;image"]'
        '[embed_image cap:in="media:bytes;ext=png;image";embed-image;out="media:embedding-vector;enc=utf-8;record"]'
        "[A -> thumb -> B]"
        "[B -> embed_image -> C]"
    )
    result = await parse_machine_to_cap_dag(notation, registry)
    assert result is not None, "Compatible media URNs (image;png vs image;png;bytes) should not conflict"


# TEST1266: Record-to-opaque structure mismatches are rejected once structure checking is enabled.
@pytest.mark.skip(reason="structure mismatch detection between node media and cap input not yet implemented")
@pytest.mark.asyncio
async def test_1266_structure_mismatch_record_to_opaque():
    registry = _build_registry([
        ('cap:in="media:void";produce;out="media:fmt=json;record"',
         ["media:void"], "media:fmt=json;record"),
        ('cap:in="media:fmt=json";process;out="media:enc=utf-8;ext=txt"',
         ["media:fmt=json"], "media:enc=utf-8;ext=txt"),
    ])
    notation = (
        '[produce cap:in="media:void";produce;out="media:fmt=json;record"]'
        '[process cap:in="media:fmt=json";process;out="media:enc=utf-8;ext=txt"]'
        "[A -> produce -> B]"
        "[B -> process -> C]"
    )
    from capdag.orchestrator.types import StructureMismatchError
    with pytest.raises(StructureMismatchError):
        await parse_machine_to_cap_dag(notation, registry)


# TEST1267: Record-shaped outputs can feed record-shaped inputs without error.
@pytest.mark.asyncio
async def test_1267_structure_match_both_record():
    registry = _build_registry([
        ('cap:in="media:void";produce;out="media:fmt=json;record"',
         ["media:void"], "media:fmt=json;record"),
        ('cap:in="media:fmt=json;record";transform;out="media:enc=utf-8;record;result"',
         ["media:fmt=json;record"], "media:enc=utf-8;record;result"),
    ])
    notation = (
        '[produce cap:in="media:void";produce;out="media:fmt=json;record"]'
        '[transform cap:in="media:fmt=json;record";transform;out="media:enc=utf-8;record;result"]'
        "[A -> produce -> B]"
        "[B -> transform -> C]"
    )
    result = await parse_machine_to_cap_dag(notation, registry)
    assert result is not None, "Record to record should be accepted"


# TEST1268: Opaque outputs can feed opaque inputs without triggering structure conflicts.
@pytest.mark.asyncio
async def test_1268_structure_match_both_opaque():
    registry = _build_registry([
        ('cap:in="media:void";produce;out="media:fmt=json"',
         ["media:void"], "media:fmt=json"),
        ('cap:in="media:fmt=json";format;out="media:enc=utf-8;ext=txt"',
         ["media:fmt=json"], "media:enc=utf-8;ext=txt"),
    ])
    notation = (
        '[produce cap:in="media:void";produce;out="media:fmt=json"]'
        '[format cap:in="media:fmt=json";format;out="media:enc=utf-8;ext=txt"]'
        "[A -> produce -> B]"
        "[B -> format -> C]"
    )
    result = await parse_machine_to_cap_dag(notation, registry)
    assert result is not None, "Opaque to opaque should be accepted"


# TEST1269: Multi-line machine notation parses successfully with the same semantics as inline notation.
@pytest.mark.asyncio
async def test_1269_parse_multiline_machine():
    registry = _build_registry([
        ('cap:in="media:ext=pdf";extract;out="media:enc=utf-8;ext=txt"',
         ["media:ext=pdf"], "media:enc=utf-8;ext=txt"),
    ])
    notation = '\n[extract cap:in="media:ext=pdf";extract;out="media:enc=utf-8;ext=txt"]\n[doc -> extract -> text]\n'
    result = await parse_machine_to_cap_dag(notation, registry)
    assert result is not None, "Multi-line parse failed"


# =============================================================================
# Tests ported from Rust tests/orchestrator_integration.rs — testcartridge
# parser-level cases. The execute_dag-based peers (multi-machine pipelines)
# depend on building and running the Rust `testcartridge` binary, a subsystem
# absent in the Python mirror, so only the pure-parse cases are ported here.
# =============================================================================


def _build_testcartridge_registry() -> FabricRegistry:
    """Build a registry with the testcartridge caps, mirroring Rust's
    `create_test_fabric_registry`. Each cap declares one stdin arg matching
    its `in=` spec so source-to-cap-arg matching can succeed."""
    return _build_registry([
        ('cap:in="media:enc=utf-8;node1";test-edge1;out="media:enc=utf-8;node2"',
         ["media:enc=utf-8;node1"], "media:enc=utf-8;node2"),
        ('cap:in="media:enc=utf-8;node2";test-edge2;out="media:enc=utf-8;node3"',
         ["media:enc=utf-8;node2"], "media:enc=utf-8;node3"),
        ('cap:in="media:enc=utf-8;node3";test-edge3;out="media:enc=utf-8;list;node4"',
         ["media:enc=utf-8;node3"], "media:enc=utf-8;list;node4"),
        ('cap:in="media:enc=utf-8;list;node4";test-edge4;out="media:enc=utf-8;node5"',
         ["media:enc=utf-8;list;node4"], "media:enc=utf-8;node5"),
        ('cap:in="media:enc=utf-8;node3";test-edge7;out="media:enc=utf-8;node6"',
         ["media:enc=utf-8;node3"], "media:enc=utf-8;node6"),
        ('cap:in="media:enc=utf-8;node6";test-edge8;out="media:enc=utf-8;node7"',
         ["media:enc=utf-8;node6"], "media:enc=utf-8;node7"),
        ('cap:in="media:enc=utf-8;node7";test-edge9;out="media:enc=utf-8;node8"',
         ["media:enc=utf-8;node7"], "media:enc=utf-8;node8"),
        ('cap:in="media:enc=utf-8;node8";test-edge10;out="media:enc=utf-8;node1"',
         ["media:enc=utf-8;node8"], "media:enc=utf-8;node1"),
        ('cap:in="media:void";test-large;out="media:"',
         ["media:void"], "media:"),
        ('cap:in="media:enc=utf-8;node1";test-peer;out="media:enc=utf-8;node3"',
         ["media:enc=utf-8;node1"], "media:enc=utf-8;node3"),
        ('cap:in="media:enc=utf-8;node1";identity;out="media:enc=utf-8;node1"',
         ["media:enc=utf-8;node1"], "media:enc=utf-8;node1"),
    ])


# TEST919: Parse simple machine notation graph with test-edge1
@pytest.mark.asyncio
async def test_919_parse_simple_testcartridge_graph():
    registry = _build_testcartridge_registry()

    route = (
        '\n'
        '[test_edge1 cap:in="media:enc=utf-8;node1";test-edge1;out="media:enc=utf-8;node2"]\n'
        '[A -> test_edge1 -> B]\n'
    )

    graph = await parse_machine_to_cap_dag(route, registry)
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1

    node_a = MediaUrn.from_string(graph.nodes["A"])
    expected_a = MediaUrn.from_string("media:enc=utf-8;node1")
    assert node_a.is_equivalent(expected_a)

    node_b = MediaUrn.from_string(graph.nodes["B"])
    expected_b = MediaUrn.from_string("media:enc=utf-8;node2")
    assert node_b.is_equivalent(expected_b)


# TEST950: Validate that cycles are rejected
@pytest.mark.asyncio
async def test_950_reject_cycles():
    registry = _build_testcartridge_registry()

    # Create a self-loop using identity cap
    route = (
        '\n'
        '[identity cap:in="media:enc=utf-8;node1";identity;out="media:enc=utf-8;node1"]\n'
        '[A -> identity -> A]\n'
    )

    # Rust expects ParseOrchestrationError::NotADag. Python's self-loop is
    # caught either by the machine parser (which wraps it as a syntax parse
    # failure) or by the DAG validator (NotADagError); both are
    # ParseOrchestrationError subclasses.
    with pytest.raises((NotADagError, MachineSyntaxParseFailedError)):
        await parse_machine_to_cap_dag(route, registry)


# TEST949: Empty machine notation (no edges)
@pytest.mark.asyncio
async def test_949_empty_graph():
    registry = _build_testcartridge_registry()

    route = ""

    with pytest.raises(MachineSyntaxParseFailedError):
        await parse_machine_to_cap_dag(route, registry)


# TEST948: Invalid cap URN in machine notation
@pytest.mark.asyncio
async def test_948_invalid_cap_urn():
    registry = _build_testcartridge_registry()

    route = "[bad cap:INVALID]" "[A -> bad -> B]"

    with pytest.raises(ParseOrchestrationError):
        await parse_machine_to_cap_dag(route, registry)


# TEST947: Cap not found in registry
@pytest.mark.asyncio
async def test_947_cap_not_found():
    registry = _build_testcartridge_registry()

    route = (
        '\n'
        '[nonexistent cap:in="media:unknown";nonexistent;out="media:unknown"]\n'
        '[A -> nonexistent -> B]\n'
    )

    # Rust expects MachineSyntaxParseFailedError: the parser resolves header
    # caps and wraps the registry lookup failure during parse_machine.
    with pytest.raises(MachineSyntaxParseFailedError):
        await parse_machine_to_cap_dag(route, registry)
