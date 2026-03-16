"""LiveCapGraph — Precomputed capability graph for path finding

This module provides a live, incrementally-updated graph of capabilities
for efficient path finding and reachability queries.

Design Principles:
1. Typed URNs: Store MediaUrn and CapUrn directly, not strings.
2. Exact matching: For target matching, use is_equivalent() not conforms_to().
3. Conformance for traversal: Use conforms_to() for graph traversal.
4. Deterministic ordering: Results sorted by (path_length, specificity, urn).
"""

from __future__ import annotations

from collections import defaultdict, deque
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn
from capdag.planner.cardinality import InputCardinality


class LiveCapEdgeType(Enum):
    """Type of edge in the capability graph."""
    CAP = "cap"
    FOR_EACH = "for_each"
    COLLECT = "collect"
    WRAP_IN_LIST = "wrap_in_list"


class LiveCapEdge:
    """An edge in the live capability graph."""

    __slots__ = (
        "from_spec", "to_spec", "edge_type",
        "cap_urn", "cap_title", "specificity_val",
        "input_cardinality", "output_cardinality",
    )

    def __init__(
        self,
        from_spec: MediaUrn,
        to_spec: MediaUrn,
        edge_type: LiveCapEdgeType,
        cap_urn: Optional[CapUrn] = None,
        cap_title: str = "",
        specificity_val: int = 0,
        input_cardinality: InputCardinality = InputCardinality.SINGLE,
        output_cardinality: InputCardinality = InputCardinality.SINGLE,
    ):
        self.from_spec = from_spec
        self.to_spec = to_spec
        self.edge_type = edge_type
        self.cap_urn = cap_urn
        self.cap_title = cap_title
        self.specificity_val = specificity_val
        self.input_cardinality = input_cardinality
        self.output_cardinality = output_cardinality

    def title(self) -> str:
        if self.edge_type == LiveCapEdgeType.CAP:
            return self.cap_title
        elif self.edge_type == LiveCapEdgeType.FOR_EACH:
            return "ForEach (iterate over list)"
        elif self.edge_type == LiveCapEdgeType.COLLECT:
            return "Collect (gather results)"
        elif self.edge_type == LiveCapEdgeType.WRAP_IN_LIST:
            return "WrapInList (create single-item list)"
        return ""

    def specificity(self) -> int:
        if self.edge_type == LiveCapEdgeType.CAP:
            return self.specificity_val
        return 0

    def is_cap(self) -> bool:
        return self.edge_type == LiveCapEdgeType.CAP

    def get_cap_urn(self) -> Optional[CapUrn]:
        if self.edge_type == LiveCapEdgeType.CAP:
            return self.cap_urn
        return None


class CapChainStepType(Enum):
    """Type of step in a capability chain path."""
    CAP = "cap"
    FOR_EACH = "for_each"
    COLLECT = "collect"
    WRAP_IN_LIST = "wrap_in_list"


class CapChainStepInfo:
    """Information about a single step in a capability chain path."""

    __slots__ = (
        "step_type", "from_spec", "to_spec",
        "cap_urn", "step_title", "specificity_val",
        "list_spec", "item_spec",
    )

    def __init__(
        self,
        step_type: CapChainStepType,
        from_spec: MediaUrn,
        to_spec: MediaUrn,
        cap_urn: Optional[CapUrn] = None,
        step_title: str = "",
        specificity_val: int = 0,
        list_spec: Optional[MediaUrn] = None,
        item_spec: Optional[MediaUrn] = None,
    ):
        self.step_type = step_type
        self.from_spec = from_spec
        self.to_spec = to_spec
        self.cap_urn = cap_urn
        self.step_title = step_title
        self.specificity_val = specificity_val
        self.list_spec = list_spec
        self.item_spec = item_spec

    def title(self) -> str:
        if self.step_type == CapChainStepType.CAP:
            return self.step_title
        elif self.step_type == CapChainStepType.FOR_EACH:
            return "ForEach"
        elif self.step_type == CapChainStepType.COLLECT:
            return "Collect"
        elif self.step_type == CapChainStepType.WRAP_IN_LIST:
            return "WrapInList"
        return ""

    def specificity(self) -> int:
        if self.step_type == CapChainStepType.CAP:
            return self.specificity_val
        return 0

    def get_cap_urn(self) -> Optional[CapUrn]:
        if self.step_type == CapChainStepType.CAP:
            return self.cap_urn
        return None

    def is_cap(self) -> bool:
        return self.step_type == CapChainStepType.CAP


class CapChainPathInfo:
    """Information about a complete capability chain path."""

    __slots__ = (
        "steps", "source_spec", "target_spec",
        "total_steps", "cap_step_count", "description",
    )

    def __init__(
        self,
        steps: List[CapChainStepInfo],
        source_spec: MediaUrn,
        target_spec: MediaUrn,
        total_steps: int,
        cap_step_count: int,
        description: str,
    ):
        self.steps = steps
        self.source_spec = source_spec
        self.target_spec = target_spec
        self.total_steps = total_steps
        self.cap_step_count = cap_step_count
        self.description = description

    def to_route_graph(self):
        """Convert this resolved path to a route graph."""
        from capdag.route.graph import RouteGraph
        return RouteGraph.from_path(self)

    def to_route_notation(self) -> str:
        """Serialize to canonical one-line route notation."""
        return self.to_route_graph().to_route_notation()


class ReachableTargetInfo:
    """Information about a reachable target from a source media type."""

    __slots__ = ("media_spec", "display_name", "min_path_length", "path_count")

    def __init__(
        self,
        media_spec: MediaUrn,
        display_name: str,
        min_path_length: int,
        path_count: int,
    ):
        self.media_spec = media_spec
        self.display_name = display_name
        self.min_path_length = min_path_length
        self.path_count = path_count


class LiveCapGraph:
    """Precomputed graph of capabilities for path finding."""

    def __init__(self):
        self._edges: List[LiveCapEdge] = []
        self._outgoing: Dict[str, List[int]] = defaultdict(list)
        self._incoming: Dict[str, List[int]] = defaultdict(list)
        self._nodes: Set[str] = set()
        self._cap_to_edges: Dict[str, List[int]] = defaultdict(list)

    def clear(self):
        """Clear the graph completely."""
        self._edges.clear()
        self._outgoing.clear()
        self._incoming.clear()
        self._nodes.clear()
        self._cap_to_edges.clear()

    def sync_from_caps(self, caps) -> None:
        """Rebuild the graph from a list of Cap definitions.

        After adding all cap edges, inserts cardinality transition
        edges (ForEach/Collect) to enable paths through list→singular boundaries.
        """
        self.clear()
        for cap in caps:
            self.add_cap(cap)
        self._insert_cardinality_transitions()

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

        from_canonical = str(from_spec)
        to_canonical = str(to_spec)
        cap_canonical = str(cap.urn)

        input_card = InputCardinality.from_media_urn(from_canonical)
        output_card = InputCardinality.from_media_urn(to_canonical)

        edge_idx = len(self._edges)
        edge = LiveCapEdge(
            from_spec=from_spec,
            to_spec=to_spec,
            edge_type=LiveCapEdgeType.CAP,
            cap_urn=cap.urn,
            cap_title=cap.title,
            specificity_val=cap.urn.specificity(),
            input_cardinality=input_card,
            output_cardinality=output_card,
        )
        self._edges.append(edge)

        self._outgoing[from_canonical].append(edge_idx)
        self._incoming[to_canonical].append(edge_idx)
        self._nodes.add(from_canonical)
        self._nodes.add(to_canonical)
        self._cap_to_edges[cap_canonical].append(edge_idx)

    def stats(self) -> Tuple[int, int]:
        """Return (node_count, edge_count)."""
        return len(self._nodes), len(self._edges)

    def _insert_cardinality_transitions(self) -> None:
        """Insert ForEach/Collect/WrapInList edges for cardinality transitions."""
        # Collect all existing list-type nodes
        list_nodes: List[str] = [n for n in self._nodes if "list" in n]

        for list_canonical in list_nodes:
            list_urn = MediaUrn.from_string(list_canonical)
            item_urn = list_urn.without_list()
            item_canonical = str(item_urn)

            # ForEach: list → item (if item is a valid node or has outgoing edges)
            foreach_idx = len(self._edges)
            foreach_edge = LiveCapEdge(
                from_spec=list_urn,
                to_spec=item_urn,
                edge_type=LiveCapEdgeType.FOR_EACH,
                input_cardinality=InputCardinality.SEQUENCE,
                output_cardinality=InputCardinality.SINGLE,
            )
            self._edges.append(foreach_edge)
            self._outgoing[list_canonical].append(foreach_idx)
            self._incoming[item_canonical].append(foreach_idx)
            self._nodes.add(item_canonical)

            # Collect: item → list
            collect_idx = len(self._edges)
            collect_edge = LiveCapEdge(
                from_spec=item_urn,
                to_spec=list_urn,
                edge_type=LiveCapEdgeType.COLLECT,
                input_cardinality=InputCardinality.SINGLE,
                output_cardinality=InputCardinality.SEQUENCE,
            )
            self._edges.append(collect_edge)
            self._outgoing[item_canonical].append(collect_idx)
            self._incoming[list_canonical].append(collect_idx)

        # WrapInList: for each non-list node that has a list counterpart in targets
        non_list_nodes = [n for n in self._nodes if "list" not in n]
        for item_canonical in non_list_nodes:
            item_urn = MediaUrn.from_string(item_canonical)
            list_urn = item_urn.with_list()
            list_canonical = str(list_urn)

            if list_canonical in self._nodes:
                wrap_idx = len(self._edges)
                wrap_edge = LiveCapEdge(
                    from_spec=item_urn,
                    to_spec=list_urn,
                    edge_type=LiveCapEdgeType.WRAP_IN_LIST,
                    input_cardinality=InputCardinality.SINGLE,
                    output_cardinality=InputCardinality.SEQUENCE,
                )
                self._edges.append(wrap_edge)
                self._outgoing[item_canonical].append(wrap_idx)
                self._incoming[list_canonical].append(wrap_idx)

    def _get_outgoing_edges(self, source: MediaUrn) -> List[LiveCapEdge]:
        """Get all edges reachable from this source (using conforms_to for traversal)."""
        results = []
        source_is_list = source.is_list()

        for edge in self._edges:
            edge_expects_list = edge.from_spec.is_list()

            # Cardinality compatibility check
            if edge.edge_type == LiveCapEdgeType.CAP:
                if edge_expects_list != source_is_list:
                    continue
            elif edge.edge_type == LiveCapEdgeType.FOR_EACH:
                if not (source_is_list and not edge.to_spec.is_list()):
                    continue
            elif edge.edge_type in (LiveCapEdgeType.COLLECT, LiveCapEdgeType.WRAP_IN_LIST):
                if not (not source_is_list and edge.to_spec.is_list()):
                    continue

            # Media type compatibility
            if source.conforms_to(edge.from_spec):
                results.append(edge)

        return results

    def get_reachable_targets(
        self,
        source: MediaUrn,
        max_depth: int = 10,
    ) -> List[ReachableTargetInfo]:
        """BFS reachability from source. Returns unique reachable targets."""
        visited: Dict[str, ReachableTargetInfo] = {}
        queue: deque = deque()

        # Seed with outgoing edges from source
        for edge in self._get_outgoing_edges(source):
            target_key = str(edge.to_spec)
            queue.append((edge.to_spec, 1))

        while queue:
            current_urn, depth = queue.popleft()
            if depth > max_depth:
                continue

            current_key = str(current_urn)

            if current_key in visited:
                info = visited[current_key]
                info.path_count += 1
                if depth < info.min_path_length:
                    info.min_path_length = depth
                continue

            visited[current_key] = ReachableTargetInfo(
                media_spec=current_urn,
                display_name=current_key,
                min_path_length=depth,
                path_count=1,
            )

            # Explore next edges
            for edge in self._get_outgoing_edges(current_urn):
                queue.append((edge.to_spec, depth + 1))

        # Sort: min_path_length ascending, then display_name
        results = sorted(
            visited.values(),
            key=lambda r: (r.min_path_length, r.display_name),
        )
        return results

    def find_paths_to_exact_target(
        self,
        source: MediaUrn,
        target: MediaUrn,
        max_depth: int = 10,
        max_paths: int = 20,
    ) -> List[CapChainPathInfo]:
        """DFS path finding with exact target matching (is_equivalent)."""
        results: List[CapChainPathInfo] = []

        def dfs(
            current: MediaUrn,
            path: List[LiveCapEdge],
            visited_edges: Set[int],
            depth: int,
        ):
            if len(results) >= max_paths:
                return
            if depth > max_depth:
                return

            # Check if we've reached the target (exact match)
            if current.is_equivalent(target):
                # Build CapChainPathInfo from edge path
                steps = []
                cap_count = 0
                for edge in path:
                    step = self._edge_to_step(edge)
                    steps.append(step)
                    if step.is_cap():
                        cap_count += 1

                if cap_count > 0:  # Must have at least one real cap step
                    titles = [s.title() for s in steps if s.is_cap()]
                    desc = " → ".join(titles)
                    results.append(CapChainPathInfo(
                        steps=steps,
                        source_spec=source,
                        target_spec=target,
                        total_steps=len(steps),
                        cap_step_count=cap_count,
                        description=desc,
                    ))
                return

            # Explore outgoing edges
            for i, edge in enumerate(self._edges):
                if i in visited_edges:
                    continue

                # Check if this edge is reachable from current
                source_is_list = current.is_list()
                edge_expects_list = edge.from_spec.is_list()

                if edge.edge_type == LiveCapEdgeType.CAP:
                    if edge_expects_list != source_is_list:
                        continue
                elif edge.edge_type == LiveCapEdgeType.FOR_EACH:
                    if not (source_is_list and not edge.to_spec.is_list()):
                        continue
                elif edge.edge_type in (LiveCapEdgeType.COLLECT, LiveCapEdgeType.WRAP_IN_LIST):
                    if not (not source_is_list and edge.to_spec.is_list()):
                        continue

                if not current.conforms_to(edge.from_spec):
                    continue

                new_visited = visited_edges | {i}
                path.append(edge)
                dfs(edge.to_spec, path, new_visited, depth + 1)
                path.pop()

        dfs(source, [], set(), 0)

        # Sort paths: cap_step_count ascending, total_specificity descending, cap URNs lexicographic
        results.sort(key=lambda p: (
            p.cap_step_count,
            -sum(s.specificity() for s in p.steps),
            [str(s.get_cap_urn()) for s in p.steps if s.is_cap()],
        ))

        return results

    def _edge_to_step(self, edge: LiveCapEdge) -> CapChainStepInfo:
        """Convert a LiveCapEdge to a CapChainStepInfo."""
        if edge.edge_type == LiveCapEdgeType.CAP:
            return CapChainStepInfo(
                step_type=CapChainStepType.CAP,
                from_spec=edge.from_spec,
                to_spec=edge.to_spec,
                cap_urn=edge.cap_urn,
                step_title=edge.cap_title,
                specificity_val=edge.specificity_val,
            )
        elif edge.edge_type == LiveCapEdgeType.FOR_EACH:
            return CapChainStepInfo(
                step_type=CapChainStepType.FOR_EACH,
                from_spec=edge.from_spec,
                to_spec=edge.to_spec,
                list_spec=edge.from_spec,
                item_spec=edge.to_spec,
            )
        elif edge.edge_type == LiveCapEdgeType.COLLECT:
            return CapChainStepInfo(
                step_type=CapChainStepType.COLLECT,
                from_spec=edge.from_spec,
                to_spec=edge.to_spec,
                item_spec=edge.from_spec,
                list_spec=edge.to_spec,
            )
        elif edge.edge_type == LiveCapEdgeType.WRAP_IN_LIST:
            return CapChainStepInfo(
                step_type=CapChainStepType.WRAP_IN_LIST,
                from_spec=edge.from_spec,
                to_spec=edge.to_spec,
                item_spec=edge.from_spec,
                list_spec=edge.to_spec,
            )
        raise ValueError(f"Unknown edge type: {edge.edge_type}")
