"""Machine notation parser: the grammar, then anchor realization.

A two-phase pipeline:

1. Lexical / grammatical — ``syntax.py`` reads the text into statements.
   Failures here surface as ``MachineSyntaxError``.
2. Resolution — the wirings are partitioned into connected components (one
   per maximal set of wirings sharing node names), each component is given to
   the resolver, and the resulting MachineStrands are assembled into a
   Machine in the order each component first appears. Failures here surface
   as ``MachineAbstractionError``.

A wiring is ``sources -> step -> targets``: members that may name their arg
or be constants, a step with an optional policy, and targets that may name
the output they take (capdag/docs/09-machine-notation.md).

The media URN of a node
-----------------------

Every node has one URN, derived from the wirings that touch it; where a
member stands in its group never decides it (09 §The URN of a node):

- a node some step produces has the URN of what that output carries;
- a node nothing produces, as a named member, has the accepted type of the
  arg it names;
- as an unnamed member that nothing else gives a URN, it has the accepted
  type of the step's main input — at most one such member per wiring, and
  only while no named member bound the main input
  (``UntypedMachineInputError`` otherwise);
- URNs given to one node must be on one specialization chain
  (``NodeMediaConflictError`` otherwise); the node has the most specific.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from capdag.machine.error import (
    AliasNotACapError,
    AmbiguousMachineMembersError,
    CyclicMachineReferenceError,
    DuplicateAliasError,
    EmptyMachineError,
    InvalidCapUrnError,
    InvalidIncludedMachineError,
    InvalidMediaUrnError,
    MachineAbstractionError,
    MachineInputBindingError,
    MachineOutputTakenTwiceError,
    MachineParseError,
    MachineReferenceWithoutSourceError,
    MachineSyntaxError,
    NodeAliasCollisionError,
    NodeMediaConflictError,
    NoEdgesError,
    PolicyOnMachineError,
    SourceDoesNotConformToMachineInputError,
    UndecidedMember,
    UndefinedAliasError,
    UnknownArgNameError,
    UnknownCapError,
    UnknownMachineInputError,
    UnknownMachineOutputError,
    UnknownMachineReferenceError,
    UnknownOutputNameError,
    UnmatchedMachineMemberError,
    UnnamedMachineTargetError,
    UntypedMachineInputError,
    UntypedMachineMemberError,
)
from capdag.machine.graph import BindingSource, Machine, NodeId
from capdag.machine.include import (
    IncludedMachine,
    MachineSource,
    MachineSourceError,
    NoMachineSource,
    included_machine_of,
)
from capdag.machine.resolve import (
    MatchFailure,
    PreInternedWiring,
    WiringTarget,
    match_sources_to_args,
    resolve_named_wirings,
)
from capdag.machine.syntax import CAP_HEADER, MACHINE_HEADER, parse_syntax
from capdag.planner.live_cap_fab import StepToken
from capdag.planner.policy import StepPolicy
from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MEDIA_VOID, MediaUrn


@dataclass
class _RawValue:
    """What a member of a wiring gives its arg: a node, by the name the text
    gives it, or a constant."""

    is_constant: bool = False
    node: str = ""
    constant: Any = None


@dataclass
class _RawMember:
    """One member of a wiring's sources."""

    #: The arg the member names, or None when it names none.
    name: Optional[str]
    value: _RawValue


@dataclass
class _RawTarget:
    """One target: the output it names (without a name, the main output) and
    the node it goes to."""

    name: Optional[str]
    node: str


@dataclass
class _RawWiring:
    """One wiring as it comes off the syntax tree, with raw alias names."""

    #: The members, in the order written. The order decides nothing but the
    #: item order of a gather.
    sources: List[_RawMember]
    cap_alias: str
    policy: StepPolicy
    targets: List[_RawTarget]
    #: The index of this wiring's statement in the text. A step written in
    #: from an included machine stands where the machine step stood.
    position: int
    #: The machine steps this step was included through, outermost first.
    included_as: List[str] = field(default_factory=list)

    def source_nodes(self) -> List[str]:
        """The name of every node this wiring consumes, in the order written."""
        return [member.value.node for member in self.sources if not member.value.is_constant]

    def nodes(self) -> List[str]:
        """The name of every node this wiring touches."""
        return self.source_nodes() + [target.node for target in self.targets]

    def unnamed_nodes(self) -> List[str]:
        """The nodes of the members that name no arg."""
        return [
            member.value.node
            for member in self.sources
            if member.name is None and not member.value.is_constant
        ]


#: Maps each node name the text wrote to the NodeId the parser allocated for
#: it, for one strand.
StrandNodeNames = Dict[str, NodeId]


def parse_machine(input_str: str, registry) -> Machine:
    """Parse machine notation into a Machine, discarding the per-strand node
    names.

    Raises MachineParseError wrapping either a MachineSyntaxError or a
    MachineAbstractionError on any failure.
    """
    machine, _ = parse_machine_with_node_names(input_str, registry)
    return machine


def parse_machine_with_node_names(
    input_str: str, registry
) -> Tuple[Machine, List[StrandNodeNames]]:
    """Parse machine notation into a Machine and, per strand (in strand
    order), the names the text gave its nodes.

    The resolver works on NodeIds; a host addresses a machine's inputs and
    outputs by the names as written, and this is where it gets them.
    """
    return parse_machine_with_sources(input_str, registry, NoMachineSource(), None)


def parse_machine_with_sources(
    input_str: str,
    registry,
    source: MachineSource,
    id: Optional[str] = None,
) -> Tuple[Machine, List[StrandNodeNames]]:
    """``parse_machine_with_node_names``, resolving the machines its machine
    headers name through ``source``. ``id`` is what the source knows the
    machine being parsed by, when it knows it: the references it writes are
    resolved relative to it, and an inclusion of it from inside is a circle.

    What comes back is the inlined whole: every step of every included
    machine is a step of this one, and no reference is left
    (capdag/docs/09-machine-notation.md, §Machines in step position).
    """
    including: List[str] = [] if id is None else [id]
    try:
        return _parse_program(input_str, registry, source, id, including)
    except MachineParseError:
        raise
    except (MachineSyntaxError, MachineAbstractionError) as error:
        raise MachineParseError(error) from error


def _parse_program(
    input_str: str,
    registry,
    source: MachineSource,
    id: Optional[str],
    including: List[str],
) -> Tuple[Machine, List[StrandNodeNames]]:
    """Parse one machine. ``including`` is every machine whose parse this one
    is inside of, this one last when it has an id. Raises MachineSyntaxError
    or MachineAbstractionError."""
    input_str = input_str.strip()
    if not input_str:
        raise EmptyMachineError()

    # Phase 1: the text, read into statements.
    statements = parse_syntax(input_str)

    # Phase 2: headers and wirings.
    alias_map: Dict[str, Tuple[CapUrn, int]] = {}
    machine_headers: List[Tuple[str, str]] = []
    # Every alias a header declares, in the order written: cap headers and
    # machine headers name steps in one space.
    declared: List[Tuple[str, int]] = []
    wirings: List[_RawWiring] = []
    for statement in statements:
        if statement.kind == CAP_HEADER:
            try:
                parsed = CapUrn.from_string(statement.cap_urn)
            except Exception as error:
                raise InvalidCapUrnError(statement.alias, str(error)) from error
            declared.append((statement.alias, statement.position))
            alias_map.setdefault(statement.alias, (parsed, statement.position))
        elif statement.kind == MACHINE_HEADER:
            declared.append((statement.alias, statement.position))
            machine_headers.append((statement.alias, statement.reference))
        else:
            written = statement.wiring
            wirings.append(
                _RawWiring(
                    sources=[
                        _RawMember(
                            name=member.name,
                            value=_RawValue(
                                is_constant=member.is_constant,
                                node=member.node,
                                constant=member.constant,
                            ),
                        )
                        for member in written.sources
                    ],
                    cap_alias=written.step,
                    policy=written.policy,
                    targets=[_RawTarget(name=t.name, node=t.node) for t in written.targets],
                    position=statement.position,
                )
            )

    # Phase 3: no alias is declared twice.
    first_declared: Dict[str, int] = {}
    for alias, position in declared:
        if alias in first_declared:
            raise DuplicateAliasError(alias, first_declared[alias])
        first_declared[alias] = position

    if not wirings and declared:
        raise NoEdgesError()
    if not wirings:
        raise EmptyMachineError()

    # Phase 3a: the machines the machine headers name, each resolved on its
    # own before anything here is. A machine is what it is alone: where it is
    # included changes nothing about it.
    machines: Dict[str, IncludedMachine] = {}
    for alias, reference in machine_headers:
        try:
            loaded = source.load(reference, id)
        except MachineSourceError as error:
            if error.no_source:
                raise MachineReferenceWithoutSourceError(alias, reference) from error
            raise UnknownMachineReferenceError(alias, reference, error.details) from error
        if loaded.id in including:
            chain = including[including.index(loaded.id):] + [loaded.id]
            raise CyclicMachineReferenceError(chain)
        including.append(loaded.id)
        try:
            machine, names = _parse_program(loaded.notation, registry, source, loaded.id, including)
        except CyclicMachineReferenceError:
            # A circle is one fact about the whole, said once: it is not a
            # defect of each machine on the way round.
            raise
        except (MachineSyntaxError, MachineAbstractionError) as error:
            raise InvalidIncludedMachineError(alias, reference, MachineParseError(error)) from error
        finally:
            including.pop()
        machines[alias] = included_machine_of(machine, names)

    # Phase 3b: cap-alias resolution against the fabric registry.
    #
    # A step name not defined by a local header is taken to be a fabric cap
    # alias and resolved through the registry — an identifier with no local
    # definition is resolved as an alias before it is declared undefined. The
    # resolved cap URN is injected into alias_map as if a header had defined
    # it. Media URNs never appear in a wiring (they are implicit), so only
    # cap aliases are resolved here; an alias that points at a media URN in
    # step position is a hard error. The lookup is the synchronous in-memory
    # cache (resolve_alias_cached); a name that resolves to nothing is left
    # for Phase 4's undefined-alias error.
    seen_unresolved = set()
    for wiring in wirings:
        name = wiring.cap_alias
        if name in alias_map or name in machines or name in seen_unresolved:
            continue
        seen_unresolved.add(name)
        target = registry.resolve_alias_cached(name)
        if target is None:
            continue
        try:
            resolved = CapUrn.from_string(target)
        except Exception as error:
            raise AliasNotACapError(name, target) from error
        # A synthetic position past every real statement.
        alias_map[name] = (resolved, len(declared) + len(wirings) + len(alias_map))

    # Phase 4: every step is defined, and no node bears a step's name.
    def is_step(name: str) -> bool:
        return name in alias_map or name in machines

    for wiring in wirings:
        if not is_step(wiring.cap_alias):
            raise UndefinedAliasError(wiring.cap_alias)
        for node in wiring.nodes():
            if is_step(node):
                raise NodeAliasCollisionError(node, node)

    # Phase 4a: every step that is a machine is written out as the steps of
    # that machine. From here on the wirings are of caps alone.
    included_media: Dict[str, MediaUrn] = {}
    if any(wiring.cap_alias in machines for wiring in wirings):
        wirings = _include_machines(wirings, alias_map, machines, included_media, registry)
    no_machines: Dict[str, IncludedMachine] = {}

    # Phase 5: connected components, in the order each first appears.
    components = _components_of(wirings)

    # Phase 6: per-component node typing, pre-interning and resolution.
    #
    # For each connected component (= strand), every node is given its URN
    # (_type_nodes), then NodeIds are allocated in the order node names are
    # encountered (walking the wirings in their textual order). Two distinct
    # node names that happen to share a media URN stay distinct NodeIds —
    # that's the parser's identity contract.
    strands = []
    strand_node_names: List[StrandNodeNames] = []
    for strand_index, member_indices in enumerate(components):
        members = [wirings[index] for index in member_indices]
        node_media = _type_nodes(
            members, alias_map, no_machines, included_media, registry, strand_index
        )

        nodes: List[MediaUrn] = []
        name_to_id: StrandNodeNames = {}

        def intern(name: str) -> NodeId:
            if name in name_to_id:
                return name_to_id[name]
            if name not in node_media:
                raise AssertionError(f"every node of the strand was given its URN: {name}")
            node_id = len(nodes)
            nodes.append(node_media[name])
            name_to_id[name] = node_id
            return node_id

        pre_interned: List[PreInternedWiring] = []
        for wiring in members:
            # The notation path has no resolved-strand step to inherit from,
            # so each parsed wiring's edge gets its own freshly minted stable
            # identity.
            pre = PreInternedWiring(
                token_id=StepToken.mint(),
                cap_urn=alias_map[wiring.cap_alias][0],
                policy=wiring.policy,
                included_as=list(wiring.included_as),
            )
            for member in wiring.sources:
                if member.name is not None and member.value.is_constant:
                    pre.named_sources.append(
                        (member.name, BindingSource.of_constant(member.value.constant))
                    )
                elif member.name is not None:
                    pre.named_sources.append(
                        (member.name, BindingSource.of_node(intern(member.value.node)))
                    )
                elif member.value.is_constant:
                    raise AssertionError("the syntax refuses a constant that names no arg")
                else:
                    pre.source_node_ids.append(intern(member.value.node))
            for target in wiring.targets:
                pre.targets.append(WiringTarget(node=intern(target.node), name=target.name))
            pre_interned.append(pre)

        # The name the text gave each node, by NodeId: what a refusal about a
        # member names it by.
        names_by_id = [""] * len(nodes)
        for name, node_id in name_to_id.items():
            names_by_id[node_id] = name
        strands.append(
            resolve_named_wirings(nodes, names_by_id, pre_interned, registry, strand_index)
        )
        strand_node_names.append(name_to_id)

    return Machine.from_resolved_strands(strands), strand_node_names


def _components_of(wirings: List[_RawWiring]) -> List[List[int]]:
    """The connected components of a wiring set: two wirings are in one iff a
    path of shared node names joins them. A wiring that touches no node at
    all (``() -> tick -> ()``) is a component of its own. Components come in
    the order each first appears; each lists its wirings in the order
    written."""
    count = len(wirings)
    union = _UnionFind(count)
    # Node name → the first wiring that touched it.
    node_first_wiring: Dict[str, int] = {}
    for index, wiring in enumerate(wirings):
        for node in wiring.nodes():
            if node in node_first_wiring:
                union.union(node_first_wiring[node], index)
            else:
                node_first_wiring[node] = index
    groups: Dict[int, List[int]] = {}
    for index in range(count):
        groups.setdefault(union.find(index), []).append(index)
    # Wirings were appended in ascending order, so each group is sorted and
    # its first member is its first appearance.
    return sorted(groups.values(), key=lambda members: members[0])


def _include_machines(
    wirings: List[_RawWiring],
    alias_map: Dict[str, Tuple[CapUrn, int]],
    machines: Dict[str, IncludedMachine],
    included_media: Dict[str, MediaUrn],
    registry,
) -> List[_RawWiring]:
    """Write every step that is a machine out as the steps of that machine
    (09 §Machines in step position).

    A machine step binds like a cap step: a named member to the input of that
    name, the unnamed members to the inputs left by type — which is read off
    the wirings as they were written, machine steps and all, before anything
    is written out. A machine has no main input and no main output: an
    unnamed member with no type of its own has nothing to be matched by, and
    an unnamed target takes the one output the other targets leave.

    The steps written in are the included machine's as IT resolved them: each
    member under the name of the arg it was bound to, each node holding the
    type it held there (``included_media``). A node inside the included
    machine becomes a node of this one under a name nothing written can bear
    (``alias#use/name``); an input becomes what was bound to it; an output
    becomes the node that takes it, and an output nothing takes is not taken
    from the step that produces it.
    """
    # What each machine step takes, by output name. Its unnamed target is
    # given its name here, so that everything after reads names alone.
    for wiring in wirings:
        machine = machines.get(wiring.cap_alias)
        if machine is None:
            continue
        if not wiring.policy.is_default():
            raise PolicyOnMachineError(wiring.position, wiring.cap_alias)
        taken = set()
        for target in wiring.targets:
            if target.name is None:
                continue
            if machine.output(target.name) is None:
                raise UnknownMachineOutputError(
                    wiring.position, wiring.cap_alias, target.name, machine.output_names()
                )
            if target.name in taken:
                raise MachineOutputTakenTwiceError(wiring.position, wiring.cap_alias, target.name)
            taken.add(target.name)
        # The syntax allows one unnamed target.
        for target in wiring.targets:
            if target.name is not None:
                continue
            left = [output for output in machine.output_names() if output not in taken]
            if len(left) != 1:
                raise UnnamedMachineTargetError(wiring.position, wiring.cap_alias, left)
            target.name = left[0]

    # The type of every node, as the wirings were written.
    media_of: List[Optional[Dict[str, MediaUrn]]] = [None] * len(wirings)
    for strand_index, member_indices in enumerate(_components_of(wirings)):
        if not any(wirings[index].cap_alias in machines for index in member_indices):
            continue
        node_media = _type_nodes(
            [wirings[index] for index in member_indices],
            alias_map,
            machines,
            included_media,
            registry,
            strand_index,
        )
        for index in member_indices:
            if wirings[index].cap_alias in machines:
                media_of[index] = node_media

    uses: Dict[str, int] = {}
    written: List[_RawWiring] = []
    for index, wiring in enumerate(wirings):
        machine = machines.get(wiring.cap_alias)
        if machine is None:
            written.append(wiring)
            continue
        node_media = media_of[index]
        if node_media is None:
            raise AssertionError("a machine step's strand was typed above")
        alias, position = wiring.cap_alias, wiring.position

        # Named members bind first, each to the input it names.
        bound: Dict[str, _RawValue] = {}
        for member in wiring.sources:
            if member.name is None:
                continue
            accepts = machine.input(member.name)
            if accepts is None:
                raise UnknownMachineInputError(position, alias, member.name, machine.input_names())
            if member.name in bound:
                count = sum(1 for other in wiring.sources if other.name == member.name)
                raise MachineInputBindingError(position, alias, member.name, count)
            if not member.value.is_constant:
                held = node_media[member.value.node]
                if not held.conforms_to(accepts):
                    raise SourceDoesNotConformToMachineInputError(
                        position, alias, member.name, accepts.to_string(), held.to_string()
                    )
            bound[member.name] = member.value

        # The unnamed members, to the inputs left, by type alone.
        unnamed = wiring.unnamed_nodes()
        if unnamed:
            free = [(name, media) for name, media in machine.inputs if name not in bound]
            sources = [node_media[node] for node in unnamed]
            accepted = [media for _, media in free]
            try:
                pairs = match_sources_to_args(sources, accepted, [False] * len(accepted), None)
            except MatchFailure as failure:
                if not failure.ambiguous:
                    raise UnmatchedMachineMemberError(
                        position, alias, sources[failure.source].to_string()
                    ) from failure
                members = [
                    UndecidedMember(
                        node=unnamed[at],
                        source_urn=sources[at].to_string(),
                        could_be=tuple(free[input_at][0] for input_at in on),
                    )
                    for at, on in failure.undecided
                ]
                raise AmbiguousMachineMembersError(position, alias, members) from failure
            # The matching answers in types. Where it is unique no two
            # members and no two inputs it paired hold one type — two that
            # did would swap — so each pair names one member and one input.
            placed = [False] * len(unnamed)
            for arg_urn, source_urn in pairs:
                input_at = next(
                    (
                        i
                        for i, (name, media) in enumerate(free)
                        if name not in bound and media.to_string() == arg_urn.to_string()
                    ),
                    None,
                )
                member_at = next(
                    (
                        i
                        for i in range(len(unnamed))
                        if not placed[i] and sources[i].to_string() == source_urn.to_string()
                    ),
                    None,
                )
                if input_at is None or member_at is None:
                    raise AssertionError(
                        "the matching pairs every member with an input it was given"
                    )
                placed[member_at] = True
                bound[free[input_at][0]] = _RawValue(node=unnamed[member_at])
        for name, _ in machine.inputs:
            if name not in bound:
                raise MachineInputBindingError(position, alias, name, 0)

        # Output name → the node that takes it. Every target of a machine
        # step was named above.
        taken_by: Dict[str, str] = {target.name: target.node for target in wiring.targets}

        # The steps, written in.
        uses[alias] = uses.get(alias, 0) + 1
        instance = f"{alias}#{uses[alias]}"

        def inside(node: str, instance: str = instance) -> str:
            return f"{instance}/{node}"

        for name, media in machine.node_media:
            if machine.input(name) is None and name not in taken_by:
                included_media[inside(name)] = media
        for step_index, step in enumerate(machine.steps):
            step_alias = f"{instance}/{step_index}"
            alias_map[step_alias] = (step.cap_urn, position)
            inlined = _RawWiring(
                sources=[],
                cap_alias=step_alias,
                policy=step.policy,
                targets=[],
                position=position,
                # The step came through this use, and then through whatever
                # uses it had already come through inside the included
                # machine.
                included_as=[instance] + list(step.included_as),
            )
            for arg, value in step.members:
                if value.is_constant:
                    given = _RawValue(is_constant=True, constant=value.constant)
                elif value.node in bound:
                    given = bound[value.node]
                else:
                    given = _RawValue(node=inside(value.node))
                inlined.sources.append(_RawMember(name=arg, value=given))
            for output, node in step.targets:
                if node in taken_by:
                    inlined.targets.append(_RawTarget(name=output, node=taken_by[node]))
                elif machine.output(node) is not None:
                    # An output of the machine that nothing here takes.
                    pass
                else:
                    inlined.targets.append(_RawTarget(name=output, node=inside(node)))
            written.append(inlined)
    return written


def _give(node_media: Dict[str, MediaUrn], node: str, media: MediaUrn) -> None:
    """Give ``node`` the URN ``media``, beside any URN it was already given:
    the two must be on one specialization chain, and the node holds the more
    specific."""
    existing = node_media.get(node)
    if existing is None:
        node_media[node] = media
        return
    if not existing.is_comparable(media):
        raise NodeMediaConflictError(node, existing.to_string(), media.to_string())
    if media.specificity() > existing.specificity():
        node_media[node] = media


def _type_nodes(
    wirings: List[_RawWiring],
    alias_map: Dict[str, Tuple[CapUrn, int]],
    machines: Dict[str, IncludedMachine],
    included_media: Dict[str, MediaUrn],
    registry,
    strand_index: int,
) -> Dict[str, MediaUrn]:
    """Give every node of one strand its media URN (see the module
    documentation and 09 §The URN of a node). The result does not depend on
    the order of the wirings: what produces a node and what names it are read
    first, for every wiring; only then is each wiring asked for the one
    unnamed machine input its main input can type, against what the first two
    passes left untyped.

    A node written in from an included machine comes with the type it held
    there (``included_media``), given before anything else. A step that is a
    machine (``machines``) gives each node it produces the type of the output
    that node takes, and each input of this machine it is given BY NAME the
    type of that input; it has no main input to type an unnamed one by.
    """

    def cap_of(wiring: _RawWiring):
        cap_urn = alias_map[wiring.cap_alias][0]
        definition = registry.get_cached_cap(cap_urn.to_string())
        if definition is None:
            raise UnknownCapError(cap_urn.to_string())
        return cap_urn, definition

    def media(text: str) -> MediaUrn:
        try:
            return MediaUrn.from_string(text)
        except Exception as error:
            raise AssertionError(
                f"cap registry invariant: a definition's media URNs are valid: {text!r}: {error}"
            ) from error

    void = media(MEDIA_VOID)

    def main_input_of(wiring: _RawWiring, cap_urn: CapUrn) -> Optional[MediaUrn]:
        """What a cap's main input accepts: its `in=`. None when it takes
        none."""
        try:
            in_media = cap_urn.in_media_urn()
        except Exception as error:
            raise InvalidMediaUrnError(wiring.cap_alias, f"in= spec: {error}") from error
        return None if in_media.is_equivalent(void) else in_media

    node_media: Dict[str, MediaUrn] = {}
    for wiring in wirings:
        for node in wiring.nodes():
            if node in included_media:
                _give(node_media, node, included_media[node])

    # What produces a node, and — for a node nothing produces — what names it.
    produced = {target.node for wiring in wirings for target in wiring.targets}
    for wiring in wirings:
        machine = machines.get(wiring.cap_alias)
        if machine is not None:
            for target in wiring.targets:
                # _include_machines named every target, against the outputs.
                _give(node_media, target.node, machine.output(target.name))
            for member in wiring.sources:
                if member.name is None or member.value.is_constant:
                    continue
                accepts = machine.input(member.name)
                if accepts is None:
                    raise UnknownMachineInputError(
                        wiring.position, wiring.cap_alias, member.name, machine.input_names()
                    )
                if member.value.node not in produced:
                    _give(node_media, member.value.node, accepts)
            continue
        cap_urn, definition = cap_of(wiring)
        for target in wiring.targets:
            if target.name is None:
                # The main output: the cap URN's `out=`. (A cap with none is
                # refused by the resolver, which holds the wiring to it.)
                try:
                    held = cap_urn.out_media_urn()
                except Exception as error:
                    raise InvalidMediaUrnError(wiring.cap_alias, f"out= spec: {error}") from error
            else:
                output = definition.output_named(target.name)
                if output is None:
                    raise UnknownOutputNameError(
                        strand_index,
                        cap_urn.to_string(),
                        target.name,
                        [each.name for each in definition.get_outputs()],
                    )
                held = media(output.media_urn)
                if output.carries is not None:
                    # An output that carries the input holds the input's type.
                    in_media = main_input_of(wiring, cap_urn)
                    if in_media is not None:
                        held = in_media
            _give(node_media, target.node, held)
        for member in wiring.sources:
            if member.name is None or member.value.is_constant:
                continue
            arg = definition.arg_named(member.name)
            if arg is None:
                raise UnknownArgNameError(
                    strand_index,
                    cap_urn.to_string(),
                    member.name,
                    [each.name for each in definition.get_args()],
                )
            # A node some step produces has that output's type; whether it
            # conforms to the arg it is named into is the resolver's to say
            # (SourceDoesNotConformToArgError). The name types an input of
            # the machine, which has no other type.
            if member.value.node not in produced:
                _give(node_media, member.value.node, media(arg.accepted_urn()))

    # What a step's MAIN input says of the unnamed member that feeds it. A
    # step has one data input, so where exactly one unnamed member can be it,
    # that member's node is given the type the main input accepts:
    #
    # - a member nothing above gave a URN is an input of the machine whose
    #   arg nothing says: one such member per wiring is the main input, and
    #   only that (UntypedMachineInputError otherwise);
    # - failing that, the one unnamed member whose URN is on the main input's
    #   specialization chain is refined to it — a consumer that asks for a
    #   tighter type than the producer declared states the type of what flows
    #   there, and the run holds the producer to it.
    #
    # Read against what the passes above left, for every wiring, before any
    # of it is applied: the order of the wirings changes nothing.
    from_main_input: List[Tuple[str, MediaUrn]] = []
    for wiring in wirings:
        if wiring.cap_alias in machines:
            continue
        unnamed = wiring.unnamed_nodes()
        if not unnamed:
            continue
        cap_urn, definition = cap_of(wiring)
        main_input = main_input_of(wiring, cap_urn)
        main_named = False
        if main_input is not None:
            for arg in definition.get_args():
                if not arg.is_main_input(main_input):
                    continue
                main_named = any(member.name == arg.name for member in wiring.sources)
                break
        untyped = [node for node in unnamed if node not in node_media]
        if not untyped and main_input is not None and not main_named:
            on_chain = [node for node in unnamed if node_media[node].is_comparable(main_input)]
            if len(on_chain) == 1:
                from_main_input.append((on_chain[0], main_input))
        elif not untyped:
            pass
        elif len(untyped) == 1 and main_input is not None and not main_named:
            from_main_input.append((untyped[0], main_input))
        else:
            raise UntypedMachineInputError(wiring.position, cap_urn.to_string(), untyped)
    for node, given in from_main_input:
        _give(node_media, node, given)

    # A machine step has no main input: an unnamed member that nothing above
    # gave a type has none to be matched by.
    for wiring in wirings:
        if wiring.cap_alias not in machines:
            continue
        untyped = [node for node in wiring.unnamed_nodes() if node not in node_media]
        if untyped:
            raise UntypedMachineMemberError(wiring.position, wiring.cap_alias, untyped)

    return node_media


class _UnionFind:
    """A tiny union-find structure for connected-components partition."""

    def __init__(self, count: int) -> None:
        self._parent = list(range(count))
        self._rank = [0] * count

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]  # path halving
            x = self._parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            self._parent[ra] = rb
        elif self._rank[ra] > self._rank[rb]:
            self._parent[rb] = ra
        else:
            self._parent[rb] = ra
            self._rank[ra] += 1
