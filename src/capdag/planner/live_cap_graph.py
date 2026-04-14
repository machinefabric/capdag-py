"""LiveCapGraph — Precomputed capability graph for path finding

This module provides a live, incrementally-updated graph of capabilities
for efficient path finding and reachability queries.

Design Principles:
1. Typed URNs: Store MediaUrn and CapUrn directly, not strings.
2. Exact matching: For target matching, use is_equivalent() not conforms_to().
3. Conformance for traversal: Use conforms_to() for graph traversal.
4. Deterministic ordering: Results sorted by (path_length, specificity, urn).
5. ForEach is synthesized dynamically in get_outgoing_edges() when is_sequence=True
   and there are scalar consumers; it is never pre-inserted as a real graph edge.
6. Collect is not synthesized — it pairs implicitly with ForEach at execution time.
"""

from __future__ import annotations

import threading
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Set, Tuple

from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn


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
        "input_is_sequence", "output_is_sequence",
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
    ):
        self.from_spec = from_spec
        self.to_spec = to_spec
        self.edge_type = edge_type
        self.cap_urn = cap_urn
        self.cap_title = cap_title
        self.specificity_val = specificity_val
        self.input_is_sequence = input_is_sequence
        self.output_is_sequence = output_is_sequence

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


class StrandStepType(Enum):
    """Type of step in a capability chain path."""
    CAP = "cap"
    FOR_EACH = "for_each"
    COLLECT = "collect"


class StrandStep:
    """Information about a single step in a capability chain path."""

    __slots__ = (
        "step_type", "from_spec", "to_spec",
        "cap_urn", "step_title", "specificity_val",
        "media_spec",
        "input_is_sequence", "output_is_sequence",
    )

    def __init__(
        self,
        step_type: StrandStepType,
        from_spec: MediaUrn,
        to_spec: MediaUrn,
        cap_urn: Optional[CapUrn] = None,
        step_title: str = "",
        specificity_val: int = 0,
        media_spec: Optional[MediaUrn] = None,
        input_is_sequence: bool = False,
        output_is_sequence: bool = False,
    ):
        self.step_type = step_type
        self.from_spec = from_spec
        self.to_spec = to_spec
        self.cap_urn = cap_urn
        self.step_title = step_title
        self.specificity_val = specificity_val
        self.media_spec = media_spec
        self.input_is_sequence = input_is_sequence
        self.output_is_sequence = output_is_sequence

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
        "steps", "source_spec", "target_spec",
        "total_steps", "cap_step_count", "description",
    )

    def __init__(
        self,
        steps: List[StrandStep],
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

    def knit(self):
        """Convert this resolved path to a machine graph."""
        from capdag.machine.graph import Machine
        return Machine.from_path(self)

    def to_machine_notation(self) -> str:
        """Serialize to canonical one-line machine notation."""
        return self.knit().to_machine_notation()


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


class LiveCapGraph:
    """Precomputed graph of capabilities for path finding.

    Only Cap edges are stored in the graph.  ForEach edges are synthesized
    dynamically in _get_outgoing_edges() when is_sequence=True and there are
    scalar consumers reachable from the source node.
    """

    def __init__(self):
        self._edges: List[LiveMachinePlanEdge] = []
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
        """Rebuild the graph from a list of Cap definitions."""
        self.clear()
        for cap in caps:
            self.add_cap(cap)

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

        # Determine input_is_sequence from the stdin arg's is_sequence field.
        input_is_sequence = False
        for arg in cap.args:
            is_stdin = any(
                getattr(src, "stdin", None) is not None
                for src in getattr(arg, "sources", [])
            )
            if is_stdin:
                input_is_sequence = bool(getattr(arg, "is_sequence", False))
                break

        # Determine output_is_sequence from the cap's output field.
        output_is_sequence = False
        if cap.output is not None:
            output_is_sequence = bool(getattr(cap.output, "is_sequence", False))

        edge_idx = len(self._edges)
        edge = LiveMachinePlanEdge(
            from_spec=from_spec,
            to_spec=to_spec,
            edge_type=LiveMachinePlanEdgeType.CAP,
            cap_urn=cap.urn,
            cap_title=cap.title,
            specificity_val=cap.urn.specificity(),
            input_is_sequence=input_is_sequence,
            output_is_sequence=output_is_sequence,
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
        one Cap edge with not input_is_sequence whose from_spec source conforms to.
        """
        results: List[Tuple[LiveMachinePlanEdge, bool]] = []
        needs_foreach = False

        for edge in self._edges:
            if edge.edge_type != LiveMachinePlanEdgeType.CAP:
                continue
            if not source.conforms_to(edge.from_spec):
                continue
            if is_sequence and not edge.input_is_sequence:
                # Sequence data reaching a scalar cap — ForEach must be synthesized.
                needs_foreach = True
                continue
            results.append((edge, edge.output_is_sequence))

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
        """BFS reachability from source. Returns unique reachable targets."""
        # visited_nodes tracks (canonical, is_sequence) pairs to avoid re-expansion.
        visited_nodes: Set[Tuple[str, bool]] = set()
        # visited maps canonical string → ReachableTargetInfo for deduplication.
        visited: Dict[str, ReachableTargetInfo] = {}
        queue: deque = deque()

        # Seed with outgoing edges from source
        for edge, out_seq in self._get_outgoing_edges(source, is_sequence):
            queue.append((edge.to_spec, out_seq, 1))

        while queue:
            current_urn, cur_is_seq, depth = queue.popleft()
            if depth > max_depth:
                continue

            node_key = (str(current_urn), cur_is_seq)
            if node_key in visited_nodes:
                current_key = str(current_urn)
                if current_key in visited:
                    info = visited[current_key]
                    info.path_count += 1
                    if depth < info.min_path_length:
                        info.min_path_length = depth
                continue
            visited_nodes.add(node_key)

            current_key = str(current_urn)
            if current_key in visited:
                info = visited[current_key]
                info.path_count += 1
                if depth < info.min_path_length:
                    info.min_path_length = depth
            else:
                visited[current_key] = ReachableTargetInfo(
                    media_spec=current_urn,
                    display_name=current_key,
                    min_path_length=depth,
                    path_count=1,
                )

            for edge, out_seq in self._get_outgoing_edges(current_urn, cur_is_seq):
                queue.append((edge.to_spec, out_seq, depth + 1))

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
        is_sequence: bool,
        max_depth: int = 10,
        max_paths: int = 20,
    ) -> List[Strand]:
        """Iterative deepening DFS path finding with exact target matching (is_equivalent)."""
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
                path=[],
                visited=visited,
                depth_limit=depth_limit,
                max_paths=max_paths,
                results=results,
            )

        # Sort paths: cap_step_count ascending, total_specificity descending, cap URNs lexicographic
        results.sort(key=lambda p: (
            p.cap_step_count,
            -sum(s.specificity() for s in p.steps),
            [str(s.get_cap_urn()) for s in p.steps if s.is_cap()],
        ))

        return results

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

        # Sort
        results.sort(key=lambda p: (
            p.cap_step_count,
            -sum(s.specificity() for s in p.steps),
            [str(s.get_cap_urn()) for s in p.steps if s.is_cap()],
        ))

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
        path: List[LiveMachinePlanEdge],
        visited: Set[Tuple[str, bool]],
        depth_limit: int,
        max_paths: int,
        results: List[Strand],
    ) -> None:
        """Depth-limited DFS from current toward target."""
        if len(results) >= max_paths:
            return

        vk = (str(current), is_sequence)
        if vk in visited:
            return
        visited.add(vk)

        try:
            if current.is_equivalent(target):
                steps = []
                cap_count = 0
                for edge in path:
                    step = self._edge_to_step(edge)
                    steps.append(step)
                    if step.is_cap():
                        cap_count += 1

                if cap_count > 0:
                    titles = [s.title() for s in steps if s.is_cap()]
                    desc = " → ".join(titles)
                    results.append(Strand(
                        steps=steps,
                        source_spec=original_source,
                        target_spec=target,
                        total_steps=len(steps),
                        cap_step_count=cap_count,
                        description=desc,
                    ))
                return

            if depth_limit == 0:
                return

            for edge, out_seq in self._get_outgoing_edges(current, is_sequence):
                if len(results) >= max_paths:
                    return
                path.append(edge)
                self._iddfs_find(
                    original_source=original_source,
                    current=edge.to_spec,
                    target=target,
                    is_sequence=out_seq,
                    path=path,
                    visited=visited,
                    depth_limit=depth_limit - 1,
                    max_paths=max_paths,
                    results=results,
                )
                path.pop()
        finally:
            visited.discard(vk)

    def _edge_to_step(self, edge: LiveMachinePlanEdge) -> StrandStep:
        """Convert a LiveMachinePlanEdge to a StrandStep."""
        if edge.edge_type == LiveMachinePlanEdgeType.CAP:
            return StrandStep(
                step_type=StrandStepType.CAP,
                from_spec=edge.from_spec,
                to_spec=edge.to_spec,
                cap_urn=edge.cap_urn,
                step_title=edge.cap_title,
                specificity_val=edge.specificity_val,
                input_is_sequence=edge.input_is_sequence,
                output_is_sequence=edge.output_is_sequence,
            )
        elif edge.edge_type == LiveMachinePlanEdgeType.FOR_EACH:
            return StrandStep(
                step_type=StrandStepType.FOR_EACH,
                from_spec=edge.from_spec,
                to_spec=edge.to_spec,
                media_spec=edge.from_spec,
            )
        elif edge.edge_type == LiveMachinePlanEdgeType.COLLECT:
            return StrandStep(
                step_type=StrandStepType.COLLECT,
                from_spec=edge.from_spec,
                to_spec=edge.to_spec,
                media_spec=edge.from_spec,
            )
        raise ValueError(f"Unknown edge type: {edge.edge_type}")
