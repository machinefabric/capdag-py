"""Tests for the strand-based Machine module.

Covers: resolve.py, graph.py (MachineStrand, Machine, EdgeAssignmentBinding,
MachineEdge), error.py (new abstraction errors), parser.py (parse_machine with
registry + union-find strand partitioning).

Test numbering starts at 1110 (after the last test1109 in TEST_CATALOG).
"""

import pytest

from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn
from capdag.cap.definition import Cap, CapArg, CapOutput, StdinSource
from capdag.cap.registry import FabricRegistry
from capdag.machine.graph import (
    EdgeAssignmentBinding,
    MachineEdge,
    MachineStrand,
    Machine,
    MachineRun,
    MachineRunStatus,
    NodeId,
)
from capdag.machine.resolve import (
    MatchFailure,
    PreInternedWiring,
    WiringTarget,
    resolve_pre_interned,
    resolve_strand,
    match_sources_to_args,
)
from capdag.machine.error import (
    AmbiguousMachineNotationError,
    CyclicMachineStrandError,
    InvalidPolicyError,
    MachineAbstractionError,
    MachineParseError,
    NoCapabilityStepsError,
    UndecidedMember,
    UnknownCapError,
    UnmatchedSourceInCapArgsError,
    MachineSyntaxError,
)
from capdag.machine.parser import parse_machine
from capdag.planner.live_cap_fab import (
    ArgSourceRef,
    CapInput,
    StepToken,
    Strand,
    StrandStep,
    StrandStepType,
)


# =============================================================================
# Test helpers
# =============================================================================

def _media(urn_str: str) -> MediaUrn:
    return MediaUrn.from_string(urn_str)


def _cap_urn(urn_str: str) -> CapUrn:
    return CapUrn.from_string(urn_str)


def _build_cap(cap_urn_str: str, title: str, stdin_urns: list, slot_urns: list, out_urn: str) -> Cap:
    """Build a Cap with one stdin arg per (stdin_urn, slot_urn) pair."""
    urn = CapUrn.from_string(cap_urn_str)
    cap = Cap.with_description(urn, title, [title.lower()], f"{title} cap")
    for stdin_u, slot_u in zip(stdin_urns, slot_urns):
        cap.add_arg(CapArg(
            media_urn=slot_u, name="input",
            required=True,
            sources=[StdinSource(stdin_u)],
        ))
    cap.add_output(CapOutput(out_urn, "output", f"{title} output"))
    return cap


def _simple_cap(cap_urn_str: str, stdin_urn: str, out_urn: str) -> Cap:
    """Build a Cap with a single stdin arg where slot_urn == stdin_urn."""
    return _build_cap(cap_urn_str, "cap", [stdin_urn], [stdin_urn], out_urn)


def _wiring(cap_urn: CapUrn, sources: list, target: int) -> PreInternedWiring:
    """One wiring of unnamed members taking its step's main output."""
    return PreInternedWiring(
        token_id=StepToken.mint(),
        cap_urn=cap_urn,
        source_node_ids=list(sources),
        targets=[WiringTarget(node=target)],
    )


def _match(sources: list, args: list):
    """The matching over scalar args, with no arg that must be bound."""
    return match_sources_to_args(sources, args, [False] * len(args), None)


def _refused(sources: list, args: list) -> MatchFailure:
    with pytest.raises(MatchFailure) as exc_info:
        _match(sources, args)
    return exc_info.value


def _registry_with(caps: list) -> FabricRegistry:
    reg = FabricRegistry.new_for_test()
    reg.add_caps_to_cache(caps)
    return reg


def _strand_with_cap_steps(steps_data: list) -> Strand:
    """Build a Strand from a list of (cap_urn_str, from_urn_str, to_urn_str) tuples.

    Wires the steps into a linear chain: each cap step's single main input is
    the previous cap step's output (identified by its stable token_id), and
    the first step's main input is the strand's own input anchor. Mirrors
    Rust's test_fixtures::chain_cap_steps under the explicit-inputs model.
    """
    steps = []
    prev_token = None
    for cap_urn_str, from_str, to_str in steps_data:
        source = ArgSourceRef.step(prev_token) if prev_token is not None else ArgSourceRef.strand_input()
        step = StrandStep(
            step_type=StrandStepType.CAP,
            from_spec=_media(from_str),
            to_spec=_media(to_str),
            cap_urn=_cap_urn(cap_urn_str),
            inputs=[CapInput(arg_urn=_media(from_str), source=source)],
        )
        steps.append(step)
        prev_token = step.token_id
    first = steps[0] if steps else None
    last = steps[-1] if steps else None
    return Strand(
        steps=steps,
        source_media_urn=first.from_spec if first else _media("media:"),
        target_media_urn=last.to_spec if last else _media("media:"),
        total_steps=len(steps),
        cap_step_count=len(steps),
        description="test strand",
    )


# TEST1188: Strand resolution fails when the strand contains no capability steps.
def test_1188_resolve_strand_no_cap_steps_fails_hard():
    reg = _registry_with([])
    with pytest.raises(NoCapabilityStepsError):
        resolve_pre_interned([], [], reg, 0)


# TEST1187: Strand resolution fails when a referenced cap is not found in the registry.
def test_1187_unknown_cap_error_when_not_in_registry():
    reg = _registry_with([])  # empty registry
    cap_urn = _cap_urn("cap:in=\"media:document;ext=pdf\";extract;out=\"media:enc=utf-8;ext=txt\"")
    nodes = [_media("media:document;ext=pdf"), _media("media:enc=utf-8;ext=txt")]
    wirings = [_wiring(cap_urn, [0], 1)]
    with pytest.raises(UnknownCapError) as exc_info:
        resolve_pre_interned(nodes, wirings, reg, 0)
    assert "cap:in=media:document;ext=pdf" in str(exc_info.value) or "extract" in str(exc_info.value)


# TEST1184: Resolving a strand with one cap produces one resolved machine edge.
def test_1184_single_edge_strand_resolves_correctly():
    cap_urn_str = "cap:in=\"media:document;ext=pdf\";extract;out=\"media:enc=utf-8;ext=txt\""
    cap = _simple_cap(cap_urn_str, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    reg = _registry_with([cap])

    strand = _strand_with_cap_steps([
        (cap_urn_str, "media:document;ext=pdf", "media:enc=utf-8;ext=txt"),
    ])
    ms = resolve_strand(strand, reg, 0)

    assert len(ms.edges()) == 1
    assert len(ms.nodes()) == 2
    assert len(ms.input_anchor_ids()) == 1
    assert len(ms.output_anchor_ids()) == 1

    # Input anchor should be media:document;ext=pdf
    assert ms.nodes()[ms.input_anchor_ids()[0]].is_equivalent(_media("media:document;ext=pdf"))
    # Output anchor should be media:enc=utf-8;ext=txt
    assert ms.nodes()[ms.output_anchor_ids()[0]].is_equivalent(_media("media:enc=utf-8;ext=txt"))


# TEST6709: Resolving a strand with two chained caps shares the intermediate node.
def test_6709_two_step_chain_shares_intermediate_node():
    urn1 = "cap:in=\"media:document;ext=pdf\";extract;out=\"media:enc=utf-8;ext=txt\""
    urn2 = "cap:in=\"media:enc=utf-8\";embed;out=\"media:vec;record\""
    cap1 = _simple_cap(urn1, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    cap2 = _simple_cap(urn2, "media:enc=utf-8", "media:vec;record")
    reg = _registry_with([cap1, cap2])

    strand = _strand_with_cap_steps([
        (urn1, "media:document;ext=pdf", "media:enc=utf-8;ext=txt"),
        (urn2, "media:enc=utf-8;ext=txt", "media:vec;record"),
    ])
    ms = resolve_strand(strand, reg, 0)

    assert len(ms.edges()) == 2
    # In a chain: node 0=source, node 1=intermediate (shared), node 2=final output.
    # But the intermediate may be one node (reused) depending on is_comparable.
    # media:enc=utf-8;ext=txt is_comparable to media:enc=utf-8 → reused.
    # So: node 0=pdf, node 1=enc=utf-8;ext=txt (output of cap1, input refinement of cap2), node 2=vec;record
    assert len(ms.nodes()) == 3

    edge0 = ms.edges()[0]
    edge1 = ms.edges()[1]

    # edge0 target is the source for edge1
    assert edge0.main_target() == edge1.assignment[0].source.node

    # Only 1 input anchor (media:document;ext=pdf), 1 output anchor (media:vec;record)
    assert len(ms.input_anchor_ids()) == 1
    assert len(ms.output_anchor_ids()) == 1


# TEST1155: Building a machine from one strand produces one strand with one resolved edge.
def test_1155_from_strand_produces_single_strand_machine():
    cap_urn_str = "cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\""
    cap = _simple_cap(cap_urn_str, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    reg = _registry_with([cap])

    strand = _strand_with_cap_steps([(cap_urn_str, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")])
    m = Machine.from_strand(strand, reg)

    assert m.strand_count() == 1
    assert not m.is_empty()
    assert len(m.strands()[0].edges()) == 1


# TEST1156: Building from multiple strands keeps them disjoint and preserves input strand order.
def test_1156_from_strands_keeps_strands_disjoint():
    urn1 = "cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\""
    urn2 = "cap:embed;in=\"media:enc=utf-8\";out=\"media:vec;record\""
    cap1 = _simple_cap(urn1, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    cap2 = _simple_cap(urn2, "media:enc=utf-8", "media:vec;record")
    reg = _registry_with([cap1, cap2])

    s1 = _strand_with_cap_steps([(urn1, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")])
    s2 = _strand_with_cap_steps([(urn2, "media:enc=utf-8;ext=txt", "media:vec;record")])
    m = Machine.from_strands([s1, s2], reg)

    assert m.strand_count() == 2
    # Strands are disjoint — each has their own NodeId space
    assert len(m.strands()[0].edges()) == 1
    assert len(m.strands()[1].edges()) == 1
    # First strand is extract, second is embed
    assert "extract" in str(m.strands()[0].edges()[0].cap_urn)
    assert "embed" in str(m.strands()[1].edges()[0].cap_urn)


# TEST1157: Building from zero strands fails with NoCapabilitySteps.
def test_1157_from_strands_empty_raises_no_capability_steps():
    reg = _registry_with([])
    with pytest.raises(NoCapabilityStepsError):
        Machine.from_strands([], reg)


# TEST1158: Machine equivalence is strict about strand order and rejects reordered strands.
def test_1158_machine_is_equivalent_strict_positional_order_matters():
    urn1 = "cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\""
    urn2 = "cap:embed;in=\"media:enc=utf-8\";out=\"media:vec;record\""
    cap1 = _simple_cap(urn1, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    cap2 = _simple_cap(urn2, "media:enc=utf-8", "media:vec;record")
    reg = _registry_with([cap1, cap2])

    s1 = _strand_with_cap_steps([(urn1, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")])
    s2 = _strand_with_cap_steps([(urn2, "media:enc=utf-8;ext=txt", "media:vec;record")])

    forward = Machine.from_strands([s1, s2], reg)
    reversed_ = Machine.from_strands([s2, s1], reg)

    # Same strands, different order → NOT equivalent
    assert not forward.is_equivalent(reversed_)
    # Each is equivalent to itself
    assert forward.is_equivalent(forward)
    assert reversed_.is_equivalent(reversed_)


# TEST1159: MachineStrand equivalence accepts two separately built but structurally identical strands.
def test_1159_strand_is_equivalent_consistent_node_bijection():
    cap_urn_str = "cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\""
    cap = _simple_cap(cap_urn_str, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    reg = _registry_with([cap])

    strand = _strand_with_cap_steps([(cap_urn_str, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")])
    m1 = Machine.from_strand(strand, reg)
    m2 = Machine.from_strand(strand, reg)

    assert m1.strands()[0].is_equivalent(m2.strands()[0])


# TEST6703: Source-to-arg matching: single source picks the unique arg.
def test_6703_match_sources_to_args_single_trivial():
    sources = [_media("media:document;ext=pdf")]
    args = [_media("media:document;ext=pdf")]
    cap_urn_str = "cap:in=\"media:document;ext=pdf\";extract;out=\"media:enc=utf-8;ext=txt\""

    pairs = _match(sources, args)

    assert len(pairs) == 1
    assert pairs[0][0].is_equivalent(_media("media:document;ext=pdf"))  # cap arg urn
    assert pairs[0][1].is_equivalent(_media("media:document;ext=pdf"))  # source urn


# TEST1179: Source-to-arg matching assigns a more specific source to a compatible general argument.
def test_1179_match_sources_more_specific_source_matches_general_arg():
    sources = [_media("media:enc=utf-8;page")]
    args = [_media("media:enc=utf-8")]
    pairs = _match(sources, args)
    assert len(pairs) == 1
    assert pairs[0][0].is_equivalent(_media("media:enc=utf-8"))
    assert pairs[0][1].is_equivalent(_media("media:enc=utf-8;page"))


# TEST1180: Matching fails when a source does not conform to any cap input argument.
def test_1180_match_sources_unmatched_source_fails_hard():
    sources = [_media("media:numeric")]
    args = [_media("media:enc=utf-8")]
    cap_urn_str = "cap:in=\"media:enc=utf-8\";t;out=\"media:enc=utf-8\""

    failure = _refused(sources, args)
    assert not failure.ambiguous
    assert failure.source == 0, "unmatched source must fail hard"

    # It is the source that fits nothing that is named, wherever it stands.
    sources = [_media("media:enc=utf-8;page"), _media("media:numeric")]
    args = [_media("media:enc=utf-8"), _media("media:enc=utf-8;page")]
    failure = _refused(sources, args)
    assert (failure.ambiguous, failure.source) == (False, 1)


# TEST1182: Matching fails as ambiguous when two sources can be swapped at equal minimum cost.
def test_1182_match_sources_ambiguous_raises_ambiguous_error():
    # Two sources both conform equally to both args at the same distance.
    sources = [_media("media:enc=utf-8"), _media("media:enc=utf-8")]
    args = [_media("media:enc=utf-8"), _media("media:enc=utf-8")]
    cap_urn_str = "cap:in=\"media:enc=utf-8\";t;out=\"media:enc=utf-8\""

    # Both are left open, and each could go to either arg.
    failure = _refused(sources, args)
    assert failure.ambiguous, "ambiguous matching must fail hard"
    assert failure.undecided == [(0, [0, 1]), (1, [0, 1])]

    # Only the sources the tie is about are named: a third that fits one arg
    # alone is decided, whatever the other two do.
    text, number = _media("media:enc=utf-8"), _media("media:numeric")
    failure = _refused([text, number, text], [text, text, number])
    assert failure.ambiguous
    assert failure.undecided == [(0, [0, 1]), (2, [0, 1])]


# TEST1308: A wiring that forms a cycle raises CyclicMachineStrandError.
def test_1308_cyclic_strand_fails_hard():
    """TEST1123: A wiring that feeds a cap's output back into itself raises CyclicMachineStrandError.

    Cycle: node 0 → cap A → node 1 → cap B → node 0
    """
    urn_a = "cap:in=\"media:document;ext=pdf\";op-a;out=\"media:enc=utf-8;ext=txt\""
    urn_b = "cap:in=\"media:enc=utf-8;ext=txt\";op-b;out=\"media:document;ext=pdf\""

    cap_a = _simple_cap(urn_a, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    cap_b = _simple_cap(urn_b, "media:enc=utf-8;ext=txt", "media:document;ext=pdf")
    reg = _registry_with([cap_a, cap_b])

    nodes = [_media("media:document;ext=pdf"), _media("media:enc=utf-8;ext=txt")]
    # node 0 -> cap_a -> node 1  and  node 1 -> cap_b -> node 0 (cycle)
    wirings = [
        _wiring(_cap_urn(urn_a), [0], 1),
        _wiring(_cap_urn(urn_b), [1], 0),
    ]

    with pytest.raises(CyclicMachineStrandError) as exc_info:
        resolve_pre_interned(nodes, wirings, reg, 5)

    assert exc_info.value.strand_index == 5


# TEST1171: Empty machine notation is rejected as a syntax error.
def test_1171_machine_parse_error_wraps_syntax_error():
    reg = _registry_with([])
    with pytest.raises(MachineParseError) as exc_info:
        parse_machine("", reg)

    err = exc_info.value
    assert err.is_syntax_error
    assert not err.is_abstraction_error
    assert isinstance(err.cause, MachineSyntaxError)


# TEST1165: Parsing fails hard when a referenced cap is missing from the registry cache.
def test_1165_parse_machine_unknown_cap_raises_parse_error_with_abstraction_cause():
    reg = _registry_with([])  # empty — no caps loaded

    notation = (
        "[extract cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\"]\n"
        "[doc -> extract -> text]"
    )

    with pytest.raises(MachineParseError) as exc_info:
        parse_machine(notation, reg)

    err = exc_info.value
    assert err.is_abstraction_error
    assert not err.is_syntax_error
    assert isinstance(err.cause, MachineAbstractionError)


# TEST1309: Parsing a single-cap machine notation produces one strand with one edge.
def test_1309_parse_machine_single_wiring_one_strand():
    cap_urn_str = "cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\""
    cap = _simple_cap(cap_urn_str, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    reg = _registry_with([cap])

    notation = (
        f'[extract {cap_urn_str}]\n'
        "[doc -> extract -> text]"
    )

    m = parse_machine(notation, reg)

    assert m.strand_count() == 1
    assert len(m.strands()[0].edges()) == 1
    assert not m.is_empty()


# TEST1164: Parsing two disconnected strand definitions yields two separate machine strands.
def test_1164_parse_machine_disconnected_wirings_become_separate_strands():
    urn1 = "cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\""
    urn2 = "cap:in=media:image;caption;out=\"media:enc=utf-8;ext=txt\""
    cap1 = _simple_cap(urn1, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    cap2 = _simple_cap(urn2, "media:image", "media:enc=utf-8;ext=txt")
    reg = _registry_with([cap1, cap2])

    # Two fully disconnected wirings (no shared node names).
    notation = (
        f"[extract {urn1}]\n"
        f"[caption {urn2}]\n"
        "[doc -> extract -> text1]\n"
        "[img -> caption -> text2]"
    )

    m = parse_machine(notation, reg)

    assert m.strand_count() == 2


# =============================================================================
# TEST6698: Two caps whose wirings share a node name are folded into a single strand with two edges.
# =============================================================================

def test_6698_parse_machine_shared_node_name_yields_one_strand():
    urn1 = "cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\""
    urn2 = "cap:embed;in=\"media:enc=utf-8\";out=\"media:vec;record\""
    cap1 = _simple_cap(urn1, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    cap2 = _simple_cap(urn2, "media:enc=utf-8", "media:vec;record")
    reg = _registry_with([cap1, cap2])

    # "text" node is shared between the two wirings.
    notation = (
        f"[extract {urn1}]\n"
        f"[embed {urn2}]\n"
        "[doc -> extract -> text]\n"
        "[text -> embed -> vecs]"
    )

    m = parse_machine(notation, reg)

    assert m.strand_count() == 1
    assert len(m.strands()[0].edges()) == 2


# =============================================================================
# TEST6713: EdgeAssignmentBinding.cap_arg_media_urn is the slot identity (outer media_urn), not the stdin inner URN.
# =============================================================================

def test_6713_binding_slot_identity_is_outer_media_urn():
    """TEST1129: EdgeAssignmentBinding.cap_arg_media_urn is the slot identity (outer media_urn),
    not the stdin inner URN.

    This tests the slot-vs-stdin distinction: a cap arg may have
    media_urn="media:enc=utf-8;file-path" with stdin="media:document;ext=pdf".
    The binding must record the slot identity, not the stdin type.
    """
    cap_urn_str = "cap:in=\"media:document;ext=pdf\";disbind;out=\"media:enc=utf-8;page\""
    urn = CapUrn.from_string(cap_urn_str)
    cap = Cap.with_description(urn, "Disbind", ["disbind"], "disbinds a PDF")
    # slot identity = "media:enc=utf-8;file-path", stdin = "media:document;ext=pdf"
    cap.add_arg(CapArg(
        media_urn="media:enc=utf-8;file-path", name="input",
        required=True,
        sources=[StdinSource("media:document;ext=pdf")],
    ))
    cap.add_output(CapOutput("media:enc=utf-8;page", "output", "page output"))
    reg = _registry_with([cap])

    nodes = [_media("media:document;ext=pdf"), _media("media:enc=utf-8;page")]
    wirings = [_wiring(_cap_urn(cap_urn_str), [0], 1)]

    ms = resolve_pre_interned(nodes, wirings, reg, 0)
    assert len(ms.edges()) == 1
    binding = ms.edges()[0].assignment[0]

    # Slot identity must be the outer media_urn ("media:enc=utf-8;file-path")
    assert binding.cap_arg_media_urn.is_equivalent(_media("media:enc=utf-8;file-path"))
    # Source NodeId must be 0
    assert not binding.source.is_constant
    assert binding.source.node == 0
    assert binding.arg_name == "input", "the binding carries the arg's name"


# =============================================================================
# TEST1310: Two strands differing only in one node's media URN are not equivalent (Python-specific coverage).
# =============================================================================

def test_1310_strand_equivalence_rejects_mismatched_node_urns():
    """TEST1130: Two strands that differ only in one node's media URN are NOT equivalent.

    The NodeBijection check requires URN-level is_equivalent at both ends of
    every mapped NodeId pair.
    """
    urn_extract = "cap:in=\"media:document;ext=pdf\";extract;out=\"media:enc=utf-8;ext=txt\""
    urn_summarize = "cap:in=\"media:document;ext=pdf\";extract;out=\"media:enc=utf-8;ext=md\""
    cap_e = _simple_cap(urn_extract, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    cap_s = _simple_cap(urn_summarize, "media:document;ext=pdf", "media:enc=utf-8;ext=md")
    reg = _registry_with([cap_e, cap_s])

    strand_e = _strand_with_cap_steps([(urn_extract, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")])
    strand_s = _strand_with_cap_steps([(urn_summarize, "media:document;ext=pdf", "media:enc=utf-8;ext=md")])

    m1 = Machine.from_strand(strand_e, reg)
    m2 = Machine.from_strand(strand_s, reg)

    # Different output URN → not equivalent
    assert not m1.strands()[0].is_equivalent(m2.strands()[0])


# =============================================================================
# TEST6710: A cap step fed by a sequence-producing predecessor maps per item
# (is_loop=True), derived purely from cardinality — the retired `LOOP`
# keyword and bare ForEach steps carry no wiring effect any more.
# =============================================================================

def test_6710_resolve_strand_foreach_sets_is_loop_on_next_cap():
    split_urn = "cap:in=\"media:list;enc=utf-8\";split;out=\"media:enc=utf-8\""
    embed_urn = "cap:in=\"media:enc=utf-8\";embed;out=\"media:vec;record\""
    splitter = _simple_cap(split_urn, "media:list;enc=utf-8", "media:enc=utf-8")
    splitter.main_output().is_sequence = True
    embed = _simple_cap(embed_urn, "media:enc=utf-8", "media:vec;record")
    reg = _registry_with([splitter, embed])

    split_step = StrandStep(
        step_type=StrandStepType.CAP,
        from_spec=_media("media:list;enc=utf-8"),
        to_spec=_media("media:enc=utf-8"),
        cap_urn=_cap_urn(split_urn),
        inputs=[CapInput(arg_urn=_media("media:list;enc=utf-8"), source=ArgSourceRef.strand_input())],
    )
    embed_step = StrandStep(
        step_type=StrandStepType.CAP,
        from_spec=_media("media:enc=utf-8"),
        to_spec=_media("media:vec;record"),
        cap_urn=_cap_urn(embed_urn),
        inputs=[CapInput(arg_urn=_media("media:enc=utf-8"), source=ArgSourceRef.step(split_step.token_id))],
    )
    strand = Strand(
        steps=[split_step, embed_step],
        source_media_urn=_media("media:list;enc=utf-8"),
        target_media_urn=_media("media:vec;record"),
        total_steps=2,
        cap_step_count=2,
        description="split then embed",
    )

    ms = resolve_strand(strand, reg, 0)
    assert len(ms.edges()) == 2
    split_edge = next(e for e in ms.edges() if "split" in str(e.cap_urn))
    embed_edge = next(e for e in ms.edges() if "embed" in str(e.cap_urn))
    assert not split_edge.is_loop, "a scalar source feeding the sequence-producing cap must not map"
    assert embed_edge.is_loop is True, "a sequence feeding a scalar-input cap must map per item"


# =============================================================================
# TEST1311: Machine.from_string is an alias for parse_machine — both produce equivalent results (Python-specific coverage).
# =============================================================================

def test_1311_machine_from_string_delegates_to_parse_machine():
    cap_urn_str = "cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\""
    cap = _simple_cap(cap_urn_str, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    reg = _registry_with([cap])

    notation = (
        f"[extract {cap_urn_str}]\n"
        "[doc -> extract -> text]"
    )

    m1 = Machine.from_string(notation, reg)
    m2 = parse_machine(notation, reg)

    assert m1.is_equivalent(m2)
    assert m1.strand_count() == 1


# =============================================================================
# Mirror-specific coverage: MachineAbstractionError subclass hierarchy is correct
# =============================================================================

def test_6689_abstraction_error_subclass_hierarchy():
    """TEST6689: All resolution error subclasses are instances of MachineAbstractionError."""
    err_no_steps = NoCapabilityStepsError()
    err_unknown = UnknownCapError("cap:x")
    err_unmatched = UnmatchedSourceInCapArgsError(0, "cap:x", "media:document;ext=pdf")
    err_ambiguous = AmbiguousMachineNotationError(1, "cap:y", [])
    err_cyclic = CyclicMachineStrandError(2)

    for err in [err_no_steps, err_unknown, err_unmatched, err_ambiguous, err_cyclic]:
        assert isinstance(err, MachineAbstractionError)
        assert isinstance(err, Exception)


# =============================================================================
# Mirror-specific coverage: MachineStrand nodes() returns correct MediaUrns by NodeId
# =============================================================================

def test_1135_strand_node_urn_accessor():
    """TEST1135: MachineStrand.node_urn(id) returns the MediaUrn at that NodeId."""
    cap_urn_str = "cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\""
    cap = _simple_cap(cap_urn_str, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    reg = _registry_with([cap])

    strand = _strand_with_cap_steps([(cap_urn_str, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")])
    ms = Machine.from_strand(strand, reg).strands()[0]

    # There are exactly 2 nodes: source (pdf) and target (enc=utf-8;ext=txt)
    for nid in range(len(ms.nodes())):
        urn = ms.node_urn(nid)
        assert isinstance(urn, MediaUrn)


# =============================================================================
# Mirror-specific coverage: parse_machine undefined alias raises MachineParseError with syntax cause
# =============================================================================

def test_1136_parse_machine_undefined_alias_raises_syntax_error():
    """TEST1136: parse_machine with undefined cap alias raises MachineParseError wrapping UndefinedAliasError."""
    reg = _registry_with([])
    notation = "[doc -> undefined_alias -> text]"

    with pytest.raises(MachineParseError) as exc_info:
        parse_machine(notation, reg)

    err = exc_info.value
    assert err.is_syntax_error


# =============================================================================
# Mirror-specific coverage: Two-strand machine to_machine_notation produces valid string
# =============================================================================

def test_6691_two_strand_machine_serializes_to_notation():
    """TEST6691: Machine with two strands serializes to a non-empty notation string."""
    import capdag.machine.serializer  # ensure methods are attached

    urn1 = "cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\""
    urn2 = "cap:in=media:image;caption;out=\"media:enc=utf-8;ext=txt\""
    cap1 = _simple_cap(urn1, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    cap2 = _simple_cap(urn2, "media:image", "media:enc=utf-8;ext=txt")
    reg = _registry_with([cap1, cap2])

    s1 = _strand_with_cap_steps([(urn1, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")])
    s2 = _strand_with_cap_steps([(urn2, "media:image", "media:enc=utf-8;ext=txt")])
    m = Machine.from_strands([s1, s2], reg)

    notation = m.to_machine_notation()
    assert len(notation) > 0
    # Both op tags appear in the output
    assert "extract" in notation
    assert "caption" in notation


# =============================================================================
# Mirror-specific coverage: Assignment bindings are sorted by cap_arg_media_urn for canonical form
# =============================================================================

def test_6692_assignment_bindings_sorted_by_slot_urn():
    """TEST6692: EdgeAssignmentBinding list is sorted by cap_arg_media_urn, enabling
    canonical comparison across different creation orders.

    Build a two-source cap where the arg order and source order could produce
    different binding orderings. Assert the bindings are always sorted.
    """
    # Cap with two stdin args in reverse alphabetical slot order
    cap_urn_str = "cap:in=\"media:document;ext=pdf\";merge;out=\"media:enc=utf-8;ext=txt\""
    urn = CapUrn.from_string(cap_urn_str)
    cap = Cap.with_description(urn, "Merge", ["merge"], "merge two inputs")
    # Slot B comes before A alphabetically; add them in B, A order.
    cap.add_arg(CapArg(
        media_urn="media:enc=utf-8", name="input",      # slot: enc=utf-8 (later alphabetically)
        required=True,
        sources=[StdinSource("media:enc=utf-8")],
    ))
    cap.add_arg(CapArg(
        media_urn="media:document;ext=pdf", name="arg1",            # slot: pdf (earlier alphabetically)
        required=True,
        sources=[StdinSource("media:document;ext=pdf")],
    ))
    cap.add_output(CapOutput("media:enc=utf-8;ext=txt", "output", "merged output"))
    reg = _registry_with([cap])

    # Two source nodes: node 0 = pdf, node 1 = enc=utf-8
    nodes = [_media("media:document;ext=pdf"), _media("media:enc=utf-8"), _media("media:enc=utf-8;ext=txt")]
    wirings = [_wiring(_cap_urn(cap_urn_str), [0, 1], 2)]

    ms = resolve_pre_interned(nodes, wirings, reg, 0)
    assert len(ms.edges()) == 1

    bindings = ms.edges()[0].assignment
    assert len(bindings) == 2

    # Bindings must be sorted by slot urn string
    slot_strs = [str(b.cap_arg_media_urn) for b in bindings]
    assert slot_strs == sorted(slot_strs), (
        f"Bindings not in sorted order: {slot_strs}"
    )


# =============================================================================
# Tests ported from Rust parser.rs (1166-1170)
# =============================================================================

# =============================================================================
# Tests ported from Rust machine/error.rs (1147-1149)
# =============================================================================

# TEST1147: a syntax error's message names the step, the statement and what
# is wrong.
def test_1147_machine_syntax_error_display_is_specific():
    err = InvalidPolicyError("fetch", 7, "unknown key 'tries'")
    assert str(err) == "invalid policy on step 'fetch' in statement 7: unknown key 'tries'"
    assert isinstance(err, MachineSyntaxError)


# TEST1148: MachineParseError::from(MachineSyntaxError) preserves the syntax error variant
def test_1148_machine_parse_error_from_syntax_preserves_variant():
    from capdag.machine.error import UndefinedAliasError
    syntax_err = UndefinedAliasError("extract")
    parse_err = MachineParseError(syntax_err)
    assert parse_err.is_syntax_error
    assert isinstance(parse_err.cause, MachineSyntaxError)
    assert "extract" in str(parse_err.cause)


# TEST1149: MachineParseError::from(MachineAbstractionError) preserves the resolution error variant
def test_1149_machine_parse_error_from_resolution_preserves_variant():
    def undecided(node: str) -> UndecidedMember:
        return UndecidedMember(node=node, source_urn="media:enc=utf-8", could_be=("left", "right"))

    ambiguous = AmbiguousMachineNotationError(
        2, "cap:in=\"media:document;ext=pdf\";out=media:text", [undecided("a"), undecided("")]
    )
    parse_err = MachineParseError(ambiguous)
    assert not parse_err.is_syntax_error
    assert parse_err.is_abstraction_error
    assert isinstance(parse_err.cause, MachineAbstractionError)
    assert parse_err.cause.strand_index == 2
    assert parse_err.cause.cap_urn == "cap:in=\"media:document;ext=pdf\";out=media:text"
    # What it says is which members to name, and what each could be.
    assert str(parse_err).endswith(
        "name them: 'a' (media:enc=utf-8) could be left or right; "
        "a member of type 'media:enc=utf-8' could be left or right"
    ), str(parse_err)
    assert len(parse_err.cause.members) == 2, "the members are carried"


_URN_EXTRACT = 'cap:extract;in="media:document;ext=pdf";out="media:enc=utf-8;ext=txt"'
_URN_EMBED = 'cap:embed;in="media:enc=utf-8";out="media:vec;record"'


def _pdf_extract_embed_registry() -> "FabricRegistry":
    cap_e = _simple_cap(_URN_EXTRACT, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    cap_b = _simple_cap(_URN_EMBED, "media:enc=utf-8", "media:vec;record")
    return _registry_with([cap_e, cap_b])


# TEST1166: Duplicate header aliases are reported as syntax errors.
def test_1166_parse_duplicate_alias_is_syntax_error():
    reg = _pdf_extract_embed_registry()
    notation = (
        f"[extract {_URN_EXTRACT}]"
        f"[extract {_URN_EMBED}]"
        "[a -> extract -> b]"
    )
    with pytest.raises(MachineParseError) as exc_info:
        parse_machine(notation, reg)
    assert exc_info.value.is_syntax_error


# TEST1167: Wiring that references an undefined alias is reported as a syntax error.
def test_1167_parse_undefined_alias_is_syntax_error():
    reg = _pdf_extract_embed_registry()
    notation = (
        f"[extract {_URN_EXTRACT}]"
        "[a -> notDefined -> b]"
    )
    with pytest.raises(MachineParseError) as exc_info:
        parse_machine(notation, reg)
    assert exc_info.value.is_syntax_error


# TEST1168: Parsing rejects node names that collide with declared cap aliases.
def test_1168_parse_node_alias_collision_with_header_alias_fails_hard():
    # "extract" is used as both a cap alias in the header and a node name in the wiring.
    reg = _pdf_extract_embed_registry()
    notation = (
        f"[extract {_URN_EXTRACT}]"
        "[extract -> extract -> b]"
    )
    with pytest.raises(MachineParseError) as exc_info:
        parse_machine(notation, reg)
    assert exc_info.value.is_syntax_error


# TEST1169: A sequence-output cap feeding a scalar-input cap makes the resolved
# edge a per-item map (is_loop), derived from cardinality — the single rule
# Cap.needs_foreach, which replaces the retired `LOOP` keyword. The
# scalar->sequence producer edge itself does not loop.
def test_1169_sequence_into_scalar_cap_derives_is_loop():
    # Producer: scalar text -> SEQUENCE of items.
    splitter = _build_cap(
        "cap:in=\"media:enc=utf-8\";split;out=\"media:enc=utf-8;item\"",
        "split",
        ["media:enc=utf-8"],
        ["media:enc=utf-8"],
        "media:enc=utf-8;item",
    )
    splitter.main_output().is_sequence = True
    # Consumer: scalar item -> scalar text.
    texter = _build_cap(
        "cap:in=\"media:enc=utf-8;item\";t;out=\"media:enc=utf-8\"",
        "t",
        ["media:enc=utf-8;item"],
        ["media:enc=utf-8;item"],
        "media:enc=utf-8",
    )
    reg = _registry_with([splitter, texter])
    notation = (
        "[split cap:in=\"media:enc=utf-8\";split;out=\"media:enc=utf-8;item\"]"
        "[t cap:in=\"media:enc=utf-8;item\";t;out=\"media:enc=utf-8\"]"
        "[a -> split -> items]"
        "[items -> t -> b]"
    )
    machine = parse_machine(notation, reg)
    assert machine.strand_count() == 1
    strand = machine.strands()[0]
    assert len(strand.edges()) == 2
    split_edge = next(e for e in strand.edges() if "split" in str(e.cap_urn))
    t_edge = next(e for e in strand.edges() if "split" not in str(e.cap_urn))
    assert not split_edge.is_loop, "a scalar source feeding the sequence-producing cap must not map"
    assert t_edge.is_loop, "a sequence feeding a scalar-input cap must map per item (is_loop)"


# TEST1170: Parsing and then serializing machine notation round-trips to the canonical form.
def test_1170_parse_then_serialize_round_trips_to_canonical_form():
    import capdag.machine.serializer  # ensure methods are attached
    reg = _pdf_extract_embed_registry()
    user_input = (
        f"[user_extract {_URN_EXTRACT}]"
        f"[user_embed {_URN_EMBED}]"
        "[doc -> user_extract -> txt]"
        "[txt -> user_embed -> vec]"
    )
    m1 = parse_machine(user_input, reg)
    canonical = m1.to_machine_notation()
    # Canonical form should NOT contain user aliases
    assert "user_extract" not in canonical
    assert "user_embed" not in canonical
    assert "edge_0" in canonical
    m2 = Machine.from_string(canonical, reg)
    assert m1.is_equivalent(m2)
    canonical2 = m2.to_machine_notation()
    assert canonical == canonical2


# =============================================================================
# Tests ported from Rust serializer.rs (1172-1177, minus 1176/1177 which need render_payload_json)
# =============================================================================

# TEST1172: Serializing a two-step strand emits the expected aliases and node names.
def test_1172_serialize_two_step_strand_emits_global_aliases_and_node_names():
    import capdag.machine.serializer  # ensure methods are attached
    reg = _pdf_extract_embed_registry()
    strand = _strand_with_cap_steps([
        (_URN_EXTRACT, "media:document;ext=pdf", "media:enc=utf-8;ext=txt"),
        (_URN_EMBED, "media:enc=utf-8;ext=txt", "media:vec;record"),
    ])
    machine = Machine.from_strand(strand, reg)
    notation = machine.to_machine_notation()
    assert "[edge_0 cap:" in notation and "[edge_1 cap:" in notation, \
        f"headers must use edge_0 / edge_1 aliases, got: {notation}"
    assert "[(input=n0) -> edge_0 -> (output=n1)]" in notation, \
        f"first wiring should bind n0 and take n1, by name, got: {notation}"
    assert "[(input=n1) -> edge_1 -> (output=n2)]" in notation, \
        f"second wiring should bind n1 and take n2, by name, got: {notation}"


# TEST1173: Serializing and reparsing a machine preserves strict machine equivalence.
def test_1173_serialize_then_parse_round_trip_preserves_strict_equivalence():
    import capdag.machine.serializer  # ensure methods are attached
    reg = _pdf_extract_embed_registry()
    strand = _strand_with_cap_steps([
        (_URN_EXTRACT, "media:document;ext=pdf", "media:enc=utf-8;ext=txt"),
        (_URN_EMBED, "media:enc=utf-8;ext=txt", "media:vec;record"),
    ])
    m1 = Machine.from_strand(strand, reg)
    notation = m1.to_machine_notation()
    m2 = Machine.from_string(notation, reg)
    assert m1.is_equivalent(m2), "machine and its serialize-reparse must be strictly equivalent"
    # Canonical form is a fixed point
    notation2 = m2.to_machine_notation()
    assert notation == notation2, "canonical notation must be a fixed point of parse-then-serialize"


# TEST1174: The line-based notation format round-trips back to the same machine.
def test_1174_line_based_format_round_trips_to_same_machine():
    import capdag.machine.serializer  # ensure methods are attached
    reg = _pdf_extract_embed_registry()
    strand = _strand_with_cap_steps([
        (_URN_EXTRACT, "media:document;ext=pdf", "media:enc=utf-8;ext=txt"),
        (_URN_EMBED, "media:enc=utf-8;ext=txt", "media:vec;record"),
    ])
    m1 = Machine.from_strand(strand, reg)
    line_based = m1.to_machine_notation_formatted("line-based")
    # Line-based form must not contain brackets
    assert "[" not in line_based, f"line-based form must not contain brackets, got: {line_based}"
    m2 = Machine.from_string(line_based, reg)
    assert m1.is_equivalent(m2)


# TEST1175: Serializing an empty machine produces an empty string.
def test_1175_empty_machine_serializes_to_empty_string():
    import capdag.machine.serializer  # ensure methods are attached
    machine = Machine.from_resolved_strands([])
    notation = machine.to_machine_notation()
    assert notation == ""


# TEST1176: Rendering payload JSON includes strand anchor metadata for a populated machine.
def test_1176_render_payload_json_includes_strand_with_anchors():
    import capdag.machine.serializer  # ensure to_render_payload_json is attached
    extract_urn = "cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\""
    embed_urn = "cap:embed;in=\"media:enc=utf-8;ext=txt\";out=\"media:record;vec\""
    cap_e = _simple_cap(extract_urn, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    cap_s = _simple_cap(embed_urn, "media:enc=utf-8;ext=txt", "media:vec;record")
    reg = _registry_with([cap_e, cap_s])
    strand = _strand_with_cap_steps([
        (extract_urn, "media:document;ext=pdf", "media:enc=utf-8;ext=txt"),
        (embed_urn, "media:enc=utf-8;ext=txt", "media:vec;record"),
    ])
    machine = Machine.from_strand(strand, reg)
    payload = machine.to_render_payload_json()
    assert payload.startswith('{"strands":[')
    assert '"nodes":[' in payload
    assert '"edges":[' in payload
    assert '"input_anchor_nodes":[' in payload
    assert '"output_anchor_nodes":[' in payload
    assert "extract" in payload
    assert "embed" in payload


# TEST1177: Rendering payload JSON for an empty machine emits an empty strands array.
def test_1177_render_payload_for_empty_machine_has_empty_strands_array():
    import capdag.machine.serializer  # ensure to_render_payload_json is attached
    machine = Machine.from_resolved_strands([])
    payload = machine.to_render_payload_json()
    assert payload == '{"strands":[]}'


# =============================================================================
# Tests ported from Rust resolve.rs (1181, 1183, 1189, 1190)
# =============================================================================

# TEST1181: Two sources disambiguated by specificity — unique minimum-cost assignment.
def test_1181_match_two_sources_disambiguated_by_specificity():
    urn = "cap:in=\"media:ext=png;image\";describe;out=\"media:enc=utf-8;image-description\""
    sources = [_media("media:ext=png;image"), _media("media:enc=utf-8;model-spec")]
    args = [_media("media:ext=png;image"), _media("media:enc=utf-8")]
    pairs = _match(sources, args)
    assert len(pairs) == 2
    found_image = False
    found_text = False
    for arg, src in pairs:
        if arg.is_equivalent(_media("media:ext=png;image")):
            assert src.is_equivalent(_media("media:ext=png;image"))
            found_image = True
        elif arg.is_equivalent(_media("media:enc=utf-8")):
            assert src.is_equivalent(_media("media:enc=utf-8;model-spec"))
            found_text = True
    assert found_image and found_text, "both arg slots must be assigned"

    # The pairs come by arg URN — its parts, not its text — whatever order
    # the sources stand in.
    for ordered in (sources, list(reversed(sources))):
        by_arg = [arg.ordering_key() for arg, _ in _match(ordered, args)]
        assert by_arg == sorted(by_arg), by_arg
        assert len(by_arg) == 2
    by_parts = _match(
        [_media("media:file-path"), _media("media:file;sample")],
        [_media("media:file-path"), _media("media:file;sample")],
    )
    assert [arg.to_string() for arg, _ in by_parts] == [
        _media("media:file;sample").to_string(), _media("media:file-path").to_string(),
    ]

    # One source that fits two args takes the one it is closest to, whichever
    # of the two is tried first.
    general, exact = _media("media:enc=utf-8"), _media("media:enc=utf-8;page")
    for either in ([general, exact], [exact, general]):
        pairs = _match([_media("media:enc=utf-8;page")], either)
        assert len(pairs) == 1
        assert pairs[0][0].is_equivalent(exact), \
            f"the exact arg, not the general one: {pairs[0][0]}"


# TEST1183: Matching fails when more sources are provided than the cap has input arguments.
def test_1183_match_more_sources_than_args_fails_hard():
    sources = [_media("media:document;ext=pdf"), _media("media:document;ext=pdf"), _media("media:document;ext=pdf")]
    args = [_media("media:document;ext=pdf"), _media("media:document;ext=pdf")]
    # Every source has somewhere to go and one of them must go without: the
    # first stands for it.
    failure = _refused(sources, args)
    assert (failure.ambiguous, failure.source) == (False, 0), "more sources than args must fail hard"

    # Where one of them fits nothing at all, that is the one named.
    sources[1] = _media("media:numeric")
    failure = _refused(sources, args)
    assert (failure.ambiguous, failure.source) == (False, 1)


# TEST1189: Strand resolution keeps canonical anchor ordering stable across equivalent inputs.
def test_1189_resolve_strand_canonical_anchor_order_is_stable():
    urn = 'cap:in="media:document;ext=pdf";extract;out="media:enc=utf-8;ext=txt"'
    cap = _simple_cap(urn, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    reg = _registry_with([cap])
    strand = _strand_with_cap_steps([(urn, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")])
    r1 = resolve_strand(strand, reg, 0)
    r2 = resolve_strand(strand, reg, 0)
    i1 = r1.input_anchors()
    i2 = r2.input_anchors()
    assert len(i1) == len(i2)
    for a, b in zip(i1, i2):
        assert a.is_equivalent(b)


# TEST1190: Inverse format converters resolve without introducing a cycle in the strand graph.
def test_1190_resolve_strand_inverse_format_converters_no_cycle():
    urn_to_int = 'cap:in="media:numeric";coerce-int;out="media:integer;numeric"'
    urn_to_num = 'cap:in="media:integer;numeric";coerce-num;out="media:numeric"'
    cap_to_int = _simple_cap(urn_to_int, "media:numeric", "media:integer;numeric")
    cap_to_num = _simple_cap(urn_to_num, "media:integer;numeric", "media:numeric")
    reg = _registry_with([cap_to_int, cap_to_num])
    strand = _strand_with_cap_steps([
        (urn_to_int, "media:numeric", "media:integer;numeric"),
        (urn_to_num, "media:integer;numeric", "media:numeric"),
    ])
    resolved = resolve_strand(strand, reg, 0)
    # Three distinct positional nodes: input (numeric), intermediate (integer;numeric), output (numeric again but new NodeId)
    assert resolved.nodes() is not None
    assert len(resolved.edges()) == 2
    # Intermediate node is shared between the two edges
    int_target = resolved.edges()[0].main_target()
    num_source = resolved.edges()[1].assignment[0].source.node
    assert int_target == num_source


# =============================================================================
# Tests ported from Rust graph.rs (1160), parser.rs (1163), resolve.rs (1178, 1185, 1186, 1191)
# =============================================================================

# TEST1160: Creating a MachineRun stores the canonical notation and starts in the pending state.
def test_1160_machine_run_new_stores_canonical_notation():
    import capdag.machine.serializer  # ensure to_machine_notation is attached
    cap_urn_str = "cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\""
    cap = _simple_cap(cap_urn_str, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    reg = _registry_with([cap])

    strand = _strand_with_cap_steps([(cap_urn_str, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")])
    machine = Machine.from_strand(strand, reg)
    canonical = machine.to_machine_notation()
    run = MachineRun.new("run-id-1", machine, strand)
    assert run.id == "run-id-1"
    assert run.machine_notation == canonical
    assert run.status == MachineRunStatus.PENDING


# TEST1163: Parsing one connected strand yields a single machine strand with both caps connected by the shared node.
def test_1163_parse_single_strand_two_caps_connected_via_shared_node():
    urn1 = "cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\""
    urn2 = "cap:embed;in=\"media:enc=utf-8\";out=\"media:vec;record\""
    cap1 = _simple_cap(urn1, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    cap2 = _simple_cap(urn2, "media:enc=utf-8", "media:vec;record")
    reg = _registry_with([cap1, cap2])

    notation = (
        f"[extract {urn1}]"
        f"[embed {urn2}]"
        "[doc -> extract -> txt]"
        "[txt -> embed -> vec]"
    )
    machine = parse_machine(notation, reg)
    # Two wirings, one shared node `txt` → ONE connected component → ONE strand.
    assert machine.strand_count() == 1
    strand = machine.strands()[0]
    assert len(strand.edges()) == 2
    # The intermediate node must be the same NodeId for both edges.
    extract_target = strand.edges()[0].main_target()
    embed_source = strand.edges()[1].assignment[0].source.node
    assert extract_target == embed_source


# TEST1178: One source is assigned to the single compatible cap argument.
def test_1178_match_single_source_picks_unique_arg():
    sources = [_media("media:document;ext=pdf")]
    args = [_media("media:document;ext=pdf")]
    pairs = _match(sources, args)
    assert len(pairs) == 1
    assert pairs[0][0].is_equivalent(_media("media:document;ext=pdf"))
    assert pairs[0][1].is_equivalent(_media("media:document;ext=pdf"))


# TEST1185: Resolving a chained strand reuses the intermediate node between adjacent caps.
def test_1185_resolve_strand_chained_caps_share_intermediate_node():
    urn_extract = "cap:in=\"media:document;ext=pdf\";extract;out=\"media:enc=utf-8;ext=txt\""
    urn_embed = "cap:in=\"media:enc=utf-8\";embed;out=\"media:vec;record\""
    extract = _simple_cap(urn_extract, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    embed = _simple_cap(urn_embed, "media:enc=utf-8", "media:vec;record")
    reg = _registry_with([extract, embed])

    strand = _strand_with_cap_steps([
        (urn_extract, "media:document;ext=pdf", "media:enc=utf-8;ext=txt"),
        (urn_embed, "media:enc=utf-8;ext=txt", "media:vec;record"),
    ])

    resolved = resolve_strand(strand, reg, 0)
    assert len(resolved.edges()) == 2
    assert len(resolved.nodes()) == 3, \
        "three distinct data positions: pdf, txt, vec;record"

    # The first edge's target NodeId must equal the second edge's primary source NodeId.
    extract_target = resolved.edges()[0].main_target()
    embed_source = resolved.edges()[1].assignment[0].source.node
    assert extract_target == embed_source, \
        "intermediate data position must be one shared NodeId"

    # Anchors.
    inputs = resolved.input_anchors()
    outputs = resolved.output_anchors()
    assert len(inputs) == 1
    assert len(outputs) == 1
    assert inputs[0].is_equivalent(_media("media:document;ext=pdf"))
    assert outputs[0].is_equivalent(_media("media:vec;record"))


# TEST1186: A ForEach step immediately following disbind is elided; is_loop is
# derived from cardinality: disbind produces a SEQUENCE of pages, and
# make_decision consumes a scalar page, so make_decision's edge maps per item.
# The trailing Collect step is also elided.
def test_1186_resolve_strand_foreach_marks_following_cap_as_loop():
    urn_disbind = "cap:in=\"media:document;ext=pdf\";disbind;out=\"media:enc=utf-8;page\""
    urn_decision = "cap:in=\"media:enc=utf-8\";make-decision;out=\"media:decision;fmt=json;record\""
    disbind = _simple_cap(urn_disbind, "media:document;ext=pdf", "media:enc=utf-8;page")
    disbind.main_output().is_sequence = True
    make_decision = _simple_cap(urn_decision, "media:enc=utf-8", "media:decision;fmt=json;record")
    reg = _registry_with([disbind, make_decision])

    disbind_step = StrandStep(
        step_type=StrandStepType.CAP,
        from_spec=_media("media:document;ext=pdf"),
        to_spec=_media("media:enc=utf-8;page"),
        cap_urn=_cap_urn(urn_disbind),
        inputs=[CapInput(arg_urn=_media("media:document;ext=pdf"), source=ArgSourceRef.strand_input())],
    )
    foreach_step = StrandStep(
        step_type=StrandStepType.FOR_EACH,
        from_spec=_media("media:enc=utf-8;page"),
        to_spec=_media("media:enc=utf-8;page"),
        media_def=_media("media:enc=utf-8;page"),
    )
    decision_step = StrandStep(
        step_type=StrandStepType.CAP,
        from_spec=_media("media:enc=utf-8"),
        to_spec=_media("media:decision;fmt=json;record"),
        cap_urn=_cap_urn(urn_decision),
        inputs=[CapInput(arg_urn=_media("media:enc=utf-8"), source=ArgSourceRef.step(disbind_step.token_id))],
    )
    collect_step = StrandStep(
        step_type=StrandStepType.COLLECT,
        from_spec=_media("media:decision;fmt=json;record"),
        to_spec=_media("media:decision;fmt=json;record"),
        media_def=_media("media:decision;fmt=json;record"),
    )
    strand = Strand(
        steps=[disbind_step, foreach_step, decision_step, collect_step],
        source_media_urn=_media("media:document;ext=pdf"),
        target_media_urn=_media("media:decision;fmt=json;record"),
        total_steps=4,
        cap_step_count=2,
        description="disbind+foreach+make_decision",
    )

    resolved = resolve_strand(strand, reg, 0)
    assert len(resolved.edges()) == 2

    # First edge (disbind) is not a loop; second (make-decision) is.
    disbind_edge = next(
        e for e in resolved.edges() if "disbind" in str(e.cap_urn)
    )
    decision_edge = next(
        e for e in resolved.edges() if "make-decision" in str(e.cap_urn)
    )
    assert not disbind_edge.is_loop, "disbind is not in a loop"
    assert decision_edge.is_loop, "make_decision is inside ForEach"

    # disbind's target NodeId must be the same as make_decision's source NodeId.
    disbind_target = disbind_edge.main_target()
    decision_source = decision_edge.assignment[0].source.node
    assert disbind_target == decision_source, \
        "disbind target and make_decision source must share the same NodeId (positional interning)"
    # The canonical URN at that shared node must be the more-specific one.
    assert resolved.node_urn(disbind_target).is_equivalent(_media("media:enc=utf-8;page")), \
        f"shared node URN must be the more-specific media:enc=utf-8;page, got: {resolved.node_urn(disbind_target)}"


# TEST1191: Disbinding a PDF with a file-path slot preserves the expected identity of the slot binding.
def test_1191_resolve_strand_disbind_pdf_with_file_path_slot_identity():
    # A cap whose arg slot identity differs from its stdin source URN.
    # slot identity = media:enc=utf-8;file-path, stdin source = media:document;ext=pdf.
    cap_urn_str = "cap:in=\"media:document;ext=pdf\";disbind;out=\"media:enc=utf-8;page\""
    urn = CapUrn.from_string(cap_urn_str)
    cap = Cap.with_description(urn, "disbind", ["disbind"], "disbind cap")
    cap.add_arg(CapArg(
        media_urn="media:enc=utf-8;file-path", name="input",
        required=True,
        sources=[StdinSource("media:document;ext=pdf")],
    ))
    cap.add_output(CapOutput("media:enc=utf-8;page", "output", "page output"))
    reg = _registry_with([cap])

    strand = _strand_with_cap_steps([(cap_urn_str, "media:document;ext=pdf", "media:enc=utf-8;page")])

    resolved = resolve_strand(strand, reg, 0)
    assert len(resolved.edges()) == 1
    binding = resolved.edges()[0].assignment[0]

    # The binding's cap_arg_media_urn must be the SLOT identity.
    assert binding.cap_arg_media_urn.is_equivalent(_media("media:enc=utf-8;file-path")), \
        f"binding cap_arg_media_urn must be the slot identity, got: {binding.cap_arg_media_urn}"

    # The source NodeId must point at a node whose URN is media:document;ext=pdf.
    source_urn = resolved.node_urn(binding.source.node)
    assert source_urn.is_equivalent(_media("media:document;ext=pdf")), \
        f"source node URN must be media:document;ext=pdf (the data-type URN), got: {source_urn}"


# TEST1196: `to_machine_notation_aliased` renders a cap by its registered
# display alias (shortest, then alphabetical), referenced directly in the
# wiring with no header; falls back to the raw URN + header for a cap with no
# alias; and the result round-trips back to the same machine (the parser
# resolves the alias from the warm cache).
def test_1196_aliased_serialization_uses_alias_and_round_trips():
    import capdag.machine.serializer  # ensure aliased serializer is attached
    from capdag.fabric.registry import StoredAlias

    extract_urn = "cap:extract;in=\"media:document;ext=pdf\";out=\"media:enc=utf-8;ext=txt\""
    embed_urn = "cap:embed;in=\"media:enc=utf-8;ext=txt\";out=\"media:vec;record\""
    extract_cap = _simple_cap(extract_urn, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")
    embed_cap = _simple_cap(embed_urn, "media:enc=utf-8;ext=txt", "media:vec;record")
    reg = _registry_with([extract_cap, embed_cap])

    # Two aliases on the extract cap; "ex" is shorter than "extract-pdf".
    reg.insert_cached_alias_for_test(StoredAlias("extract-pdf", extract_urn, 1))
    reg.insert_cached_alias_for_test(StoredAlias("ex", extract_urn, 1))
    # No alias for the embed cap -> it must stay a raw URN.

    strand = _strand_with_cap_steps([
        (extract_urn, "media:document;ext=pdf", "media:enc=utf-8;ext=txt"),
        (embed_urn, "media:enc=utf-8;ext=txt", "media:vec;record"),
    ])
    m1 = Machine.from_strand(strand, reg)
    aliased = m1.to_machine_notation_aliased(reg, "bracketed")

    # The extract cap is aliased: referenced directly in the wiring by its
    # SHORTER alias `ex`, with NO header, and the URN must not appear.
    assert "-> ex ->" in aliased, \
        f"extract cap must be referenced in the wiring by the shortest alias `ex`, got: {aliased}"
    assert "cap:extract" not in aliased, \
        f"the aliased extract cap URN must not appear, got: {aliased}"
    # The embed cap has no alias -> it keeps its synthetic header + URN.
    assert "cap:embed" in aliased, \
        f"the un-aliased embed cap must keep its header URN, got: {aliased}"

    # Round-trip: parse the aliased notation back. The alias is already in the
    # warm cache (seeded above), so the sync parser resolves it.
    m2 = parse_machine(aliased, reg)
    assert m1.is_equivalent(m2), \
        "aliased serialize -> parse must preserve strict equivalence"

    # The canonical (no-arg) identity form is unchanged: it still names both
    # caps by their full URN and is independent of the alias cache.
    canonical = m1.to_machine_notation()
    assert "cap:extract" in canonical and "cap:embed" in canonical
    assert "-> ex ->" not in canonical


# =============================================================================
# Mirror-specific coverage: realize.py — realizing a resolved MachineStrand
# into an executable planner Strand.
# =============================================================================


# TEST12836: a strand's steps name where each input comes from. A strand's own
# input, taken by two steps, is one node holding the most specific type either
# declares for it; a step that names a producer no step of the strand is makes
# the strand disconnected, and is refused.
def test_12836_a_strand_input_is_one_node_and_a_missing_producer_is_refused():
    from capdag.machine.error import DisconnectedStrandError

    loose_urn = 'cap:in="media:enc=utf-8";count;out="media:count;numeric"'
    tight_urn = 'cap:in="media:enc=utf-8;page";title;out="media:enc=utf-8;title"'
    reg = _registry_with([
        _simple_cap(loose_urn, "media:enc=utf-8", "media:count;numeric"),
        _simple_cap(tight_urn, "media:enc=utf-8;page", "media:enc=utf-8;title"),
    ])

    def step(cap_urn: str, from_urn: str, to_urn: str, source) -> StrandStep:
        return StrandStep(
            step_type=StrandStepType.CAP,
            from_spec=_media(from_urn),
            to_spec=_media(to_urn),
            cap_urn=_cap_urn(cap_urn),
            inputs=[CapInput(arg_urn=_media(from_urn), source=source)],
        )

    def strand_of(steps) -> Strand:
        return Strand(
            steps=steps,
            source_media_urn=steps[0].from_spec,
            target_media_urn=steps[-1].to_spec,
            total_steps=len(steps),
            cap_step_count=len(steps),
            description="test strand",
        )

    # Both steps take the strand's input; the second declares it more tightly.
    for first, second in (
        ((loose_urn, "media:enc=utf-8", "media:count;numeric"),
         (tight_urn, "media:enc=utf-8;page", "media:enc=utf-8;title")),
        ((tight_urn, "media:enc=utf-8;page", "media:enc=utf-8;title"),
         (loose_urn, "media:enc=utf-8", "media:count;numeric")),
    ):
        resolved = resolve_strand(
            strand_of([
                step(*first, ArgSourceRef.strand_input()),
                step(*second, ArgSourceRef.strand_input()),
            ]),
            reg,
            0,
        )
        assert len(resolved.nodes()) == 3, "the input once, and what each step makes"
        assert len(resolved.input_anchor_ids()) == 1
        anchor = resolved.input_anchor_ids()[0]
        assert resolved.node_urn(anchor).is_equivalent(_media("media:enc=utf-8;page")), \
            "the most specific type a step declares for it, whichever step comes first"
        for edge in resolved.edges():
            assert edge.source_nodes() == [anchor]

    # A producer that is no step of the strand.
    orphan = step(loose_urn, "media:enc=utf-8", "media:count;numeric", ArgSourceRef.strand_input())
    reads_nothing = step(
        tight_urn, "media:enc=utf-8;page", "media:enc=utf-8;title",
        ArgSourceRef.step(StepToken.parse("no-such-step")),
    )
    with pytest.raises(DisconnectedStrandError) as exc_info:
        resolve_strand(strand_of([orphan, reads_nothing]), reg, 4)
    assert exc_info.value.strand_index == 4


# TEST12837: the resolver holds a wiring it is handed to the names its cap's
# definition declares, whoever built the wiring: a member or a target naming
# what the cap does not declare is refused by name, with what it does declare.
def test_12837_the_resolver_refuses_names_a_definition_does_not_declare():
    from capdag.machine.error import UnknownArgNameError, UnknownOutputNameError
    from capdag.machine.graph import BindingSource

    cap_urn_str = 'cap:in="media:document;ext=pdf";extract;out="media:enc=utf-8;ext=txt"'
    reg = _registry_with([_simple_cap(cap_urn_str, "media:document;ext=pdf", "media:enc=utf-8;ext=txt")])
    nodes = [_media("media:document;ext=pdf"), _media("media:enc=utf-8;ext=txt")]

    def wiring(named, targets) -> PreInternedWiring:
        return PreInternedWiring(
            token_id=StepToken.mint(),
            cap_urn=_cap_urn(cap_urn_str),
            named_sources=named,
            targets=targets,
        )

    # By the names the definition declares, it resolves.
    by_name = wiring([("input", BindingSource.of_node(0))], [WiringTarget(node=1, name="output")])
    resolved = resolve_pre_interned(list(nodes), [by_name], reg, 0)
    assert resolved.edges()[0].main_target() == 1

    with pytest.raises(UnknownArgNameError) as arg_info:
        resolve_pre_interned(
            list(nodes),
            [wiring([("document", BindingSource.of_node(0))], [WiringTarget(node=1)])],
            reg,
            2,
        )
    assert "strand 2: " in str(arg_info.value)
    assert "declares no arg named 'document' (it declares: input)" in str(arg_info.value)

    with pytest.raises(UnknownOutputNameError) as out_info:
        resolve_pre_interned(
            list(nodes),
            [wiring([("input", BindingSource.of_node(0))], [WiringTarget(node=1, name="text")])],
            reg,
            2,
        )
    assert "declares no output named 'text' (it declares: output)" in str(out_info.value)
