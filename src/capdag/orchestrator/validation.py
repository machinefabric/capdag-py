"""DAG validation for orchestration graphs.

Implements cycle detection using Kahn's algorithm for topological sort.
Mirrors Rust's orchestrator/validation.rs exactly.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List

from capdag.orchestrator.types import NotADagError, ResolvedEdge


def validate_dag(
    nodes: Dict[str, str],
    edges: List[ResolvedEdge],
) -> None:
    """Validate that the graph is a DAG (no cycles).

    Uses Kahn's algorithm for topological sort. If not all nodes can be
    sorted, the graph contains a cycle.

    Args:
        nodes: Map from node name to media URN string.
        edges: List of resolved edges.

    Raises:
        NotADagError: If the graph contains a cycle.
    """
    # Build adjacency list and in-degree map
    adj: Dict[str, List[str]] = {name: [] for name in nodes}
    in_degree: Dict[str, int] = {name: 0 for name in nodes}

    for edge in edges:
        if edge.from_node not in adj:
            adj[edge.from_node] = []
        adj[edge.from_node].append(edge.to_node)
        in_degree.setdefault(edge.to_node, 0)
        in_degree[edge.to_node] = in_degree.get(edge.to_node, 0) + 1

    # Kahn's algorithm
    queue = deque(name for name, deg in in_degree.items() if deg == 0)
    sorted_count = 0

    while queue:
        node = queue.popleft()
        sorted_count += 1

        for neighbor in adj.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # If we couldn't sort all nodes, there's a cycle
    if sorted_count != len(nodes):
        cycle_nodes = [name for name, deg in in_degree.items() if deg > 0]
        raise NotADagError(cycle_nodes)
