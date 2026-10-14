"""Tests of gathering: several sources bound to one sequence arg."""

import pytest

from capdag.machine.graph import BindingSource, Machine
from capdag.machine.resolve import (
    MatchFailure,
    PreInternedWiring,
    WiringTarget,
    match_sources_to_args,
    resolve_pre_interned,
)
from capdag.planner.live_cap_fab import StepToken
from capdag.urn.cap_urn import CapUrn

from tests.machine_fixtures import canonical, media, one_edge_of, registry_of, stdin_cap


def _refused(sources, args, arg_is_sequence) -> MatchFailure:
    with pytest.raises(MatchFailure) as exc_info:
        match_sources_to_args(sources, args, arg_is_sequence, None)
    return exc_info.value


# TEST1400: N sources gather into a single sequence arg when no injection
# exists. Three page sources feed a one-arg concat cap whose arg is a sequence
# — all three land on the same arg, in source-declaration order.
def test_1400_gather_n_sources_into_sequence_arg():
    sources = [media("media:enc=utf-8;page")] * 3
    args = [media("media:enc=utf-8")]
    pairs = match_sources_to_args(sources, args, [True], None)
    assert len(pairs) == 3, "one binding per gathered source"
    for arg, source in pairs:
        assert arg.is_equivalent(media("media:enc=utf-8"))
        assert source.is_equivalent(media("media:enc=utf-8;page"))
    # The same three with an arg that takes one value have nowhere to go.
    failure = _refused(sources, args, [False])
    assert (failure.ambiguous, failure.source) == (False, 0)


# TEST1401: product precedence — when a valid injection exists it wins, even
# though gathering everything into the sequence arg is also valid. s1 exactly
# fits the scalar page arg; s2 only fits the sequence arg.
def test_1401_product_precedence_over_gather():
    sources = [media("media:enc=utf-8;page"), media("media:enc=utf-8;summary")]
    args = [media("media:enc=utf-8;page"), media("media:enc=utf-8")]
    pairs = match_sources_to_args(sources, args, [False, True], None)
    assert len(pairs) == 2
    # The page source must claim the scalar page arg (injection), NOT be
    # gathered into the sequence arg alongside the summary.
    assert {arg.to_string(): source.to_string() for arg, source in pairs} == {
        canonical("media:enc=utf-8;page"): canonical("media:enc=utf-8;page"),
        canonical("media:enc=utf-8"): canonical("media:enc=utf-8;summary"),
    }

    # Two pages, a sequence arg that takes pages and a scalar arg that takes
    # any text: each page can take either arg, at one cost — a tie. Gathering
    # both into the sequence arg would be cheaper and unique, and it is not
    # what is asked: a tied product is ambiguous, it does not become a gather.
    pages = [media("media:enc=utf-8;page")] * 2
    failure = _refused(pages, args, [True, False])
    assert failure.ambiguous
    assert failure.undecided == [(0, [0, 1]), (1, [0, 1])]


# TEST1402: a gather tie between two sequence args is ambiguous, not silently
# ordered.
def test_1402_gather_ambiguity_and_scalar_pigeonhole_fail_hard():
    # Two equally-costed sequence args (each drops a different one of the
    # source's tags → the same absolute specificity gap) → every distribution
    # of the three sources ties → ambiguous.
    chunk = media("media:chunk;enc=utf-8;page")
    args = [media("media:enc=utf-8;page"), media("media:chunk;enc=utf-8")]
    failure = _refused([chunk] * 3, args, [True, True])
    assert failure.ambiguous, "tied gather distributions must be ambiguous"
    assert failure.undecided == [(0, [0, 1]), (1, [0, 1]), (2, [0, 1])]


URN_A = 'cap:in="media:document;ext=pdf";op-a;out="media:enc=utf-8;page"'
URN_B = 'cap:in="media:ext=md";op-b;out="media:enc=utf-8;page"'
URN_CONCAT = 'cap:in="media:enc=utf-8";concat;out="media:enc=utf-8;ext=txt"'


def _gather_fixture(first_produces_sequence: bool):
    """Two producers of a page and a `concat` whose one arg takes a sequence,
    wired `(page from a, page from b) -> concat`."""
    cap_a = stdin_cap(URN_A, "op_a", "media:document;ext=pdf", "media:enc=utf-8;page")
    cap_a.main_output().is_sequence = first_produces_sequence
    cap_b = stdin_cap(URN_B, "op_b", "media:ext=md", "media:enc=utf-8;page")
    concat = stdin_cap(URN_CONCAT, "concat", "media:enc=utf-8", "media:enc=utf-8;ext=txt")
    concat.get_args()[0].is_sequence = True
    registry = registry_of([cap_a, cap_b, concat])

    # nodes: 0=pdf, 1=md, 2=page(from a), 3=page(from b), 4=txt
    nodes = [
        media("media:document;ext=pdf"),
        media("media:ext=md"),
        media("media:enc=utf-8;page"),
        media("media:enc=utf-8;page"),
        media("media:enc=utf-8;ext=txt"),
    ]

    def wiring(token: str, cap_urn: str, sources, target: int) -> PreInternedWiring:
        return PreInternedWiring(
            token_id=StepToken.parse(token),
            cap_urn=CapUrn.from_string(cap_urn),
            source_node_ids=list(sources),
            targets=[WiringTarget(node=target)],
        )

    wirings = [
        wiring("tok-a", URN_A, [0], 2),
        wiring("tok-b", URN_B, [1], 3),
        wiring("tok-concat", URN_CONCAT, [2, 3], 4),
    ]
    return resolve_pre_interned(nodes, wirings, registry, 0)


# TEST1403: resolve_pre_interned emits N bindings on ONE sequence arg for a
# fan-in gather `(x, y) -> concat`, with is_loop false (the gathered value IS
# the sequence the arg consumes) and stable source order.
def test_1403_resolve_gather_emits_n_bindings_on_sequence_arg():
    strand = _gather_fixture(False)
    machine = Machine.from_resolved_strands([strand])
    edge = one_edge_of(machine, "concat")
    assert len(edge.assignment) == 2, "the sequence arg gathers BOTH producers as two bindings"
    # Both bindings target the same slot.
    assert edge.assignment[0].cap_arg_media_urn.is_equivalent(edge.assignment[1].cap_arg_media_urn)
    assert [binding.arg_name for binding in edge.assignment] == ["input", "input"]
    # Deterministic gather order = source declaration order (node 2 then 3).
    assert [(b.source.is_constant, b.source.node) for b in edge.assignment] == [(False, 2), (False, 3)]
    # The gathered value IS the sequence the arg consumes — no map.
    assert not edge.is_loop, "gather-fed sequence arg must not loop"
    # The step keeps the identity it was given.
    assert edge.token_id == "tok-concat"
    # Anchors: two inputs (pdf, md), one output (txt).
    assert len(strand.input_anchors()) == 2
    assert len(strand.output_anchors()) == 1
    # Anchors come by the URN they hold, not by when their node was made.
    assert [anchor.to_string() for anchor in strand.input_anchors()] == [
        canonical("media:document;ext=pdf"), canonical("media:ext=md"),
    ]
    assert strand.input_anchor_ids() == [0, 1]
    # The gather is written as its arg's name once per member, in item order.
    # Nodes are named in the order the canonical walk meets them: the pdf and
    # its page, the markdown and its page, then the text.
    text = machine.to_machine_notation()
    assert "[(input=n0) -> edge_0 -> (output=n1)][(input=n2) -> edge_1 -> (output=n3)]" in text
    assert "[(input=n1, input=n3) -> edge_2 -> (output=n4)]" in text


# TEST1404: a sequence PRODUCER inside a gather resolves — the gather flattens
# at execution (each member contributes its item(s) in binding order). This is
# the batch-plus-single convergence shape: one leg yields a sequence, the
# other one item, and the fold consumes them all as one sequence.
def test_1404_sequence_producer_in_gather_flattens():
    strand = _gather_fixture(True)
    edge = one_edge_of(Machine.from_resolved_strands([strand]), "concat")
    assert len(edge.assignment) == 2, "both members bound to the sequence arg"
    assert not edge.is_loop, "the gathered value IS the sequence the arg consumes — no map"
    assert strand.node_is_sequence(2), "the node op-a produces holds a sequence"
    assert not strand.node_is_sequence(3)
    # A binding source is a node or a constant, never both.
    assert BindingSource.of_node(2).is_constant is False
    assert BindingSource.of_constant([1, "a"]).constant == [1, "a"]
    with pytest.raises(ValueError):
        BindingSource.of_constant(object())
    with pytest.raises(ValueError):
        BindingSource.of_constant(float("nan"))
    with pytest.raises(ValueError):
        BindingSource.of_constant(2 ** 64)
