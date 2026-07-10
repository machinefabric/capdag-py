"""Anchor-realization for MachineStrands.

Turns either a planner-produced Strand (linear cap-step sequence, one
source per step) or a parser-produced wiring set (potentially
multi-source per wiring) into a fully-resolved MachineStrand.

Resolution requires FabricRegistry access to look up each cap's full
argument list (cap.args) so the matching algorithm has the per-arg
media URN identities to match against.

Source-to-cap-arg matching:
    For each edge, run a minimum-cost bipartite matching:
    - Sources: the URNs feeding this edge.
    - Cap arguments: the cap's stdin args (identified by slot media_urn).
    - Cost of pairing source s with arg a: spec(s) - spec(a) if s.conforms_to(a).
    - The minimum-cost assignment must be unique; ties raise AmbiguousMachineNotationError.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn
from capdag.machine.graph import EdgeAssignmentBinding, MachineEdge, MachineStrand, NodeId
from capdag.machine.error import (
    AmbiguousMachineNotationError,
    CyclicMachineStrandError,
    DisconnectedStrandError,
    NoCapabilityStepsError,
    UnknownCapError,
    UnmatchedSourceInCapArgsError,
)

if TYPE_CHECKING:
    from capdag.cap.registry import FabricRegistry
    from capdag.planner.live_cap_fab import Strand


class PreInternedWiring:
    """One wiring after source/target slots have been pre-interned into NodeIds.

    The resolver consumes this shape via resolve_pre_interned and does NOT
    do any URN-based interning of its own. Two distinct NodeIds whose
    underlying URNs are is_equivalent stay distinct — this is what the
    notation parser needs to honor the user's node-name identity contract.
    """

    __slots__ = ("token_id", "cap_urn", "source_node_ids", "target_node_id")

    def __init__(
        self,
        cap_urn: CapUrn,
        source_node_ids: List[NodeId],
        target_node_id: NodeId,
        token_id: str = "",
    ):
        # The originating resolved-strand step's stable identity, carried
        # onto the resulting MachineEdge (see MachineEdge.token_id).
        self.token_id = token_id
        self.cap_urn = cap_urn
        # Source NodeIds in the order the upstream layer wrote them. Position
        # carries no semantics — the matching below re-derives per-arg
        # identity from URNs.
        self.source_node_ids = source_node_ids
        # Target NodeId.
        self.target_node_id = target_node_id


def resolve_strand(
    strand: "Strand",
    registry: "FabricRegistry",
    strand_index: int,
) -> MachineStrand:
    """Resolve a planner-produced Strand into a single MachineStrand.

    Walks the strand step-by-step. Each `Cap` step declares ALL of its
    data-flow inputs explicitly (`step.inputs`, a list of `CapInput`
    naming each input's producer by that producer step's stable
    `token_id`, or the sentinel `ArgSourceRef.strand_input()` for the
    strand's own input anchor). There is no positional predecessor
    assumption — every input names its producer explicitly, so fan-out and
    convergence are both expressible. `ForEach`/`Collect` steps are elided:
    `is_loop` is not carried on the wiring; it is derived from cardinality
    in `resolve_pre_interned`, the single source of truth shared with path
    search.

    Raises MachineAbstractionError on resolution failure.
    """
    from capdag.planner.live_cap_fab import StrandStepType

    nodes: List[MediaUrn] = []
    pre_interned: List[PreInternedWiring] = []

    # Producer of each node, by producing step's stable `token_id` → its
    # output NodeId. Explicit input sources resolve against this — no
    # positional predecessor assumption, so fan-out and convergence both
    # wire correctly.
    producer_node: Dict[str, NodeId] = {}
    # The single shared strand input anchor node, allocated on first
    # StrandInput reference and refined to the most specific consuming
    # from_spec.
    strand_input_node: Optional[NodeId] = None

    for step in strand.steps:
        if step.step_type == StrandStepType.CAP:
            if not step.inputs:
                raise DisconnectedStrandError(strand_index)

            source_node_ids: List[NodeId] = []
            for cap_input in step.inputs:
                source = cap_input.source
                if source.is_strand_input():
                    if strand_input_node is not None:
                        if step.from_spec.specificity() > nodes[strand_input_node].specificity():
                            nodes[strand_input_node] = step.from_spec
                        source_id = strand_input_node
                    else:
                        source_id = len(nodes)
                        nodes.append(step.from_spec)
                        strand_input_node = source_id
                else:
                    if source.token_id not in producer_node:
                        raise DisconnectedStrandError(strand_index)
                    source_id = producer_node[source.token_id]
                source_node_ids.append(source_id)

            # Target: always a fresh position.
            target_id = len(nodes)
            nodes.append(step.to_spec)

            pre_interned.append(PreInternedWiring(
                cap_urn=step.cap_urn,
                source_node_ids=source_node_ids,
                target_node_id=target_id,
                token_id=step.token_id,
            ))

            producer_node[step.token_id] = target_id

        # StrandStepType.FOR_EACH / COLLECT: elided — cardinality transitions
        # are implicit. Caps name their producers directly, and `is_loop` is
        # derived from cardinality in resolve_pre_interned, so these steps
        # carry no wiring here.

    if not pre_interned:
        raise NoCapabilityStepsError()

    return resolve_pre_interned(nodes, pre_interned, registry, strand_index)


def resolve_pre_interned(
    nodes: List[MediaUrn],
    wirings: List[PreInternedWiring],
    registry: "FabricRegistry",
    strand_index: int,
) -> MachineStrand:
    """Resolve a pre-interned wiring set into a MachineStrand.

    The caller has already allocated NodeIds for every distinct data
    position. This function:
    1. Per-wiring source-to-cap-arg matching (bipartite, uniqueness required).
    2. Cycle detection via Kahn's algorithm.
    3. Canonical edge ordering with structural tiebreaker.
    4. Anchor computation (input roots / output leaves).

    Raises MachineAbstractionError on any failure.
    """
    if not wirings:
        raise NoCapabilityStepsError()

    # Cardinality of every node, derived from the single canonical rule
    # (`Cap.sequence_shape`): a node holds a sequence iff the cap that
    # PRODUCES it has a sequence output; root nodes (never a wiring target)
    # are scalar. This is exactly the `is_sequence` state
    # `planner.live_cap_fab` threads through a path, evaluated over the
    # resolved graph so `is_loop` is DERIVED from cardinality, never
    # authored. It replaces the retired `LOOP` keyword.
    node_is_sequence: List[bool] = [False] * len(nodes)
    for wiring in wirings:
        cap_urn_str = str(wiring.cap_urn)
        cap = registry.get_cached_cap(cap_urn_str)
        if cap is None:
            raise UnknownCapError(cap_urn_str)
        _input_is_sequence, output_is_sequence = cap.sequence_shape()
        node_is_sequence[wiring.target_node_id] = output_is_sequence

    indexed_edges: List[MachineEdge] = []

    for wiring in wirings:
        cap_urn_str = str(wiring.cap_urn)
        cap = registry.get_cached_cap(cap_urn_str)
        if cap is None:
            raise UnknownCapError(cap_urn_str)

        # Build two parallel lists:
        # - stdin_arg_urns: the per-arg stream URN to match against (what upstream
        #   caps produce)
        # - stdin_arg_slot_urns: the slot identity (cap arg's outer media_urn) for
        #   bindings
        #
        # Wiring sources are matched against EVERY arg by its stream URN (its Stdin
        # source URN if it declares one, else its declared URN — a cap may have no
        # stdin at all). ALL args are producer-feedable: a producer is anything that
        # supplies a value (a prior cap's output, config, a literal, …), so every arg
        # is a candidate. The Hungarian matcher assigns each source to the arg it
        # conforms to; args no source matches take their value from config/defaults;
        # genuine ambiguity is a hard failure (in match_sources_to_args). `stdin_*`
        # names are historical — these are the per-arg stream and slot URNs.
        stdin_arg_urns: List[MediaUrn] = []
        stdin_arg_slot_urns: List[MediaUrn] = []

        for arg in cap.args:
            stream_urn = MediaUrn.from_string(arg.stream_urn())
            slot_urn = MediaUrn.from_string(arg.media_urn)
            stdin_arg_urns.append(stream_urn)
            stdin_arg_slot_urns.append(slot_urn)

        # Pull source URNs from the nodes table.
        source_urns: List[MediaUrn] = [nodes[sid] for sid in wiring.source_node_ids]

        # Run minimum-cost bipartite matching.
        # Returns (matched_stdin_urn, source_urn) pairs sorted by stdin_urn.
        sorted_assignment = match_sources_to_args(
            source_urns, stdin_arg_urns, cap_urn_str, strand_index
        )

        # Build EdgeAssignmentBindings. For each (matched_stdin_urn, source_urn) pair,
        # find the slot identity by looking up matched_stdin_urn in stdin_arg_urns.
        # Map source_urn back to its NodeId (walk unconsumed positions to handle
        # duplicate URNs across different NodeIds).
        bindings: List[EdgeAssignmentBinding] = []
        consumed_positions = [False] * len(wiring.source_node_ids)

        for matched_stdin_urn, source_urn in sorted_assignment:
            # Find the slot identity for this matched stdin URN.
            slot_urn: Optional[MediaUrn] = None
            for stdin_u, slot_u in zip(stdin_arg_urns, stdin_arg_slot_urns):
                if stdin_u.is_equivalent(matched_stdin_urn):
                    slot_urn = slot_u
                    break
            assert slot_urn is not None, (
                "matching returned a stdin URN not in the cap's stdin args list"
            )

            # Find the source NodeId by URN equivalence (unconsumed positions only).
            chosen_pos: Optional[int] = None
            for pos, sid in enumerate(wiring.source_node_ids):
                if consumed_positions[pos]:
                    continue
                if nodes[sid].is_equivalent(source_urn):
                    chosen_pos = pos
                    break
            assert chosen_pos is not None, (
                "matching returned a source URN not in the wiring's source positions"
            )
            consumed_positions[chosen_pos] = True
            bindings.append(EdgeAssignmentBinding(
                cap_arg_media_urn=slot_urn,
                source=wiring.source_node_ids[chosen_pos],
            ))

        # Re-sort bindings by slot identity (cap_arg_media_urn) for canonical form.
        bindings.sort(key=lambda b: str(b.cap_arg_media_urn))

        # Derive `is_loop` from cardinality — the single ForEach rule
        # (`Cap.needs_foreach`): the primary data input (the first stdin arg)
        # carries a sequence but this cap consumes it as a scalar, so it maps
        # per-item. The primary stdin source node is the binding feeding the
        # first stdin arg's slot. A cap with no stdin arg (config-only) never
        # loops.
        primary_stdin_source_is_sequence = False
        if stdin_arg_slot_urns:
            primary_slot = stdin_arg_slot_urns[0]
            for b in bindings:
                if b.cap_arg_media_urn.is_equivalent(primary_slot):
                    primary_stdin_source_is_sequence = node_is_sequence[b.source]
                    break
        is_loop = cap.needs_foreach(primary_stdin_source_is_sequence)

        indexed_edges.append(MachineEdge(
            cap_urn=wiring.cap_urn,
            assignment=bindings,
            target=wiring.target_node_id,
            is_loop=is_loop,
            token_id=wiring.token_id,
        ))

    # Cycle detection + canonical edge order.
    canonical_order = _topo_sort(indexed_edges, nodes, strand_index)
    edges = [indexed_edges[i] for i in canonical_order]

    # Anchor computation.
    produced_node_ids: set = set()
    consumed_node_ids: set = set()
    for e in edges:
        produced_node_ids.add(e.target)
        for b in e.assignment:
            consumed_node_ids.add(b.source)

    input_anchor_ids: List[NodeId] = [
        i for i in range(len(nodes))
        if i not in produced_node_ids and i in consumed_node_ids
    ]
    output_anchor_ids: List[NodeId] = [
        i for i in range(len(nodes))
        if i not in consumed_node_ids and i in produced_node_ids
    ]

    # Sort anchors by canonical (URN string, NodeId) for stable output.
    input_anchor_ids.sort(key=lambda i: (str(nodes[i]), i))
    output_anchor_ids.sort(key=lambda i: (str(nodes[i]), i))

    return MachineStrand(
        nodes=nodes,
        edges=edges,
        input_anchor_ids=input_anchor_ids,
        output_anchor_ids=output_anchor_ids,
    )


# =============================================================================
# Source-to-cap-arg matching
# =============================================================================

def match_sources_to_args(
    sources: List[MediaUrn],
    args: List[MediaUrn],
    cap_urn: str,
    strand_index: int,
) -> List[Tuple[MediaUrn, MediaUrn]]:
    """Match a wiring's source URNs to a cap's stdin arg URNs by minimum-cost bipartite matching.

    Returns matched pairs as (cap_arg_media_urn, source_urn), sorted by
    cap_arg_media_urn. Fails hard on:
    - Any source not conforming to any arg (UnmatchedSourceInCapArgsError).
    - More sources than args (pigeonhole — at least one is unmatched).
    - Multiple minimum-cost matchings (AmbiguousMachineNotationError).
    """
    n_sources = len(sources)
    n_args = len(args)

    if n_sources > n_args:
        # Pigeonhole: find first source with no candidate and report it.
        for source in sources:
            if not any(source.conforms_to(a) for a in args):
                raise UnmatchedSourceInCapArgsError(strand_index, cap_urn, str(source))
        # All sources have at least one candidate but count > slots.
        raise UnmatchedSourceInCapArgsError(strand_index, cap_urn, str(sources[0]))

    # Build cost matrix. cost[s][a] = distance if source[s] conforms to args[a], else None.
    cost: List[List[Optional[int]]] = [[None] * n_args for _ in range(n_sources)]
    for s_idx, source in enumerate(sources):
        for a_idx, arg in enumerate(args):
            if source.conforms_to(arg):
                distance = source.specificity() - arg.specificity()
                cost[s_idx][a_idx] = distance
        # Per-source: must have at least one candidate.
        if all(cost[s_idx][a] is None for a in range(n_args)):
            raise UnmatchedSourceInCapArgsError(strand_index, cap_urn, str(source))

    # Brute-force enumerate all injections of sources into args with defined cost.
    best_cost: List[Optional[int]] = [None]
    best_assignments: List[List[int]] = []
    current: List[int] = [0] * n_sources
    used: List[bool] = [False] * n_args

    _enumerate_matchings(cost, 0, current, used, best_cost, best_assignments)

    if best_cost[0] is None:
        # Hall's theorem violation: no valid injection exists.
        raise UnmatchedSourceInCapArgsError(strand_index, cap_urn, str(sources[0]))

    if len(best_assignments) != 1:
        raise AmbiguousMachineNotationError(strand_index, cap_urn)

    # Convert unique assignment into (cap_arg_urn, source_urn) pairs sorted by cap_arg_urn.
    assignment = best_assignments[0]
    pairs: List[Tuple[MediaUrn, MediaUrn]] = [
        (args[assignment[s_idx]], sources[s_idx])
        for s_idx in range(n_sources)
    ]
    pairs.sort(key=lambda p: str(p[0]))
    return pairs


def _enumerate_matchings(
    cost: List[List[Optional[int]]],
    s_idx: int,
    current: List[int],
    used: List[bool],
    best_cost: List[Optional[int]],
    best_assignments: List[List[int]],
) -> None:
    """Recursively enumerate all injections of sources into args with defined cost.

    Tracks the minimum total cost and all assignments achieving it.
    """
    n_sources = len(cost)
    if s_idx == n_sources:
        total = sum(cost[s][current[s]] for s in range(n_sources))  # type: ignore[misc]
        if best_cost[0] is None:
            best_cost[0] = total
            best_assignments.clear()
            best_assignments.append(list(current))
        elif total < best_cost[0]:
            best_cost[0] = total
            best_assignments.clear()
            best_assignments.append(list(current))
        elif total == best_cost[0]:
            best_assignments.append(list(current))
        return

    for a_idx in range(len(cost[s_idx])):
        if used[a_idx]:
            continue
        if cost[s_idx][a_idx] is None:
            continue
        used[a_idx] = True
        current[s_idx] = a_idx
        _enumerate_matchings(cost, s_idx + 1, current, used, best_cost, best_assignments)
        used[a_idx] = False


# =============================================================================
# Topological sort with structural tiebreaker
# =============================================================================

def _topo_sort(
    edges: List[MachineEdge],
    nodes: List[MediaUrn],
    strand_index: int,
) -> List[int]:
    """Kahn's algorithm over the resolved data-flow dependency graph.

    Edge B depends on edge A iff some binding in B.assignment has
    source == A.target (NodeId equality). Returns a canonical ordering of
    edge indices. Raises CyclicMachineStrandError if the graph has a cycle.
    """
    n = len(edges)
    if n == 0:
        return []

    # Map: NodeId → list of edge indices that produce this NodeId as target.
    producers_of: Dict[NodeId, List[int]] = {}
    for idx, e in enumerate(edges):
        producers_of.setdefault(e.target, []).append(idx)

    # Build indegree and successors.
    indegree = [0] * n
    successors: List[List[int]] = [[] for _ in range(n)]

    for b_idx, b in enumerate(edges):
        for binding in b.assignment:
            for a_idx in producers_of.get(binding.source, []):
                if a_idx == b_idx:
                    continue
                successors[a_idx].append(b_idx)
                indegree[b_idx] += 1

    result: List[int] = []
    ready: List[int] = [i for i in range(n) if indegree[i] == 0]
    _sort_ready(ready, edges, nodes)

    while ready:
        idx = ready.pop(0)
        result.append(idx)
        for succ in successors[idx]:
            indegree[succ] -= 1
            if indegree[succ] == 0:
                ready.append(succ)
                _sort_ready(ready, edges, nodes)

    if len(result) < n:
        raise CyclicMachineStrandError(strand_index)

    return result


def _sort_ready(
    ready: List[int],
    edges: List[MachineEdge],
    nodes: List[MediaUrn],
) -> None:
    """Sort the ready set in canonical structural order for deterministic Kahn output.

    Order:
    1. cap URN (string sort, mirrors Rust CapUrn::Ord)
    2. assignment vec element-wise (cap_arg_media_urn string, then source URN string)
    3. target node URN string
    4. is_loop flag
    """
    def key(i: int):
        e = edges[i]
        assignment_key = tuple(
            (str(b.cap_arg_media_urn), str(nodes[b.source]))
            for b in e.assignment
        )
        return (
            str(e.cap_urn),
            assignment_key,
            len(e.assignment),
            str(nodes[e.target]),
            e.is_loop,
        )

    ready.sort(key=key)
