"""Route graph — typed DAG representation for machine notation

A Machine is the semantic model behind machine notation. It represents
a directed acyclic graph of capability edges, where each edge transforms
one or more source media types into a target media type via a capability.

Equivalence:
Two Machines are equivalent if they have the same set of edges,
compared using MediaUrn.is_equivalent() for media types and
CapUrn.is_equivalent() for capabilities. Alias names and statement
ordering are serialization concerns only — they do not affect equivalence.
"""

from __future__ import annotations

from typing import List, Optional

from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn


class MachineEdge:
    """A single edge in the route graph.

    Each edge represents a capability that transforms one or more source
    media types into a target media type. The is_loop flag indicates
    ForEach semantics (the capability is applied to each item in a list).
    """

    __slots__ = ("sources", "cap_urn", "target", "is_loop")

    def __init__(
        self,
        sources: List[MediaUrn],
        cap_urn: CapUrn,
        target: MediaUrn,
        is_loop: bool = False,
    ):
        self.sources = sources
        self.cap_urn = cap_urn
        self.target = target
        self.is_loop = is_loop

    def is_equivalent(self, other: MachineEdge) -> bool:
        """Check if two edges are semantically equivalent.

        Equivalence is defined as:
        - Same number of sources, and each source in self has an equivalent source in other
        - Equivalent cap URNs (via CapUrn.is_equivalent)
        - Equivalent target media URNs (via MediaUrn.is_equivalent)
        - Same is_loop flag

        Source order does not matter — fan-in sources are compared as sets.
        """
        if self.is_loop != other.is_loop:
            return False

        if not self.cap_urn.is_equivalent(other.cap_urn):
            return False

        # Target equivalence
        if not self.target.is_equivalent(other.target):
            return False

        # Source set equivalence — order-independent comparison
        if len(self.sources) != len(other.sources):
            return False

        # For each source in self, find a matching source in other.
        # Track which indices in other have been matched to avoid double-counting.
        matched = [False] * len(other.sources)
        for self_src in self.sources:
            found = False
            for j, other_src in enumerate(other.sources):
                if matched[j]:
                    continue
                if self_src.is_equivalent(other_src):
                    matched[j] = True
                    found = True
                    break
            if not found:
                return False

        return True

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MachineEdge):
            return NotImplemented
        return self.is_equivalent(other)

    def __hash__(self) -> int:
        # Edges are compared by equivalence, not identity.
        # Use a rough hash based on cap_urn and source/target count.
        return hash((str(self.cap_urn), len(self.sources), self.is_loop))

    def __repr__(self) -> str:
        sources_str = ", ".join(str(s) for s in self.sources)
        loop_prefix = "LOOP " if self.is_loop else ""
        return f"({sources_str}) -{loop_prefix}{self.cap_urn}-> {self.target}"

    def __str__(self) -> str:
        return self.__repr__()


class Machine:
    """A route graph — the semantic model behind machine notation.

    The graph is a collection of directed edges where each edge is a capability
    that transforms source media types into a target media type. The graph
    structure captures the full transformation pipeline.

    Equivalence:
    Two graphs are equivalent if they have the same set of edges, regardless
    of ordering. Alias names used in the textual notation are not part of
    the graph model.
    """

    __slots__ = ("_edges",)

    def __init__(self, edges: Optional[List[MachineEdge]] = None):
        self._edges: List[MachineEdge] = edges if edges is not None else []

    @classmethod
    def empty(cls) -> Machine:
        """Create an empty route graph."""
        return cls([])

    def edges(self) -> List[MachineEdge]:
        """Get the edges of this graph."""
        return self._edges

    def edge_count(self) -> int:
        """Number of edges in the graph."""
        return len(self._edges)

    def is_empty(self) -> bool:
        """Check if the graph has no edges."""
        return len(self._edges) == 0

    def is_equivalent(self, other: Machine) -> bool:
        """Check if two route graphs are semantically equivalent.

        Two graphs are equivalent if they have the same set of edges
        (compared using MachineEdge.is_equivalent). Edge ordering
        does not matter.
        """
        if len(self._edges) != len(other._edges):
            return False

        # For each edge in self, find a matching edge in other.
        matched = [False] * len(other._edges)
        for self_edge in self._edges:
            found = False
            for j, other_edge in enumerate(other._edges):
                if matched[j]:
                    continue
                if self_edge.is_equivalent(other_edge):
                    matched[j] = True
                    found = True
                    break
            if not found:
                return False

        return True

    def root_sources(self) -> List[MediaUrn]:
        """Collect all unique source media URNs across all edges that are not
        also produced as targets by any other edge. These are the "root"
        inputs to the graph.
        """
        roots: List[MediaUrn] = []
        for edge in self._edges:
            for src in edge.sources:
                # Check if any edge produces this source as a target
                is_produced = any(
                    e.target.is_equivalent(src) for e in self._edges
                )
                if not is_produced:
                    # Avoid duplicates (by equivalence)
                    already_added = any(r.is_equivalent(src) for r in roots)
                    if not already_added:
                        roots.append(src)
        return roots

    def leaf_targets(self) -> List[MediaUrn]:
        """Collect all unique target media URNs that are not consumed as sources
        by any other edge. These are the "leaf" outputs of the graph.
        """
        leaves: List[MediaUrn] = []
        for edge in self._edges:
            is_consumed = any(
                any(s.is_equivalent(edge.target) for s in e.sources)
                for e in self._edges
            )
            if not is_consumed:
                already_added = any(
                    l.is_equivalent(edge.target) for l in leaves
                )
                if not already_added:
                    leaves.append(edge.target)
        return leaves

    @classmethod
    def from_string(cls, input_str: str) -> Machine:
        """Parse machine notation into a Machine."""
        from capdag.machine.parser import parse_machine
        return parse_machine(input_str)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Machine):
            return NotImplemented
        return self.is_equivalent(other)

    def __hash__(self) -> int:
        return hash(len(self._edges))

    def __repr__(self) -> str:
        if not self._edges:
            return "Machine(empty)"
        return f"Machine({len(self._edges)} edges)"

    def __str__(self) -> str:
        return self.__repr__()
