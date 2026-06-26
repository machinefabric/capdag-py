"""Tests for orchestrator types parity with Rust."""

from capdag.cap.definition import Cap
from capdag.orchestrator.types import ResolvedEdge, ResolvedGraph
from capdag.urn.cap_urn import CapUrn


def _make_test_cap(urn: str, title: str) -> Cap:
    return Cap.with_description(CapUrn.from_string(urn), title, "test-command", "test cap")


# TEST1142: ResolvedGraph.to_mermaid() renders node shapes, deduplicates edges, and escapes labels
def test_1142_resolved_graph_to_mermaid_renders_shapes_dedupes_edges_and_escapes():
    cap = _make_test_cap(
        'cap:in="media:pdf";extract;out="media:enc=utf-8;ext=txt"',
        'Extract "Title" <One>\\path',
    )
    second_cap = _make_test_cap(
        'cap:in="media:enc=utf-8;ext=txt";embed;out="media:embedding;record"',
        "Embed",
    )
    graph = ResolvedGraph(
        nodes={
            "input": "media:pdf",
            "middle": "media:enc=utf-8;ext=txt",
            "output": "media:embedding;record",
        },
        edges=[
            ResolvedEdge("input", "middle", cap.urn.to_string(), cap, "media:pdf", "media:enc=utf-8;ext=txt"),
            ResolvedEdge("input", "middle", cap.urn.to_string(), cap, "media:pdf", "media:enc=utf-8;ext=txt"),
            ResolvedEdge(
                "middle",
                "output",
                second_cap.urn.to_string(),
                second_cap,
                "media:enc=utf-8;ext=txt",
                "media:embedding;record",
            ),
        ],
        graph_name="demo",
    )

    mermaid = graph.to_mermaid()

    assert mermaid.startswith("graph LR\n")
    assert 'input(["input<br/><small>media:pdf</small>"])' in mermaid
    assert 'middle["middle<br/><small>media:textable;txt</small>"]' in mermaid
    assert 'output(("output<br/><small>media:embedding;record</small>"))' in mermaid
    assert 'Extract #quot;Title#quot; &lt;One&gt;\\\\path' in mermaid
    assert "<small>cap:" in mermaid
    assert mermaid.count("input -->|") == 1
