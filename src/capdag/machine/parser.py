"""Machine notation parser — PEG parser producing a strand-based Machine.

Parses the machine notation format into a Machine using the python-pest
library with the same grammar defined in machine.pest (shared with Rust).

Grammar (PEG / EBNF):

    program      = stmt*
    stmt         = "[" inner "]" | inner
    inner        = wiring | header
    header       = alias cap_urn
    wiring       = source arrow loop_cap arrow alias
    source       = group | alias
    group        = "(" alias ("," alias)+ ")"
    arrow        = "-"+ ">"
    loop_cap     = "LOOP" alias | alias
    alias        = (ALPHA | "_") (ALNUM | "_" | "-")*
    cap_urn      = "cap:" cap_urn_body*
    cap_urn_body = quoted_value | !("]" | NEWLINE) ANY
    quoted_value = '"' ('\\"' | '\\\\' | !'"' ANY)* '"'

Parsing phases:
    1. Pest parse — produce AST.
    2. Alias map — collect headers, check for duplicates.
    3. Node media derivation — derive MediaUrn for each node name.
    4. Wiring collection — validate aliases and node-alias collisions.
    5. Connected components — union-find partition of wirings into strands.
    6. Per-component resolution — resolve_pre_interned for each strand.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from pest import Parser as PestParser

from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn

from capdag.machine.error import (
    MachineSyntaxError,
    MachineAbstractionError,
    MachineParseError,
    EmptyMachineError,
    InvalidCapUrnError,
    UndefinedAliasError,
    DuplicateAliasError,
    InvalidWiringError,
    InvalidMediaUrnError,
    NoEdgesError,
    NodeAliasCollisionError,
    ParseError,
)
from capdag.machine.graph import Machine, NodeId
from capdag.machine.resolve import PreInternedWiring, resolve_pre_interned

# Load the pest grammar once at module level
_GRAMMAR_PATH = os.path.join(os.path.dirname(__file__), "machine.pest")
with open(_GRAMMAR_PATH, encoding="utf-8") as _f:
    _GRAMMAR = _f.read()

_PARSER = PestParser.from_grammar(_GRAMMAR)


def parse_machine(input_str: str, registry) -> Machine:
    """Parse machine notation into a strand-based Machine.

    Uses the pest-generated PEG parser to parse the input, derives
    node media URNs from cap in/out specs, partitions wirings into
    connected components via union-find, then resolves each component
    into a MachineStrand via the registry.

    Args:
        input_str: Machine notation string.
        registry: CapRegistry — caps referenced in headers must be pre-loaded.

    Returns:
        A fully-resolved Machine.

    Raises:
        MachineParseError wrapping either a MachineSyntaxError or
        MachineAbstractionError on any failure.
    """
    try:
        return _parse_machine_inner(input_str, registry)
    except MachineParseError:
        raise
    except MachineSyntaxError as e:
        raise MachineParseError(e) from e
    except MachineAbstractionError as e:
        raise MachineParseError(e) from e


def _parse_machine_inner(input_str: str, registry) -> Machine:
    """Inner implementation — raises MachineSyntaxError / MachineAbstractionError directly."""
    input_str = input_str.strip()
    if not input_str:
        raise EmptyMachineError()

    # Phase 1: Parse with pest grammar.
    try:
        parse_tree = _PARSER.parse("program", input_str)
    except Exception as e:
        raise ParseError(str(e)) from e

    # Phase 2: Walk AST and collect headers + wirings.
    headers: List[Tuple[str, CapUrn, int]] = []  # (alias, cap_urn, position)
    # (sources: List[str], cap_alias: str, target: str, is_loop: bool, position: int)
    raw_wirings: List[Tuple[List[str], str, str, bool, int]] = []

    program_pair = _first_child(parse_tree)
    stmt_idx = 0
    for pair in program_pair:
        if pair.rule.name != "stmt":
            continue

        inner = _first_child(pair)
        content = _first_child(inner)

        if content.rule.name == "header":
            children = list(content)
            alias = children[0].text
            cap_urn_str = children[1].text

            try:
                cap_urn = CapUrn.from_string(cap_urn_str)
            except Exception as e:
                raise InvalidCapUrnError(alias, str(e)) from e

            headers.append((alias, cap_urn, stmt_idx))

        elif content.rule.name == "wiring":
            children = list(content)
            source_pair = children[0]
            sources = _parse_source(source_pair)
            loop_cap_pair = children[2]
            is_loop, cap_alias = _parse_loop_cap(loop_cap_pair)
            target = children[4].text
            raw_wirings.append((sources, cap_alias, target, is_loop, stmt_idx))

        stmt_idx += 1

    # Phase 3: Build alias -> (CapUrn, position) map, checking for duplicates.
    alias_map: Dict[str, Tuple[CapUrn, int]] = {}
    for alias, cap_urn, position in headers:
        if alias in alias_map:
            first_pos = alias_map[alias][1]
            raise DuplicateAliasError(alias, first_pos)
        alias_map[alias] = (cap_urn, position)

    if not raw_wirings and headers:
        raise NoEdgesError()

    # Phase 4: Resolve raw wirings — derive node media URNs and build flat wiring records.
    # node_media: node_name -> MediaUrn (assigned by first use)
    node_media: Dict[str, MediaUrn] = {}
    # wiring_records: flat list of (sources, cap_urn, target, is_loop)
    wiring_records: List[Tuple[List[str], CapUrn, str, bool]] = []

    for sources, cap_alias, target, is_loop, position in raw_wirings:
        if cap_alias not in alias_map:
            raise UndefinedAliasError(cap_alias)
        cap_urn, _ = alias_map[cap_alias]

        # Node-alias collision check.
        for src in sources:
            if src in alias_map:
                raise NodeAliasCollisionError(src, src)
        if target in alias_map:
            raise NodeAliasCollisionError(target, target)

        # Derive media URNs from cap's in=/out= specs.
        try:
            cap_in_media = cap_urn.in_media_urn()
        except Exception as e:
            raise InvalidMediaUrnError(cap_alias, f"in= spec: {e}") from e

        try:
            cap_out_media = cap_urn.out_media_urn()
        except Exception as e:
            raise InvalidMediaUrnError(cap_alias, f"out= spec: {e}") from e

        # Assign/check source node media URNs.
        for i, src in enumerate(sources):
            if i == 0:
                _assign_or_check_node(src, cap_in_media, node_media, position)
            else:
                # Secondary fan-in source: use existing type if assigned, else wildcard.
                if src not in node_media:
                    node_media[src] = MediaUrn.from_string("media:")

        # Assign target node media URN.
        _assign_or_check_node(target, cap_out_media, node_media, position)

        wiring_records.append((sources, cap_urn, target, is_loop))

    if not wiring_records:
        raise EmptyMachineError()

    # Phase 5: Connected-components partition via union-find.
    # Each wiring belongs to one component; wirings that share a node name
    # belong to the same component.
    n = len(wiring_records)
    parent = list(range(n))
    rank_arr = [0] * n

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]  # path compression
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        if rank_arr[ra] < rank_arr[rb]:
            ra, rb = rb, ra
        parent[rb] = ra
        if rank_arr[ra] == rank_arr[rb]:
            rank_arr[ra] += 1

    # Map node_name -> index of the first wiring that mentions it.
    node_first_wiring: Dict[str, int] = {}
    for w_idx, (sources, _cap_urn, target, _is_loop) in enumerate(wiring_records):
        for node_name in list(sources) + [target]:
            if node_name in node_first_wiring:
                union(w_idx, node_first_wiring[node_name])
            else:
                node_first_wiring[node_name] = w_idx

    # Group wiring indices by their union-find root.
    groups: Dict[int, List[int]] = {}
    for w_idx in range(n):
        root = find(w_idx)
        groups.setdefault(root, []).append(w_idx)

    # Order groups by minimum wiring index (first-appearance order).
    ordered_groups = sorted(groups.values(), key=lambda g: min(g))

    # Phase 6: Per-component pre-interning + resolve_pre_interned.
    resolved_strands = []
    for strand_index, group in enumerate(ordered_groups):
        # Pre-intern nodes: assign NodeIds by node name within this component.
        component_node_ids: Dict[str, NodeId] = {}
        component_nodes = []

        def intern_node(name: str) -> NodeId:
            if name not in component_node_ids:
                nid = len(component_nodes)
                component_node_ids[name] = nid
                component_nodes.append(node_media[name])
            return component_node_ids[name]

        pre_interned: List[PreInternedWiring] = []
        for w_idx in group:
            sources_names, cap_urn, target_name, is_loop = wiring_records[w_idx]
            source_ids = [intern_node(s) for s in sources_names]
            target_id = intern_node(target_name)
            pre_interned.append(PreInternedWiring(
                cap_urn=cap_urn,
                source_node_ids=source_ids,
                target_node_id=target_id,
                is_loop=is_loop,
            ))

        strand = resolve_pre_interned(
            list(component_nodes), pre_interned, registry, strand_index
        )
        resolved_strands.append(strand)

    return Machine.from_resolved_strands(resolved_strands)


def _first_child(pair):
    """Get the first child of a parse tree pair."""
    for child in pair:
        return child
    raise ParseError(f"expected child in {pair.rule}")


def _parse_source(pair) -> List[str]:
    """Extract source node names from a source pair (single alias or group)."""
    inner = _first_child(pair)
    if inner.rule.name == "group":
        return [p.text for p in inner if p.rule.name == "alias"]
    elif inner.rule.name == "alias":
        return [inner.text]
    else:
        raise ParseError(f"unexpected source rule: {inner.rule}")


def _parse_loop_cap(pair) -> Tuple[bool, str]:
    """Extract is_loop flag and cap alias from a loop_cap pair."""
    is_loop = False
    cap_alias = ""
    for inner in pair:
        if inner.rule.name == "loop_keyword":
            is_loop = True
        elif inner.rule.name == "alias":
            cap_alias = inner.text
    return is_loop, cap_alias


def _assign_or_check_node(
    node: str,
    media_urn: MediaUrn,
    node_media: Dict[str, MediaUrn],
    position: int,
) -> None:
    """Assign a media URN to a node, or check consistency if already assigned."""
    if node in node_media:
        existing = node_media[node]
        if not existing.is_comparable(media_urn):
            raise InvalidWiringError(
                position,
                f"node '{node}' has conflicting media types: "
                f"existing '{existing}', new '{media_urn}'",
            )
    else:
        node_media[node] = media_urn
