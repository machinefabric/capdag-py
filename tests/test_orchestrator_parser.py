"""Parity tests for orchestrator/parser.py — ported from Rust orchestrator/parser.rs."""

import pytest

from capdag.cap.definition import Cap, CapArg, CapOutput, StdinSource
from capdag.cap.registry import CapRegistry
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


def _build_registry(specs: list) -> CapRegistry:
    """Build a registry from (cap_urn_str, stdin_urns_list, out_urn) tuples."""
    registry = CapRegistry.new_for_test()
    caps = [_build_cap(urn_str, stdins, out) for urn_str, stdins, out in specs]
    registry.add_caps_to_cache(caps)
    return registry


def _media(s: str) -> MediaUrn:
    return MediaUrn.from_string(s)


# TEST1256: Parsing a single-cap machine notation produces a graph with 2 nodes and 1 edge.
@pytest.mark.asyncio
async def test_1256_parse_simple_machine():
    registry = _build_registry([
        ('cap:in="media:pdf";op=extract;out="media:txt;textable"', ["media:pdf"], "media:txt;textable"),
    ])
    notation = (
        '[extract cap:in="media:pdf";op=extract;out="media:txt;textable"]'
        "[A -> extract -> B]"
    )
    graph = await parse_machine_to_cap_dag(notation, registry)
    assert len(graph.nodes) == 2
    assert len(graph.edges) == 1

    node_a = _media(graph.nodes["A"])
    assert node_a.is_equivalent(_media("media:pdf"))

    node_b = _media(graph.nodes["B"])
    assert node_b.is_equivalent(_media("media:txt;textable"))


# TEST1257: Two sequential wirings preserve the intermediate node media type.
@pytest.mark.asyncio
async def test_1257_parse_two_step_chain():
    registry = _build_registry([
        ('cap:in="media:pdf";op=extract;out="media:txt;textable"', ["media:pdf"], "media:txt;textable"),
        ('cap:in="media:txt;textable";op=embed;out="media:embedding-vector;record;textable"',
         ["media:txt;textable"], "media:embedding-vector;record;textable"),
    ])
    notation = (
        '[extract cap:in="media:pdf";op=extract;out="media:txt;textable"]'
        '[embed cap:in="media:txt;textable";op=embed;out="media:embedding-vector;record;textable"]'
        "[A -> extract -> B]"
        "[B -> embed -> C]"
    )
    graph = await parse_machine_to_cap_dag(notation, registry)
    assert len(graph.nodes) == 3
    assert len(graph.edges) == 2

    node_b = _media(graph.nodes["B"])
    assert node_b.is_equivalent(_media("media:txt;textable")), \
        f"Intermediate node B should be media:txt;textable, got {node_b}"


# TEST1261: A cap URN not present in the registry cache causes a parse orchestration error.
def test_1261_cap_not_found_in_registry():
    # Python raises MachineSyntaxParseFailedError (wraps UnknownCapError from parse_machine)
    # rather than CapNotFoundError, because the cap lookup happens inside parse_machine.
    import asyncio
    registry = _build_registry([])
    notation = (
        '[ex cap:in="media:unknown";op=test;out="media:unknown"]'
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


# TEST1263: Cyclic wirings are rejected as non-DAG orchestrations.
@pytest.mark.asyncio
async def test_1263_cycle_detection():
    registry = _build_registry([
        ('cap:in="media:txt;textable";op=process;out="media:txt;textable"',
         ["media:txt;textable"], "media:txt;textable"),
    ])
    notation = (
        '[proc cap:in="media:txt;textable";op=process;out="media:txt;textable"]'
        "[A -> proc -> B]"
        "[B -> proc -> C]"
        "[C -> proc -> A]"
    )
    with pytest.raises((NotADagError, MachineSyntaxParseFailedError)):
        await parse_machine_to_cap_dag(notation, registry)
