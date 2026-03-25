"""Orchestrator types — error types, resolved graph, and registry trait.

Mirrors Rust's orchestrator/types.rs exactly.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Set, Tuple

from capdag.cap.definition import Cap
from capdag.planner.cardinality import InputStructure


# --- Error hierarchy ---

class ParseOrchestrationError(Exception):
    """Base class for all orchestration parse errors."""
    pass


class MachineSyntaxParseFailedError(ParseOrchestrationError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"Machine notation parse failed: {message}")


class CapNotFoundError(ParseOrchestrationError):
    def __init__(self, cap_urn: str) -> None:
        self.cap_urn = cap_urn
        super().__init__(f"Cap URN '{cap_urn}' not found in registry")


class NodeMediaConflictError(ParseOrchestrationError):
    def __init__(self, node: str, existing: str, required_by_cap: str) -> None:
        self.node = node
        self.existing = existing
        self.required_by_cap = required_by_cap
        super().__init__(
            f"Node '{node}' has conflicting media URNs: "
            f"existing='{existing}', required_by_cap='{required_by_cap}'"
        )


class NotADagError(ParseOrchestrationError):
    def __init__(self, cycle_nodes: List[str]) -> None:
        self.cycle_nodes = cycle_nodes
        super().__init__(
            f"Graph is not a DAG, contains cycle involving nodes: {cycle_nodes}"
        )


class InvalidGraphError(ParseOrchestrationError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"Invalid graph: {message}")


class CapUrnParseError(ParseOrchestrationError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"Failed to parse Cap URN: {message}")


class MediaUrnParseError(ParseOrchestrationError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"Failed to parse Media URN: {message}")


class RegistryError(ParseOrchestrationError):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(f"Registry error: {message}")


class StructureMismatchError(ParseOrchestrationError):
    def __init__(self, node: str, source_structure: InputStructure,
                 expected_structure: InputStructure) -> None:
        self.node = node
        self.source_structure = source_structure
        self.expected_structure = expected_structure
        super().__init__(
            f"Structure mismatch at node '{node}': source is "
            f"{source_structure.value} but cap expects {expected_structure.value}"
        )


# --- Data types ---

class ResolvedEdge:
    """A resolved edge in the orchestration graph.

    Each edge represents a cap transformation from one node to another,
    with the full cap definition and media URN strings resolved.
    """

    __slots__ = ("from_node", "to_node", "cap_urn", "cap", "in_media", "out_media")

    def __init__(
        self,
        from_node: str,
        to_node: str,
        cap_urn: str,
        cap: Cap,
        in_media: str,
        out_media: str,
    ) -> None:
        self.from_node = from_node
        self.to_node = to_node
        self.cap_urn = cap_urn
        self.cap = cap
        self.in_media = in_media
        self.out_media = out_media

    def __repr__(self) -> str:
        return f"ResolvedEdge({self.from_node!r} -> {self.to_node!r}, cap={self.cap_urn!r})"


def _mermaid_escape(s: str) -> str:
    """Escape a string for use in Mermaid labels."""
    return (s
            .replace("\\", "\\\\")
            .replace('"', "#quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


class ResolvedGraph:
    """A fully resolved orchestration graph.

    Contains nodes (name → media URN) and edges (resolved cap transformations).
    """

    __slots__ = ("nodes", "edges", "graph_name")

    def __init__(
        self,
        nodes: Dict[str, str],
        edges: List[ResolvedEdge],
        graph_name: Optional[str] = None,
    ) -> None:
        self.nodes = nodes
        self.edges = edges
        self.graph_name = graph_name

    def to_mermaid(self) -> str:
        """Generate Mermaid graph LR flowchart."""
        out = "graph LR\n"

        targets: Set[str] = {e.to_node for e in self.edges}
        sources: Set[str] = {e.from_node for e in self.edges}

        for name, media_urn in self.nodes.items():
            is_input = name in sources and name not in targets
            is_output = name in targets and name not in sources
            esc_name = _mermaid_escape(name)
            esc_urn = _mermaid_escape(media_urn)

            if is_input:
                out += f'    {name}(["{esc_name}<br/><small>{esc_urn}</small>"])\n'
            elif is_output:
                out += f'    {name}(("{esc_name}<br/><small>{esc_urn}</small>"))\n'
            else:
                out += f'    {name}["{esc_name}<br/><small>{esc_urn}</small>"]\n'

        out += "\n"

        seen_edges: Set[Tuple[str, str, str]] = set()
        for edge in self.edges:
            key = (edge.from_node, edge.to_node, edge.cap_urn)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            title = _mermaid_escape(edge.cap.title)
            urn = _mermaid_escape(edge.cap_urn)
            out += f'    {edge.from_node} -->|"{title}<br/><small>{urn}</small>"| {edge.to_node}\n'

        return out

    def __repr__(self) -> str:
        return f"ResolvedGraph(nodes={len(self.nodes)}, edges={len(self.edges)})"


# --- Registry trait ---

class CapRegistryTrait(ABC):
    """Abstract interface for cap registry lookup.

    Implementations must provide async lookup of caps by URN string.
    """

    @abstractmethod
    async def lookup(self, urn: str) -> Cap:
        """Look up a cap by URN string. Raises ParseOrchestrationError on failure."""
        ...
