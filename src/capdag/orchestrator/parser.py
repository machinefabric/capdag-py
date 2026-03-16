"""Route notation parsing and Cap URN resolution for orchestration.

Parses route notation and resolves cap URNs via a registry, validates
the graph, and produces a validated, executable DAG IR.
Mirrors Rust's orchestrator/parser.rs exactly.
"""

from __future__ import annotations

from typing import Dict, List

from capdag.urn.media_urn import MediaUrn
from capdag.planner.cardinality import InputStructure
from capdag.route.graph import RouteGraph
from capdag.route.parser import _PARSER

from capdag.orchestrator.types import (
    CapRegistryTrait,
    ParseOrchestrationError,
    RouteNotationParseFailedError,
    CapNotFoundError,
    NodeMediaConflictError,
    MediaUrnParseError,
    StructureMismatchError,
    ResolvedEdge,
    ResolvedGraph,
)
from capdag.orchestrator.validation import validate_dag


def _media_urns_compatible(a: MediaUrn, b: MediaUrn) -> bool:
    """Check if two media URNs are on the same specialization chain.

    Returns True if either URN accepts the other, meaning they represent
    related media types where one may be more specific than the other.
    """
    try:
        return a.is_comparable(b)
    except Exception as e:
        raise MediaUrnParseError(str(e)) from e


def _check_structure_compatibility(
    source: MediaUrn,
    target: MediaUrn,
    node_name: str,
) -> None:
    """Check if two media URNs have compatible structures (record/opaque).

    Raises StructureMismatchError on conflict.
    """
    source_structure = InputStructure.RECORD if source.is_record() else InputStructure.OPAQUE
    target_structure = InputStructure.RECORD if target.is_record() else InputStructure.OPAQUE

    if source_structure != target_structure:
        raise StructureMismatchError(node_name, source_structure, target_structure)


class _WiringInfo:
    """Information about a single wiring statement's node names."""

    __slots__ = ("source_names", "target_name")

    def __init__(self, source_names: List[str], target_name: str) -> None:
        self.source_names = source_names
        self.target_name = target_name


def _extract_wiring_info(route: str) -> List[_WiringInfo]:
    """Extract wiring node names from route notation via the pest parser.

    The RouteGraph model intentionally discards alias/node names (they're
    serialization concerns). But the executor uses node names as data-flow
    keys. This function extracts them from the wiring statements in order.
    """
    try:
        parse_tree = _PARSER.parse("program", route.strip())
    except Exception as e:
        raise RouteNotationParseFailedError(str(e)) from e

    wirings: List[_WiringInfo] = []

    for pair in parse_tree:
        if pair.rule != "stmt":
            continue

        inner = _first_child(pair)
        content = _first_child(inner)

        if content.rule != "wiring":
            continue  # Skip headers — we only need wiring node names

        children = list(content)

        # Parse source (single alias or group)
        source_pair = children[0]
        source_names = _parse_source_names(source_pair)

        # Skip arrow (children[1])
        # Skip loop_cap (children[2])
        # Skip arrow (children[3])
        # Target alias (children[4])
        target_name = children[4].text

        wirings.append(_WiringInfo(source_names, target_name))

    return wirings


def _first_child(pair):
    """Get the first child of a parse tree pair."""
    for child in pair:
        return child
    raise RouteNotationParseFailedError(f"expected child in {pair.rule}")


def _parse_source_names(pair) -> List[str]:
    """Extract source node names from a source pair."""
    inner = _first_child(pair)
    if inner.rule == "group":
        return [p.text for p in inner if p.rule == "alias"]
    elif inner.rule == "alias":
        return [inner.text]
    else:
        raise RouteNotationParseFailedError(f"unexpected source rule: {inner.rule}")


async def parse_route_to_cap_dag(
    route: str,
    registry: CapRegistryTrait,
) -> ResolvedGraph:
    """Parse route notation and produce a validated orchestration graph.

    Each cap URN is resolved via the registry. Node media URNs are derived
    from the cap's in=/out= specs. Media type consistency and structure
    compatibility (record vs opaque) are validated at each node.

    Args:
        route: Route notation string.
        registry: Cap registry for resolving cap URNs.

    Returns:
        A validated ResolvedGraph.

    Raises:
        ParseOrchestrationError subclasses for any validation failure.
    """
    # Step 1: Parse route notation into a RouteGraph.
    try:
        route_graph = RouteGraph.from_string(route)
    except Exception as e:
        raise RouteNotationParseFailedError(str(e)) from e

    # Step 2: Extract node names from the route notation.
    wiring_info = _extract_wiring_info(route)

    # Validate that wiring count matches edge count.
    if len(wiring_info) != len(route_graph.edges()):
        raise RouteNotationParseFailedError(
            f"internal error: {len(wiring_info)} wirings but "
            f"{len(route_graph.edges())} edges — route parser edge ordering invariant violated"
        )

    # Step 3: For each edge, resolve cap via registry and build ResolvedEdge entries.
    node_media: Dict[str, MediaUrn] = {}
    resolved_edges: List[ResolvedEdge] = []

    for edge_idx, edge in enumerate(route_graph.edges()):
        cap_urn_str = str(edge.cap_urn)
        cap = await registry.lookup(cap_urn_str)

        try:
            cap_in_media = edge.cap_urn.in_media_urn()
        except Exception as e:
            raise MediaUrnParseError(str(e)) from e

        try:
            cap_out_media = edge.cap_urn.out_media_urn()
        except Exception as e:
            raise MediaUrnParseError(str(e)) from e

        wiring = wiring_info[edge_idx]

        # Build resolved edges — one per source (fan-in produces multiple edges)
        for i, src_name in enumerate(wiring.source_names):
            if i == 0:
                # Primary source: use cap's in= spec
                edge_in_media = cap_in_media
            else:
                # Secondary source (fan-in): resolve from existing assignment
                # or from the cap's args list
                existing = node_media.get(src_name)
                is_wildcard = existing is not None and str(existing) == "media:"
                if existing is not None and not is_wildcard:
                    edge_in_media = existing
                else:
                    # Resolve from cap.args — secondary sources map to args
                    # beyond the primary in= spec (arg index i-1 for source i)
                    arg_idx = i - 1
                    arg_media = None
                    if arg_idx < len(cap.args):
                        try:
                            arg_media = MediaUrn.from_string(cap.args[arg_idx].media_urn)
                        except Exception:
                            pass

                    if arg_media is not None:
                        edge_in_media = arg_media
                    else:
                        raise RouteNotationParseFailedError(
                            f"fan-in secondary source '{src_name}' (index {i}) has no media type "
                            f"and cap '{cap_urn_str}' has no matching arg at index {arg_idx}"
                        )

            # Validate source node media compatibility
            if src_name in node_media:
                existing_media = node_media[src_name]
                if not _media_urns_compatible(existing_media, edge_in_media):
                    raise NodeMediaConflictError(
                        src_name, str(existing_media), str(edge_in_media)
                    )
                _check_structure_compatibility(existing_media, edge_in_media, src_name)
            else:
                node_media[src_name] = edge_in_media

            # Validate target node media compatibility
            if wiring.target_name in node_media:
                existing_media = node_media[wiring.target_name]
                if not _media_urns_compatible(existing_media, cap_out_media):
                    raise NodeMediaConflictError(
                        wiring.target_name, str(existing_media), str(cap_out_media)
                    )
                _check_structure_compatibility(cap_out_media, existing_media, wiring.target_name)
            else:
                node_media[wiring.target_name] = cap_out_media

            resolved_edges.append(ResolvedEdge(
                from_node=src_name,
                to_node=wiring.target_name,
                cap_urn=cap_urn_str,
                cap=cap,
                in_media=str(edge_in_media),
                out_media=str(cap_out_media),
            ))

    # Step 4: DAG validation (cycle detection via topological sort)
    node_media_strings: Dict[str, str] = {
        k: str(v) for k, v in node_media.items()
    }
    validate_dag(node_media_strings, resolved_edges)

    return ResolvedGraph(
        nodes=node_media_strings,
        edges=resolved_edges,
        graph_name=None,
    )
