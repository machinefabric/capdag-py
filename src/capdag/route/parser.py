"""Route notation parser — pest-generated PEG parser

Parses the route notation format into a RouteGraph using the python-pest
library with the same grammar defined in route.pest (shared with Rust).

Grammar (PEG / EBNF):

    program      = stmt*
    stmt         = "[" inner "]"
    inner        = wiring | header
    header       = alias cap_urn
    wiring       = source arrow loop_cap arrow alias
    source       = group | alias
    group        = "(" alias ("," alias)+ ")"
    arrow        = "-"+ ">"
    loop_cap     = "LOOP" alias | alias
    alias        = (ALPHA | "_") (ALNUM | "_" | "-")*
    cap_urn      = "cap:" cap_urn_body*
    cap_urn_body = quoted_value | !"]" ANY
    quoted_value = '"' ('\\"' | '\\\\' | !'"' ANY)* '"'

Whitespace between tokens is handled implicitly by pest's WHITESPACE
rule. The alias and cap_urn rules are atomic (@{}), so whitespace
is not skipped inside them.

Media URN Derivation:

Node media URNs are derived from the cap's in= and out= specs:

- For [src -> cap_alias -> dst]: src gets cap's in=, dst gets cap's out=
- For fan-in [(primary, secondary) -> cap_alias -> dst]:
  - First group member gets cap's in= spec
  - Additional members must have types already assigned by prior wirings.
    If unassigned, they get wildcard media: — the orchestrator parser will
    resolve the real type from the cap's args via registry lookup.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from pest import Parser as PestParser

from capdag.urn.cap_urn import CapUrn
from capdag.urn.media_urn import MediaUrn

from capdag.route.error import (
    RouteNotationError,
    EmptyRouteError,
    InvalidCapUrnError,
    UndefinedAliasError,
    DuplicateAliasError,
    InvalidWiringError,
    InvalidMediaUrnError,
    NoEdgesError,
    NodeAliasCollisionError,
    ParseError,
)
from capdag.route.graph import RouteEdge, RouteGraph

# Load the pest grammar once at module level
_GRAMMAR_PATH = os.path.join(os.path.dirname(__file__), "route.pest")
with open(_GRAMMAR_PATH, encoding="utf-8") as _f:
    _GRAMMAR = _f.read()

_PARSER = PestParser.from_grammar(_GRAMMAR)


def parse_route_notation(input_str: str) -> RouteGraph:
    """Parse route notation into a RouteGraph.

    Uses the pest-generated PEG parser to parse the input, then resolves
    cap URNs and derives media URNs from cap in/out specs.

    Raises RouteNotationError for any parse failure. Fails hard — no
    fallbacks, no guessing, no recovery.
    """
    input_str = input_str.strip()
    if not input_str:
        raise EmptyRouteError()

    # Phase 1: Parse with pest grammar
    try:
        parse_tree = _PARSER.parse("program", input_str)
    except Exception as e:
        raise ParseError(str(e)) from e

    # Phase 2: Walk the AST and collect headers + wirings
    headers: List[Tuple[str, CapUrn, int]] = []  # (alias, cap_urn, position)
    wirings: List[Tuple[List[str], str, str, bool, int]] = []  # (sources, cap_alias, target, is_loop, position)

    stmt_idx = 0
    for pair in parse_tree:
        if pair.rule != "stmt":
            continue

        inner = _first_child(pair)
        content = _first_child(inner)

        if content.rule == "header":
            children = list(content)
            alias = children[0].text
            cap_urn_str = children[1].text

            try:
                cap_urn = CapUrn.from_string(cap_urn_str)
            except Exception as e:
                raise InvalidCapUrnError(alias, str(e)) from e

            headers.append((alias, cap_urn, stmt_idx))

        elif content.rule == "wiring":
            children = list(content)

            # Parse source (single alias or group)
            source_pair = children[0]
            sources = _parse_source(source_pair)

            # Skip first arrow (children[1])
            # Parse loop_cap (children[2])
            loop_cap_pair = children[2]
            is_loop, cap_alias = _parse_loop_cap(loop_cap_pair)

            # Skip second arrow (children[3])
            # Parse target alias (children[4])
            target = children[4].text

            wirings.append((sources, cap_alias, target, is_loop, stmt_idx))

        stmt_idx += 1

    # Phase 3: Build alias -> CapUrn map, checking for duplicates
    alias_map: Dict[str, Tuple[CapUrn, int]] = {}
    for alias, cap_urn, position in headers:
        if alias in alias_map:
            first_pos = alias_map[alias][1]
            raise DuplicateAliasError(alias, first_pos)
        alias_map[alias] = (cap_urn, position)

    # Phase 4: Resolve wirings into RouteEdges
    if not wirings and headers:
        raise NoEdgesError()

    node_media: Dict[str, MediaUrn] = {}
    edges: List[RouteEdge] = []

    for sources, cap_alias, target, is_loop, position in wirings:
        # Look up the cap alias
        if cap_alias not in alias_map:
            raise UndefinedAliasError(cap_alias)
        cap_urn, _ = alias_map[cap_alias]

        # Check node-alias collisions
        for src in sources:
            if src in alias_map:
                raise NodeAliasCollisionError(src, src)
        if target in alias_map:
            raise NodeAliasCollisionError(target, target)

        # Derive media URNs from cap's in=/out= specs
        try:
            cap_in_media = cap_urn.in_media_urn()
        except Exception as e:
            raise InvalidMediaUrnError(cap_alias, f"in= spec: {e}") from e

        try:
            cap_out_media = cap_urn.out_media_urn()
        except Exception as e:
            raise InvalidMediaUrnError(cap_alias, f"out= spec: {e}") from e

        # Resolve source media URNs
        source_urns: List[MediaUrn] = []
        for i, src in enumerate(sources):
            if i == 0:
                # Primary source: use cap's in= spec
                _assign_or_check_node(src, cap_in_media, node_media, position)
                source_urns.append(cap_in_media)
            else:
                # Secondary source (fan-in): use existing type if assigned,
                # otherwise use wildcard media:
                if src in node_media:
                    source_urns.append(node_media[src])
                else:
                    wildcard = MediaUrn.from_string("media:")
                    node_media[src] = wildcard
                    source_urns.append(wildcard)

        # Assign target media URN
        _assign_or_check_node(target, cap_out_media, node_media, position)

        edges.append(RouteEdge(
            sources=source_urns,
            cap_urn=cap_urn,
            target=cap_out_media,
            is_loop=is_loop,
        ))

    return RouteGraph(edges)


def _first_child(pair):
    """Get the first child of a parse tree pair."""
    for child in pair:
        return child
    raise ParseError(f"expected child in {pair.rule}")


def _parse_source(pair) -> List[str]:
    """Extract source node names from a source pair (single alias or group)."""
    inner = _first_child(pair)
    if inner.rule == "group":
        return [p.text for p in inner if p.rule == "alias"]
    elif inner.rule == "alias":
        return [inner.text]
    else:
        raise ParseError(f"unexpected source rule: {inner.rule}")


def _parse_loop_cap(pair) -> Tuple[bool, str]:
    """Extract is_loop flag and cap alias from a loop_cap pair."""
    is_loop = False
    cap_alias = ""
    for inner in pair:
        if inner.rule == "loop_keyword":
            is_loop = True
        elif inner.rule == "alias":
            cap_alias = inner.text
    return is_loop, cap_alias


def _assign_or_check_node(
    node: str,
    media_urn: MediaUrn,
    node_media: Dict[str, MediaUrn],
    position: int,
) -> None:
    """Assign a media URN to a node, or check consistency if already assigned.

    Uses MediaUrn.is_comparable() — two types on the same specialization
    chain are compatible.
    """
    if node in node_media:
        existing = node_media[node]
        compatible = existing.is_comparable(media_urn)
        if not compatible:
            raise InvalidWiringError(
                position,
                f"node '{node}' has conflicting media types: "
                f"existing '{existing}', new '{media_urn}'",
            )
    else:
        node_media[node] = media_urn
