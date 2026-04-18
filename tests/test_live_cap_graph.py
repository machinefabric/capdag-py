"""Parity tests for planner.live_cap_graph."""

import json

import pytest

from capdag.cap.definition import Cap, CapArg, CapOutput, StdinSource
from capdag.cap.registry import CapRegistry
from capdag.planner.live_cap_graph import LiveCapGraph, StrandStepType
from capdag.standard.caps import identity_urn
from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn


def _media(urn_str: str) -> MediaUrn:
    return MediaUrn.from_string(urn_str)


def _make_test_cap(
    in_spec: str,
    out_spec: str,
    op: str,
    title: str,
    *,
    input_is_sequence: bool = False,
    output_is_sequence: bool = False,
) -> Cap:
    urn = CapUrn.from_string(f'cap:in="{in_spec}";op={op};out="{out_spec}"')
    cap = Cap.with_description(urn, title, op, f"{title} cap")
    cap.add_arg(
        CapArg(
            media_urn=in_spec,
            required=True,
            sources=[StdinSource(in_spec)],
            is_sequence=input_is_sequence,
        )
    )
    cap.set_output(
        CapOutput(
            out_spec,
            f"{title} output",
            is_sequence=output_is_sequence,
        )
    )
    return cap


# TEST772: Tests find_paths_to_exact_target() finds multi-step paths Verifies that paths through intermediate nodes are found correctly
def test_772_find_paths_finds_multi_step_paths():
    graph = LiveCapGraph()
    graph.add_cap(_make_test_cap("media:a", "media:b", "step1", "A to B"))
    graph.add_cap(_make_test_cap("media:b", "media:c", "step2", "B to C"))

    paths = graph.find_paths_to_exact_target(_media("media:a"), _media("media:c"), False, 5, 10)

    assert len(paths) == 1
    assert len(paths[0].steps) == 2
    assert paths[0].steps[0].title() == "A to B"
    assert paths[0].steps[1].title() == "B to C"


# TEST773: Tests find_paths_to_exact_target() returns empty when no path exists Verifies that pathfinding returns no paths when target is unreachable
def test_773_find_paths_returns_empty_when_no_path():
    graph = LiveCapGraph()
    graph.add_cap(_make_test_cap("media:a", "media:b", "step1", "A to B"))

    paths = graph.find_paths_to_exact_target(_media("media:a"), _media("media:c"), False, 5, 10)

    assert paths == []


# TEST774: Tests get_reachable_targets() returns all reachable targets Verifies that reachable targets include direct cap targets and cardinality variants (list versions via Collect)
def test_774_get_reachable_targets_finds_all_targets():
    graph = LiveCapGraph()
    graph.add_cap(_make_test_cap("media:a", "media:b", "step1", "A to B"))
    graph.add_cap(_make_test_cap("media:a", "media:d", "step3", "A to D"))

    targets = graph.get_reachable_targets(_media("media:a"), False, 5)
    assert any(t.media_spec.is_equivalent(_media("media:b")) for t in targets)
    assert any(t.media_spec.is_equivalent(_media("media:d")) for t in targets)


# TEST777: Tests type checking prevents using PDF-specific cap with PNG input Verifies that media type compatibility is enforced during pathfinding
def test_777_type_mismatch_pdf_cap_does_not_match_png_input():
    graph = LiveCapGraph()
    graph.add_cap(_make_test_cap("media:pdf", "media:textable", "pdf2text", "PDF to Text"))

    paths = graph.find_paths_to_exact_target(
        _media("media:png"),
        _media("media:textable"),
        False,
        5,
        10,
    )

    assert paths == []


# TEST778: Tests type checking prevents using PNG-specific cap with PDF input Verifies that media type compatibility is enforced during pathfinding
def test_778_type_mismatch_png_cap_does_not_match_pdf_input():
    graph = LiveCapGraph()
    graph.add_cap(_make_test_cap("media:png", "media:thumbnail", "png2thumb", "PNG to Thumbnail"))

    paths = graph.find_paths_to_exact_target(
        _media("media:pdf"),
        _media("media:thumbnail"),
        False,
        5,
        10,
    )

    assert paths == []


# TEST779: Tests get_reachable_targets() only returns targets reachable via type-compatible caps Verifies that PNG and PDF inputs reach different cap targets (not each other's)
def test_779_get_reachable_targets_respects_type_matching():
    graph = LiveCapGraph()
    graph.add_cap(_make_test_cap("media:pdf", "media:textable", "pdf2text", "PDF to Text"))
    graph.add_cap(_make_test_cap("media:png", "media:thumbnail", "png2thumb", "PNG to Thumbnail"))

    png_targets = graph.get_reachable_targets(_media("media:png"), False, 5)
    assert any(t.media_spec.is_equivalent(_media("media:thumbnail")) for t in png_targets)
    assert not any(t.media_spec.is_equivalent(_media("media:textable")) for t in png_targets)

    pdf_targets = graph.get_reachable_targets(_media("media:pdf"), False, 5)
    assert any(t.media_spec.is_equivalent(_media("media:textable")) for t in pdf_targets)
    assert not any(t.media_spec.is_equivalent(_media("media:thumbnail")) for t in pdf_targets)


# TEST781: Tests find_paths_to_exact_target() enforces type compatibility across multi-step chains Verifies that paths are only found when all intermediate types are compatible
def test_781_find_paths_respects_type_chain():
    graph = LiveCapGraph()
    graph.add_cap(_make_test_cap("media:png", "media:resized-png", "resize", "Resize PNG"))
    graph.add_cap(_make_test_cap("media:resized-png", "media:thumbnail", "thumb", "To Thumbnail"))

    png_paths = graph.find_paths_to_exact_target(
        _media("media:png"),
        _media("media:thumbnail"),
        False,
        5,
        10,
    )
    assert len(png_paths) == 1
    assert len(png_paths[0].steps) == 2

    pdf_paths = graph.find_paths_to_exact_target(
        _media("media:pdf"),
        _media("media:thumbnail"),
        False,
        5,
        10,
    )
    assert pdf_paths == []


# TEST787: Tests find_paths_to_exact_target() sorts paths by length, preferring shorter ones Verifies that among multiple paths, the shortest is ranked first
def test_787_find_paths_sorting_prefers_shorter():
    graph = LiveCapGraph()
    graph.add_cap(_make_test_cap("media:format-a", "media:format-c", "direct", "Direct"))
    graph.add_cap(_make_test_cap("media:format-a", "media:format-b", "step1", "Step 1"))
    graph.add_cap(_make_test_cap("media:format-b", "media:format-c", "step2", "Step 2"))

    paths = graph.find_paths_to_exact_target(
        _media("media:format-a"),
        _media("media:format-c"),
        False,
        5,
        10,
    )

    assert len(paths) >= 2
    assert len(paths[0].steps) == 1
    assert paths[0].steps[0].title() == "Direct"


# TEST788: ForEach is only synthesized when is_sequence=true
def test_788_foreach_only_with_sequence_input():
    graph = LiveCapGraph()
    graph.sync_from_caps(
        [
            _make_test_cap("media:pdf", "media:page;textable", "disbind", "Disbind PDF"),
            _make_test_cap(
                "media:textable",
                "media:decision;json;record;textable",
                "choose",
                "Make a Decision",
            ),
        ]
    )

    source = _media("media:pdf")
    target = _media("media:decision;json;record;textable")

    scalar_paths = graph.find_paths_to_exact_target(source, target, False, 10, 20)
    assert scalar_paths
    assert not any(
        any(step.step_type == StrandStepType.FOR_EACH for step in path.steps)
        for path in scalar_paths
    )

    seq_paths = graph.find_paths_to_exact_target(source, target, True, 10, 20)
    assert any(
        any(step.step_type == StrandStepType.FOR_EACH for step in path.steps)
        for path in seq_paths
    )


# TEST789: Tests that caps loaded from JSON have correct in_spec/out_spec
def test_789_cap_from_json_has_valid_specs():
    cap = Cap.from_dict(
        json.loads(
            r"""{
                "urn": "cap:in=media:pdf;op=disbind;out=\"media:disbound-page;textable\"",
                "command": "disbind",
                "title": "Disbind PDF",
                "args": [],
                "output": null
            }"""
        )
    )

    in_spec = cap.urn.in_spec()
    out_spec = cap.urn.out_spec()

    assert in_spec == "media:pdf"
    assert out_spec
    assert "disbound-page" in out_spec


# TEST790: Tests identity_urn is specific and doesn't match everything
def test_790_identity_urn_is_specific():
    identity = identity_urn()
    assert identity.in_spec() == "media:"
    assert identity.out_spec() == "media:"

    specific_cap = CapUrn.from_string(
        'cap:in=media:pdf;op=disbind;out="media:disbound-page;textable"'
    )
    assert not specific_cap.is_equivalent(identity)


# TEST791: Tests sync_from_cap_urns actually adds edges
@pytest.mark.asyncio
async def test_791_sync_from_cap_urns_adds_edges():
    registry = CapRegistry.new_for_test()
    disbind = _make_test_cap("media:pdf", "media:page;textable", "disbind", "Disbind PDF")
    choose = _make_test_cap(
        "media:textable",
        "media:decision;json;record;textable",
        "choose",
        "Make a Decision",
    )
    registry.add_caps_to_cache([disbind, choose])

    graph = LiveCapGraph()
    await graph.sync_from_cap_urns([str(disbind.urn), str(choose.urn)], registry)

    node_count, edge_count = graph.stats()
    assert edge_count == 2
    assert node_count >= 3


# TEST1289: BFS reachable targets includes the source itself when round-trip paths exist. A→B and B→A means A is reachable from A (via A→B→A).
def test_1289_bfs_reachable_includes_source_roundtrip():
    graph = LiveCapGraph()
    graph.add_cap(
        _make_test_cap(
            "media:textable",
            "media:integer;numeric;textable",
            "coerce_to_int",
            "Coerce to Integer",
        )
    )
    graph.add_cap(
        _make_test_cap(
            "media:integer;numeric;textable",
            "media:textable",
            "coerce_to_text",
            "Coerce to Text",
        )
    )

    source = _media("media:textable")
    targets = graph.get_reachable_targets(source, False, 5)
    assert any(t.media_spec.is_equivalent(source) for t in targets)


# TEST1290: IDDFS find_paths_to_exact_target finds round-trip paths when source == target.
def test_1290_iddfs_finds_roundtrip_paths():
    graph = LiveCapGraph()
    graph.add_cap(
        _make_test_cap(
            "media:textable",
            "media:integer;numeric;textable",
            "coerce_to_int",
            "Coerce to Integer",
        )
    )
    graph.add_cap(
        _make_test_cap(
            "media:integer;numeric;textable",
            "media:textable",
            "coerce_to_text",
            "Coerce to Text",
        )
    )

    source = _media("media:textable")
    paths = graph.find_paths_to_exact_target(source, source, False, 5, 100)
    assert paths
    shortest = min(paths, key=lambda p: p.total_steps)
    assert shortest.total_steps == 2


# TEST1291: IDDFS round-trip paths are also found with is_sequence=true.
def test_1291_iddfs_roundtrip_with_sequence():
    graph = LiveCapGraph()
    graph.add_cap(
        _make_test_cap(
            "media:textable",
            "media:integer;numeric;textable",
            "coerce_to_int",
            "Coerce to Integer",
        )
    )
    graph.add_cap(
        _make_test_cap(
            "media:integer;numeric;textable",
            "media:textable",
            "coerce_to_text",
            "Coerce to Text",
        )
    )

    source = _media("media:textable")
    paths = graph.find_paths_to_exact_target(source, source, True, 5, 100)
    assert paths


# TEST1292: BFS and IDDFS agree that round-trip targets exist.
def test_1292_bfs_iddfs_roundtrip_consistency():
    graph = LiveCapGraph()
    graph.add_cap(_make_test_cap("media:a", "media:b", "a_to_b", "A to B"))
    graph.add_cap(_make_test_cap("media:b", "media:c", "b_to_c", "B to C"))
    graph.add_cap(_make_test_cap("media:c", "media:a", "c_to_a", "C to A"))

    source = _media("media:a")
    bfs_targets = graph.get_reachable_targets(source, False, 5)
    assert any(t.media_spec.is_equivalent(source) for t in bfs_targets)

    paths = graph.find_paths_to_exact_target(source, source, False, 5, 100)
    assert paths
    shortest = min(paths, key=lambda p: p.total_steps)
    assert shortest.total_steps == 3


# TEST1293: IDDFS round-trip does not produce paths with 0 cap steps.
def test_1293_roundtrip_requires_cap_steps():
    graph = LiveCapGraph()
    graph.add_cap(_make_test_cap("media:a", "media:b", "a_to_b", "A to B"))

    source = _media("media:a")
    paths = graph.find_paths_to_exact_target(source, source, False, 5, 100)
    assert paths == []
