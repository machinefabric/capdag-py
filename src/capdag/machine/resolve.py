"""Anchor realization for MachineStrands.

Turns either a planner-produced Strand or a parser-produced wiring set into a
fully resolved MachineStrand: a connected sub-graph whose every edge has an
explicit source-to-cap-arg assignment and names the outputs it takes,
anchored by the input root URNs and output leaf URNs of the strand.

Binding a wiring's members
--------------------------

Members that name an arg bind first, each to the arg of that name; the source
must conform to what that arg ACCEPTS. A name written more than once gathers,
and only a sequence arg may be gathered into. A constant is held to the
validation of the arg's media definition.

The members that name no arg are matched by type over the args no name
bound, by minimum-cost assignment in two phases of strict precedence:

- Cost of pairing source s with arg a: spec(s) - spec(a) if s conforms to
  what a accepts — how much more the source says than the arg asks;
  otherwise the pair is impossible.
- Phase 1 — product: each source claims a distinct arg. Whenever such an
  assignment exists, this phase decides.
- Phase 2 — gather: only when no such assignment exists, a sequence arg may
  absorb several conforming sources (scalar args still take at most one).
- The minimum-cost assignment of the deciding phase must be unique: a tie is
  ``AmbiguousMachineNotationError``. Where a member stands in its group is
  never a tiebreaker (it only fixes the item order within one gathered arg).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from capdag.machine.constant import constant_text
from capdag.machine.error import (
    AmbiguousMachineNotationError,
    ArgBoundTwiceError,
    CapDoesNotDeclareInputError,
    ConstantFailsValidationError,
    CyclicMachineStrandError,
    DisconnectedStrandError,
    MainInputUnboundError,
    NoCapabilityStepsError,
    NoMainOutputError,
    OutputTakenTwiceError,
    RuntimeMediaInferenceError,
    SourceDoesNotConformToArgError,
    UndecidedMember,
    UnknownArgNameError,
    UnknownCapError,
    UnknownOutputNameError,
    UnknownStrandOutputError,
    UnmatchedSourceInCapArgsError,
)
from capdag.machine.graph import (
    BindingSource,
    EdgeAssignmentBinding,
    EdgeOutput,
    MachineEdge,
    MachineStrand,
    NodeId,
)
from capdag.machine.iteration import (
    CyclicSteps,
    MemberShape,
    OutputShape,
    StepShape,
    iteration_of,
)
from capdag.planner.policy import StepPolicy
from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MEDIA_VOID, MediaUrn

if TYPE_CHECKING:
    from capdag.cap.registry import FabricRegistry
    from capdag.planner.live_cap_fab import StepToken, Strand


@dataclass
class WiringTarget:
    """An output taken: the output's NAME in the cap definition (without a
    name, the main output) and the node it goes to."""

    node: NodeId
    name: Optional[str] = None


@dataclass
class PreInternedWiring:
    """One wiring after the caller has pre-interned its source and target
    slots into NodeIds against a parallel nodes list.

    The resolver does no URN-based interning of its own: two distinct NodeIds
    whose URNs are equivalent stay distinct, which is what lets the notation
    parser honor the identity of node names.
    """

    #: The originating step's stable identity, carried onto the resulting
    #: MachineEdge (see ``MachineEdge.token_id``).
    token_id: "StepToken"
    cap_urn: CapUrn
    #: Members that say which arg they are for, by the arg's NAME in the cap
    #: definition. They bind first, in the order written.
    named_sources: List[Tuple[str, BindingSource]] = field(default_factory=list)
    #: Members that name no arg. Position carries no semantics — the matching
    #: assigns each to a cap arg no named member bound.
    source_node_ids: List[NodeId] = field(default_factory=list)
    #: The outputs taken. Empty: a sink.
    targets: List[WiringTarget] = field(default_factory=list)
    #: What the step does when it fails.
    policy: StepPolicy = StepPolicy()
    #: The machine steps this step was included through, outermost first;
    #: empty for a step the machine wrote itself.
    included_as: List[str] = field(default_factory=list)


def resolve_strand(
    strand: "Strand",
    registry: "FabricRegistry",
    strand_index: int,
) -> MachineStrand:
    """Convert a planner-produced Strand into a single MachineStrand.

    Every cap step names each of its inputs' producers explicitly (the
    strand's input, or another step's token) — there is no positional
    predecessor assumption, so fan-out and convergence both wire correctly.
    ForEach and Collect steps are elided here; ``is_loop`` is derived from
    cardinality in ``resolve_pre_interned``.

    Raises MachineAbstractionError on resolution failure.
    """
    from capdag.planner.live_cap_fab import StrandStepType

    nodes: List[MediaUrn] = []
    pre_interned: List[PreInternedWiring] = []

    # Producer of each node, by the producing step's stable token → its
    # output NodeId.
    producer_node: Dict[str, NodeId] = {}
    # The single shared strand input anchor node, allocated on first
    # reference and refined to the most specific consuming from_spec.
    strand_input_node: Optional[NodeId] = None

    for step in strand.steps:
        if step.step_type != StrandStepType.CAP:
            # Cardinality transitions are elided — caps name their producers
            # directly, and is_loop is derived from cardinality in
            # resolve_pre_interned, so these steps carry no wiring here.
            continue
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

        # A strand step produces the output it takes: its cap's main output,
        # or the other output its URN identifies.
        target = WiringTarget(node=target_id)
        if step.output_urn is not None:
            target.name = _strand_output_name(registry, step.cap_urn, step.output_urn, strand_index)
        pre_interned.append(
            PreInternedWiring(
                token_id=step.token_id,
                cap_urn=step.cap_urn,
                source_node_ids=source_node_ids,
                targets=[target],
            )
        )
        producer_node[step.token_id] = target_id

    if not pre_interned:
        raise NoCapabilityStepsError()

    return resolve_pre_interned(nodes, pre_interned, registry, strand_index)


def _strand_output_name(registry, cap_urn: CapUrn, output_urn: MediaUrn, strand_index: int) -> str:
    """The name a strand step's taken output has in its cap's definition. A
    strand records an output by its media URN, its identity; a wiring takes it
    by its name, a label that is unique per cap. The main output is not another
    output."""
    definition = registry.get_cached_cap(cap_urn.to_string())
    if definition is None:
        raise UnknownCapError(cap_urn.to_string())
    main = definition.main_output()

    def is_main(output) -> bool:
        return main is not None and main.media_urn == output.media_urn

    output = definition.output_by_urn(output_urn.to_string())
    if output is not None and not is_main(output):
        return output.name
    raise UnknownStrandOutputError(
        strand_index,
        cap_urn.to_string(),
        output_urn.to_string(),
        [o.media_urn for o in definition.get_outputs() if not is_main(o)],
    )


def _must_media(text: str, what: str) -> MediaUrn:
    try:
        return MediaUrn.from_string(text)
    except Exception as error:
        raise AssertionError(
            f"cap registry invariant: {what} is a valid MediaUrn: {text!r}: {error}"
        ) from error


def resolve_pre_interned(
    nodes: List[MediaUrn],
    wirings: List[PreInternedWiring],
    registry: "FabricRegistry",
    strand_index: int,
) -> MachineStrand:
    """Resolve a pre-interned wiring set into a MachineStrand.

    The caller has already allocated NodeIds for every distinct data
    position.

    Steps:
      0. The outputs each wiring takes, and with them the cardinality of
         every node.
      1. Per-wiring binding of sources to cap args.
      2. Which steps map (``iteration_of``).
      3. Cycle detection and canonical edge ordering.
      4. Anchor computation (NodeIds with no producer / no consumer in the
         strand).
    """
    return _resolve_wirings(nodes, None, wirings, registry, strand_index)


def resolve_named_wirings(
    nodes: List[MediaUrn],
    node_names: List[str],
    wirings: List[PreInternedWiring],
    registry: "FabricRegistry",
    strand_index: int,
) -> MachineStrand:
    """``resolve_pre_interned`` for wirings read from notation: ``node_names``
    is the name the text gave each node, indexed by NodeId, so that a refusal
    about a member can say which member."""
    if len(nodes) != len(node_names):
        raise AssertionError("every node of a strand read from notation has a name")
    return _resolve_wirings(nodes, node_names, wirings, registry, strand_index)


def _resolve_wirings(
    nodes: List[MediaUrn],
    node_names: Optional[List[str]],
    wirings: List[PreInternedWiring],
    registry: "FabricRegistry",
    strand_index: int,
) -> MachineStrand:
    if not wirings:
        raise NoCapabilityStepsError()

    # Step 0: the outputs each wiring takes, by the names its targets wrote,
    # and with them the cardinality of every node.
    #
    # A node holds a sequence, IN THE SCOPE IT LIVES IN, iff the output that
    # produces it is declared a sequence: one run of the step yields a
    # sequence. (A node a mapped step produces has one such value per item;
    # what it is from outside the map is the iteration structure's to say.)
    # An input of the machine is one value: notation has no run shape.
    node_is_sequence = [False] * len(nodes)
    definitions = []
    wiring_outputs: List[List[EdgeOutput]] = []
    for wiring in wirings:
        cap_urn = wiring.cap_urn.to_string()
        definition = registry.get_cached_cap(cap_urn)
        if definition is None:
            raise UnknownCapError(cap_urn)
        definitions.append(definition)
        outputs: List[EdgeOutput] = []
        for target in wiring.targets:
            if target.name is None:
                # The unnamed target takes the main output.
                output = definition.main_output()
                if output is None:
                    raise NoMainOutputError(strand_index, cap_urn)
            else:
                output = definition.output_named(target.name)
                if output is None:
                    raise UnknownOutputNameError(
                        strand_index,
                        cap_urn,
                        target.name,
                        [each.name for each in definition.get_outputs()],
                    )
            output_media_urn = _must_media(output.media_urn, "every output media_urn")
            if any(taken.output_media_urn.is_equivalent(output_media_urn) for taken in outputs):
                raise OutputTakenTwiceError(strand_index, cap_urn, output.name)
            node_is_sequence[target.node] = output.is_sequence
            outputs.append(EdgeOutput(output_media_urn, output.name, target.node))
        # Canonical order, like the assignment's.
        outputs.sort(key=lambda each: each.output_media_urn.ordering_key())
        wiring_outputs.append(outputs)

    # Step 1: per-wiring binding of sources to cap args. Named members bind
    # first; the rest are matched by type over the args no name bound.
    void = _must_media(MEDIA_VOID, "media:void")
    shapes: List[StepShape] = []
    assignments: List[List[EdgeAssignmentBinding]] = []
    for index, wiring in enumerate(wirings):
        definition = definitions[index]
        cap_urn = wiring.cap_urn.to_string()
        args = definition.get_args()
        try:
            cap_in_spec = MediaUrn.from_string(definition.urn.in_spec())
        except Exception as error:
            raise RuntimeMediaInferenceError(
                strand_index,
                cap_urn,
                definition.urn.in_spec(),
                f"cap `in=` is not a valid media URN: {error}",
            ) from error
        primary_arg_index: Optional[int] = None
        if not cap_in_spec.is_equivalent(void):
            for arg_index, arg in enumerate(args):
                if arg.is_main_input(cap_in_spec):
                    primary_arg_index = arg_index
                    break
            if primary_arg_index is None:
                raise CapDoesNotDeclareInputError(strand_index, cap_urn)

        # Every arg, by what it ACCEPTS (the type a source must conform to:
        # its stdin source URN for the main input, its `accepts` when it
        # gives one, its own URN otherwise) and by its SLOT (its media_urn,
        # the identity a binding records and the URN its stream is delivered
        # under). How an arg is supplied on a command line plays no part:
        # every arg can be bound by a wiring.
        arg_accepts = [_must_media(arg.accepted_urn(), "what every arg accepts") for arg in args]
        arg_slots = [_must_media(arg.media_urn, "every cap arg media_urn") for arg in args]

        # Named members bind first.
        bindings: List[EdgeAssignmentBinding] = []
        named_count = [0] * len(args)
        for name, source in wiring.named_sources:
            arg_index = next((i for i, arg in enumerate(args) if arg.name == name), None)
            if arg_index is None:
                raise UnknownArgNameError(
                    strand_index, cap_urn, name, [arg.name for arg in args]
                )
            if source.is_constant:
                _check_constant(registry, cap_urn, args[arg_index], source.constant, strand_index)
            else:
                source_urn = nodes[source.node]
                if not source_urn.conforms_to(arg_accepts[arg_index]):
                    raise SourceDoesNotConformToArgError(
                        strand_index,
                        cap_urn,
                        name,
                        arg_accepts[arg_index].to_string(),
                        source_urn.to_string(),
                    )
            named_count[arg_index] += 1
            bindings.append(
                EdgeAssignmentBinding(arg_slots[arg_index], args[arg_index].name, source)
            )
        for arg_index, count in enumerate(named_count):
            if count > 1 and not args[arg_index].is_sequence:
                raise ArgBoundTwiceError(strand_index, cap_urn, args[arg_index].name, count)

        # The unnamed members are matched by type over the args no name bound.
        free = [i for i in range(len(args)) if named_count[i] == 0]
        free_accepts = [arg_accepts[i] for i in free]
        free_is_sequence = [args[i].is_sequence for i in free]
        # The main input, when no named member bound it.
        must_bind = free.index(primary_arg_index) if primary_arg_index in free else None
        source_urns = [nodes[node_id] for node_id in wiring.source_node_ids]

        if source_urns:
            try:
                matched = match_sources_to_args(
                    source_urns, free_accepts, free_is_sequence, must_bind
                )
            except MatchFailure as failure:
                if not failure.ambiguous:
                    raise UnmatchedSourceInCapArgsError(
                        strand_index, cap_urn, source_urns[failure.source].to_string()
                    ) from failure
                # Which members the types leave open, by the names the text
                # gave them, and the args each could go to.
                members = [
                    UndecidedMember(
                        node=(
                            node_names[wiring.source_node_ids[source]]
                            if node_names is not None
                            else ""
                        ),
                        source_urn=source_urns[source].to_string(),
                        could_be=tuple(args[free[arg]].name for arg in on),
                    )
                    for source, on in failure.undecided
                ]
                raise AmbiguousMachineNotationError(strand_index, cap_urn, members) from failure
            # The matching answers in URNs. Each accepted URN is translated
            # back to its slot identity, and each source URN to its position
            # among the wiring's unnamed sources, walking the positions not
            # yet taken so that two sources that share a URN stay two.
            consumed = [False] * len(wiring.source_node_ids)
            for arg_urn, source_urn in matched:
                arg_at = next(
                    (i for i, accepts in enumerate(free_accepts) if accepts.is_equivalent(arg_urn)),
                    None,
                )
                source_at = next(
                    (
                        position
                        for position, node_id in enumerate(wiring.source_node_ids)
                        if not consumed[position] and nodes[node_id].is_equivalent(source_urn)
                    ),
                    None,
                )
                if arg_at is None or source_at is None:
                    raise AssertionError("the matching answered in a URN it was not given")
                consumed[source_at] = True
                bindings.append(
                    EdgeAssignmentBinding(
                        arg_slots[free[arg_at]],
                        args[free[arg_at]].name,
                        BindingSource.of_node(wiring.source_node_ids[source_at]),
                    )
                )

        # The bindings are in the order they were made: the named ones as
        # written, then the matched ones. To keep the canonical equivalence
        # comparison stable, re-sort by slot identity; the sort is stable, so
        # several bindings gathered onto one arg keep their declaration order
        # — the gathered sequence's item order.
        bindings.sort(key=lambda binding: binding.cap_arg_media_urn.ordering_key())

        # A cap that takes an input is given it.
        if primary_arg_index is not None:
            main_slot = arg_slots[primary_arg_index]
            if not any(b.cap_arg_media_urn.is_equivalent(main_slot) for b in bindings):
                raise MainInputUnboundError(strand_index, cap_urn, args[primary_arg_index].name)

        # What the step is given, as far as iteration is concerned: each node
        # and whether the arg it is bound to takes a sequence. A constant is
        # one value wherever the step runs.
        shape = StepShape()
        for binding in bindings:
            if binding.source.is_constant:
                continue
            for arg_index, slot in enumerate(arg_slots):
                if slot.is_equivalent(binding.cap_arg_media_urn):
                    shape.members.append(
                        MemberShape(
                            node=binding.source.node,
                            arg_is_sequence=args[arg_index].is_sequence,
                        )
                    )
                    break
        for output in wiring_outputs[index]:
            shape.outputs.append(
                OutputShape(node=output.node, is_sequence=node_is_sequence[output.node])
            )
        shapes.append(shape)
        assignments.append(bindings)

    # Step 2: which steps map. Iteration is DERIVED from cardinality, never
    # authored (docs 09 §Iteration); iteration_of is the one place the rule
    # is computed. Notation has no run, so an input of the machine is one
    # value here.
    try:
        iteration = iteration_of(shapes, lambda _node: False)
    except CyclicSteps as cyclic:
        raise CyclicMachineStrandError(strand_index) from cyclic

    indexed_edges = [
        MachineEdge(
            cap_urn=wiring.cap_urn,
            assignment=assignments[index],
            outputs=wiring_outputs[index],
            token_id=wiring.token_id,
            policy=wiring.policy,
            included_as=list(wiring.included_as),
            is_loop=iteration.steps()[index].maps,
        )
        for index, wiring in enumerate(wirings)
    ]

    # Step 3: canonical edge order. The steps are acyclic: every one of them
    # was placed above.
    edges = [indexed_edges[index] for index in _topo_sort(indexed_edges, nodes)]

    # Step 4: anchor computation.
    produced = {node for edge in edges for node in edge.output_nodes()}
    consumed_nodes = {node for edge in edges for node in edge.source_nodes()}
    # Every node is a source or an output of some step — that is what makes
    # it a node of the strand. One nothing produces is an input of the
    # strand; one nothing consumes is an output of it.
    input_anchor_ids: List[NodeId] = []
    output_anchor_ids: List[NodeId] = []
    for node_id in range(len(nodes)):
        if node_id not in produced and node_id not in consumed_nodes:
            raise AssertionError(
                f"node {node_id} of strand {strand_index} is touched by no wiring"
            )
        if node_id not in produced:
            input_anchor_ids.append(node_id)
        if node_id not in consumed_nodes:
            output_anchor_ids.append(node_id)
    # Sort anchors by canonical (URN, NodeId) order so the result is stable
    # across node-allocation orders that yield equivalent strands.
    by_urn_then_id = lambda node_id: (nodes[node_id].ordering_key(), node_id)  # noqa: E731
    input_anchor_ids.sort(key=by_urn_then_id)
    output_anchor_ids.sort(key=by_urn_then_id)

    return MachineStrand(nodes, edges, input_anchor_ids, output_anchor_ids, node_is_sequence)


def _check_constant(registry, cap_urn: str, arg, value: Any, strand_index: int) -> None:
    """Hold a constant to the validation of the arg it is bound to: the rules
    and the schema the arg's media definition declares. A constant is a value
    like any other the arg is given; it is known when the machine is
    resolved, so that is when it is checked."""
    from capdag.cap.schema_validation import schema_violations
    from capdag.media.spec import MediaValidation

    def refused(reason: str) -> ConstantFailsValidationError:
        return ConstantFailsValidationError(
            strand_index, cap_urn, arg.name, constant_text(value), reason
        )

    # Without the definition there is nothing to hold the constant to, and a
    # constant nobody checked is not bound.
    definition = registry.get_cached_media_def(arg.media_urn)
    if definition is None:
        raise refused(
            f"the media definition of '{arg.media_urn}' is not available, "
            "so the constant cannot be validated"
        )
    validation = definition.validation
    if validation is not None:
        if not isinstance(validation, MediaValidation):
            validation = MediaValidation.from_dict(validation)
        try:
            rule = validation.violation(value)
        except ValueError as error:
            raise refused(str(error)) from error
        if rule is not None:
            raise refused("it breaks the rule: " + rule)
    if definition.schema is not None:
        details = schema_violations(definition.schema, value)
        if details:
            raise refused("it does not match the schema: " + "; ".join(details))


class MatchFailure(Exception):
    """Why the unnamed members of a wiring could not be placed. It speaks in
    positions — of the sources and args the matching was given — because what
    a source or an arg is CALLED is its caller's to say."""

    def __init__(
        self,
        source: int = 0,
        undecided: Optional[List[Tuple[int, List[int]]]] = None,
    ):
        #: The types leave more than one answer, and `undecided` says about
        #: which sources. Otherwise the source at `source` fits no arg left
        #: for it.
        self.ambiguous = undecided is not None
        self.source = source
        #: Each source the minimum-cost assignments place differently, and the
        #: args they place it on, in the order the args were given.
        self.undecided: List[Tuple[int, List[int]]] = list(undecided or [])
        super().__init__(
            "the types leave more than one answer"
            if self.ambiguous
            else f"source {source} fits no arg left for it"
        )


def match_sources_to_args(
    sources: List[MediaUrn],
    args: List[MediaUrn],
    arg_is_sequence: List[bool],
    must_bind: Optional[int],
) -> List[Tuple[MediaUrn, MediaUrn]]:
    """Match a wiring's sources to a cap's args by minimum total
    specificity-distance, with a uniqueness requirement.

    Two phases, in strict precedence order:

    1. Product — each source claims a distinct arg. It wins whenever such an
       assignment exists, including the hard failure on tied minimum-cost
       assignments.
    2. Gather — only when no such assignment exists (more sources than args,
       or a Hall violation): a sequence arg may absorb several conforming
       sources; a scalar arg still takes at most one. The minimum-cost such
       assignment must be unique.

    ``must_bind`` is the index of the arg an assignment MUST bind — the cap's
    main input, when these sources are what can feed it — or None.

    Returns pairs ``(arg, source)`` sorted by arg URN (stably: several sources
    gathered into one arg keep their declaration order, which fixes the
    gathered sequence's item order). Raises ``MatchFailure``.
    """
    has_sequence_arg = any(arg_is_sequence)

    def fits_something(source: MediaUrn) -> bool:
        return any(source.conforms_to(arg) for arg in args)

    if len(sources) > len(args) and not has_sequence_arg:
        # Pigeonhole: at least one source has no arg slot and no sequence arg
        # exists to gather the surplus. The first source with no candidate
        # arg is the one named; when every source has one, at least one of
        # them MUST end up unmatched, and the first stands for it.
        for position, source in enumerate(sources):
            if not fits_something(source):
                raise MatchFailure(source=position)
        raise MatchFailure(source=0)

    # cost[s][a] is the distance when sources[s] conforms to args[a], else
    # None: the pairing cannot be made.
    cost: List[List[Optional[int]]] = []
    for position, source in enumerate(sources):
        if not fits_something(source):
            raise MatchFailure(source=position)
        row: List[Optional[int]] = []
        for arg in args:
            if not source.conforms_to(arg):
                row.append(None)
                continue
            # The specificity distance: how much more the source says than
            # the arg asks. It is never negative — refining never scores
            # lower (04 §Predicates, tagScore_monotone).
            distance = source.specificity() - arg.specificity()
            if distance < 0:
                raise AssertionError(
                    "a source that conforms to an arg is never less specific than it: "
                    f"{source} conforms to {arg}"
                )
            row.append(distance)
        cost.append(row)

    # An assignment binds the arg that MUST be bound. A cap that takes an
    # input is given it, so a way of placing the sources that leaves the main
    # input out is not an assignment at all; it does not tie with one that
    # is. This is what makes `series -> compare -> result` resolve when
    # `compare` has a second arg that accepts a series: the lone source is
    # the main input. It is a constraint, not a tiebreak: two sources that
    # both fit the main input and the other arg still tie.
    if must_bind is not None and not any(row[must_bind] is not None for row in cost):
        must_bind = None

    # Phase 1: product.
    if len(sources) <= len(args):
        best = _assignments(cost, must_bind, [False] * len(args))
        if best:
            # A tie among minimum-cost assignments is a hard ambiguity; it
            # never falls through to gather, which would mask it.
            return _one_assignment(best, sources, args)

    # Phase 2: gather.
    if not has_sequence_arg:
        # Every source has a candidate, but the candidates cannot all be
        # claimed by distinct args (a Hall violation). The first source
        # stands for the one that goes unmatched.
        raise MatchFailure(source=0)
    best = _assignments(cost, must_bind, arg_is_sequence)
    if not best:
        raise MatchFailure(source=0)
    return _one_assignment(best, sources, args)


def _one_assignment(
    best: List[List[int]], sources: List[MediaUrn], args: List[MediaUrn]
) -> List[Tuple[MediaUrn, MediaUrn]]:
    """The one minimum-cost assignment, as pairs — or, when several tie, a
    failure naming the sources they disagree about."""
    if len(best) == 1:
        pairs = [(args[arg], sources[source]) for source, arg in enumerate(best[0])]
        # Stable, and the pairs are in source order.
        pairs.sort(key=lambda pair: pair[0].ordering_key())
        return pairs
    undecided: List[Tuple[int, List[int]]] = []
    for source in range(len(sources)):
        placed = sorted({assignment[source] for assignment in best})
        if len(placed) >= 2:
            undecided.append((source, placed))
    raise MatchFailure(undecided=undecided)


def _assignments(
    cost: List[List[Optional[int]]],
    must_bind: Optional[int],
    can_gather: List[bool],
) -> List[List[int]]:
    """Every source→arg assignment of minimum total cost. ``can_gather[a]``
    gives arg ``a`` unbounded capacity (a sequence arg in the gather phase);
    otherwise the arg is claimed by at most one source. Empty when there is
    no assignment."""
    arg_count = len(cost[0]) if cost else 0
    best_cost: Optional[int] = None
    best: List[List[int]] = []
    current = [0] * len(cost)
    used = [False] * arg_count

    def place(source: int) -> None:
        nonlocal best_cost, best
        if source == len(cost):
            # A placement that leaves out the arg that must be bound is not
            # an assignment.
            if must_bind is not None and must_bind not in current:
                return
            total = sum(cost[at][arg] for at, arg in enumerate(current))  # type: ignore[misc]
            if best_cost is None or total < best_cost:
                best_cost = total
                best = [list(current)]
            elif total == best_cost:
                best.append(list(current))
            return
        for arg in range(arg_count):
            if (used[arg] and not can_gather[arg]) or cost[source][arg] is None:
                continue
            was_used = used[arg]
            used[arg] = True
            current[source] = arg
            place(source + 1)
            used[arg] = was_used

    place(0)
    return best


def _edge_order_key(edge: MachineEdge, nodes: List[MediaUrn]):
    """The canonical structural order of edges that are ready together:

    1. cap URN, structurally
    2. assignment (element-wise: the arg's slot URN, then the source — a node
       by its URN, a constant by its text, after every node), a shorter
       assignment that is a prefix of a longer one first
    3. outputs (element-wise: the output's URN, then the URN of the node it
       goes to), likewise
    4. the is_loop flag
    """

    def source_key(source: BindingSource):
        if source.is_constant:
            return (True, constant_text(source.constant))
        return (False, nodes[source.node].ordering_key())

    assignment = tuple(
        (binding.cap_arg_media_urn.ordering_key(),) + source_key(binding.source)
        for binding in edge.assignment
    )
    outputs = tuple(
        (output.output_media_urn.ordering_key(), nodes[output.node].ordering_key())
        for output in edge.outputs
    )
    # A tuple compares element-wise and then by length, which is the order
    # above. URNs are ordered by their parts (``ordering_key``), never by
    # their text.
    return (edge.cap_urn.ordering_key(), assignment, outputs, edge.is_loop)


def _topo_sort(edges: List[MachineEdge], nodes: List[MediaUrn]) -> List[int]:
    """Kahn's algorithm over the resolved data-flow dependency graph,
    returning the canonical ordering of edge indices.

    Edge B depends on edge A iff B is given a node A produces. The edges it
    is given are acyclic: steps that wait on one another are refused when the
    steps are placed (``iteration_of``), before any edge is made of them.
    """
    count = len(edges)
    producers_of: Dict[NodeId, List[int]] = {}
    for index, edge in enumerate(edges):
        for node in edge.output_nodes():
            producers_of.setdefault(node, []).append(index)

    indegree = [0] * count
    successors: List[List[int]] = [[] for _ in range(count)]
    for b_index, b in enumerate(edges):
        for source in b.source_nodes():
            for a_index in producers_of.get(source, []):
                successors[a_index].append(b_index)
                indegree[b_index] += 1

    keys = [_edge_order_key(edge, nodes) for edge in edges]
    # Sorting is stable: edges with one key stay in the order they were given.
    ready = sorted((i for i in range(count) if indegree[i] == 0), key=lambda i: keys[i])
    result: List[int] = []
    while ready:
        index = ready.pop(0)
        result.append(index)
        for successor in successors[index]:
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)
                ready.sort(key=lambda i: keys[i])
    if len(result) < count:
        raise AssertionError(f"{count - len(result)} of {count} placed steps wait on one another")
    return result
