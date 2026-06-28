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
          │    └── assignment: List[EdgeAssignmentBinding]
          │         └── (cap_arg_media_urn, source: NodeId)
          ├── input_anchor_ids: List[NodeId]  # root nodes (no producer)
          └── output_anchor_ids: List[NodeId] # leaf nodes (no consumer)

Equivalence:
    Machine.is_equivalent is strict and positional: same number of strands,
    and self.strands[i].is_equivalent(other.strands[i]) for every i.
    Strand declaration order matters.

    MachineStrand.is_equivalent walks both strands in canonical edge order,
    building a NodeId bijection on the fly. Anchor URNs are sorted multisets.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import TYPE_CHECKING, List, Optional

from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn

if TYPE_CHECKING:
    from capdag.cap.registry import FabricRegistry
    from capdag.planner.live_cap_fab import Strand

# NodeId is a dense integer index into a MachineStrand's nodes list.
# Scoped to a single strand — two strands in the same Machine use disjoint spaces.
NodeId = int


class EdgeAssignmentBinding:
    """One slot in a resolved MachineEdge's source-to-cap-arg assignment.

    Records which cap argument (cap_arg_media_urn) is fed by which
    data-position in the strand (source NodeId). The cap_arg_media_urn
    is the cap argument's slot identity (the outer media_urn from the
    cap definition), not the stdin inner type.
    """

    __slots__ = ("cap_arg_media_urn", "source")

    def __init__(self, cap_arg_media_urn: MediaUrn, source: NodeId):
        self.cap_arg_media_urn = cap_arg_media_urn
        self.source = source

    def __repr__(self) -> str:
        return f"EdgeAssignmentBinding({self.cap_arg_media_urn}<-#{self.source})"


class MachineEdge:
    """One resolved cap-step inside a MachineStrand.

    Each edge represents one application of a capability. The assignment
    field carries the explicit source-to-cap-arg mapping: pairs of
    (cap arg slot media URN, the strand NodeId that feeds it). Sorted
    by cap_arg_media_urn for canonical comparison.
    """

    __slots__ = ("cap_urn", "assignment", "target", "is_loop")

    def __init__(
        self,
        cap_urn: CapUrn,
        assignment: List[EdgeAssignmentBinding],
        target: NodeId,
        is_loop: bool = False,
    ):
        self.cap_urn = cap_urn
        self.assignment = assignment
        self.target = target
        self.is_loop = is_loop

    def __repr__(self) -> str:
        assignments_str = ", ".join(
            f"{b.cap_arg_media_urn}<-#{b.source}" for b in self.assignment
        )
        loop_prefix = "LOOP " if self.is_loop else ""
        return f"{loop_prefix}{self.cap_urn} ({assignments_str}) -> #{self.target}"


class _NodeBijection:
    """Maps NodeIds in self-strand to NodeIds in other-strand during equivalence walk.

    Each bind() call either records a new self→other mapping or confirms
    an existing one. If the same self NodeId maps to two different other
    NodeIds (or vice versa), bind() returns False and the strands are
    not equivalent. The URNs at both ends must also be is_equivalent.
    """

    def __init__(self, self_len: int, other_len: int):
        self._self_to_other: List[Optional[NodeId]] = [None] * self_len
        self._other_to_self: List[Optional[NodeId]] = [None] * other_len

    def bind(
        self,
        self_id: NodeId,
        other_id: NodeId,
        self_strand: "MachineStrand",
        other_strand: "MachineStrand",
    ) -> bool:
        # URNs at both ends must be structurally equivalent.
        if not self_strand._nodes[self_id].is_equivalent(other_strand._nodes[other_id]):
            return False

        existing_other = self._self_to_other[self_id]
        if existing_other is None:
            self._self_to_other[self_id] = other_id
        elif existing_other != other_id:
            return False

        existing_self = self._other_to_self[other_id]
        if existing_self is None:
            self._other_to_self[other_id] = self_id
        elif existing_self != self_id:
            return False

        return True


class MachineStrand:
    """One connected component of resolved cap edges with explicit anchor commitments.

    A MachineStrand is a maximal connected sub-graph: every edge shares
    at least one NodeId (transitively) with every other edge. Built once
    via resolve.resolve_strand or resolve.resolve_pre_interned; after
    construction the strand is immutable.
    """

    __slots__ = ("_nodes", "_edges", "_input_anchor_ids", "_output_anchor_ids")

    def __init__(
        self,
        nodes: List[MediaUrn],
        edges: List[MachineEdge],
        input_anchor_ids: List[NodeId],
        output_anchor_ids: List[NodeId],
    ):
        self._nodes = nodes
        self._edges = edges
        self._input_anchor_ids = input_anchor_ids
        self._output_anchor_ids = output_anchor_ids

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

        Walks both strands in canonical edge order, building a NodeId
        bijection on the fly. Any mismatch (cap URN, assignment, target
        node, is_loop, anchor count, or inconsistent node bijection)
        returns False.
        """
        if len(self._nodes) != len(other._nodes):
            return False
        if len(self._edges) != len(other._edges):
            return False
        if len(self._input_anchor_ids) != len(other._input_anchor_ids):
            return False
        if len(self._output_anchor_ids) != len(other._output_anchor_ids):
            return False

        node_map = _NodeBijection(len(self._nodes), len(other._nodes))

        # Anchors are sorted multisets — pair-wise equivalence on sorted form.
        for self_id, other_id in zip(self._input_anchor_ids, other._input_anchor_ids):
            if not node_map.bind(self_id, other_id, self, other):
                return False
        for self_id, other_id in zip(self._output_anchor_ids, other._output_anchor_ids):
            if not node_map.bind(self_id, other_id, self, other):
                return False

        for self_edge, other_edge in zip(self._edges, other._edges):
            if self_edge.is_loop != other_edge.is_loop:
                return False
            if not self_edge.cap_urn.is_equivalent(other_edge.cap_urn):
                return False
            if len(self_edge.assignment) != len(other_edge.assignment):
                return False
            # assignment vecs are pre-sorted by cap_arg_media_urn → positional comparison is canonical.
            for self_b, other_b in zip(self_edge.assignment, other_edge.assignment):
                if not self_b.cap_arg_media_urn.is_equivalent(other_b.cap_arg_media_urn):
                    return False
                if not node_map.bind(self_b.source, other_b.source, self, other):
                    return False
            if not node_map.bind(self_edge.target, other_edge.target, self, other):
                return False

        return True

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MachineStrand):
            return NotImplemented
        return self.is_equivalent(other)

    def __repr__(self) -> str:
        return (
            f"MachineStrand({len(self._nodes)} nodes, {len(self._edges)} edges, "
            f"inputs={self._input_anchor_ids}, outputs={self._output_anchor_ids})"
        )


class Machine:
    """An ordered collection of resolved MachineStrands.

    Strand declaration order matters: the executor walks the strands in
    this order at runtime, and is_equivalent compares strand-by-strand
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
        source-to-arg assignment via minimum-cost bipartite matching.

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
