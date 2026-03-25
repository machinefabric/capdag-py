"""Machine notation serializer — deterministic canonical form

Converts a Machine to its machine notation string representation.
The output is deterministic: the same graph always produces the same string.

Alias Generation:
Aliases are derived from the cap URN's op= tag value. If no op= tag
exists, aliases are generated as edge_0, edge_1, etc. Duplicate
aliases from identical op tags are disambiguated with numeric suffixes.

Node Name Generation:
Node names are generated deterministically from topological position.
The first root source is n0, etc. Intermediate nodes get names based
on their topological order.

Canonical Ordering:
Edges are sorted by (cap_urn canonical string, sources canonical, target canonical)
for stable output. Headers are emitted first (sorted by alias), then wirings
in the same edge order.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from capdag.machine.graph import MachineEdge, Machine


def _build_serialization_maps(
    graph: Machine,
) -> Tuple[Dict[str, Tuple[int, str]], Dict[str, str], List[int]]:
    """Build the alias map, node name map, and edge ordering for serialization.

    Returns:
    - aliases: alias -> (edge_index, cap_urn_string)
    - node_names: media_urn_canonical_string -> node_name
    - edge_order: edge indices in canonical order
    """
    edges = graph.edges()

    # Step 1: Generate canonical edge ordering
    edge_order = list(range(len(edges)))
    edge_order.sort(key=lambda idx: (
        str(edges[idx].cap_urn),
        [str(s) for s in edges[idx].sources],
        str(edges[idx].target),
    ))

    # Step 2: Generate aliases from op= tag
    aliases: Dict[str, Tuple[int, str]] = {}
    alias_counts: Dict[str, int] = {}

    for idx in edge_order:
        edge = edges[idx]
        base_alias = edge.cap_urn.get_tag("op")
        if base_alias is None:
            base_alias = f"edge_{idx}"

        count = alias_counts.get(base_alias, 0)
        if count == 0:
            alias = base_alias
        else:
            alias = f"{base_alias}_{count}"
        alias_counts[base_alias] = count + 1

        cap_str = str(edge.cap_urn)
        aliases[alias] = (idx, cap_str)

    # Step 3: Generate node names
    # Collect all unique media URNs, assign names in order of first appearance
    node_names: Dict[str, str] = {}
    node_counter = 0

    for idx in edge_order:
        edge = edges[idx]
        for src in edge.sources:
            key = str(src)
            if key not in node_names:
                node_names[key] = f"n{node_counter}"
                node_counter += 1
        target_key = str(edge.target)
        if target_key not in node_names:
            node_names[target_key] = f"n{node_counter}"
            node_counter += 1

    return aliases, node_names, edge_order


def to_machine_notation(graph: Machine) -> str:
    """Serialize this machine graph to canonical one-line machine notation.

    The output is deterministic: same graph -> same string. This is the
    primary serialization format for accessibility identifiers and
    comparison.
    """
    if graph.is_empty():
        return ""

    aliases, node_names, edge_order = _build_serialization_maps(graph)
    edges = graph.edges()
    output_parts: List[str] = []

    # Emit headers in alias-sorted order
    sorted_aliases = sorted(aliases.items(), key=lambda item: item[0])

    for alias, (edge_idx, _cap_str) in sorted_aliases:
        edge = edges[edge_idx]
        output_parts.append(f"[{alias} {edge.cap_urn}]")

    # Emit wirings in edge order
    for edge_idx in edge_order:
        edge = edges[edge_idx]
        # Find alias for this edge
        alias = None
        for a, (idx, _) in aliases.items():
            if idx == edge_idx:
                alias = a
                break

        # Source node name(s)
        sources = [node_names[str(s)] for s in edge.sources]

        # Target node name
        target_name = node_names[str(edge.target)]

        loop_prefix = "LOOP " if edge.is_loop else ""

        if len(sources) == 1:
            output_parts.append(f"[{sources[0]} -> {loop_prefix}{alias} -> {target_name}]")
        else:
            group = ", ".join(sources)
            output_parts.append(f"[({group}) -> {loop_prefix}{alias} -> {target_name}]")

    return "".join(output_parts)


def to_machine_notation_multiline(graph: Machine) -> str:
    """Serialize to multi-line machine notation (one statement per line)."""
    if graph.is_empty():
        return ""

    aliases, node_names, edge_order = _build_serialization_maps(graph)
    edges = graph.edges()
    output_lines: List[str] = []

    # Emit headers
    sorted_aliases = sorted(aliases.items(), key=lambda item: item[0])

    for alias, (edge_idx, _cap_str) in sorted_aliases:
        edge = edges[edge_idx]
        output_lines.append(f"[{alias} {edge.cap_urn}]")

    # Emit wirings
    for edge_idx in edge_order:
        edge = edges[edge_idx]
        alias = None
        for a, (idx, _) in aliases.items():
            if idx == edge_idx:
                alias = a
                break

        sources = [node_names[str(s)] for s in edge.sources]
        target_name = node_names[str(edge.target)]
        loop_prefix = "LOOP " if edge.is_loop else ""

        if len(sources) == 1:
            output_lines.append(f"[{sources[0]} -> {loop_prefix}{alias} -> {target_name}]")
        else:
            group = ", ".join(sources)
            output_lines.append(f"[({group}) -> {loop_prefix}{alias} -> {target_name}]")

    return "\n".join(output_lines)


def from_path(path) -> Machine:
    """Convert a Strand (resolved linear path) into a Machine.

    The conversion:
    - Each Cap step becomes a MachineEdge with a single source
    - ForEach steps set is_loop=True on the next Cap edge
    - Collect and WrapInList steps are elided (implicit in transitions)
    """
    from capdag.machine.graph import MachineEdge
    from capdag.planner.live_cap_graph import StrandStepType

    edges: List[MachineEdge] = []
    pending_loop = False

    for step in path.steps:
        if step.step_type == StrandStepType.CAP:
            edges.append(MachineEdge(
                sources=[step.from_spec],
                cap_urn=step.cap_urn,
                target=step.to_spec,
                is_loop=pending_loop,
            ))
            pending_loop = False
        elif step.step_type == StrandStepType.FOR_EACH:
            pending_loop = True
        # Collect and WrapInList are elided

    return Machine(edges)


# Attach methods to Machine
Machine.to_machine_notation = to_machine_notation  # type: ignore[attr-defined]
Machine.to_machine_notation_multiline = to_machine_notation_multiline  # type: ignore[attr-defined]
Machine.from_path = staticmethod(from_path)  # type: ignore[attr-defined]
