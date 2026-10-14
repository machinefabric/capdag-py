"""Machine graph — strand-based, anchor-realized representation.

A Machine is the canonical, anchor-realized form of a set of capability
strands. It sits between a planner Strand (linear cap-step sequence, no
anchor commitment) and a MachineRun (concrete execution against actual
input data).

Structure:
    Machine
     └── strands: List[MachineStrand]        # ordered, declaration order matters
          ├── nodes: List[MediaUrn]           # data positions in this strand
          ├── edges: List[MachineEdge]        # canonical-order resolved cap steps
          │    ├── assignment: List[EdgeAssignmentBinding]
          │    │    └── (cap_arg_media_urn, arg_name, source: a node or a constant)
          │    ├── outputs: List[EdgeOutput]
          │    │    └── (output_media_urn, output_name, node)
          │    └── policy, included_as, is_loop, token_id
          ├── input_anchor_ids: List[NodeId]  # root nodes (no producer)
          └── output_anchor_ids: List[NodeId] # leaf nodes (no consumer)

Equivalence:
    Machine.is_equivalent is strict and positional: same number of strands,
    and self.strands[i].is_equivalent(other.strands[i]) for every i.
    Strand declaration order matters.

    MachineStrand.is_equivalent walks both strands in canonical edge order,
    building a NodeId bijection on the fly. The edges decide which node is
    which; names never do.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, List, Optional

from capdag.machine.constant import constant_text, constants_equal
from capdag.planner.policy import StepPolicy
from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn

if TYPE_CHECKING:
    from capdag.cap.registry import FabricRegistry
    from capdag.planner.live_cap_fab import StepToken, Strand

# NodeId is a dense integer index into a MachineStrand's nodes list.
# Scoped to a single strand — two strands in the same Machine use disjoint spaces.
NodeId = int

_WHOLE_MIN = -(2 ** 63)
_WHOLE_MAX = 2 ** 64 - 1


def _checked_constant(value: Any) -> Any:
    """`value` if it is a constant of machine notation — a JSON value, whole
    numbers within sixty-four bits, floats finite — and a refusal if not."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int):
        if not _WHOLE_MIN <= value <= _WHOLE_MAX:
            raise ValueError(f"{value} is not a whole number a constant can hold")
        return value
    if isinstance(value, float):
        if math.isinf(value) or math.isnan(value):
            raise ValueError(f"{value!r} is not a number a constant can hold")
        return value
    if isinstance(value, (list, tuple)):
        return [_checked_constant(item) for item in value]
    if isinstance(value, dict):
        checked = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"an object's key is a string, not {key!r}")
            checked[key] = _checked_constant(item)
        return checked
    raise ValueError(f"{type(value).__name__} is not a JSON value")


@dataclass(frozen=True, eq=False)
class BindingSource:
    """What feeds one cap argument of a step: a data position of the strand,
    or a constant written in the machine (any JSON value). A constant is part
    of the binding, not a node — nothing else can consume it."""

    #: Which of the two this is.
    is_constant: bool
    #: The data position, when the source is one.
    node: NodeId = 0
    #: The value, when the source is a constant.
    constant: Any = None

    @staticmethod
    def of_node(node: NodeId) -> "BindingSource":
        """A binding source that is a node of the strand."""
        return BindingSource(is_constant=False, node=node)

    @staticmethod
    def of_constant(value: Any) -> "BindingSource":
        """A binding source that is a constant: any JSON value. Whole numbers
        and floats are kept apart as notation keeps them."""
        return BindingSource(is_constant=True, constant=_checked_constant(value))

    def __repr__(self) -> str:
        if self.is_constant:
            return constant_text(self.constant)
        return f"#{self.node}"


class EdgeAssignmentBinding:
    """One slot in a resolved MachineEdge's source-to-cap-arg assignment.

    Records which cap argument (identified by its slot media URN) is fed by
    what: a data position of the strand or a constant.
    """

    __slots__ = ("cap_arg_media_urn", "arg_name", "source")

    def __init__(self, cap_arg_media_urn: MediaUrn, arg_name: str, source: BindingSource):
        #: Slot identity per the cap definition.
        self.cap_arg_media_urn = cap_arg_media_urn
        #: The arg's name in the cap definition: the label notation writes the
        #: binding under. It is carried so a machine can be written back
        #: without the definitions, and it is NOT identity —
        #: `cap_arg_media_urn` is, and equivalence never reads this.
        self.arg_name = arg_name
        self.source = source

    def __repr__(self) -> str:
        return f"EdgeAssignmentBinding({self.cap_arg_media_urn}<-{self.source!r})"


class EdgeOutput:
    """One output of a step that its wiring takes, and the node it goes to.

    `output_media_urn` is the output's identity per the cap definition
    (RULE20: unique among a cap's outputs).
    """

    __slots__ = ("output_media_urn", "output_name", "node")

    def __init__(self, output_media_urn: MediaUrn, output_name: str, node: NodeId):
        self.output_media_urn = output_media_urn
        #: The output's name in the cap definition: a label, carried like
        #: `EdgeAssignmentBinding.arg_name` and never compared.
        self.output_name = output_name
        self.node = node

    def __repr__(self) -> str:
        return f"EdgeOutput({self.output_media_urn}->#{self.node})"


class MachineEdge:
    """One resolved cap-step inside a MachineStrand.

    `assignment` carries the explicit source-to-cap-arg mapping computed by
    the resolver, sorted by `cap_arg_media_urn` for canonical comparison.
    """

    __slots__ = (
        "cap_urn", "assignment", "outputs", "policy", "included_as", "is_loop", "token_id",
    )

    def __init__(
        self,
        cap_urn: CapUrn,
        assignment: List[EdgeAssignmentBinding],
        outputs: List[EdgeOutput],
        token_id: "StepToken",
        policy: StepPolicy = StepPolicy(),
        included_as: Optional[List[str]] = None,
        is_loop: bool = False,
    ):
        self.cap_urn = cap_urn
        self.assignment = assignment
        #: The outputs the wiring takes, sorted by output media URN. An output
        #: the cap declares and no entry names is discarded; an empty list is
        #: a sink.
        self.outputs = outputs
        #: What the step does when it fails. Part of what the machine is: two
        #: machines that differ in it behave differently.
        self.policy = policy
        #: The machine steps this step was included through, outermost first,
        #: each as `alias#use`: the alias its header gave the included machine
        #: and which use of it this is, counted from one in the order written.
        #: Empty for a step the machine wrote itself. It says where a step of
        #: the inlined whole came from — a label, like `arg_name`:
        #: equivalence never reads it, and canonical notation does not write
        #: it.
        self.included_as: List[str] = list(included_as or [])
        self.is_loop = is_loop
        #: Stable identity of the originating resolved-strand step (see
        #: `StrandStep.token_id`), carried onto the executable DAG unit so a
        #: running cap can report *which* step it is — the key the run's live
        #: updates route by. It is IDENTITY, not semantics: `is_equivalent`
        #: deliberately ignores it (two structurally-identical machines stay
        #: equivalent even with different per-run token_ids).
        self.token_id = token_id

    def main_target(self) -> Optional[NodeId]:
        """The node the step's MAIN output goes to: the taken output whose URN
        is the cap URN's `out=`. None when the wiring does not take it."""
        out = self.cap_urn.out_media_urn()
        for output in self.outputs:
            if output.output_media_urn.is_equivalent(out):
                return output.node
        return None

    def output_nodes(self) -> List[NodeId]:
        """Every node this step produces."""
        return [output.node for output in self.outputs]

    def source_nodes(self) -> List[NodeId]:
        """Every node this step consumes. A constant is not a node."""
        return [b.source.node for b in self.assignment if not b.source.is_constant]

    def __repr__(self) -> str:
        assignments = ", ".join(
            f"{b.cap_arg_media_urn}<-{b.source!r}" for b in self.assignment
        )
        outputs = ", ".join(f"{o.output_media_urn}->#{o.node}" for o in self.outputs)
        # Debug-only marker for a per-item map edge. Not notation syntax (the
        # `LOOP` keyword is retired); `is_loop` is a derived cardinality
        # property.
        loop_prefix = "map " if self.is_loop else ""
        return (
            f"{loop_prefix}{self.cap_urn}{self.policy.to_notation()} "
            f"({assignments}) -> ({outputs})"
        )


class NodeBijection:
    """Maps the nodes of one strand to the nodes of another during an
    equivalence walk. Each bind records a new pair or confirms one already
    made; a node of either strand paired with two nodes of the other is
    refused, and a refused pairing leaves no trace."""

    def __init__(self, self_len: int, other_len: int):
        self._self_to_other: List[Optional[NodeId]] = [None] * self_len
        self._other_to_self: List[Optional[NodeId]] = [None] * other_len

    def bind(self, self_id: NodeId, other_id: NodeId) -> bool:
        existing_other = self._self_to_other[self_id]
        if existing_other is not None and existing_other != other_id:
            return False
        existing_self = self._other_to_self[other_id]
        if existing_self is not None and existing_self != self_id:
            return False
        self._self_to_other[self_id] = other_id
        self._other_to_self[other_id] = self_id
        return True


class MachineStrand:
    """One connected component of resolved cap edges with explicit anchor commitments.

    A MachineStrand is a maximal connected sub-graph: every edge shares
    at least one NodeId (transitively) with every other edge. Built once
    by the resolver; after construction the strand is immutable.
    """

    __slots__ = (
        "_nodes", "_edges", "_input_anchor_ids", "_output_anchor_ids", "_node_is_sequence",
    )

    def __init__(
        self,
        nodes: List[MediaUrn],
        edges: List[MachineEdge],
        input_anchor_ids: List[NodeId],
        output_anchor_ids: List[NodeId],
        node_is_sequence: List[bool],
    ):
        if len(nodes) != len(node_is_sequence):
            raise ValueError("every node of a strand has a cardinality")
        self._nodes = nodes
        self._edges = edges
        self._input_anchor_ids = input_anchor_ids
        self._output_anchor_ids = output_anchor_ids
        self._node_is_sequence = node_is_sequence

    def node_is_sequence(self, id: NodeId) -> bool:
        """Whether node `id` holds a sequence, as its producer's output
        declares (a node nothing produces is a single value here: what a run
        gives it is the run's to say). A sequence bound to an arg that takes
        a single value is what makes a step run once per item."""
        return self._node_is_sequence[id]

    def nodes(self) -> List[MediaUrn]:
        """All distinct data positions in this strand, indexed by NodeId."""
        return self._nodes

    def edges(self) -> List[MachineEdge]:
        """The cap-step edges in canonical topological order."""
        return self._edges

    def input_anchor_ids(self) -> List[NodeId]:
        """NodeIds of the strand's input anchor nodes (roots: not produced by any edge)."""
        return self._input_anchor_ids

    def output_anchor_ids(self) -> List[NodeId]:
        """NodeIds of the strand's output anchor nodes (leaves: not consumed by any edge)."""
        return self._output_anchor_ids

    def node_urn(self, id: NodeId) -> MediaUrn:
        """Look up a node's MediaUrn by NodeId. Fails hard if id is out of range."""
        return self._nodes[id]

    def input_anchors(self) -> List[MediaUrn]:
        """Sorted multiset of input anchor URNs."""
        return [self._nodes[i] for i in self._input_anchor_ids]

    def output_anchors(self) -> List[MediaUrn]:
        """Sorted multiset of output anchor URNs."""
        return [self._nodes[i] for i in self._output_anchor_ids]

    def is_equivalent(self, other: "MachineStrand") -> bool:
        """Strict equivalence with another MachineStrand.

        Walks both strands in canonical edge order, building a bijection
        between NodeIds on the fly. Any edge mismatch (cap URN, policy,
        assignment, outputs, or is_loop) fails the comparison, and so does an
        inconsistent bijection or two paired nodes that hold different types.
        """
        if len(self._edges) != len(other._edges):
            return False

        node_map = NodeBijection(len(self._nodes), len(other._nodes))

        def bind(self_id: NodeId, other_id: NodeId) -> bool:
            # The two nodes must hold equivalent URNs, whatever the bijection
            # says: nodes that stand for each other carry one type.
            return self._nodes[self_id].is_equivalent(other._nodes[other_id]) and node_map.bind(
                self_id, other_id
            )

        # The edges decide which node is which: every node is a source or an
        # output of some edge, and an edge says what each of its nodes is FOR
        # (which arg it feeds, which output it is). Two inputs of one type are
        # told apart by that and by nothing else — not by the order they were
        # first written in, which is not part of what a machine is.
        for self_edge, other_edge in zip(self._edges, other._edges):
            if self_edge.is_loop != other_edge.is_loop:
                return False
            if self_edge.policy != other_edge.policy:
                return False
            if not self_edge.cap_urn.is_equivalent(other_edge.cap_urn):
                return False
            if len(self_edge.assignment) != len(other_edge.assignment):
                return False
            if len(self_edge.outputs) != len(other_edge.outputs):
                return False
            # Assignment is pre-sorted by cap_arg_media_urn — positional
            # comparison is canonical.
            for self_b, other_b in zip(self_edge.assignment, other_edge.assignment):
                if not self_b.cap_arg_media_urn.is_equivalent(other_b.cap_arg_media_urn):
                    return False
                if self_b.source.is_constant != other_b.source.is_constant:
                    return False
                if self_b.source.is_constant:
                    # Two machines that give an arg different constants behave
                    # differently.
                    if not constants_equal(self_b.source.constant, other_b.source.constant):
                        return False
                elif not bind(self_b.source.node, other_b.source.node):
                    return False
            # Sorted by output media URN, like the assignment.
            for self_o, other_o in zip(self_edge.outputs, other_edge.outputs):
                if not self_o.output_media_urn.is_equivalent(other_o.output_media_urn):
                    return False
                if not bind(self_o.node, other_o.node):
                    return False

        # Every node of a strand is a source or an output of one of its edges,
        # so the walk has paired every node of each strand with one of the
        # other: the strands have the same nodes, and the same of them are
        # anchors.
        return True

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MachineStrand):
            return NotImplemented
        return self.is_equivalent(other)

    def __hash__(self) -> int:
        return hash(len(self._edges))

    def __repr__(self) -> str:
        return (
            f"MachineStrand({len(self._nodes)} nodes, {len(self._edges)} edges, "
            f"inputs={self._input_anchor_ids}, outputs={self._output_anchor_ids})"
        )


class Machine:
    """An ordered collection of resolved MachineStrands.

    Strand declaration order matters: is_equivalent compares strand-by-strand
    positionally.
    """

    __slots__ = ("_strands",)

    def __init__(self, strands: List[MachineStrand]):
        self._strands = strands

    @classmethod
    def from_resolved_strands(cls, strands: List[MachineStrand]) -> "Machine":
        """Construct a Machine from already-resolved strands."""
        return cls(strands)

    @classmethod
    def from_strand(cls, strand: "Strand", registry: "FabricRegistry") -> "Machine":
        """Build a Machine containing exactly one MachineStrand from a planner Strand.

        The cap registry is consulted to look up each cap's args list for
        source-to-arg matching.

        Raises MachineAbstractionError on resolution failure.
        """
        from capdag.machine.resolve import resolve_strand
        resolved = resolve_strand(strand, registry, 0)
        return cls([resolved])

    @classmethod
    def from_strands(
        cls, strands: List["Strand"], registry: "FabricRegistry"
    ) -> "Machine":
        """Build a Machine from N planner Strands, one MachineStrand per input.

        Each strand is resolved independently. No cross-strand joining.

        Raises NoCapabilityStepsError if strands is empty.
        Raises MachineAbstractionError on any resolution failure.
        """
        from capdag.machine.error import NoCapabilityStepsError
        from capdag.machine.resolve import resolve_strand
        if not strands:
            raise NoCapabilityStepsError()
        resolved = [resolve_strand(s, registry, idx) for idx, s in enumerate(strands)]
        return cls(resolved)

    def strands(self) -> List[MachineStrand]:
        """All resolved strands in declaration order."""
        return self._strands

    def strand_count(self) -> int:
        """Number of strands."""
        return len(self._strands)

    def is_empty(self) -> bool:
        """Whether this machine has no strands."""
        return len(self._strands) == 0

    def is_equivalent(self, other: "Machine") -> bool:
        """Strict, positional equivalence.

        Two Machines are equivalent iff they have the same number of
        strands and self.strands[i].is_equivalent(other.strands[i]) for
        every i. Strand order matters.
        """
        if len(self._strands) != len(other._strands):
            return False
        for self_strand, other_strand in zip(self._strands, other._strands):
            if not self_strand.is_equivalent(other_strand):
                return False
        return True

    @classmethod
    def from_string(cls, input_str: str, registry: "FabricRegistry") -> "Machine":
        """Parse machine notation into a Machine.

        Delegates to parse_machine. Raises MachineParseError on any failure.
        """
        from capdag.machine.parser import parse_machine
        return parse_machine(input_str, registry)

    def to_machine_notation(self) -> str:
        """Serialize to canonical one-line machine notation.

        Delegates to the serializer. Attached by serializer.py at import time.
        """
        raise NotImplementedError(
            "to_machine_notation is attached by capdag.machine.serializer at import time"
        )

    def to_machine_notation_aliased(self, registry, fmt: str = "bracketed") -> str:
        """Serialize rendering each cap by its registered display alias when one
        exists (the "store aliased" form).

        Delegates to the serializer. Attached by serializer.py at import time.
        """
        raise NotImplementedError(
            "to_machine_notation_aliased is attached by capdag.machine.serializer at import time"
        )

    def to_render_payload_json(self) -> str:
        """Serialize to render payload JSON.

        Delegates to the serializer. Attached by serializer.py at import time.
        """
        raise NotImplementedError(
            "to_render_payload_json is attached by capdag.machine.serializer at import time"
        )

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Machine):
            return NotImplemented
        return self.is_equivalent(other)

    def __hash__(self) -> int:
        return hash(len(self._strands))

    def __repr__(self) -> str:
        if not self._strands:
            return "Machine(empty)"
        edge_count = sum(len(s.edges()) for s in self._strands)
        return f"Machine({len(self._strands)} strands, {edge_count} edges)"

    def __str__(self) -> str:
        return self.__repr__()


class MachineRunStatus(Enum):
    """Lifecycle status of a single MachineRun."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


def _unix_now() -> int:
    """Current UNIX time in whole seconds."""
    return int(time.time())


class MachineRun:
    """A single execution attempt of a Machine."""

    __slots__ = (
        "id",
        "machine_notation",
        "resolved_strand",
        "status",
        "error_message",
        "created_at_unix",
        "started_at_unix",
        "completed_at_unix",
    )

    def __init__(
        self,
        id: str,
        machine_notation: str,
        resolved_strand: "Strand",
        status: MachineRunStatus,
        error_message: Optional[str],
        created_at_unix: int,
        started_at_unix: Optional[int],
        completed_at_unix: Optional[int],
    ):
        self.id = id
        self.machine_notation = machine_notation
        self.resolved_strand = resolved_strand
        self.status = status
        self.error_message = error_message
        self.created_at_unix = created_at_unix
        self.started_at_unix = started_at_unix
        self.completed_at_unix = completed_at_unix

    @classmethod
    def new(cls, id: str, machine: "Machine", resolved_strand: "Strand") -> "MachineRun":
        """Construct a new MachineRun bound to a machine and its resolved strand.

        The machine's canonical notation is computed and stored as the run's
        stable identifier. Fails hard with NoCapabilityStepsError if the
        machine has no strands (its data-flow serializes to an empty string).
        """
        from capdag.machine.error import NoCapabilityStepsError

        machine_notation = machine.to_machine_notation()
        if machine_notation == "":
            raise NoCapabilityStepsError()
        return cls(
            id=id,
            machine_notation=machine_notation,
            resolved_strand=resolved_strand,
            status=MachineRunStatus.PENDING,
            error_message=None,
            created_at_unix=_unix_now(),
            started_at_unix=None,
            completed_at_unix=None,
        )

    def start(self) -> None:
        self.status = MachineRunStatus.RUNNING
        self.started_at_unix = _unix_now()

    def complete(self) -> None:
        self.status = MachineRunStatus.COMPLETED
        self.completed_at_unix = _unix_now()
        self.error_message = None

    def fail(self, error_message: str) -> None:
        self.status = MachineRunStatus.FAILED
        self.completed_at_unix = _unix_now()
        self.error_message = error_message

    def cancel(self) -> None:
        self.status = MachineRunStatus.CANCELLED
        self.completed_at_unix = _unix_now()
