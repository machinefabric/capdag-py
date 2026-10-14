"""Machine notation serializer — the canonical text of a Machine.

The serializer walks the strands in declaration order and emits one notation
document covering all of them. Two strictly-equivalent Machines produce
byte-identical notation, because both the canonical edge order within each
strand and the allocation of step and node names are deterministic functions
of the resolved structure.

All headers come first, then all wirings. Steps are named ``edge_<n>`` in the
order of the walk across all strands; nodes are named ``n<n>`` in the order
the walk first meets them. Strand boundaries are unmarked: the parser
recovers them from shared node names, and each strand's node names are a
range of its own.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, List

from capdag.machine.constant import constant_text
from capdag.machine.error import UncachedCapError, UncachedMediaDefError
from capdag.machine.graph import Machine, MachineEdge

#: Each statement wrapped in ``[...]``: the canonical, single-line form used
#: as a stable identifier.
FORMAT_BRACKETED = "bracketed"
#: One statement per line, no brackets.
FORMAT_LINE_BASED = "line-based"


@dataclass
class _StrandPlan:
    """One strand's names."""

    #: The step-position token of each edge, in canonical edge order: the
    #: cap's display alias when the plan aliases and one exists, the
    #: synthetic ``edge_N`` otherwise.
    edge_tokens: List[str] = field(default_factory=list)
    #: True for a synthetic ``edge_N``, which a header binds to the cap URN.
    needs_header: List[bool] = field(default_factory=list)
    #: The name of each node, indexed by NodeId.
    node_names: List[str] = field(default_factory=list)


def _serialization_plan(graph: Machine, registry) -> List[_StrandPlan]:
    """Name every step and node of the machine. With a registry a cap that
    has a display alias is written by it."""
    plans: List[_StrandPlan] = []
    next_alias = 0
    next_node = 0
    for strand in graph.strands():
        plan = _StrandPlan(node_names=[""] * len(strand.nodes()))
        for edge in strand.edges():
            token = f"edge_{next_alias}"
            needs_header = True
            if registry is not None:
                alias = registry.display_alias_for_urn(edge.cap_urn.to_string())
                if alias is not None:
                    token, needs_header = alias, False
            plan.edge_tokens.append(token)
            plan.needs_header.append(needs_header)
            next_alias += 1
        # Nodes are named in the order the canonical edge walk first meets
        # them: each edge's sources in assignment order, then its outputs.
        # The name of a node is then a property of the machine, not of the
        # order its nodes happened to be allocated in — two inputs of one
        # type get the same names whichever was written first.
        named = [False] * len(strand.nodes())
        for edge in strand.edges():
            for node in edge.source_nodes() + edge.output_nodes():
                if not named[node]:
                    plan.node_names[node] = f"n{next_node}"
                    named[node] = True
                    next_node += 1
        for node, is_named in enumerate(named):
            if not is_named:
                raise AssertionError(
                    "every node of a strand is a source or an output of an edge: "
                    f"node {node} is neither"
                )
        plans.append(plan)
    return plans


def _format_wiring(edge: MachineEdge, token: str, plan: _StrandPlan) -> str:
    """Write one wiring statement for an edge, without brackets.

    Every binding is written under its arg's name and every taken output
    under its output's name, in the canonical (URN-sorted) order of the edge.
    Nothing is left for a reader of the text to match by type, so what is
    written resolves to the edge it was written from whatever other args the
    cap has. A gather writes its arg's name once per member, in item order.

    The per-item map (``edge.is_loop``) is not written: it is a derived
    cardinality property, and re-parsing derives the same from the cap
    shapes.
    """
    members = []
    for binding in edge.assignment:
        if binding.source.is_constant:
            members.append(f"{binding.arg_name}={constant_text(binding.source.constant)}")
        else:
            members.append(f"{binding.arg_name}={plan.node_names[binding.source.node]}")
    targets = [f"{output.output_name}={plan.node_names[output.node]}" for output in edge.outputs]
    return (
        f"({', '.join(members)}) -> {token}{edge.policy.to_notation()} -> ({', '.join(targets)})"
    )


def _emit(graph: Machine, plans: List[_StrandPlan], opening: str, closing: str, between: str) -> str:
    """Write every statement between ``opening`` and ``closing``, joined by
    ``between``."""
    if graph.is_empty():
        return ""
    statements: List[str] = []
    # Headers across all strands — only for edges whose step token is a
    # synthetic `edge_N`.
    for strand, plan in zip(graph.strands(), plans):
        for index, edge in enumerate(strand.edges()):
            if plan.needs_header[index]:
                statements.append(f"{opening}{plan.edge_tokens[index]} {edge.cap_urn}{closing}")
    # Wirings across all strands, in canonical edge order.
    for strand, plan in zip(graph.strands(), plans):
        for index, edge in enumerate(strand.edges()):
            statements.append(
                opening + _format_wiring(edge, plan.edge_tokens[index], plan) + closing
            )
    return between.join(statements)


def _emit_formatted(graph: Machine, plans: List[_StrandPlan], fmt: str) -> str:
    if fmt == FORMAT_BRACKETED:
        return _emit(graph, plans, "[", "]", "")
    if fmt == FORMAT_LINE_BASED:
        return _emit(graph, plans, "", "", "\n")
    raise ValueError(
        f"unknown notation format {fmt!r}: it is {FORMAT_BRACKETED!r} or {FORMAT_LINE_BASED!r}"
    )


def to_machine_notation(graph: Machine) -> str:
    """Serialize to canonical one-line bracketed notation. Caps are written
    by their canonical URN."""
    return _emit_formatted(graph, _serialization_plan(graph, None), FORMAT_BRACKETED)


def to_machine_notation_multiline(graph: Machine) -> str:
    """Serialize to multi-line bracketed notation: one statement per line,
    each wrapped in ``[...]``. The same statements as the canonical form, with
    newlines between them for reading."""
    return _emit(graph, _serialization_plan(graph, None), "[", "]", "\n")


def to_machine_notation_formatted(graph: Machine, fmt: str) -> str:
    """Serialize in the specified format (``FORMAT_BRACKETED`` or
    ``FORMAT_LINE_BASED``), caps written by their canonical URN."""
    return _emit_formatted(graph, _serialization_plan(graph, None), fmt)


def to_machine_notation_aliased(graph: Machine, registry, fmt: str = FORMAT_BRACKETED) -> str:
    """Serialize writing each cap by its registered display alias (shortest
    name, ties alphabetical) when one exists, and by a header otherwise.

    This is the "store aliased" form: generated and persisted machines use it
    so the saved notation reads in terms of aliases. An aliased cap is
    referenced directly in the wiring's step position by its alias, with no
    header (the grammar permits an alias only there, never in a header). The
    parser resolves the aliases back to URNs on load, so the form
    round-trips.
    """
    return _emit_formatted(graph, _serialization_plan(graph, registry), fmt)


def strand_to_machine_notation(strand, registry) -> str:
    """Knit a planner-produced Strand into a single-strand Machine and
    serialize it to one-line bracketed notation writing each cap by its
    registered display alias (the "store aliased" form). This is the notation
    used for generated/discovered paths and for persistence.

    Alias-independent canonical identity, when needed, comes from
    ``Machine.to_machine_notation()`` on the knitted machine — not this.
    """
    return to_machine_notation_aliased(Machine.from_strand(strand, registry), registry)


def _text(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def to_render_payload_json(graph: Machine, registry) -> str:
    """Serialize the machine to the JSON payload a graph view draws from::

        {"strands":[{"nodes":[{"id","urn","title"}],
                     "edges":[{"alias","cap_urn","title","is_loop","retry","on_error","included_as",
                               "assignment":[{"cap_arg_media_urn","arg_name","is_main_input",
                                              "source_node"|"constant"}],
                               "outputs":[{"output_media_urn","output_name","is_main_output",
                                           "node"}]}],
                     "input_anchor_nodes":[...],"output_anchor_nodes":[...]}]}

    Node names are those of the canonical notation, so a notation string and
    its render payload share node identities; each step is its canonical
    ``edge_N``. Each node carries the title of its cached media definition and
    each step the title of its cached cap definition. One that is not cached
    is refused (``UncachedMediaDefError``, ``UncachedCapError``): a title is
    never made up from a URN. Each binding and output says whether it is the
    step's main input or main output, by the step's definition, so a view
    draws the main wires plain and names the others.
    """
    if graph.is_empty():
        return '{"strands":[]}'
    plans = _serialization_plan(graph, None)

    def media_title(urn: str) -> str:
        spec = registry.get_cached_media_def(urn)
        if spec is None:
            raise UncachedMediaDefError(urn)
        return spec.title

    def cap_definition(urn: str):
        cap = registry.get_cached_cap(urn)
        if cap is None:
            raise UncachedCapError(urn)
        return cap

    def listed(items: List[str]) -> str:
        return "[" + ",".join(items) + "]"

    strands: List[str] = []
    for strand, plan in zip(graph.strands(), plans):
        nodes = [
            '{"id":'
            + _text(plan.node_names[node_id])
            + ',"urn":'
            + _text(urn.to_string())
            + ',"title":'
            + _text(media_title(urn.to_string()))
            + "}"
            for node_id, urn in enumerate(strand.nodes())
        ]
        edges: List[str] = []
        for index, edge in enumerate(strand.edges()):
            definition = cap_definition(edge.cap_urn.to_string())
            # A binding and an output carry the name the resolver read from
            # this same definition, where a name is unique: the definition's
            # main arg and main output are found by it.
            main_arg = definition.main_input_arg()
            main_output = definition.main_output()
            main_input_name = main_arg.name if main_arg is not None else None
            main_output_name = main_output.name if main_output is not None else None
            # Each binding says which arg (its URN and its name) and what
            # feeds it: a node of the strand, or a constant (a JSON value).
            assignment = []
            for binding in edge.assignment:
                if binding.source.is_constant:
                    fed = '"constant":' + constant_text(binding.source.constant)
                else:
                    fed = '"source_node":' + _text(plan.node_names[binding.source.node])
                assignment.append(
                    '{"cap_arg_media_urn":'
                    + _text(binding.cap_arg_media_urn.to_string())
                    + ',"arg_name":'
                    + _text(binding.arg_name)
                    + ',"is_main_input":'
                    + ("true" if binding.arg_name == main_input_name else "false")
                    + ","
                    + fed
                    + "}"
                )
            # Each output the step's wiring takes, and the node it goes to.
            outputs = [
                '{"output_media_urn":'
                + _text(output.output_media_urn.to_string())
                + ',"output_name":'
                + _text(output.output_name)
                + ',"is_main_output":'
                + ("true" if output.output_name == main_output_name else "false")
                + ',"node":'
                + _text(plan.node_names[output.node])
                + "}"
                for output in edge.outputs
            ]
            edges.append(
                '{"alias":'
                + _text(plan.edge_tokens[index])
                + ',"cap_urn":'
                + _text(edge.cap_urn.to_string())
                + ',"title":'
                + _text(definition.title)
                + ',"is_loop":'
                + ("true" if edge.is_loop else "false")
                + ',"retry":'
                + str(edge.policy.retry)
                + ',"on_error":'
                + _text(edge.policy.on_error)
                # The machine steps the step was included through, outermost
                # first: what a view groups the steps of an included machine
                # by.
                + ',"included_as":'
                + listed([_text(each) for each in edge.included_as])
                + ',"assignment":'
                + listed(assignment)
                + ',"outputs":'
                + listed(outputs)
                + "}"
            )
        strands.append(
            '{"nodes":'
            + listed(nodes)
            + ',"edges":'
            + listed(edges)
            + ',"input_anchor_nodes":'
            + listed([_text(plan.node_names[i]) for i in strand.input_anchor_ids()])
            + ',"output_anchor_nodes":'
            + listed([_text(plan.node_names[i]) for i in strand.output_anchor_ids()])
            + "}"
        )
    return '{"strands":' + listed(strands) + "}"


# Attach serialization methods to Machine.
Machine.to_machine_notation = to_machine_notation  # type: ignore[attr-defined]
Machine.to_machine_notation_multiline = to_machine_notation_multiline  # type: ignore[attr-defined]
Machine.to_machine_notation_formatted = to_machine_notation_formatted  # type: ignore[attr-defined]
Machine.to_machine_notation_aliased = to_machine_notation_aliased  # type: ignore[attr-defined]
Machine.to_render_payload_json = to_render_payload_json  # type: ignore[attr-defined]
