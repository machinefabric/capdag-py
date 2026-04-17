"""Machine notation serializer — deterministic canonical form.

Converts a strand-based Machine to its machine notation string representation.
The output is deterministic: the same machine always produces the same string.

Serialization walks strands in order. Within each strand, edges are already in
canonical topological order (as produced by the resolver). Node names are
assigned per strand (scoped — two strands have disjoint NodeId spaces).
Global node names across strands are deduplicated with a strand prefix.

Alias Generation:
    Aliases are derived from the cap URN's op= tag value. If no op= tag
    exists, aliases are generated as edge_N. Duplicate aliases from identical
    op tags are disambiguated with numeric suffixes (machine-global).

Node Name Generation:
    Node names are generated deterministically from first-appearance order
    within each strand, prefixed by strand index: s0n0, s0n1, ..., s1n0, ...

Canonical Ordering:
    Headers are emitted sorted by alias. Wirings follow in strand order,
    then canonical edge order within each strand.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from capdag.machine.graph import Machine, MachineStrand


def _build_serialization_maps(
    graph: Machine,
) -> Tuple[Dict[str, Tuple[int, int, str]], Dict[Tuple[int, int], str], List[Tuple[int, int]]]:
    """Build alias map, node name map, and emission order for serialization.

    Returns:
    - aliases: alias -> (strand_idx, edge_idx_in_strand, cap_urn_string)
    - node_names: (strand_idx, node_id) -> node_name
    - emit_order: list of (strand_idx, edge_idx_in_strand) in emission order
    """
    aliases: Dict[str, Tuple[int, int, str]] = {}
    alias_counts: Dict[str, int] = {}
    node_names: Dict[Tuple[int, int], str] = {}
    emit_order: List[Tuple[int, int]] = []

    for s_idx, strand in enumerate(graph.strands()):
        # Assign node names for this strand: sXnY
        for node_id in range(len(strand.nodes())):
            node_names[(s_idx, node_id)] = f"s{s_idx}n{node_id}"

        for e_idx, edge in enumerate(strand.edges()):
            # Derive alias from op= tag or fallback.
            base_alias = edge.cap_urn.get_tag("op")
            if base_alias is None:
                base_alias = f"edge_{s_idx}_{e_idx}"

            count = alias_counts.get(base_alias, 0)
            alias = base_alias if count == 0 else f"{base_alias}_{count}"
            alias_counts[base_alias] = count + 1

            cap_str = str(edge.cap_urn)
            aliases[alias] = (s_idx, e_idx, cap_str)
            emit_order.append((s_idx, e_idx))

    return aliases, node_names, emit_order


def to_machine_notation(graph: Machine) -> str:
    """Serialize to canonical one-line machine notation.

    The output is deterministic: same machine -> same string.
    """
    if graph.is_empty():
        return ""

    aliases, node_names, emit_order = _build_serialization_maps(graph)
    output_parts: List[str] = []

    # Emit headers in alias-sorted order.
    sorted_aliases = sorted(aliases.items(), key=lambda item: item[0])
    for alias, (s_idx, e_idx, _cap_str) in sorted_aliases:
        edge = graph.strands()[s_idx].edges()[e_idx]
        output_parts.append(f"[{alias} {edge.cap_urn}]")

    # Emit wirings in emission order (strand order, then edge order within strand).
    for s_idx, e_idx in emit_order:
        edge = graph.strands()[s_idx].edges()[e_idx]
        # Find alias for this edge.
        alias = _alias_for(aliases, s_idx, e_idx)

        # Source node names from assignment bindings, sorted by source NodeId.
        sorted_bindings = sorted(edge.assignment, key=lambda b: b.source)
        sources = [node_names[(s_idx, b.source)] for b in sorted_bindings]

        target_name = node_names[(s_idx, edge.target)]
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

    aliases, node_names, emit_order = _build_serialization_maps(graph)
    output_lines: List[str] = []

    sorted_aliases = sorted(aliases.items(), key=lambda item: item[0])
    for alias, (s_idx, e_idx, _cap_str) in sorted_aliases:
        edge = graph.strands()[s_idx].edges()[e_idx]
        output_lines.append(f"[{alias} {edge.cap_urn}]")

    for s_idx, e_idx in emit_order:
        edge = graph.strands()[s_idx].edges()[e_idx]
        alias = _alias_for(aliases, s_idx, e_idx)

        sorted_bindings = sorted(edge.assignment, key=lambda b: b.source)
        sources = [node_names[(s_idx, b.source)] for b in sorted_bindings]
        target_name = node_names[(s_idx, edge.target)]
        loop_prefix = "LOOP " if edge.is_loop else ""

        if len(sources) == 1:
            output_lines.append(f"[{sources[0]} -> {loop_prefix}{alias} -> {target_name}]")
        else:
            group = ", ".join(sources)
            output_lines.append(f"[({group}) -> {loop_prefix}{alias} -> {target_name}]")

    return "\n".join(output_lines)


def to_machine_notation_formatted(graph: Machine, fmt: str) -> str:
    """Serialize to machine notation in the specified format.

    Args:
        graph: The machine to serialize.
        fmt: 'bracketed' (default) or 'line-based'.
    """
    if graph.is_empty():
        return ""

    aliases, node_names, emit_order = _build_serialization_maps(graph)

    bracketed = fmt == "bracketed"
    open_delim = "[" if bracketed else ""
    close_delim = "]" if bracketed else ""
    output_parts: List[str] = []

    sorted_aliases = sorted(aliases.items(), key=lambda item: item[0])
    for alias, (s_idx, e_idx, _cap_str) in sorted_aliases:
        edge = graph.strands()[s_idx].edges()[e_idx]
        output_parts.append(f"{open_delim}{alias} {edge.cap_urn}{close_delim}")

    for s_idx, e_idx in emit_order:
        edge = graph.strands()[s_idx].edges()[e_idx]
        alias = _alias_for(aliases, s_idx, e_idx)

        sorted_bindings = sorted(edge.assignment, key=lambda b: b.source)
        sources = [node_names[(s_idx, b.source)] for b in sorted_bindings]
        target_name = node_names[(s_idx, edge.target)]
        loop_prefix = "LOOP " if edge.is_loop else ""

        if len(sources) == 1:
            output_parts.append(
                f"{open_delim}{sources[0]} -> {loop_prefix}{alias} -> {target_name}{close_delim}"
            )
        else:
            group = ", ".join(sources)
            output_parts.append(
                f"{open_delim}({group}) -> {loop_prefix}{alias} -> {target_name}{close_delim}"
            )

    if bracketed:
        return "".join(output_parts)
    else:
        return "\n".join(output_parts)


def _alias_for(
    aliases: Dict[str, Tuple[int, int, str]],
    s_idx: int,
    e_idx: int,
) -> str:
    """Find the alias assigned to a specific (strand_idx, edge_idx) pair."""
    for alias, (si, ei, _) in aliases.items():
        if si == s_idx and ei == e_idx:
            return alias
    raise AssertionError(f"no alias found for strand {s_idx} edge {e_idx}")


def from_strand(path, registry) -> Machine:
    """Convert a planner Strand into a Machine via the resolver.

    Delegates to Machine.from_strand which uses resolve_strand internally.
    The cap registry is required for source-to-arg matching.
    """
    return Machine.from_strand(path, registry)


# Attach methods to Machine at import time.
Machine.to_machine_notation = to_machine_notation  # type: ignore[attr-defined]
Machine.to_machine_notation_multiline = to_machine_notation_multiline  # type: ignore[attr-defined]
Machine.to_machine_notation_formatted = to_machine_notation_formatted  # type: ignore[attr-defined]
Machine.from_strand_path = staticmethod(from_strand)  # type: ignore[attr-defined]
