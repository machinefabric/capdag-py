"""The syntax of machine notation: one walk of the parse tree into a list of
statements.

This is the only reader of the grammar's rules (``machine.pest``, shared with
the reference). The resolver's parser (``parser.py``) consumes the statements
for what they say. Nothing here knows a cap definition: a name is a name, a
node is a node, and whether either exists is the resolver's question.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, List, Optional

from pest import Parser as PestParser

from capdag.machine.constant import decode_constant
from capdag.machine.error import (
    InvalidPolicyError,
    ParseError,
    ReservedNodeNameError,
    SeveralUnnamedTargetsError,
    UnnamedConstantError,
)
from capdag.planner.policy import MAX_RETRY, ON_ERROR_ABSENT, StepPolicy

_GRAMMAR_PATH = os.path.join(os.path.dirname(__file__), "machine.pest")
with open(_GRAMMAR_PATH, encoding="utf-8") as _grammar_file:
    _PARSER = PestParser.from_grammar(_grammar_file.read())


@dataclass(frozen=True)
class SyntaxMember:
    """One member of a wiring's sources: a node or a constant, under the arg
    it names when it names one."""

    #: The arg the member names, or None when it names none.
    name: Optional[str]
    #: Whether the member is a constant; it is then `constant`, else `node`.
    is_constant: bool = False
    node: str = ""
    constant: Any = None


@dataclass(frozen=True)
class SyntaxTarget:
    """One target of a wiring."""

    #: The output the target names. Without one the target takes the step's
    #: main output.
    name: Optional[str]
    node: str


@dataclass(frozen=True)
class SyntaxWiring:
    """A wiring: one invocation."""

    sources: List[SyntaxMember]
    step: str
    policy: StepPolicy
    targets: List[SyntaxTarget]


CAP_HEADER = "cap_header"
MACHINE_HEADER = "machine_header"
WIRING = "wiring"


@dataclass(frozen=True)
class SyntaxStatement:
    """One statement of a program."""

    #: CAP_HEADER, MACHINE_HEADER or WIRING.
    kind: str
    #: The statement's index among the program's statements.
    position: int
    #: A header's alias.
    alias: str = ""
    #: The cap URN a cap header gives its alias.
    cap_urn: str = ""
    #: The unescaped reference a machine header gives its alias.
    reference: str = ""
    wiring: Optional[SyntaxWiring] = field(default=None)


#: The words the notation reads as constants. A node may not bear one.
RESERVED_NODE_NAMES = frozenset({"true", "false", "null"})


def _children(pair) -> list:
    return list(pair)


def _node(pair, position: int) -> str:
    name = pair.text
    if name in RESERVED_NODE_NAMES:
        raise ReservedNodeNameError(name, position)
    return name


def _constant(pair) -> Any:
    # The grammar's `constant` is JSON's value grammar: this is where its text
    # is read as the value it writes, and a number no constant can hold is
    # refused.
    text = pair.text.strip()
    try:
        return decode_constant(text)
    except ValueError as error:
        raise ParseError(f"{text} is not a JSON value: {error}") from error


def _member(pair, position: int) -> SyntaxMember:
    inner = _children(pair)[0]
    rule = inner.rule.name
    if rule == "named_member":
        name_pair, value = _children(inner)
        if value.rule.name == "constant":
            return SyntaxMember(name=name_pair.text, is_constant=True, constant=_constant(value))
        return SyntaxMember(name=name_pair.text, node=_node(value, position))
    if rule == "constant":
        # A constant has no type of its own to be matched by: it says which
        # arg it is for, or it is not a member.
        raise UnnamedConstantError(inner.text.strip(), position)
    if rule == "alias":
        return SyntaxMember(name=None, node=_node(inner, position))
    raise AssertionError(f"a member is named, a constant or an alias, not {rule}")


def _policy(pair, step: str, position: int) -> StepPolicy:
    retry = 0
    on_error = None
    seen = set()
    for entry in _children(pair):
        key_pair, value_pair = _children(entry)
        key = key_pair.text
        value = _children(value_pair)[0]
        if key in seen:
            raise InvalidPolicyError(step, position, f"'{key}' is given twice")
        if key == "retry":
            # A count of further attempts: a whole number, not negative.
            text = value.text
            whole = value.rule.name == "number" and text.isascii() and text.isdigit()
            if not whole or int(text) > MAX_RETRY:
                raise InvalidPolicyError(
                    step,
                    position,
                    f"retry takes a whole number of further attempts, not '{text}'",
                )
            retry = int(text)
        elif key == "on_error":
            if value.text != "absent":
                raise InvalidPolicyError(
                    step, position, f"on_error takes 'absent', not '{value.text}'"
                )
            on_error = ON_ERROR_ABSENT
        else:
            raise InvalidPolicyError(
                step, position, f"unknown key '{key}' (a policy takes retry and on_error)"
            )
        seen.add(key)
    if on_error is None:
        return StepPolicy(retry=retry)
    return StepPolicy(retry=retry, on_error=on_error)


def _wiring(pair, position: int) -> SyntaxWiring:
    # sources, arrow, step, arrow, targets
    sources_pair, _, step_pair, _, targets_pair = _children(pair)

    sources_inner = _children(sources_pair)[0]
    if sources_inner.rule.name == "alias":
        sources = [SyntaxMember(name=None, node=_node(sources_inner, position))]
    elif sources_inner.rule.name == "source_group":
        sources = [_member(each, position) for each in _children(sources_inner)]
    else:
        raise AssertionError(f"sources is a group or an alias, not {sources_inner.rule.name}")

    step_children = _children(step_pair)
    step = step_children[0].text
    policy = StepPolicy()
    if len(step_children) > 1:
        policy = _policy(step_children[1], step, position)

    targets_inner = _children(targets_pair)[0]
    targets: List[SyntaxTarget] = []
    if targets_inner.rule.name == "alias":
        targets.append(SyntaxTarget(name=None, node=_node(targets_inner, position)))
    elif targets_inner.rule.name == "target_group":
        for each in _children(targets_inner):
            inner = _children(each)[0]
            if inner.rule.name == "named_target":
                name_pair, node_pair = _children(inner)
                targets.append(SyntaxTarget(name=name_pair.text, node=_node(node_pair, position)))
            else:
                targets.append(SyntaxTarget(name=None, node=_node(inner, position)))
    else:
        raise AssertionError(f"targets is a group or an alias, not {targets_inner.rule.name}")

    # The unnamed target is the main output, and a step has one.
    unnamed = [target.node for target in targets if target.name is None]
    if len(unnamed) > 1:
        raise SeveralUnnamedTargetsError(position, unnamed)
    return SyntaxWiring(sources=sources, step=step, policy=policy, targets=targets)


def parse_syntax(input_str: str) -> List[SyntaxStatement]:
    """Read ``input_str`` into its statements, in the order written.

    Raises a ``MachineSyntaxError`` on text the grammar does not accept
    (``ParseError``) and on the rules the text alone decides. An input with
    no statement at all is not an error here: what an empty program means is
    the caller's question.
    """
    try:
        tree = _PARSER.parse("program", input_str)
    except Exception as error:
        raise ParseError(str(error)) from error

    statements: List[SyntaxStatement] = []
    program = _children(tree)[0]
    for stmt in program:
        if stmt.rule.name != "stmt":
            continue
        position = len(statements)
        content = _children(_children(stmt)[0])[0]
        rule = content.rule.name
        if rule == "header":
            alias_pair, cap_urn_pair = _children(content)
            statements.append(
                SyntaxStatement(
                    kind=CAP_HEADER,
                    position=position,
                    alias=alias_pair.text,
                    cap_urn=cap_urn_pair.text,
                )
            )
        elif rule == "machine_header":
            # alias, the `machine` keyword, the reference
            alias_pair, _, string_pair = _children(content)
            text = string_pair.text.strip()
            try:
                reference = decode_constant(text)
            except ValueError:
                reference = None
            if not isinstance(reference, str):
                raise ParseError(f"{text} is not a JSON string")
            statements.append(
                SyntaxStatement(
                    kind=MACHINE_HEADER,
                    position=position,
                    alias=alias_pair.text,
                    reference=reference,
                )
            )
        elif rule == "wiring":
            statements.append(
                SyntaxStatement(kind=WIRING, position=position, wiring=_wiring(content, position))
            )
        else:
            raise AssertionError(f"a statement is a header or a wiring, not {rule}")
    return statements
