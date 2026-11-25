"""LiveCapFab — Precomputed capability graph for path finding

This module provides a live, incrementally-updated graph of capabilities
for efficient path finding and reachability queries.

Design Principles:
1. Typed URNs: Store MediaUrn and CapUrn directly, not strings.
2. Exact matching: For target matching, use is_equivalent() not conforms_to().
   A node that may have several shapes (``…;fmt=json;?list;?record``) ends on
   the bookends its shapes are, read complete (``MediaUrn.ends_on``), and a
   route reaching it reaches each of them.
3. Satisfaction for traversal: a node, read complete, satisfies the next cap's
   input (satisfies()).
4. Deterministic ordering: paths sorted by cap step count (fewest first), then total specificity (highest first), then step order.
5. ForEach is synthesized dynamically in get_outgoing_edges() when is_sequence=True
   and there are scalar consumers; it is never pre-inserted as a real graph edge.
6. Collect is not synthesized — it pairs implicitly with ForEach at execution time.
"""

from __future__ import annotations

import functools
import threading
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Set, Tuple

from capdag.urn.cap_urn import CapUrn, CapUrnError, routes_in_order
from capdag.urn.media_urn import MediaUrn


class StepTokenError(ValueError):
    """The only way a :class:`StepToken` can fail to exist."""


class StepToken(str):
    """The stable identity of one step of a resolved strand — the ONLY address by
    which a step, or an argument value destined for it, is ever named.

    This is a distinct type rather than a bare ``str`` so that an unidentified
    step is not a state the program can be in. There is exactly one way to make a
    token (:meth:`mint`) and exactly one way to recover one that was already
    minted (:meth:`parse`, which refuses an empty id). Decoding a persisted
    strand goes through ``parse``, so a stored ``""`` fails to load rather than
    loading into a strand whose steps cannot be addressed.

    Nothing derives a token. Not from a position — a strand is a DAG, and
    parallel branches merging downstream have no ordinal, so two identical caps
    on separate branches differ only by token. Not from notation — a plan holds
    strictly more than the notation it was planned from, and reducing one back to
    the other discards exactly the identities this type exists to carry. A token
    comes from the plan that minted it or it does not exist.

    Subclassing ``str`` keeps a token usable everywhere the wire needs its text
    (dict keys, JSON, format strings) without a second representation to keep in
    step; the construction rules above are what make it a type rather than an
    alias.
    """

    __slots__ = ()

    def __new__(cls, raw: str) -> "StepToken":
        if not raw:
            raise StepTokenError(
                "a strand step token_id is empty; a step without a token came "
                "from no plan and cannot be addressed"
            )
        return super().__new__(cls, raw)

    @staticmethod
    def mint() -> "StepToken":
        """Mint a fresh identity. This is how every step in production is born."""
        return StepToken(str(uuid.uuid4()))

    @staticmethod
    def parse(raw: str) -> "StepToken":
        """Recover an already-minted token — from decoding, from a protocol
        message, from a persisted run. An empty id is not a token: it names no
        step, so a value bound to it could never be delivered."""
        return StepToken(raw)


class LiveMachinePlanEdgeType(Enum):
    """Type of edge in the capability graph."""
    CAP = "cap"
    FOR_EACH = "for_each"
    COLLECT = "collect"


class LiveMachinePlanEdge:
    """An edge in the live capability graph."""

    __slots__ = (
        "from_spec", "to_spec", "edge_type",
        "cap_urn", "cap_title", "specificity_val",
        "input_is_sequence", "output_is_sequence", "output_urn",
    )

    def __init__(
        self,
        from_spec: MediaUrn,
        to_spec: MediaUrn,
        edge_type: LiveMachinePlanEdgeType,
        cap_urn: Optional[CapUrn] = None,
        cap_title: str = "",
        specificity_val: int = 0,
        input_is_sequence: bool = False,
        output_is_sequence: bool = False,
        output_urn: Optional[MediaUrn] = None,
    ):
        self.from_spec = from_spec
        self.to_spec = to_spec
        self.edge_type = edge_type
        self.cap_urn = cap_urn
        self.cap_title = cap_title
        self.specificity_val = specificity_val
        self.input_is_sequence = input_is_sequence
        # Whether the output this edge reaches produces a sequence.
        self.output_is_sequence = output_is_sequence
        # The output this edge reaches, when it is not the cap's main one: that
        # output's media URN, its identity in the definition. None: the main
        # output.
        self.output_urn = output_urn

    def title(self) -> str:
        if self.edge_type == LiveMachinePlanEdgeType.CAP:
            return self.cap_title
        elif self.edge_type == LiveMachinePlanEdgeType.FOR_EACH:
            return "ForEach (iterate over list)"
        elif self.edge_type == LiveMachinePlanEdgeType.COLLECT:
            return "Collect (gather results)"
        return ""

    def specificity(self) -> int:
        if self.edge_type == LiveMachinePlanEdgeType.CAP:
            return self.specificity_val
        return 0

    def is_cap(self) -> bool:
        return self.edge_type == LiveMachinePlanEdgeType.CAP

    def get_cap_urn(self) -> Optional[CapUrn]:
        if self.edge_type == LiveMachinePlanEdgeType.CAP:
            return self.cap_urn
        return None


class ArgSourceRef:
    """The producer of one of a cap step's inputs.

    A `Strand` is a DAG of steps: an input is fed either by the strand's own
    input (an input anchor) or by another cap step's output. There are no
    positional assumptions — every input names its producer explicitly, so
    fan-out (one producer feeding several caps' main inputs) and convergence
    (one cap fed by several producers) are both expressible.
    """

    STRAND_INPUT = "strand_input"
    STEP = "step"

    __slots__ = ("kind", "token_id")

    def __init__(self, kind: str, token_id: Optional[str] = None):
        self.kind = kind
        self.token_id = token_id

    @staticmethod
    def strand_input() -> "ArgSourceRef":
        """Fed by the strand's input anchor — the strand's own input flows into this arg."""
        return ArgSourceRef(ArgSourceRef.STRAND_INPUT)

    @staticmethod
    def step(token_id: str) -> "ArgSourceRef":
        """Fed by another cap step's output, identified by that step's stable token."""
        return ArgSourceRef(ArgSourceRef.STEP, StepToken.parse(token_id))

    def is_strand_input(self) -> bool:
        return self.kind == ArgSourceRef.STRAND_INPUT

    def __eq__(self, other) -> bool:
        return (
            isinstance(other, ArgSourceRef)
            and self.kind == other.kind
            and self.token_id == other.token_id
        )

    def __hash__(self) -> int:
        return hash((self.kind, self.token_id))

    def __repr__(self) -> str:
        if self.kind == ArgSourceRef.STEP:
            return f"ArgSourceRef.Step({self.token_id!r})"
        return "ArgSourceRef.StrandInput"


@dataclass
class CapInput:
    """One input to a cap step: the cap argument it feeds (by the argument's
    slot media URN) and the producer of that input.

    A cap step lists ALL of its data-flow inputs — the primary (stdin/main)
    input and every convergence input — with no positional ordering
    assumptions. The PRIMARY input is the one whose `arg_urn` is the cap's
    stdin argument URN; it threads the step's `from_spec` runtime media. Arg
    URNs into one cap are all distinct, so `arg_urn` alone identifies the slot.
    """

    arg_urn: MediaUrn
    source: ArgSourceRef


class StrandStepType(Enum):
    """Type of step in a capability chain path."""
    CAP = "cap"
    FOR_EACH = "for_each"
    COLLECT = "collect"


class StrandStep:
    """Information about a single step in a capability chain path."""

    __slots__ = (
        "token_id", "step_type", "from_spec", "to_spec",
        "cap_urn", "step_title", "specificity_val",
        "media_def",
        "input_is_sequence", "output_is_sequence", "output_urn",
        "inputs",
    )

    def __init__(
        self,
        step_type: StrandStepType,
        from_spec: MediaUrn,
        to_spec: MediaUrn,
        cap_urn: Optional[CapUrn] = None,
        step_title: str = "",
        specificity_val: int = 0,
        media_def: Optional[MediaUrn] = None,
        input_is_sequence: bool = False,
        output_is_sequence: bool = False,
        inputs: Optional[List["CapInput"]] = None,
        token_id: Optional[str] = None,
        output_urn: Optional[MediaUrn] = None,
    ):
        # Stable per-step identity, minted once when the step is created (the
        # very source of a resolved strand) unless the caller preserves an
        # existing one (e.g. deserialization). It is the single key that ties
        # this element of the realized graph to every live update the run
        # emits for it, so a repeated cap URN in one strand is never
        # ambiguous.
        self.token_id = (
            StepToken.parse(token_id) if token_id is not None else StepToken.mint()
        )
        self.step_type = step_type
        self.from_spec = from_spec
        self.to_spec = to_spec
        self.cap_urn = cap_urn
        self.step_title = step_title
        self.specificity_val = specificity_val
        self.media_def = media_def
        self.input_is_sequence = input_is_sequence
        # Whether the output this step takes produces a sequence.
        self.output_is_sequence = output_is_sequence
        # The output this step takes, when it is not the cap's main one: that
        # output's media URN, its identity in the definition (never its name,
        # which is a label). None: the main output. Only meaningful for CAP
        # steps.
        self.output_urn = output_urn
        # ALL of this cap step's data-flow inputs — the primary (stdin) input
        # plus any convergence inputs — each naming its producer explicitly.
        # Only meaningful for CAP steps; None for ForEach/Collect.
        self.inputs = inputs

    def title(self) -> str:
        if self.step_type == StrandStepType.CAP:
            return self.step_title
        elif self.step_type == StrandStepType.FOR_EACH:
            return "ForEach"
        elif self.step_type == StrandStepType.COLLECT:
            return "Collect"
        return ""

    def specificity(self) -> int:
        if self.step_type == StrandStepType.CAP:
            return self.specificity_val
        return 0

    def get_cap_urn(self) -> Optional[CapUrn]:
        if self.step_type == StrandStepType.CAP:
            return self.cap_urn
        return None

    def is_cap(self) -> bool:
        return self.step_type == StrandStepType.CAP


class Strand:
    """Information about a complete capability chain path."""

    __slots__ = (
        "steps", "source_media_urn", "target_media_urn",
        "total_steps", "cap_step_count", "description",
    )

    def __init__(
        self,
        steps: List[StrandStep],
        source_media_urn: MediaUrn,
        target_media_urn: MediaUrn,
        total_steps: int,
        cap_step_count: int,
        description: str,
    ):
        self.steps = steps
        self.source_media_urn = source_media_urn
        self.target_media_urn = target_media_urn
        self.total_steps = total_steps
        self.cap_step_count = cap_step_count
        self.description = description

    def knit(self, registry) -> "Machine":
        """Convert this resolved path to a Machine via the cap registry.

        The registry is required for source-to-cap-arg assignment matching.
        Raises MachineAbstractionError on resolution failure.
        """
        from capdag.machine.graph import Machine
        return Machine.from_strand(self, registry)

    def to_machine_notation(self, registry) -> str:
        """Serialize to ALIASED one-line machine notation — the "store aliased"
        form used for path generation and persistence.

        Each cap is rendered by its registered display alias (shortest name,
        ties alphabetical) when one exists, referenced directly in the wiring
        with no header; un-aliased caps keep their synthetic ``edge_N`` token +
        ``[edge_N cap:...]`` header. The canonical alias-independent identity
        still comes from the no-arg ``Machine.to_machine_notation``.

        The registry is required both for source-to-cap-arg assignment matching
        and for reverse-resolving URNs to aliases.
        """
        return self.knit(registry).to_machine_notation_aliased(registry, "bracketed")


class ReachableTargetInfo:
    """Information about a reachable target from a source media type."""

    __slots__ = ("media_def", "display_name", "min_path_length", "path_count")

    def __init__(
        self,
        media_def: MediaUrn,
        display_name: str,
        min_path_length: int,
        path_count: int,
    ):
        self.media_def = media_def
        self.display_name = display_name
        self.min_path_length = min_path_length
        self.path_count = path_count


# ---------------------------------------------------------------------------
# PathFindingEvent hierarchy
# ---------------------------------------------------------------------------

@dataclass
class PathFindingEventDepthComplete:
    """Emitted when one IDDFS depth pass is complete."""
    depth: int
    max_depth: int
    nodes_explored: int
    paths_found: int


@dataclass
class PathFindingEventPathFound:
    """Emitted when a path is found."""
    path: Strand


@dataclass
class PathFindingEventComplete:
    """Emitted when path finding is fully done."""
    total_paths: int
    total_nodes_explored: int


PathFindingEvent = (
    PathFindingEventDepthComplete
    | PathFindingEventPathFound
    | PathFindingEventComplete
)


_STEP_RANK = {
    StrandStepType.CAP: 0,
    StrandStepType.FOR_EACH: 1,
    StrandStepType.COLLECT: 2,
}


def _cmp(a, b) -> int:
    return (a > b) - (a < b)


def _optional_media_key(media: Optional[MediaUrn]) -> tuple:
    """The main output (None) before any named one, as the reference orders
    an absent output URN."""
    return (0,) if media is None else (1, media.ordering_key())


def _compare_steps(a: StrandStep, b: StrandStep) -> int:
    """Structural order of two strand steps: a cap before a ForEach before a
    Collect; caps by their cap URNs' structural order and then the output
    they take; ForEach and Collect by their media definition; then each
    step's from_spec and to_spec by the media URN's structural order."""
    rank = _cmp(_STEP_RANK[a.step_type], _STEP_RANK[b.step_type])
    if rank != 0:
        return rank
    if a.step_type == StrandStepType.CAP:
        detail = _cmp(a.cap_urn.ordering_key(), b.cap_urn.ordering_key()) or _cmp(
            _optional_media_key(a.output_urn), _optional_media_key(b.output_urn)
        )
    else:
        detail = _cmp(a.media_def.ordering_key(), b.media_def.ordering_key())
    if detail != 0:
        return detail
    return _cmp(a.from_spec.ordering_key(), b.from_spec.ordering_key()) or _cmp(
        a.to_spec.ordering_key(), b.to_spec.ordering_key()
    )


def _compare_paths(a: Strand, b: Strand) -> int:
    """Path order: fewest cap steps first (ForEach and Collect do not count),
    then the highest sum of step specificities, then the steps compared
    structurally in turn, the shorter path first when one is a prefix of the
    other. No URN is compared as text."""
    by_count = _cmp(a.cap_step_count, b.cap_step_count)
    if by_count != 0:
        return by_count
    by_specificity = _cmp(
        sum(s.specificity() for s in b.steps), sum(s.specificity() for s in a.steps)
    )
    if by_specificity != 0:
        return by_specificity
    for step_a, step_b in zip(a.steps, b.steps):
        by_step = _compare_steps(step_a, step_b)
        if by_step != 0:
            return by_step
    return _cmp(len(a.steps), len(b.steps))


def _in_route_order(target: MediaUrn, routes: List[Strand]) -> List[Strand]:
    """The routes to ``target`` in the proved model's order
    (``routes_in_order``): the nearest to what was asked first, measured as
    dispatch ranks caps, then fewer cap steps, then the higher total
    specificity. Routes equal in all three keep ``_compare_paths``'
    structural order, which they are handed to the model in."""
    routes = sorted(routes, key=functools.cmp_to_key(_compare_paths))
    order = routes_in_order(
        target,
        [([step.cap_urn for step in route.steps if step.is_cap()], route.target_media_urn) for route in routes],
    )
    return [routes[index] for index in order]


class LiveCapFab:
    """Precomputed graph of capabilities for path finding.

    Only Cap edges are stored in the graph.  ForEach edges are synthesized
    dynamically in _get_outgoing_edges() when is_sequence=True and there are
    scalar consumers reachable from the source node.
    """

    def __init__(self):
        self._edges: List[LiveMachinePlanEdge] = []
        self._outgoing: Dict[str, List[int]] = defaultdict(list)
        self._incoming: Dict[str, List[int]] = defaultdict(list)
        self._nodes: Set[MediaUrn] = set()
        self._cap_to_edges: Dict[str, List[int]] = defaultdict(list)
        # The nodes that end on bookends (sources or targets of a transmute),
        # each with the bookends it ends on: one for each shape the node may
        # have, the published file type that shape is read complete
        # (MediaUrn.ends_on). A node of one shape that is a file type ends on
        # that file type; a node any of whose shapes is no file type ends on
        # none and is not listed. Computed at sync time from the registry
        # snapshot supplied to sync_from_caps / sync_from_cap_urns.
        self._bookend_nodes: Dict[MediaUrn, List[MediaUrn]] = {}

    def clear(self):
        """Clear the graph completely."""
        self._edges.clear()
        self._outgoing.clear()
        self._incoming.clear()
        self._nodes.clear()
        self._cap_to_edges.clear()
        self._bookend_nodes.clear()

    def is_bookend(self, urn: MediaUrn) -> bool:
        """Whether the given node ends on bookends: every shape it may have is
        a file type, so whatever a route reaching it gives can sit on disk as
        a file.

        Strand bookends (transmute source or target) MUST end on bookends.
        Internal URNs that appear as cap inputs/outputs but do not name a
        concrete file format (wildcards like ``media:enc=utf8``, primitives
        like ``media:integer;numeric``, role markers like
        ``media:enc=utf8;page``) are tracked as nodes for path-finding but end
        on no bookend and never appear as transmute sources/targets.
        """
        return urn in self._bookend_nodes

    def ends_on(self, node: MediaUrn) -> List[MediaUrn]:
        """The bookends ``node`` ends on, one for each shape it may have;
        empty when it ends on none."""
        return list(self._bookend_nodes.get(node, []))

    @staticmethod
    def _reaches(node: MediaUrn, target: MediaUrn) -> bool:
        """Whether a route reaching ``node`` reaches ``target``: what the node
        holds, read complete, is inside the target, read open. A node that may
        also be something outside the target (``…;?list;?record`` for a JSON
        record target) does not reach it: a possibility is no guarantee."""
        return node.satisfies(target)

    def sync_from_caps(self, caps, bookend_urns: Set[MediaUrn]) -> None:
        """Rebuild the graph from a list of Cap definitions.

        ``bookend_urns`` is the live snapshot of media-registry URNs whose
        stored definition has at least one file extension. Each node in the
        graph is marked with the bookends among them it ends on, once per
        sync; lookups during traversal make no registry call.
        """
        self.clear()
        for cap in caps:
            self.add_cap(cap)
        self._refresh_bookends(bookend_urns)

    def set_bookends(self, bookend_urns: Set[MediaUrn]) -> None:
        """Recompute which nodes end on bookends, and on which, from the
        supplied registry snapshot. Public so callers that build the graph
        incrementally via ``add_cap`` (e.g. tests) can refresh the bookend set
        independently of a full sync."""
        self._refresh_bookends(bookend_urns)

    def _refresh_bookends(self, bookend_urns: Set[MediaUrn]) -> None:
        """Recompute which nodes end on bookends, and on which, from the
        supplied registry snapshot."""
        bookends = sorted(bookend_urns, key=MediaUrn.ordering_key)
        self._bookend_nodes = self._nodes_ending_on(self._nodes, bookends)

    @staticmethod
    def _nodes_ending_on(
        nodes: Set[MediaUrn], bookends: List[MediaUrn]
    ) -> Dict[MediaUrn, List[MediaUrn]]:
        """Each of ``nodes`` that ends on ``bookends``, with the bookends it
        ends on, each named once."""
        ending: Dict[MediaUrn, List[MediaUrn]] = {}
        for node in nodes:
            ends = node.ends_on(bookends)
            if ends is None:
                continue
            ending[node] = sorted(set(ends), key=MediaUrn.ordering_key)
        return ending

    async def sync_from_cap_urns(
        self, cap_urns: List[str], registry, bookend_urns: Set[MediaUrn]
    ) -> None:
        """Rebuild the graph from cap URN strings using the registry cache,
        each node marked with the bookends among ``bookend_urns`` it ends on
        (as :meth:`sync_from_caps`)."""
        self.clear()

        all_caps = await registry.get_cached_caps()

        from capdag.standard.caps import identity_urn

        for cap_urn_str in cap_urns:
            cap_urn = CapUrn.from_string(cap_urn_str)

            if cap_urn.is_equivalent(identity_urn()):
                continue

            matching_cap = next(
                (registry_cap for registry_cap in all_caps if cap_urn.is_equivalent(registry_cap.urn)),
                None,
            )
            if matching_cap is not None:
                self.add_cap(matching_cap)

        self._refresh_bookends(bookend_urns)

    @classmethod
    async def from_fabric(cls, registry) -> "LiveCapFab":
        """The graph of the whole fabric: every cap the registry's pinned
        manifest names (``FabricRegistry.manifest_caps``), each node marked
        with the bookends it ends on: for each shape it may have, the media
        definition the manifest publishes for that shape, read complete, when
        that definition is a bookend (``StoredMediaDef.is_bookend``).

        Nothing comes from what the cache happens to hold: the caps not cached
        are fetched, and so is every definition a node's shape is. A cap or a
        definition that cannot be had raises the registry's error naming it,
        never a graph with a part of the fabric missing.
        """
        caps = await registry.manifest_caps()
        fab = cls()
        for cap in caps:
            fab.add_cap(cap)
        # `media:` takes anything and names no definition: nothing is a file
        # of it.
        published = sorted(
            (urn for urn in registry.manifest_media_urns() if not urn.is_top()),
            key=MediaUrn.ordering_key,
        )
        is_bookend: Dict[MediaUrn, bool] = {}
        for node, shapes in cls._nodes_ending_on(fab._nodes, published).items():
            ends_on_bookends = True
            for shape in shapes:
                known = is_bookend.get(shape)
                if known is None:
                    known = (await registry.get_media_def(str(shape))).is_bookend()
                    is_bookend[shape] = known
                ends_on_bookends &= known
            if ends_on_bookends:
                fab._bookend_nodes[node] = shapes
        return fab

    def add_cap(self, cap) -> None:
        """Add a capability as an edge in the graph."""
        from capdag.standard.caps import identity_urn

        in_spec_str = cap.urn.in_spec()
        out_spec_str = cap.urn.out_spec()

        if not in_spec_str or not out_spec_str:
            return

        # Skip identity caps
        if cap.urn.is_equivalent(identity_urn()):
            return

        try:
            from_spec = MediaUrn.from_string(in_spec_str)
        except Exception:
            return

        try:
            to_spec = MediaUrn.from_string(out_spec_str)
        except Exception:
            return

        # A sink (`out=media:void`) produces nothing, so a path cannot go on
        # through it: it has no main output, and declares no other. Every type
        # conforms to `media:`, so an edge to `media:void` would let a path
        # continue from a value that never exists into any cap that takes
        # anything.
        if to_spec.is_void():
            return

        input_is_sequence, output_is_sequence = cap.sequence_shape()
        self._push_cap_edge(cap, from_spec, to_spec, input_is_sequence, output_is_sequence, None)

        # Every other output the cap declares is reachable too: an edge from
        # the cap's input to that output's own type. An output that carries the
        # input unchanged (a router's) has no type of its own to reach.
        main = cap.main_output()
        for output in cap.get_outputs():
            if output.carries is not None:
                continue
            if main is not None and main.media_urn == output.media_urn:
                continue
            output_urn = MediaUrn.from_string(output.media_urn)
            self._push_cap_edge(
                cap, from_spec, output_urn, input_is_sequence, output.is_sequence, output_urn
            )

    def _push_cap_edge(
        self,
        cap,
        from_spec: MediaUrn,
        to_spec: MediaUrn,
        input_is_sequence: bool,
        output_is_sequence: bool,
        output_urn: Optional[MediaUrn],
    ) -> None:
        """Store one edge of `cap`, from its input to one of its outputs."""
        from_canonical = str(from_spec)
        to_canonical = str(to_spec)
        cap_canonical = str(cap.urn)

        edge_idx = len(self._edges)
        self._edges.append(
            LiveMachinePlanEdge(
                from_spec=from_spec,
                to_spec=to_spec,
                edge_type=LiveMachinePlanEdgeType.CAP,
                cap_urn=cap.urn,
                cap_title=cap.title,
                specificity_val=cap.urn.specificity(),
                input_is_sequence=input_is_sequence,
                output_is_sequence=output_is_sequence,
                output_urn=output_urn,
            )
        )

        self._outgoing[from_canonical].append(edge_idx)
        self._incoming[to_canonical].append(edge_idx)
        self._nodes.add(from_spec)
        self._nodes.add(to_spec)
        self._cap_to_edges[cap_canonical].append(edge_idx)

    def stats(self) -> Tuple[int, int]:
        """Return (node_count, edge_count)."""
        return len(self._nodes), len(self._edges)

    def _get_outgoing_edges(
        self,
        source: MediaUrn,
        is_sequence: bool,
    ) -> List[Tuple[LiveMachinePlanEdge, bool]]:
        """Get all edges reachable from source given is_sequence context.

        Returns a list of (edge, out_is_sequence) pairs.

        For Cap edges:
          - If is_sequence and not edge.input_is_sequence: skip (needs ForEach first).
          - Otherwise: include with out_is_sequence = edge.output_is_sequence.

        Synthesizes a ForEach edge when is_sequence=True and there is at least
        one Cap edge with not input_is_sequence whose from_spec source satisfies.

        A source is what a step gave or a file's detected type, a complete
        thing: what it does not mention it does not have, so it takes an edge
        whose input it satisfies.
        """
        results: List[Tuple[LiveMachinePlanEdge, bool]] = []
        needs_foreach = False

        for edge in self._edges:
            if edge.edge_type != LiveMachinePlanEdgeType.CAP:
                continue
            if not source.satisfies(edge.from_spec):
                continue
            if is_sequence and not edge.input_is_sequence:
                # Sequence data reaching a scalar cap — ForEach must be synthesized.
                needs_foreach = True
                continue
            # The main output's runtime type follows the cap URN's effect: what
            # the cap gives for what it is sent (an effect=patch cap keeps what
            # it does not change). Any other output gives its own type.
            taken = edge
            if edge.output_urn is None:
                try:
                    given = edge.cap_urn.infer_runtime_output_media(source)
                except CapUrnError:
                    continue
                taken = LiveMachinePlanEdge(
                    from_spec=source,
                    to_spec=given,
                    edge_type=edge.edge_type,
                    cap_urn=edge.cap_urn,
                    cap_title=edge.cap_title,
                    specificity_val=edge.specificity_val,
                    input_is_sequence=edge.input_is_sequence,
                    output_is_sequence=edge.output_is_sequence,
                )
            results.append((taken, taken.output_is_sequence))

        # Synthesize a ForEach edge so path finding can iterate into scalar caps.
        if is_sequence and needs_foreach:
            synthetic = LiveMachinePlanEdge(
                from_spec=source,
                to_spec=source,
                edge_type=LiveMachinePlanEdgeType.FOR_EACH,
            )
            results.append((synthetic, False))

        return results

    def get_reachable_targets(
        self,
        source: MediaUrn,
        is_sequence: bool,
        max_depth: int = 10,
    ) -> List[ReachableTargetInfo]:
        """BFS reachability from source. Returns the bookends the reached
        nodes end on, one target each, sorted by (min_path_length,
        display_name)."""
        # The third key member tracks whether a synthesized ForEach still needs
        # its immediately following scalar-input cap.
        visited_nodes: Set[Tuple[str, bool, bool]] = set()
        # visited maps canonical string → ReachableTargetInfo for deduplication.
        visited: Dict[str, ReachableTargetInfo] = {}
        queue: deque = deque()

        # Seed with outgoing edges from source
        for edge, out_seq in self._get_outgoing_edges(source, is_sequence):
            queue.append((
                edge.to_spec,
                out_seq,
                edge.edge_type == LiveMachinePlanEdgeType.FOR_EACH,
                1,
            ))

        while queue:
            current_urn, cur_is_seq, pending_foreach, depth = queue.popleft()
            if depth > max_depth:
                continue

            node_key = (str(current_urn), cur_is_seq, pending_foreach)
            if node_key in visited_nodes:
                if not pending_foreach:
                    current_key = str(current_urn)
                    if current_key in visited:
                        info = visited[current_key]
                        info.path_count += 1
                        if depth < info.min_path_length:
                            info.min_path_length = depth
                continue
            visited_nodes.add(node_key)

            if not pending_foreach:
                current_key = str(current_urn)
                if current_key in visited:
                    info = visited[current_key]
                    info.path_count += 1
                    if depth < info.min_path_length:
                        info.min_path_length = depth
                else:
                    visited[current_key] = ReachableTargetInfo(
                        media_def=current_urn,
                        display_name=current_key,
                        min_path_length=depth,
                        path_count=1,
                    )

            for edge, out_seq in self._get_outgoing_edges(current_urn, cur_is_seq):
                if pending_foreach and not self._can_follow_foreach(edge):
                    continue
                queue.append((
                    edge.to_spec,
                    out_seq,
                    edge.edge_type == LiveMachinePlanEdgeType.FOR_EACH,
                    depth + 1,
                ))

        # The targets are the bookends the reached nodes end on. Reachability
        # in the cap graph includes URNs that exist only as cap-input
        # wildcards (e.g. `media:enc=utf8`, `media:integer;numeric`). Such
        # URNs describe the value type a cap accepts, not a file format that
        # can sit on disk, so they are never valid transmute targets. A node
        # that may have several shapes reaches each bookend it ends on, one
        # target each. The bookends are precomputed at sync time from the
        # live media registry — no registry call here.
        by_bookend: Dict[MediaUrn, ReachableTargetInfo] = {}
        for reached in visited.values():
            for bookend in self.ends_on(reached.media_def):
                target = by_bookend.get(bookend)
                if target is None:
                    by_bookend[bookend] = ReachableTargetInfo(
                        media_def=bookend,
                        display_name=str(bookend),
                        min_path_length=reached.min_path_length,
                        path_count=reached.path_count,
                    )
                else:
                    target.min_path_length = min(target.min_path_length, reached.min_path_length)
                    target.path_count += reached.path_count

        # Sort: min_path_length ascending, then display_name
        results = sorted(
            by_bookend.values(),
            key=lambda r: (r.min_path_length, r.display_name),
        )
        return results

    def _distances_to_exact_target(
        self,
        source: MediaUrn,
        target: MediaUrn,
        is_sequence: bool,
        max_depth: int,
    ) -> Optional[Dict[Tuple[str, bool, bool], int]]:
        """How few steps each search state reachable from the source is from
        the target, for the states the target is reachable from within
        ``max_depth`` of the source; None when no step reaches the target at
        all.

        A state is ``(media, is_sequence, pending_foreach)``, as the path
        search walks it. The states are found forward from the source over the
        edges ``_get_outgoing_edges`` gives, and the distances backward over
        those same steps from the states that reach the target (``_reaches``:
        media inside it). A state
        missing from the map cannot reach the target; one at distance d cannot
        reach it in fewer than d steps.
        """
        start = (str(source), is_sequence, False)
        steps_into: Dict[Tuple[str, bool, bool], List[Tuple[str, bool, bool]]] = defaultdict(list)
        target_states: Set[Tuple[str, bool, bool]] = set()
        seen = {start}
        queue = deque([(source, is_sequence, False, 0)])
        while queue:
            current, current_is_seq, pending_foreach, depth = queue.popleft()
            if depth >= max_depth:
                continue
            from_state = (str(current), current_is_seq, pending_foreach)
            for edge, out_seq in self._get_outgoing_edges(current, current_is_seq):
                if pending_foreach and not self._can_follow_foreach(edge):
                    continue
                next_pending = edge.edge_type == LiveMachinePlanEdgeType.FOR_EACH
                next_state = (str(edge.to_spec), out_seq, next_pending)
                steps_into[next_state].append(from_state)
                # The target: a media inside it, reached by a step, not
                # waiting on a ForEach's cap.
                if not next_pending and self._reaches(edge.to_spec, target):
                    target_states.add(next_state)
                if next_state not in seen:
                    seen.add(next_state)
                    queue.append((edge.to_spec, out_seq, next_pending, depth + 1))
        if not target_states:
            return None
        distances = {state: 0 for state in target_states}
        backward = deque(target_states)
        while backward:
            state = backward.popleft()
            for before in steps_into.get(state, []):
                if before not in distances:
                    distances[before] = distances[state] + 1
                    backward.append(before)
        return distances

    def find_paths_to_exact_target(
        self,
        source: MediaUrn,
        target: MediaUrn,
        is_sequence: bool,
        max_depth: int = 10,
        max_paths: int = 20,
    ) -> List[Strand]:
        """Iterative deepening DFS to the routes to ``target``, read open: a
        route ends where its node, read complete, is inside the target
        (``_reaches``), and names what it gives as its ``target_media_urn``.
        It steps only into states the target is within reach of, and returns
        the routes in ``_in_route_order``."""
        distances = self._distances_to_exact_target(source, target, is_sequence, max_depth)
        if distances is None:
            return []
        results: List[Strand] = []

        for depth_limit in range(1, max_depth + 1):
            if len(results) >= max_paths:
                break
            visited: Set[Tuple[str, bool]] = set()
            self._iddfs_find(
                original_source=source,
                current=source,
                target=target,
                is_sequence=is_sequence,
                distances=distances,
                path=[],
                visited=visited,
                depth_limit=depth_limit,
                max_paths=max_paths,
                results=results,
            )

        return _in_route_order(target, results)

    def find_paths_streaming(
        self,
        source: MediaUrn,
        target: MediaUrn,
        is_sequence: bool,
        max_depth: int,
        max_paths: int,
        cancelled: Optional[threading.Event],
        on_event: Callable[[PathFindingEvent], None],
    ) -> List[Strand]:
        """Iterative deepening DFS that streams events to on_event.

        cancelled: a threading.Event that, if set, will stop the search.
        on_event: called with PathFindingEventDepthComplete after each depth,
                  PathFindingEventPathFound for each found path (after sort),
                  and PathFindingEventComplete at the end.
        """
        distances = self._distances_to_exact_target(source, target, is_sequence, max_depth)
        if distances is None:
            return []
        results: List[Strand] = []
        total_nodes_explored = 0

        for depth_limit in range(1, max_depth + 1):
            if len(results) >= max_paths:
                break
            if cancelled is not None and cancelled.is_set():
                break

            visited: Set[Tuple[str, bool]] = set()
            paths_before = len(results)

            self._iddfs_find(
                original_source=source,
                current=source,
                target=target,
                is_sequence=is_sequence,
                distances=distances,
                path=[],
                visited=visited,
                depth_limit=depth_limit,
                max_paths=max_paths,
                results=results,
            )

            nodes_this_depth = len(visited)
            total_nodes_explored += nodes_this_depth
            paths_this_depth = len(results) - paths_before

            on_event(PathFindingEventDepthComplete(
                depth=depth_limit,
                max_depth=max_depth,
                nodes_explored=nodes_this_depth,
                paths_found=paths_this_depth,
            ))

        results = _in_route_order(target, results)

        on_event(PathFindingEventComplete(
            total_paths=len(results),
            total_nodes_explored=total_nodes_explored,
        ))

        for p in results:
            on_event(PathFindingEventPathFound(path=p))

        return results

    def _iddfs_find(
        self,
        original_source: MediaUrn,
        current: MediaUrn,
        target: MediaUrn,
        is_sequence: bool,
        distances: Dict[Tuple[str, bool, bool], int],
        path: List[LiveMachinePlanEdge],
        visited: Set[Tuple[str, bool]],
        depth_limit: int,
        max_paths: int,
        results: List[Strand],
    ) -> None:
        """Depth-limited DFS from current toward target.

        ``distances`` is ``_distances_to_exact_target``'s: a step into a state
        the target is not within the steps left of is not taken, since no
        route through it ends at the target within the depth limit.
        """
        if len(results) >= max_paths:
            return

        pending_foreach = bool(
            path and path[-1].edge_type == LiveMachinePlanEdgeType.FOR_EACH
        )

        # The node reaches the target: it is inside it.
        if path and self._reaches(current, target):
            steps = []
            cap_count = 0
            # A fabricated cap's single input is its MAIN (stdin) input, fed by the
            # previous cap step in the path being built, or by the strand input when
            # this is the first cap. Path finding routes solely on main input→output
            # (one main input, one output); non-main args are never routed by the
            # planner, so a fabricated step has exactly one input by construction.
            prev_cap_token: Optional[str] = None
            for edge in path:
                step = self._edge_to_step(edge, prev_cap_token)
                steps.append(step)
                if step.is_cap():
                    cap_count += 1
                    prev_cap_token = step.token_id

            if depth_limit == 0:
                if cap_count > 0 and not pending_foreach:
                    desc = " → ".join(step.title() for step in steps)
                    results.append(Strand(
                        steps=steps,
                        source_media_urn=original_source,
                        # What the route gives, inside the target asked for.
                        target_media_urn=current,
                        total_steps=len(steps),
                        cap_step_count=cap_count,
                        description=desc,
                    ))
                return

            if cap_count > 0 and not pending_foreach:
                return

        if depth_limit == 0:
            return

        vk = (str(current), is_sequence)
        if vk in visited:
            return
        visited.add(vk)

        try:
            for edge, out_seq in self._get_outgoing_edges(current, is_sequence):
                if len(results) >= max_paths:
                    return
                if pending_foreach and not self._can_follow_foreach(edge):
                    continue
                next_state = (
                    str(edge.to_spec),
                    out_seq,
                    edge.edge_type == LiveMachinePlanEdgeType.FOR_EACH,
                )
                distance = distances.get(next_state)
                if distance is None or distance > depth_limit - 1:
                    continue
                next_key = (str(edge.to_spec), out_seq)
                if next_key in visited and not self._reaches(edge.to_spec, target):
                    continue
                path.append(edge)
                self._iddfs_find(
                    original_source=original_source,
                    current=edge.to_spec,
                    target=target,
                    is_sequence=out_seq,
                    distances=distances,
                    path=path,
                    visited=visited,
                    depth_limit=depth_limit - 1,
                    max_paths=max_paths,
                    results=results,
                )
                path.pop()
        finally:
            visited.discard(vk)

    @staticmethod
    def _can_follow_foreach(edge: LiveMachinePlanEdge) -> bool:
        return (
            edge.edge_type == LiveMachinePlanEdgeType.CAP
            and not edge.input_is_sequence
        )

    def _edge_to_step(
        self,
        edge: LiveMachinePlanEdge,
        prev_cap_token: Optional[str] = None,
    ) -> StrandStep:
        """Convert a LiveMachinePlanEdge to a StrandStep.

        `prev_cap_token` is the `token_id` of the most recently emitted CAP
        step in the path being built (skipping over ForEach/Collect), or
        `None` if this is the first cap. It becomes this step's single main
        input's producer.
        """
        if edge.edge_type == LiveMachinePlanEdgeType.CAP:
            in_spec_urn = MediaUrn.from_string(edge.cap_urn.in_spec())
            source = (
                ArgSourceRef.step(prev_cap_token)
                if prev_cap_token is not None
                else ArgSourceRef.strand_input()
            )
            return StrandStep(
                step_type=StrandStepType.CAP,
                from_spec=edge.from_spec,
                to_spec=edge.to_spec,
                cap_urn=edge.cap_urn,
                step_title=edge.cap_title,
                specificity_val=edge.specificity_val,
                input_is_sequence=edge.input_is_sequence,
                output_is_sequence=edge.output_is_sequence,
                output_urn=edge.output_urn,
                inputs=[CapInput(arg_urn=in_spec_urn, source=source)],
            )
        elif edge.edge_type == LiveMachinePlanEdgeType.FOR_EACH:
            return StrandStep(
                step_type=StrandStepType.FOR_EACH,
                from_spec=edge.from_spec,
                to_spec=edge.to_spec,
                media_def=edge.from_spec,
            )
        elif edge.edge_type == LiveMachinePlanEdgeType.COLLECT:
            return StrandStep(
                step_type=StrandStepType.COLLECT,
                from_spec=edge.from_spec,
                to_spec=edge.to_spec,
                media_def=edge.from_spec,
            )
        raise ValueError(f"Unknown edge type: {edge.edge_type}")
