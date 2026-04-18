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
from capdag.cap.registry import CapRegistry
from capdag.machine.graph import (
    EdgeAssignmentBinding,
    MachineEdge,
    MachineStrand,
    Machine,
    NodeId,
)
from capdag.machine.resolve import (
    PreInternedWiring,
    resolve_pre_interned,
    resolve_strand,
    match_sources_to_args,
)
from capdag.machine.error import (
    AmbiguousMachineNotationError,
    CyclicMachineStrandError,
    MachineAbstractionError,
    MachineParseError,
    NoCapabilityStepsError,
    UnknownCapError,
    UnmatchedSourceInCapArgsError,
    MachineSyntaxError,
)
from capdag.machine.parser import parse_machine
from capdag.planner.live_cap_graph import Strand, StrandStep, StrandStepType


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
    cap = Cap.with_description(urn, title, title.lower(), f"{title} cap")
    for stdin_u, slot_u in zip(stdin_urns, slot_urns):
        cap.add_arg(CapArg(
            media_urn=slot_u,
            required=True,
            sources=[StdinSource(stdin_u)],
        ))
    cap.set_output(CapOutput(out_urn, f"{title} output"))
    return cap


def _simple_cap(cap_urn_str: str, stdin_urn: str, out_urn: str) -> Cap:
    """Build a Cap with a single stdin arg where slot_urn == stdin_urn."""
    return _build_cap(cap_urn_str, "cap", [stdin_urn], [stdin_urn], out_urn)


def _registry_with(caps: list) -> CapRegistry:
    reg = CapRegistry.new_for_test()
    reg.add_caps_to_cache(caps)
    return reg


def _strand_with_cap_steps(steps_data: list) -> Strand:
    """Build a Strand from a list of (cap_urn_str, from_urn_str, to_urn_str) tuples."""
    steps = []
    for cap_urn_str, from_str, to_str in steps_data:
        steps.append(StrandStep(
            step_type=StrandStepType.CAP,
            from_spec=_media(from_str),
            to_spec=_media(to_str),
            cap_urn=_cap_urn(cap_urn_str),
        ))
    first = steps[0] if steps else None
    last = steps[-1] if steps else None
    return Strand(
        steps=steps,
        source_spec=first.from_spec if first else _media("media:"),
        target_spec=last.to_spec if last else _media("media:"),
        total_steps=len(steps),
        cap_step_count=len(steps),
        description="test strand",
    )


# =============================================================================
# TEST1110: NoCapabilityStepsError on empty wiring list
# =============================================================================

def test_1110_no_capability_steps_error_on_empty_wirings():
    """TEST1110: resolve_pre_interned with empty wirings raises NoCapabilityStepsError."""
    reg = _registry_with([])
    with pytest.raises(NoCapabilityStepsError):
        resolve_pre_interned([], [], reg, 0)


# =============================================================================
# TEST1111: UnknownCapError when cap not in registry
# =============================================================================

def test_1111_unknown_cap_error_when_not_in_registry():
    """TEST1111: resolve_pre_interned raises UnknownCapError when cap is not cached."""
    reg = _registry_with([])  # empty registry
    cap_urn = _cap_urn("cap:in=media:pdf;op=extract;out=\"media:txt;textable\"")
    nodes = [_media("media:pdf"), _media("media:txt;textable")]
    wirings = [PreInternedWiring(
        cap_urn=cap_urn,
        source_node_ids=[0],
        target_node_id=1,
        is_loop=False,
    )]
    with pytest.raises(UnknownCapError) as exc_info:
        resolve_pre_interned(nodes, wirings, reg, 0)
    assert "cap:in=media:pdf" in str(exc_info.value) or "op=extract" in str(exc_info.value)


# =============================================================================
# TEST1112: Single-edge strand resolves correctly with correct node structure
# =============================================================================

def test_1112_single_edge_strand_resolves_correctly():
    """TEST1112: resolve_strand on a one-cap strand produces one edge, correct anchors."""
    cap_urn_str = "cap:in=media:pdf;op=extract;out=\"media:txt;textable\""
    cap = _simple_cap(cap_urn_str, "media:pdf", "media:txt;textable")
    reg = _registry_with([cap])

    strand = _strand_with_cap_steps([
        (cap_urn_str, "media:pdf", "media:txt;textable"),
    ])
    ms = resolve_strand(strand, reg, 0)

    assert len(ms.edges()) == 1
    assert len(ms.nodes()) == 2
    assert len(ms.input_anchor_ids()) == 1
    assert len(ms.output_anchor_ids()) == 1

    # Input anchor should be media:pdf
    assert ms.nodes()[ms.input_anchor_ids()[0]].is_equivalent(_media("media:pdf"))
    # Output anchor should be media:txt;textable
    assert ms.nodes()[ms.output_anchor_ids()[0]].is_equivalent(_media("media:txt;textable"))


# =============================================================================
# TEST1113: Two-step chain shares intermediate node
# =============================================================================

def test_1113_two_step_chain_shares_intermediate_node():
    """TEST1113: resolve_strand on a two-cap chain shares the intermediate NodeId."""
    urn1 = "cap:in=media:pdf;op=extract;out=\"media:txt;textable\""
    urn2 = "cap:in=media:textable;op=embed;out=\"media:vec;record\""
    cap1 = _simple_cap(urn1, "media:pdf", "media:txt;textable")
    cap2 = _simple_cap(urn2, "media:textable", "media:vec;record")
    reg = _registry_with([cap1, cap2])

    strand = _strand_with_cap_steps([
        (urn1, "media:pdf", "media:txt;textable"),
        (urn2, "media:txt;textable", "media:vec;record"),
    ])
    ms = resolve_strand(strand, reg, 0)

    assert len(ms.edges()) == 2
    # In a chain: node 0=source, node 1=intermediate (shared), node 2=final output.
    # But the intermediate may be one node (reused) depending on is_comparable.
    # media:txt;textable is_comparable to media:textable → reused.
    # So: node 0=pdf, node 1=txt;textable (output of cap1, input refinement of cap2), node 2=vec;record
    assert len(ms.nodes()) == 3

    edge0 = ms.edges()[0]
    edge1 = ms.edges()[1]

    # edge0 target is the source for edge1
    assert edge0.target == edge1.assignment[0].source

    # Only 1 input anchor (media:pdf), 1 output anchor (media:vec;record)
    assert len(ms.input_anchor_ids()) == 1
    assert len(ms.output_anchor_ids()) == 1


# =============================================================================
# TEST1114: Machine.from_strand produces single-strand machine
# =============================================================================

def test_1114_from_strand_produces_single_strand_machine():
    """TEST1114: Machine.from_strand always yields exactly one strand."""
    cap_urn_str = "cap:in=media:pdf;op=extract;out=\"media:txt;textable\""
    cap = _simple_cap(cap_urn_str, "media:pdf", "media:txt;textable")
    reg = _registry_with([cap])

    strand = _strand_with_cap_steps([(cap_urn_str, "media:pdf", "media:txt;textable")])
    m = Machine.from_strand(strand, reg)

    assert m.strand_count() == 1
    assert not m.is_empty()
    assert len(m.strands()[0].edges()) == 1


# =============================================================================
# TEST1115: Machine.from_strands keeps strands disjoint
# =============================================================================

def test_1115_from_strands_keeps_strands_disjoint():
    """TEST1115: Machine.from_strands with two strands produces two disjoint MachineStrands."""
    urn1 = "cap:in=media:pdf;op=extract;out=\"media:txt;textable\""
    urn2 = "cap:in=media:textable;op=embed;out=\"media:vec;record\""
    cap1 = _simple_cap(urn1, "media:pdf", "media:txt;textable")
    cap2 = _simple_cap(urn2, "media:textable", "media:vec;record")
    reg = _registry_with([cap1, cap2])

    s1 = _strand_with_cap_steps([(urn1, "media:pdf", "media:txt;textable")])
    s2 = _strand_with_cap_steps([(urn2, "media:textable", "media:vec;record")])
    m = Machine.from_strands([s1, s2], reg)

    assert m.strand_count() == 2
    # Strands are disjoint — each has their own NodeId space
    assert len(m.strands()[0].edges()) == 1
    assert len(m.strands()[1].edges()) == 1
    # First strand is extract, second is embed
    assert "extract" in str(m.strands()[0].edges()[0].cap_urn)
    assert "embed" in str(m.strands()[1].edges()[0].cap_urn)


# =============================================================================
# TEST1116: Machine.from_strands with empty list raises NoCapabilityStepsError
# =============================================================================

def test_1116_from_strands_empty_raises_no_capability_steps():
    """TEST1116: Machine.from_strands([]) raises NoCapabilityStepsError."""
    reg = _registry_with([])
    with pytest.raises(NoCapabilityStepsError):
        Machine.from_strands([], reg)


# =============================================================================
# TEST1117: Machine.is_equivalent is strict and positional — order matters
# =============================================================================

def test_1117_machine_is_equivalent_strict_positional_order_matters():
    """TEST1117: Two machines with same strands in different order are NOT equivalent."""
    urn1 = "cap:in=media:pdf;op=extract;out=\"media:txt;textable\""
    urn2 = "cap:in=media:textable;op=embed;out=\"media:vec;record\""
    cap1 = _simple_cap(urn1, "media:pdf", "media:txt;textable")
    cap2 = _simple_cap(urn2, "media:textable", "media:vec;record")
    reg = _registry_with([cap1, cap2])

    s1 = _strand_with_cap_steps([(urn1, "media:pdf", "media:txt;textable")])
    s2 = _strand_with_cap_steps([(urn2, "media:textable", "media:vec;record")])

    forward = Machine.from_strands([s1, s2], reg)
    reversed_ = Machine.from_strands([s2, s1], reg)

    # Same strands, different order → NOT equivalent
    assert not forward.is_equivalent(reversed_)
    # Each is equivalent to itself
    assert forward.is_equivalent(forward)
    assert reversed_.is_equivalent(reversed_)


# =============================================================================
# TEST1118: MachineStrand.is_equivalent walks NodeId bijection correctly
# =============================================================================

def test_1118_strand_is_equivalent_consistent_node_bijection():
    """TEST1118: Two MachineStrands built from identical inputs are equivalent.

    The bijection logic must confirm that NodeIds map consistently across
    both the anchor lists and the edge assignment vecs.
    """
    cap_urn_str = "cap:in=media:pdf;op=extract;out=\"media:txt;textable\""
    cap = _simple_cap(cap_urn_str, "media:pdf", "media:txt;textable")
    reg = _registry_with([cap])

    strand = _strand_with_cap_steps([(cap_urn_str, "media:pdf", "media:txt;textable")])
    m1 = Machine.from_strand(strand, reg)
    m2 = Machine.from_strand(strand, reg)

    assert m1.strands()[0].is_equivalent(m2.strands()[0])


# =============================================================================
# TEST1119: match_sources_to_args single source trivial assignment
# =============================================================================

def test_1119_match_sources_to_args_single_trivial():
    """TEST1119: Single source matching single arg at distance 0 succeeds with correct pair."""
    sources = [_media("media:pdf")]
    args = [_media("media:pdf")]
    cap_urn_str = "cap:in=media:pdf;op=extract;out=\"media:txt;textable\""

    pairs = match_sources_to_args(sources, args, cap_urn_str, 0)

    assert len(pairs) == 1
    assert pairs[0][0].is_equivalent(_media("media:pdf"))  # cap arg urn
    assert pairs[0][1].is_equivalent(_media("media:pdf"))  # source urn


# =============================================================================
# TEST1120: match_sources_to_args more-specific source matches general arg
# =============================================================================

def test_1120_match_sources_more_specific_source_matches_general_arg():
    """TEST1120: source media:txt;textable conforms to arg media:textable → matched with nonzero cost."""
    sources = [_media("media:txt;textable")]
    args = [_media("media:textable")]
    pairs = match_sources_to_args(sources, args, "cap:in=media:textable;op=embed;out=media:vec", 0)
    assert len(pairs) == 1
    assert pairs[0][0].is_equivalent(_media("media:textable"))
    assert pairs[0][1].is_equivalent(_media("media:txt;textable"))


# =============================================================================
# TEST1121: match_sources_to_args unmatched source raises UnmatchedSourceInCapArgsError
# =============================================================================

def test_1121_match_sources_unmatched_source_fails_hard():
    """TEST1121: Source that conforms to no arg raises UnmatchedSourceInCapArgsError."""
    sources = [_media("media:numeric")]
    args = [_media("media:textable")]
    cap_urn_str = "cap:in=media:textable;op=t;out=media:textable"

    with pytest.raises(UnmatchedSourceInCapArgsError) as exc_info:
        match_sources_to_args(sources, args, cap_urn_str, 7)

    err = exc_info.value
    assert err.strand_index == 7
    assert "media:numeric" in err.source_urn


# =============================================================================
# TEST1122: match_sources_to_args ambiguous assignment raises AmbiguousMachineNotationError
# =============================================================================

def test_1122_match_sources_ambiguous_raises_ambiguous_error():
    """TEST1122: Two sources with identical URNs competing for two identical-cost args → ambiguous."""
    # Two sources both conform equally to both args at the same distance.
    sources = [_media("media:textable"), _media("media:textable")]
    args = [_media("media:textable"), _media("media:textable")]
    cap_urn_str = "cap:in=media:textable;op=merge;out=media:textable"

    with pytest.raises(AmbiguousMachineNotationError) as exc_info:
        match_sources_to_args(sources, args, cap_urn_str, 3)

    err = exc_info.value
    assert err.strand_index == 3


# =============================================================================
# TEST1123: CyclicMachineStrandError on a hand-crafted cyclic wiring
# =============================================================================

def test_1123_cyclic_strand_fails_hard():
    """TEST1123: A wiring that feeds a cap's output back into itself raises CyclicMachineStrandError.

    Cycle: node 0 → cap A → node 1 → cap B → node 0
    """
    urn_a = "cap:in=media:pdf;op=op_a;out=\"media:txt;textable\""
    urn_b = "cap:in=\"media:txt;textable\";op=op_b;out=media:pdf"

    cap_a = _simple_cap(urn_a, "media:pdf", "media:txt;textable")
    cap_b = _simple_cap(urn_b, "media:txt;textable", "media:pdf")
    reg = _registry_with([cap_a, cap_b])

    nodes = [_media("media:pdf"), _media("media:txt;textable")]
    # node 0 -> cap_a -> node 1  and  node 1 -> cap_b -> node 0 (cycle)
    wirings = [
        PreInternedWiring(_cap_urn(urn_a), [0], 1, False),
        PreInternedWiring(_cap_urn(urn_b), [1], 0, False),
    ]

    with pytest.raises(CyclicMachineStrandError) as exc_info:
        resolve_pre_interned(nodes, wirings, reg, 5)

    assert exc_info.value.strand_index == 5


# =============================================================================
# TEST1124: MachineParseError wraps MachineSyntaxError correctly
# =============================================================================

def test_1124_machine_parse_error_wraps_syntax_error():
    """TEST1124: parse_machine on empty input raises MachineParseError wrapping MachineSyntaxError."""
    reg = _registry_with([])
    with pytest.raises(MachineParseError) as exc_info:
        parse_machine("", reg)

    err = exc_info.value
    assert err.is_syntax_error
    assert not err.is_abstraction_error
    assert isinstance(err.cause, MachineSyntaxError)


# =============================================================================
# TEST1125: parse_machine raises MachineParseError wrapping UnknownCapError
# =============================================================================

def test_1125_parse_machine_unknown_cap_raises_parse_error_with_abstraction_cause():
    """TEST1125: parse_machine with cap not in registry raises MachineParseError (abstraction)."""
    reg = _registry_with([])  # empty — no caps loaded

    notation = (
        "[extract cap:in=media:pdf;op=extract;out=\"media:txt;textable\"]\n"
        "[doc -> extract -> text]"
    )

    with pytest.raises(MachineParseError) as exc_info:
        parse_machine(notation, reg)

    err = exc_info.value
    assert err.is_abstraction_error
    assert not err.is_syntax_error
    assert isinstance(err.cause, MachineAbstractionError)


# =============================================================================
# TEST1126: parse_machine single-wiring notation produces one strand
# =============================================================================

def test_1126_parse_machine_single_wiring_one_strand():
    """TEST1126: parse_machine on a simple one-edge notation produces Machine with one strand."""
    cap_urn_str = "cap:in=media:pdf;op=extract;out=\"media:txt;textable\""
    cap = _simple_cap(cap_urn_str, "media:pdf", "media:txt;textable")
    reg = _registry_with([cap])

    notation = (
        f'[extract {cap_urn_str}]\n'
        "[doc -> extract -> text]"
    )

    m = parse_machine(notation, reg)

    assert m.strand_count() == 1
    assert len(m.strands()[0].edges()) == 1
    assert not m.is_empty()


# =============================================================================
# TEST1127: parse_machine union-find partitions disconnected wirings into separate strands
# =============================================================================

def test_1127_parse_machine_disconnected_wirings_become_separate_strands():
    """TEST1127: Two wirings with no shared node names are separate strands."""
    urn1 = "cap:in=media:pdf;op=extract;out=\"media:txt;textable\""
    urn2 = "cap:in=media:image;op=caption;out=\"media:txt;textable\""
    cap1 = _simple_cap(urn1, "media:pdf", "media:txt;textable")
    cap2 = _simple_cap(urn2, "media:image", "media:txt;textable")
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
# TEST1128: parse_machine shared node name connects wirings into same strand
# =============================================================================

def test_1128_parse_machine_shared_node_name_yields_one_strand():
    """TEST1128: Two wirings sharing a node name form one connected strand."""
    urn1 = "cap:in=media:pdf;op=extract;out=\"media:txt;textable\""
    urn2 = "cap:in=media:textable;op=embed;out=\"media:vec;record\""
    cap1 = _simple_cap(urn1, "media:pdf", "media:txt;textable")
    cap2 = _simple_cap(urn2, "media:textable", "media:vec;record")
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
# TEST1129: EdgeAssignmentBinding stores correct slot identity (not stdin inner type)
# =============================================================================

def test_1129_binding_slot_identity_is_outer_media_urn():
    """TEST1129: EdgeAssignmentBinding.cap_arg_media_urn is the slot identity (outer media_urn),
    not the stdin inner URN.

    This tests the slot-vs-stdin distinction: a cap arg may have
    media_urn="media:file-path;textable" with stdin="media:pdf".
    The binding must record the slot identity, not the stdin type.
    """
    cap_urn_str = "cap:in=media:pdf;op=read_pdf;out=\"media:txt;textable\""
    urn = CapUrn.from_string(cap_urn_str)
    cap = Cap.with_description(urn, "ReadPdf", "read_pdf", "reads a PDF")
    # slot identity = "media:file-path;textable", stdin = "media:pdf"
    cap.add_arg(CapArg(
        media_urn="media:file-path;textable",
        required=True,
        sources=[StdinSource("media:pdf")],
    ))
    cap.set_output(CapOutput("media:txt;textable", "text output"))
    reg = _registry_with([cap])

    nodes = [_media("media:pdf"), _media("media:txt;textable")]
    wirings = [PreInternedWiring(
        cap_urn=_cap_urn(cap_urn_str),
        source_node_ids=[0],
        target_node_id=1,
        is_loop=False,
    )]

    ms = resolve_pre_interned(nodes, wirings, reg, 0)
    assert len(ms.edges()) == 1
    binding = ms.edges()[0].assignment[0]

    # Slot identity must be the outer media_urn ("media:file-path;textable")
    assert binding.cap_arg_media_urn.is_equivalent(_media("media:file-path;textable"))
    # Source NodeId must be 0
    assert binding.source == 0


# =============================================================================
# TEST1130: MachineStrand.is_equivalent rejects strands with wrong URN at bijected node
# =============================================================================

def test_1130_strand_equivalence_rejects_mismatched_node_urns():
    """TEST1130: Two strands that differ only in one node's media URN are NOT equivalent.

    The NodeBijection check requires URN-level is_equivalent at both ends of
    every mapped NodeId pair.
    """
    urn_extract = "cap:in=media:pdf;op=extract;out=\"media:txt;textable\""
    urn_summarize = "cap:in=media:pdf;op=extract;out=\"media:md;textable\""
    cap_e = _simple_cap(urn_extract, "media:pdf", "media:txt;textable")
    cap_s = _simple_cap(urn_summarize, "media:pdf", "media:md;textable")
    reg = _registry_with([cap_e, cap_s])

    strand_e = _strand_with_cap_steps([(urn_extract, "media:pdf", "media:txt;textable")])
    strand_s = _strand_with_cap_steps([(urn_summarize, "media:pdf", "media:md;textable")])

    m1 = Machine.from_strand(strand_e, reg)
    m2 = Machine.from_strand(strand_s, reg)

    # Different output URN → not equivalent
    assert not m1.strands()[0].is_equivalent(m2.strands()[0])


# =============================================================================
# TEST1131: resolve_strand with ForEach sets is_loop on next cap edge
# =============================================================================

def test_1131_resolve_strand_foreach_sets_is_loop_on_next_cap():
    """TEST1131: A strand with a ForEach step followed by a Cap step produces is_loop=True on the edge."""
    cap_urn_str = "cap:in=media:textable;op=embed;out=\"media:vec;record\""
    cap = _simple_cap(cap_urn_str, "media:textable", "media:vec;record")
    reg = _registry_with([cap])

    foreach_step = StrandStep(
        step_type=StrandStepType.FOR_EACH,
        from_spec=_media("media:list;textable"),
        to_spec=_media("media:textable"),
        media_spec=_media("media:textable"),
    )
    cap_step = StrandStep(
        step_type=StrandStepType.CAP,
        from_spec=_media("media:textable"),
        to_spec=_media("media:vec;record"),
        cap_urn=_cap_urn(cap_urn_str),
    )
    strand = Strand(
        steps=[foreach_step, cap_step],
        source_spec=_media("media:list;textable"),
        target_spec=_media("media:vec;record"),
        total_steps=2,
        cap_step_count=1,
        description="foreach embed",
    )

    ms = resolve_strand(strand, reg, 0)
    assert len(ms.edges()) == 1
    assert ms.edges()[0].is_loop is True


# =============================================================================
# TEST1132: resolve_strand with only ForEach/Collect steps (no cap) raises error
# =============================================================================

def test_1132_resolve_strand_no_cap_steps_raises_no_capability_steps():
    """TEST1132: A strand with only ForEach (no CAP step) raises NoCapabilityStepsError."""
    reg = _registry_with([])

    foreach_step = StrandStep(
        step_type=StrandStepType.FOR_EACH,
        from_spec=_media("media:list;textable"),
        to_spec=_media("media:textable"),
        media_spec=_media("media:textable"),
    )
    strand = Strand(
        steps=[foreach_step],
        source_spec=_media("media:list;textable"),
        target_spec=_media("media:textable"),
        total_steps=1,
        cap_step_count=0,
        description="only foreach",
    )

    with pytest.raises(NoCapabilityStepsError):
        resolve_strand(strand, reg, 0)


# =============================================================================
# TEST1133: Machine.from_string is an alias for parse_machine with registry
# =============================================================================

def test_1133_machine_from_string_delegates_to_parse_machine():
    """TEST1133: Machine.from_string(notation, registry) returns the same Machine as parse_machine."""
    cap_urn_str = "cap:in=media:pdf;op=extract;out=\"media:txt;textable\""
    cap = _simple_cap(cap_urn_str, "media:pdf", "media:txt;textable")
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

def test_abstraction_error_subclass_hierarchy():
    """TEST1134: All resolution error subclasses are instances of MachineAbstractionError."""
    err_no_steps = NoCapabilityStepsError()
    err_unknown = UnknownCapError("cap:op=x")
    err_unmatched = UnmatchedSourceInCapArgsError(0, "cap:op=x", "media:pdf")
    err_ambiguous = AmbiguousMachineNotationError(1, "cap:op=y")
    err_cyclic = CyclicMachineStrandError(2)

    for err in [err_no_steps, err_unknown, err_unmatched, err_ambiguous, err_cyclic]:
        assert isinstance(err, MachineAbstractionError)
        assert isinstance(err, Exception)


# =============================================================================
# Mirror-specific coverage: MachineStrand nodes() returns correct MediaUrns by NodeId
# =============================================================================

def test_strand_node_urn_accessor():
    """TEST1135: MachineStrand.node_urn(id) returns the MediaUrn at that NodeId."""
    cap_urn_str = "cap:in=media:pdf;op=extract;out=\"media:txt;textable\""
    cap = _simple_cap(cap_urn_str, "media:pdf", "media:txt;textable")
    reg = _registry_with([cap])

    strand = _strand_with_cap_steps([(cap_urn_str, "media:pdf", "media:txt;textable")])
    ms = Machine.from_strand(strand, reg).strands()[0]

    # There are exactly 2 nodes: source (pdf) and target (txt;textable)
    for nid in range(len(ms.nodes())):
        urn = ms.node_urn(nid)
        assert isinstance(urn, MediaUrn)


# =============================================================================
# Mirror-specific coverage: parse_machine undefined alias raises MachineParseError with syntax cause
# =============================================================================

def test_parse_machine_undefined_alias_raises_syntax_error():
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

def test_two_strand_machine_serializes_to_notation():
    """TEST1137: Machine with two strands serializes to a non-empty notation string."""
    import capdag.machine.serializer  # ensure methods are attached

    urn1 = "cap:in=media:pdf;op=extract;out=\"media:txt;textable\""
    urn2 = "cap:in=media:image;op=caption;out=\"media:txt;textable\""
    cap1 = _simple_cap(urn1, "media:pdf", "media:txt;textable")
    cap2 = _simple_cap(urn2, "media:image", "media:txt;textable")
    reg = _registry_with([cap1, cap2])

    s1 = _strand_with_cap_steps([(urn1, "media:pdf", "media:txt;textable")])
    s2 = _strand_with_cap_steps([(urn2, "media:image", "media:txt;textable")])
    m = Machine.from_strands([s1, s2], reg)

    notation = m.to_machine_notation()
    assert len(notation) > 0
    # Both op tags appear in the output
    assert "extract" in notation
    assert "caption" in notation


# =============================================================================
# Mirror-specific coverage: Assignment bindings are sorted by cap_arg_media_urn for canonical form
# =============================================================================

def test_assignment_bindings_sorted_by_slot_urn():
    """TEST1138: EdgeAssignmentBinding list is sorted by cap_arg_media_urn, enabling
    canonical comparison across different creation orders.

    Build a two-source cap where the arg order and source order could produce
    different binding orderings. Assert the bindings are always sorted.
    """
    # Cap with two stdin args in reverse alphabetical slot order
    cap_urn_str = "cap:in=media:pdf;op=merge;out=\"media:txt;textable\""
    urn = CapUrn.from_string(cap_urn_str)
    cap = Cap.with_description(urn, "Merge", "merge", "merge two inputs")
    # Slot B comes before A alphabetically; add them in B, A order.
    cap.add_arg(CapArg(
        media_urn="media:textable",       # slot: textable (later alphabetically)
        required=True,
        sources=[StdinSource("media:textable")],
    ))
    cap.add_arg(CapArg(
        media_urn="media:pdf",            # slot: pdf (earlier alphabetically)
        required=True,
        sources=[StdinSource("media:pdf")],
    ))
    cap.set_output(CapOutput("media:txt;textable", "merged output"))
    reg = _registry_with([cap])

    # Two source nodes: node 0 = pdf, node 1 = textable
    nodes = [_media("media:pdf"), _media("media:textable"), _media("media:txt;textable")]
    wirings = [PreInternedWiring(
        cap_urn=_cap_urn(cap_urn_str),
        source_node_ids=[0, 1],  # pdf first, textable second
        target_node_id=2,
        is_loop=False,
    )]

    ms = resolve_pre_interned(nodes, wirings, reg, 0)
    assert len(ms.edges()) == 1

    bindings = ms.edges()[0].assignment
    assert len(bindings) == 2

    # Bindings must be sorted by slot urn string
    slot_strs = [str(b.cap_arg_media_urn) for b in bindings]
    assert slot_strs == sorted(slot_strs), (
        f"Bindings not in sorted order: {slot_strs}"
    )
