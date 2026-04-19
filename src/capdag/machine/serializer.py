"""Machine notation serializer — deterministic canonical form.

Converts a strand-based Machine to its machine notation string representation.
The output is deterministic: the same machine always produces the same string.

This matches the Rust serializer's canonical form exactly:

Alias Generation:
    Aliases are generated as edge_0, edge_1, ... in the global order they
    appear across all strands (strand order, then edge order within strand).
    This matches Rust's GlobalAliasCounter.

Node Name Generation:
    Node names are n0, n1, ... assigned globally across all strands in
    first-appearance order (strand order, then NodeId appearance order within
    each strand's edges). This matches Rust's GlobalNodeCounter.

Canonical Ordering:
    Headers are emitted sorted by alias (edge_0 < edge_1 < ...).
    Wirings follow in global emission order (strand 0 edges, then strand 1, ...).
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
    node_names: Dict[Tuple[int, int], str] = {}
    emit_order: List[Tuple[int, int]] = []

    global_edge_counter = 0
    global_node_counter = 0

    for s_idx, strand in enumerate(graph.strands()):
        # Assign node names globally in first-appearance order across all strands.
        # Walk edges in order; each new NodeId (source or target) gets the next nN name.
        seen_nodes: Dict[int, str] = {}

        for e_idx, edge in enumerate(strand.edges()):
            # Sources first (sorted by NodeId for determinism), then target.
            source_ids = sorted(b.source for b in edge.assignment)
            for nid in source_ids:
                if nid not in seen_nodes:
                    name = f"n{global_node_counter}"
                    global_node_counter += 1
                    seen_nodes[nid] = name
                    node_names[(s_idx, nid)] = name
            target_nid = edge.target
            if target_nid not in seen_nodes:
                name = f"n{global_node_counter}"
                global_node_counter += 1
                seen_nodes[target_nid] = name
                node_names[(s_idx, target_nid)] = name

            # Assign global edge alias.
            alias = f"edge_{global_edge_counter}"
            global_edge_counter += 1
            cap_str = str(edge.cap_urn)
            aliases[alias] = (s_idx, e_idx, cap_str)
            emit_order.append((s_idx, e_idx))

    return aliases, node_names, emit_order


def to_machine_notation(graph: Machine) -> str:
    """Serialize to canonical one-line machine notation.

    The output is deterministic: same machine -> same string.
    Matches Rust's MachineSerializer canonical form.
    """
    if graph.is_empty():
        return ""

    aliases, node_names, emit_order = _build_serialization_maps(graph)
    output_parts: List[str] = []

    # Emit headers in alias-sorted order (edge_0, edge_1, ...).
    sorted_aliases = sorted(aliases.items(), key=lambda item: item[0])
    for alias, (s_idx, e_idx, _cap_str) in sorted_aliases:
        edge = graph.strands()[s_idx].edges()[e_idx]
        output_parts.append(f"[{alias} {edge.cap_urn}]")

    # Emit wirings in emission order (strand order, then edge order within strand).
    for s_idx, e_idx in emit_order:
        edge = graph.strands()[s_idx].edges()[e_idx]
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


def _json_escape(s: str) -> str:
    """Minimal JSON string-escape for canonical CapUrn/MediaUrn text."""
    out: List[str] = []
    for c in s:
        if c == "\\":
            out.append("\\\\")
        elif c == '"':
            out.append('\\"')
        elif c == "\n":
            out.append("\\n")
        elif c == "\r":
            out.append("\\r")
        elif c == "\t":
            out.append("\\t")
        else:
            out.append(c)
    return "".join(out)


def to_render_payload_json(graph: Machine) -> str:
    """Serialize to render payload JSON.

    Produces {"strands":[...]} with nodes, edges, input_anchor_nodes,
    output_anchor_nodes for each strand. Mirrors Rust's to_render_payload_json.
    """
    if graph.is_empty():
        return '{"strands":[]}'

    aliases, node_names, emit_order = _build_serialization_maps(graph)

    # Build (s_idx, e_idx) -> alias reverse map
    edge_to_alias: Dict[Tuple[int, int], str] = {}
    for alias, (s_idx, e_idx, _) in aliases.items():
        edge_to_alias[(s_idx, e_idx)] = alias

    strand_parts: List[str] = []
    for s_idx, strand in enumerate(graph.strands()):
        # nodes
        nodes_json_parts: List[str] = []
        for node_id, urn in enumerate(strand.nodes()):
            name = node_names.get((s_idx, node_id), f"n{node_id}")
            nodes_json_parts.append(
                f'{{"id":"{name}","urn":"{_json_escape(str(urn))}"}}'
            )

        # edges
        edges_json_parts: List[str] = []
        for e_idx, edge in enumerate(strand.edges()):
            alias = edge_to_alias.get((s_idx, e_idx), f"edge_{e_idx}")
            is_loop_str = "true" if edge.is_loop else "false"
            assignment_parts: List[str] = []
            for b in edge.assignment:
                src_name = node_names.get((s_idx, b.source), f"n{b.source}")
                assignment_parts.append(
                    f'{{"cap_arg_media_urn":"{_json_escape(str(b.cap_arg_media_urn))}",'
                    f'"source_node":"{src_name}"}}'
                )
            target_name = node_names.get((s_idx, edge.target), f"n{edge.target}")
            edges_json_parts.append(
                f'{{"alias":"{alias}",'
                f'"cap_urn":"{_json_escape(str(edge.cap_urn))}",'
                f'"is_loop":{is_loop_str},'
                f'"assignment":[{",".join(assignment_parts)}],'
                f'"target_node":"{target_name}"}}'
            )

        # input_anchor_nodes
        input_names = [
            f'"{node_names.get((s_idx, i), f"n{i}")}"'
            for i in strand.input_anchor_ids()
        ]
        # output_anchor_nodes
        output_names = [
            f'"{node_names.get((s_idx, i), f"n{i}")}"'
            for i in strand.output_anchor_ids()
        ]

        strand_parts.append(
            f'{{"nodes":[{",".join(nodes_json_parts)}],'
            f'"edges":[{",".join(edges_json_parts)}],'
            f'"input_anchor_nodes":[{",".join(input_names)}],'
            f'"output_anchor_nodes":[{",".join(output_names)}]}}'
        )

    return f'{{"strands":[{",".join(strand_parts)}]}}'


# Attach methods to Machine at import time.
Machine.to_machine_notation = to_machine_notation  # type: ignore[attr-defined]
Machine.to_machine_notation_multiline = to_machine_notation_multiline  # type: ignore[attr-defined]
Machine.to_machine_notation_formatted = to_machine_notation_formatted  # type: ignore[attr-defined]
Machine.to_render_payload_json = to_render_payload_json  # type: ignore[attr-defined]
Machine.from_strand_path = staticmethod(from_strand)  # type: ignore[attr-defined]
