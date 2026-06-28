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
    Headers are emitted in global edge order (strand 0 edges, then strand 1,
    ...), then wirings follow in that same global emission order.

Cap rendering (canonical vs aliased):
    By default (no registry) every edge is rendered by a synthetic ``edge_N``
    token bound to the cap URN by a ``[edge_N cap:...]`` header — the
    alias-independent identity form. When a registry is supplied (aliased
    rendering), a cap that has a registered display alias (shortest name, ties
    alphabetical) is referenced DIRECTLY in the wiring's cap position by that
    alias name with NO header — the grammar only permits a ``:``-free alias
    token in the wiring loop_cap position, never in a header (which requires a
    ``cap:`` URN). Un-aliased caps keep the ``edge_N`` token + header.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from capdag.machine.graph import Machine, MachineStrand


def _build_serialization_maps(
    graph: Machine,
    registry=None,
) -> Tuple[
    Dict[Tuple[int, int], str],
    Dict[Tuple[int, int], bool],
    Dict[Tuple[int, int], str],
    List[Tuple[int, int]],
]:
    """Build edge-token map, needs-header map, node name map, and emission order.

    Returns:
    - edge_tokens: (strand_idx, edge_idx) -> cap-position token. The synthetic
      ``edge_N`` for canonical/un-aliased rendering, or the cap's display alias
      for an aliased cap.
    - needs_header: (strand_idx, edge_idx) -> bool. True when the token is a
      synthetic ``edge_N`` (needs a ``[edge_N cap:...]`` header); False for a
      cap alias (referenced directly in the wiring, no header).
    - node_names: (strand_idx, node_id) -> node_name
    - emit_order: list of (strand_idx, edge_idx_in_strand) in emission order

    When ``registry`` is None this is the canonical (alias-independent) form:
    every edge token is ``edge_N`` and every edge needs a header. When a
    registry is supplied, an edge whose cap has a registered display alias gets
    that alias as its token with no header.
    """
    edge_tokens: Dict[Tuple[int, int], str] = {}
    needs_header: Dict[Tuple[int, int], bool] = {}
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

            # Cap-position token. Aliased rendering: a cap with a registered
            # display alias is referenced directly in the wiring (no header).
            alias_name = (
                registry.display_alias_for_urn(str(edge.cap_urn))
                if registry is not None
                else None
            )
            if alias_name is not None:
                edge_tokens[(s_idx, e_idx)] = alias_name
                needs_header[(s_idx, e_idx)] = False
            else:
                edge_tokens[(s_idx, e_idx)] = f"edge_{global_edge_counter}"
                needs_header[(s_idx, e_idx)] = True
            # The global edge counter advances for every edge regardless of
            # whether it produced a synthetic token, mirroring Rust's
            # `next_alias += 1` after every edge.
            global_edge_counter += 1
            emit_order.append((s_idx, e_idx))

    return edge_tokens, needs_header, node_names, emit_order


def _format_wiring(
    edge,
    token: str,
    s_idx: int,
    node_names: Dict[Tuple[int, int], str],
    open_delim: str,
    close_delim: str,
) -> str:
    """Format one wiring statement for a single edge."""
    sorted_bindings = sorted(edge.assignment, key=lambda b: b.source)
    sources = [node_names[(s_idx, b.source)] for b in sorted_bindings]
    target_name = node_names[(s_idx, edge.target)]
    loop_prefix = "LOOP " if edge.is_loop else ""

    if len(sources) == 1:
        return f"{open_delim}{sources[0]} -> {loop_prefix}{token} -> {target_name}{close_delim}"
    group = ", ".join(sources)
    return f"{open_delim}({group}) -> {loop_prefix}{token} -> {target_name}{close_delim}"


def _emit(graph: Machine, registry, bracketed: bool, joiner: str) -> str:
    """Shared emitter for the canonical/aliased bracketed and line-based forms.

    Headers (only for edges whose token is a synthetic ``edge_N``) come first in
    global edge order, then all wirings in that same order.
    """
    edge_tokens, needs_header, node_names, emit_order = _build_serialization_maps(
        graph, registry
    )

    open_delim = "[" if bracketed else ""
    close_delim = "]" if bracketed else ""
    output_parts: List[str] = []

    # Headers across all strands, in global edge order — only for un-aliased
    # edges (aliased caps are referenced directly in the wiring, no header).
    for s_idx, e_idx in emit_order:
        if needs_header[(s_idx, e_idx)]:
            edge = graph.strands()[s_idx].edges()[e_idx]
            token = edge_tokens[(s_idx, e_idx)]
            output_parts.append(f"{open_delim}{token} {edge.cap_urn}{close_delim}")

    # Wirings across all strands, in global edge order.
    for s_idx, e_idx in emit_order:
        edge = graph.strands()[s_idx].edges()[e_idx]
        token = edge_tokens[(s_idx, e_idx)]
        output_parts.append(
            _format_wiring(edge, token, s_idx, node_names, open_delim, close_delim)
        )

    return joiner.join(output_parts)


def to_machine_notation(graph: Machine) -> str:
    """Serialize to canonical one-line machine notation.

    The output is deterministic: same machine -> same string. Caps are rendered
    by their canonical URN (alias-independent identity form). Matches Rust's
    MachineSerializer canonical form.
    """
    if graph.is_empty():
        return ""
    return _emit(graph, None, bracketed=True, joiner="")


def to_machine_notation_multiline(graph: Machine) -> str:
    """Serialize to multi-line bracketed machine notation (one statement per line)."""
    if graph.is_empty():
        return ""
    return _emit(graph, None, bracketed=True, joiner="\n")


def to_machine_notation_formatted(graph: Machine, fmt: str) -> str:
    """Serialize to machine notation in the specified format.

    Args:
        graph: The machine to serialize.
        fmt: 'bracketed' (default) or 'line-based'.
    """
    if graph.is_empty():
        return ""
    bracketed = fmt == "bracketed"
    joiner = "" if bracketed else "\n"
    return _emit(graph, None, bracketed=bracketed, joiner=joiner)


def to_machine_notation_aliased(graph: Machine, registry, fmt: str = "bracketed") -> str:
    """Serialize rendering each cap by its registered display alias when one
    exists (shortest name, ties alphabetical), falling back to the canonical
    URN otherwise. This is the "store aliased" form: generated and persisted
    machines use it so the saved notation reads in terms of aliases. The parser
    resolves these aliases back to URNs on load (its async warm-up hydrates the
    alias cache), so the form round-trips.

    Args:
        graph: The machine to serialize.
        registry: The FabricRegistry used to reverse-resolve URNs to aliases.
        fmt: 'bracketed' (default) or 'line-based'.
    """
    if graph.is_empty():
        return ""
    bracketed = fmt == "bracketed"
    joiner = "" if bracketed else "\n"
    return _emit(graph, registry, bracketed=bracketed, joiner=joiner)


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


def to_render_payload_json(graph: Machine, registry=None) -> str:
    """Serialize to render payload JSON.

    Produces {"strands":[...]} with nodes, edges, input_anchor_nodes,
    output_anchor_nodes for each strand. Mirrors Rust's to_render_payload_json.

    The render payload is a display surface, so when a registry is supplied
    edges are labelled by the cap's display alias (aliased rendering), falling
    back to the synthetic ``edge_N`` for un-aliased caps.
    """
    if graph.is_empty():
        return '{"strands":[]}'

    edge_tokens, _needs_header, node_names, _emit_order = _build_serialization_maps(
        graph, registry
    )

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
            token = edge_tokens.get((s_idx, e_idx), f"edge_{e_idx}")
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
                f'{{"alias":"{token}",'
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
Machine.to_machine_notation_aliased = to_machine_notation_aliased  # type: ignore[attr-defined]
Machine.to_render_payload_json = to_render_payload_json  # type: ignore[attr-defined]
Machine.from_strand_path = staticmethod(from_strand)  # type: ignore[attr-defined]
