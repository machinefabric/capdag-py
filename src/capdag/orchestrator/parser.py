"""Machine notation parsing and Cap URN resolution for orchestration.

Parses machine notation and resolves cap URNs via a registry, validates
the graph, and produces a validated, executable DAG IR.
Mirrors Rust's orchestrator/parser.rs exactly.
"""

from __future__ import annotations

from typing import Dict, List

from capdag.urn.media_urn import MediaUrn
from capdag.planner.cardinality import InputStructure
from capdag.machine.parser import _PARSER, parse_machine

from capdag.cap.registry import CapRegistry
from capdag.orchestrator.types import (
    ParseOrchestrationError,
    MachineSyntaxParseFailedError,
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

    __slots__ = ("source_names", "target_name", "cap_alias")

    def __init__(self, source_names: List[str], target_name: str, cap_alias: str) -> None:
        self.source_names = source_names
        self.target_name = target_name
        self.cap_alias = cap_alias


def _extract_wiring_and_header_info(notation: str):
    """Extract wiring node names and header alias→cap_urn map from machine notation.

    Returns (wirings, alias_to_cap_urn) where:
    - wirings: list of _WiringInfo in notation order, each carrying the cap alias
    - alias_to_cap_urn: dict mapping cap alias string → normalized cap URN string
    """
    try:
        parse_tree = _PARSER.parse("program", notation.strip())
    except Exception as e:
        raise MachineSyntaxParseFailedError(str(e)) from e

    wirings: List[_WiringInfo] = []
    alias_to_cap_urn: Dict[str, str] = {}

    program_pair = _first_child(parse_tree)
    for pair in program_pair:
        if pair.rule.name != "stmt":
            continue

        inner = _first_child(pair)
        content = _first_child(inner)

        if content.rule.name == "header":
            children = list(content)
            alias = children[0].text
            cap_urn_text = children[1].text
            # Normalize by parsing through CapUrn
            try:
                from capdag.urn.cap_urn import CapUrn
                alias_to_cap_urn[alias] = str(CapUrn.from_string(cap_urn_text))
            except Exception:
                alias_to_cap_urn[alias] = cap_urn_text

        elif content.rule.name == "wiring":
            children = list(content)

            # Parse source (single alias or group)
            source_pair = children[0]
            source_names = _parse_source_names(source_pair)

            # children[2] is loop_cap — its text is "LOOP alias" or just "alias"
            loop_cap_text = children[2].text.strip()
            cap_alias = loop_cap_text.removeprefix("LOOP").strip()

            # children[4] is the target alias
            target_name = children[4].text

            wirings.append(_WiringInfo(source_names, target_name, cap_alias))

    return wirings, alias_to_cap_urn


def _first_child(pair):
    """Get the first child of a parse tree pair."""
    for child in pair:
        return child
    raise MachineSyntaxParseFailedError(f"expected child in {pair.rule}")


def _parse_source_names(pair) -> List[str]:
    """Extract source node names from a source pair."""
    inner = _first_child(pair)
    if inner.rule.name == "group":
        return [p.text for p in inner if p.rule.name == "alias"]
    elif inner.rule.name == "alias":
        return [inner.text]
    else:
        raise MachineSyntaxParseFailedError(f"unexpected source rule: {inner.rule}")


async def parse_machine_to_cap_dag(
    notation: str,
    registry: CapRegistry,
) -> ResolvedGraph:
    """Parse machine notation and produce a validated orchestration graph.

    Each cap URN is resolved via the registry's get_cached_cap. Node media URNs are
    derived from the cap's in=/out= specs. Media type consistency and structure
    compatibility (record vs opaque) are validated at each node.
    Caps must be pre-loaded into the registry cache before calling this function.

    Args:
        notation: Machine notation string.
        registry: Cap registry — caps must be pre-loaded in cache.

    Returns:
        A validated ResolvedGraph.

    Raises:
        ParseOrchestrationError subclasses for any validation failure.
    """
    # Step 1: Parse machine notation into a strand-based Machine.
    # This performs full resolution (registry lookup + source-to-arg matching).
    try:
        machine = parse_machine(notation, registry)
    except Exception as e:
        raise MachineSyntaxParseFailedError(str(e)) from e

    # Step 2: Extract node names and header alias→cap_urn map from notation.
    wiring_info, alias_to_cap_urn = _extract_wiring_and_header_info(notation)

    # Flatten strands into an ordered list of edges for pairing with wiring_info.
    # Strands may reorder edges topologically, so we match by cap URN rather than position.
    all_strand_edges = []
    for strand in machine.strands():
        for edge in strand.edges():
            all_strand_edges.append(edge)

    # Build cap_urn → wiring lookup (normalized strings → _WiringInfo).
    # Fan-in caps appear once in headers but generate multiple edges; each edge
    # resolves to the same wiring info entry for that cap alias.
    cap_urn_to_wiring: Dict[str, _WiringInfo] = {}
    for w in wiring_info:
        normalized_urn = alias_to_cap_urn.get(w.cap_alias, w.cap_alias)
        cap_urn_to_wiring[normalized_urn] = w

    # Validate that wiring count matches edge count.
    if len(wiring_info) != len(all_strand_edges):
        raise MachineSyntaxParseFailedError(
            f"internal error: {len(wiring_info)} wirings but "
            f"{len(all_strand_edges)} edges — machine parser edge ordering invariant violated"
        )

    # Step 3: For each edge (in topological order), match to wiring info by cap URN.
    node_media: Dict[str, MediaUrn] = {}
    resolved_edges: List[ResolvedEdge] = []

    for edge_idx, edge in enumerate(all_strand_edges):
        cap_urn_str = str(edge.cap_urn)
        cap = registry.get_cached_cap(cap_urn_str)
        if cap is None:
            raise CapNotFoundError(f"Cap not found in registry cache: {cap_urn_str!r}")

        try:
            cap_in_media = edge.cap_urn.in_media_urn()
        except Exception as e:
            raise MediaUrnParseError(str(e)) from e

        try:
            cap_out_media = edge.cap_urn.out_media_urn()
        except Exception as e:
            raise MediaUrnParseError(str(e)) from e

        wiring = cap_urn_to_wiring.get(cap_urn_str)
        if wiring is None:
            # Fallback: positional match (for cases where alias lookup fails)
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
                        raise MachineSyntaxParseFailedError(
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
