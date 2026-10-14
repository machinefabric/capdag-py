"""Which steps of a machine run once per item, and inside which map.

Notation never writes iteration: it follows from cardinality (docs 09
§Iteration). This module is the one place that rule is computed. The resolver
asks it which steps map. Notation has no run, so its inputs are single
values; a caller that knows a run says which inputs it binds a sequence to.

The rule
--------

Every node lives in a scope: the machine itself, or a map. A node in a map
has one value per run of that map. Seen from outside the map it is the
sequence of those values in item order — and when the map is itself inside
another, seen from outside both it is one flat sequence.

A map is what it iterates: the sequences it zips, in the scope it is opened
in. Two steps that map over the same sequences in the same scope run in the
same map, so what each produces for an item can be given to a third step for
that item.

A step is first placed in the deepest scope its members ask for, when those
scopes lie on one line of nesting; when they do not, in the scope that
encloses them all. What a member asks for:

- bound to an arg that takes one value: the scope the node lives in;
- a sequence bound to an arg that takes a sequence: the scope it lives in —
  the step is given that sequence whole;
- a single value bound to an arg that takes a sequence: the scope that
  encloses the node's map — the step folds what the map collected. (A single
  value of the machine itself asks for the machine.)

From its placement, each member bound to an arg that takes one value is one
of:

- a single value there: given as it is;
- the sequence a map the placement is inside iterates: given as that map's
  item — the step joins the map;
- a sequence that lives in the placement, or was collected into it: mapped —
  the step runs in the map over it, opened inside the placement. Several
  mapped members are zipped;
- a sequence from outside that no enclosing map iterates. Mapping it here
  would run every item of it for every item of the enclosing map: a cross
  product nobody wrote. The step is placed further out instead — where that
  sequence lives — and what it was given from the inner map is collected and
  zipped with it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

NodeId = int

#: Names a scope of iteration: the machine itself (SCOPE_ROOT) or one map.
ScopeId = int

#: The machine itself: what is not inside any map.
SCOPE_ROOT: ScopeId = 0


@dataclass(frozen=True)
class MemberShape:
    """One node a step is given, and what the arg it is bound to takes."""

    node: NodeId
    #: The arg takes a sequence (a member alone on it is given whole; several
    #: on it are gathered).
    arg_is_sequence: bool


@dataclass(frozen=True)
class OutputShape:
    """One node a step produces, and whether the output that produces it is
    declared a sequence."""

    node: NodeId
    is_sequence: bool


@dataclass
class StepShape:
    """A step, as far as iteration is concerned."""

    #: The nodes the step is given. A constant is not a member: it is one
    #: value wherever the step runs.
    members: List[MemberShape] = field(default_factory=list)
    outputs: List[OutputShape] = field(default_factory=list)


@dataclass
class StepPlacement:
    """Where a step runs."""

    #: The scope the step is placed in: where it is given its members.
    placed_in: ScopeId
    #: The map the step runs in, when it maps: opened inside its placement.
    #: None when it does not map.
    map: Optional[ScopeId] = None
    #: The members the step maps over, zipped: distinct nodes, in the order
    #: the step lists them. Empty exactly when the step does not map.
    mapped: List[NodeId] = field(default_factory=list)

    @property
    def maps(self) -> bool:
        """Whether the step maps."""
        return self.map is not None

    def scope(self) -> ScopeId:
        """The scope the step's invocations run in, and its outputs live in:
        the map it maps in, or its placement."""
        return self.map if self.map is not None else self.placed_in


class CyclicSteps(Exception):
    """The steps a machine cannot place because they wait on one another."""

    def __init__(self, steps: List[int]):
        self.steps = list(steps)
        super().__init__(f"steps {self.steps} wait on one another")


@dataclass
class _Scope:
    #: The scope that encloses this one; the machine encloses itself.
    parent: ScopeId
    #: The sequences a map zips, sorted; none for the machine.
    sources: Tuple[NodeId, ...] = ()
    #: The steps that map in it, by index.
    mappers: List[int] = field(default_factory=list)


class IterationStructure:
    """The scopes of a machine and the place of every step and node in
    them."""

    def __init__(self) -> None:
        self._scopes: List[_Scope] = [_Scope(parent=SCOPE_ROOT)]
        self._steps: List[StepPlacement] = []
        self._node_scope: Dict[NodeId, ScopeId] = {}
        self._node_is_sequence: Dict[NodeId, bool] = {}

    def _all_placed(self, members: List[MemberShape]) -> bool:
        return all(member.node in self._node_scope for member in members)

    def _place(self, index: int, step: StepShape) -> StepPlacement:
        # What each member asks for.
        asked: List[ScopeId] = []
        for member in step.members:
            scope = self._node_scope[member.node]
            if member.arg_is_sequence and not self._node_is_sequence[member.node]:
                scope = self._scopes[scope].parent
            asked.append(scope)
        deepest = SCOPE_ROOT
        for position, scope in enumerate(asked):
            # Two different scopes of one depth are not on one line of
            # nesting, and then the deepest is not where the step is placed.
            if position == 0 or self.depth(scope) > self.depth(deepest):
                deepest = scope
        on_one_line = all(self.encloses(scope, deepest) for scope in asked)
        placed_in = deepest
        if not on_one_line:
            placed_in = asked[0]
            for scope in asked[1:]:
                placed_in = self.common_scope(placed_in, scope)

        # What each member bound to an arg that takes one value is from there.
        # A sequence from outside that no enclosing map iterates moves the
        # placement out to where it lives, and the members are read again.
        while True:
            mapped: List[NodeId] = []
            moved = False
            for member in step.members:
                if member.arg_is_sequence:
                    continue
                lives_in = self._node_scope[member.node]
                if self.encloses(lives_in, placed_in):
                    if not self._node_is_sequence[member.node]:
                        continue  # one value here
                    if lives_in != placed_in:
                        if self._iterated_between(member.node, placed_in, lives_in):
                            continue  # the item of a map the step is inside
                        placed_in = lives_in
                        moved = True
                        break
                    # A sequence that lives here: mapped.
                # Otherwise the node lives in a map the placement is not
                # inside, and the placement encloses that map (it encloses
                # every scope a member asked for): the node is seen here as
                # what the map collected — a sequence, mapped.
                if member.node not in mapped:
                    mapped.append(member.node)
            if not moved:
                break

        placement = StepPlacement(placed_in=placed_in, mapped=mapped)
        if not mapped:
            return placement
        sources = tuple(sorted(mapped))
        found = None
        for scope_id, scope in enumerate(self._scopes):
            # The machine itself zips nothing, so it is never the map sought.
            if scope.parent == placed_in and scope.sources == sources:
                found = scope_id
                break
        if found is None:
            self._scopes.append(_Scope(parent=placed_in, sources=sources))
            found = len(self._scopes) - 1
        self._scopes[found].mappers.append(index)
        placement.map = found
        return placement

    def _iterated_between(self, node: NodeId, inner: ScopeId, outer: ScopeId) -> bool:
        """Whether a map from `inner` outward, short of `outer`, iterates
        `node`."""
        at = inner
        while at != outer:
            if node in self._scopes[at].sources:
                return True
            at = self._scopes[at].parent
        return False

    def steps(self) -> List[StepPlacement]:
        """Where each step runs, in the order the steps were given."""
        return self._steps

    def scope_count(self) -> int:
        """How many scopes there are, the machine included."""
        return len(self._scopes)

    def parent(self, scope: ScopeId) -> ScopeId:
        """The scope that encloses `scope`. The machine encloses itself."""
        return self._scopes[scope].parent

    def sources(self, scope: ScopeId) -> List[NodeId]:
        """The sequences map `scope` zips, in a fixed order; none for the
        machine."""
        return list(self._scopes[scope].sources)

    def opened_by(self, scope: ScopeId) -> Optional[int]:
        """The first step that maps in `scope`: the one the map is opened by.
        The machine is opened by none."""
        mappers = self._scopes[scope].mappers
        return mappers[0] if mappers else None

    def item_map(self, node: NodeId, from_scope: ScopeId) -> Optional[ScopeId]:
        """The map that gives a step running in `from_scope` the ITEM of
        `node`: the innermost map at or around `from_scope` that iterates it.
        None when no map the step is inside iterates the node: the step is
        given it whole."""
        at = from_scope
        while at != SCOPE_ROOT:
            if node in self._scopes[at].sources:
                return at
            at = self._scopes[at].parent
        return None

    def node_scope(self, node: NodeId) -> ScopeId:
        """The scope a node lives in."""
        return self._node_scope[node]

    def depth(self, scope: ScopeId) -> int:
        """How many maps enclose `scope`, itself included."""
        depth = 0
        at = scope
        while at != SCOPE_ROOT:
            depth += 1
            at = self._scopes[at].parent
        return depth

    def encloses(self, outer: ScopeId, inner: ScopeId) -> bool:
        """Whether `outer` is `inner` or encloses it."""
        at = inner
        while True:
            if at == outer:
                return True
            if at == SCOPE_ROOT:
                return False
            at = self._scopes[at].parent

    def common_scope(self, a: ScopeId, b: ScopeId) -> ScopeId:
        """The deepest scope that encloses both."""
        at = a
        while not self.encloses(at, b):
            at = self._scopes[at].parent
        return at

    def is_sequence_from(self, node: NodeId, from_scope: ScopeId) -> bool:
        """Whether `node` is a sequence as a step placed in `from_scope` is
        given it: what it is in its own scope when that scope encloses
        `from_scope`, and the collected sequence otherwise."""
        if self.encloses(self._node_scope[node], from_scope):
            return self._node_is_sequence[node]
        return True


def iteration_of(
    steps: List[StepShape], input_is_sequence: Callable[[NodeId], bool]
) -> IterationStructure:
    """Place every step. `input_is_sequence` says, for a node no step
    produces, whether it holds a sequence. Raises ``CyclicSteps`` naming the
    steps that wait on one another."""
    produced = {output.node for step in steps for output in step.outputs}

    structure = IterationStructure()
    # An input of the machine lives in the machine.
    for step in steps:
        for member in step.members:
            if member.node not in produced:
                structure._node_scope[member.node] = SCOPE_ROOT
                structure._node_is_sequence[member.node] = input_is_sequence(member.node)

    # A step is placed once every node it is given has a place. The order
    # steps are placed in does not change where any of them lands: a
    # placement reads only its members, and a map is found by what it
    # iterates.
    placements: List[Optional[StepPlacement]] = [None] * len(steps)
    remaining = len(steps)
    while remaining > 0:
        before = remaining
        for index, step in enumerate(steps):
            if placements[index] is not None or not structure._all_placed(step.members):
                continue
            placement = structure._place(index, step)
            for output in step.outputs:
                structure._node_scope[output.node] = placement.scope()
                structure._node_is_sequence[output.node] = output.is_sequence
            placements[index] = placement
            remaining -= 1
        if remaining == before:
            raise CyclicSteps([i for i, placement in enumerate(placements) if placement is None])
    structure._steps = list(placements)  # type: ignore[arg-type]
    for scope in structure._scopes:
        scope.mappers.sort()
    return structure
