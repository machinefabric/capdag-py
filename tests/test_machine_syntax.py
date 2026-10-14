"""Tests for the syntax of machine notation: what the text alone says, and
what it alone refuses."""

import pytest

from capdag.machine.constant import constant_text, constants_equal, decode_constant
from capdag.machine.error import (
    InvalidPolicyError,
    MachineSyntaxError,
    ParseError,
    ReservedNodeNameError,
    SeveralUnnamedTargetsError,
    UnnamedConstantError,
)
from capdag.machine.syntax import (
    CAP_HEADER,
    MACHINE_HEADER,
    WIRING,
    SyntaxWiring,
    parse_syntax,
)
from capdag.planner.policy import ON_ERROR_ABSENT, ON_ERROR_FAIL, StepPolicy


def _wirings(input_str: str):
    return [s.wiring for s in parse_syntax(input_str) if s.kind == WIRING]


def _one(input_str: str) -> SyntaxWiring:
    wirings = _wirings(input_str)
    assert len(wirings) == 1, input_str
    return wirings[0]


# A member or a target as the tests read it: the name it bears (None for
# none) and its node, or `=` and its constant's text.
def _named(name: str, value: str):
    return (name, value)


def _bare(value: str):
    return (None, value)


def _members(wiring: SyntaxWiring):
    return [
        (member.name, "=" + constant_text(member.constant) if member.is_constant else member.node)
        for member in wiring.sources
    ]


def _targets(wiring: SyntaxWiring):
    return [(target.name, target.node) for target in wiring.targets]


# TEST12732: every form of a wiring's sources and targets reads as the spec
# writes it: a bare node, a group of nodes, named members, constants of every
# JSON kind, an empty group on either side, and several targets with at most
# one unnamed. Both statement forms read alike.
def test_12732_the_forms_of_a_wiring():
    w = _one("doc -> extract -> text")
    assert _members(w) == [_bare("doc")]
    assert w.step == "extract"
    assert _targets(w) == [_bare("text")]
    assert w.policy.is_default()

    w = _one("[(thumbnail, model_spec) -> describe -> description]")
    assert _members(w) == [_bare("thumbnail"), _bare("model_spec")]

    w = _one("(path, benchmark=bench) -> compare -> result")
    assert _members(w) == [_bare("path"), _named("benchmark", "bench")]

    w = _one('(prices, window=20, statistic="mean") -> rolling -> smooth')
    assert _members(w) == [
        _bare("prices"), _named("window", "=20"), _named("statistic", '="mean"'),
    ]

    # A source fed only by constants, and one fed nothing at all.
    w = _one('(reference="fred/UNRATE") -> fetch -> series')
    assert _members(w) == [_named("reference", '="fred/UNRATE"')]
    w = _one("() -> now -> stamp")
    assert w.sources == []
    assert _targets(w) == [_bare("stamp")]

    # A sink, and several outputs.
    w = _one("report -> publish -> ()")
    assert w.targets == []
    w = _one("obs -> regress -> (fit, residuals=res)")
    assert _targets(w) == [_bare("fit"), _named("residuals", "res")]
    w = _one("item -> route -> (yes=kept, no=dropped)")
    assert _targets(w) == [_named("yes", "kept"), _named("no", "dropped")]

    # A group of one is a group.
    assert _members(_one("(x) -> f -> y")) == [_bare("x")]
    assert _targets(_one("x -> f -> (y)")) == [_bare("y")]

    # Every JSON kind is a constant, nested ones too, and a string may hold
    # what would end a statement.
    w = _one(
        '[(a=true, b=false, c=null, d=-1.5e3, e=[1, "two", {"k": [3]}], '
        'f={"x": {"y": null}}, g="a ] \\" \\n b") -> f -> y]'
    )
    want = [
        True,
        False,
        None,
        -1500.0,
        [1, "two", {"k": [3]}],
        {"x": {"y": None}},
        'a ] " \n b',
    ]
    assert len(w.sources) == len(want)
    for index, member in enumerate(w.sources):
        assert member.is_constant, f"member {index} is a constant"
        assert constants_equal(member.constant, want[index]), f"member {index}: {member.constant!r}"
    # A whole number and a float are kept apart, as they are written.
    assert isinstance(w.sources[3].constant, float)
    assert isinstance(w.sources[4].constant[0], int)

    # A word that only starts like a constant is a node.
    assert _members(_one("(a=truely, b=nullable) -> f -> y")) == [
        _named("a", "truely"), _named("b", "nullable"),
    ]

    # Statements need no separator beyond their own shape.
    every = _wirings("a -> f -> b\n(b, k=1) -> g -> (c, d=e)\n[e -> h -> ()] [() -> i -> z]")
    assert len(every) == 4
    assert every[1].step == "g"
    assert every[3].step == "i"


# TEST12734: the two headers. A cap header reads its URN to the end of the
# statement; a machine header names another machine by an opaque reference,
# written as a string with JSON's escapes; and the word `machine` is only a
# keyword where a header puts it.
def test_12734_cap_headers_and_machine_headers():
    statements = parse_syntax(
        'extract cap:in="media:document;ext=pdf";extract;out="media:enc=utf-8"\n'
        'clean machine "lib/clean \\"v2\\".machine"\n'
        "[machine cap:in=media:;machine;out=media:]\n"
        "machine -> machine -> machinery"
    )
    assert len(statements) == 4

    assert statements[0].kind == CAP_HEADER
    assert statements[0].alias == "extract"
    assert statements[0].cap_urn == 'cap:in="media:document;ext=pdf";extract;out="media:enc=utf-8"'

    assert statements[1].kind == MACHINE_HEADER
    assert statements[1].alias == "clean"
    assert statements[1].reference == 'lib/clean "v2".machine', "the reference is unescaped"

    # An alias may be the word `machine`, and so may a node and a step.
    assert statements[2].kind == CAP_HEADER
    assert statements[2].alias == "machine"
    assert statements[3].kind == WIRING
    assert _members(statements[3].wiring) == [_bare("machine")]
    assert statements[3].wiring.step == "machine"
    assert _targets(statements[3].wiring) == [_bare("machinery")]
    assert [statement.position for statement in statements] == [0, 1, 2, 3]


# TEST12735: a step's policy. It is read from the braces after the step,
# either key or both, in any order; and what it writes back is one form.
def test_12735_a_step_policy():
    def policy(input_str: str) -> StepPolicy:
        return _one(input_str).policy

    assert policy("a -> f -> b").is_default()
    assert policy("a -> f{} -> b").is_default()
    assert policy("a -> f{retry=3} -> b") == StepPolicy(retry=3)
    assert policy("a -> f{on_error=absent} -> b") == StepPolicy(on_error=ON_ERROR_ABSENT)
    both = StepPolicy(retry=2, on_error=ON_ERROR_ABSENT)
    assert policy("a -> f{retry=2, on_error=absent} -> b") == both
    assert policy("a -> f { on_error = absent , retry = 2 } -> b") == both
    assert _one("a -> f{retry=2} -> b").step == "f", "the policy is not part of the step's name"

    assert StepPolicy().to_notation() == ""
    assert StepPolicy(retry=3).to_notation() == "{retry=3}"
    assert StepPolicy(on_error=ON_ERROR_ABSENT).to_notation() == "{on_error=absent}"
    assert both.to_notation() == "{retry=2, on_error=absent}"
    # A policy that says `fail` in so many words is the default, and writes
    # nothing.
    assert StepPolicy(on_error=ON_ERROR_FAIL).is_default()
    assert StepPolicy(on_error=ON_ERROR_FAIL) == StepPolicy()
    assert both != StepPolicy(retry=2)
    assert both != StepPolicy(retry=3, on_error=ON_ERROR_ABSENT)
    # What is written back reads as what it was.
    for each in [StepPolicy(), both, StepPolicy(retry=7)]:
        assert policy(f"a -> f{each.to_notation()} -> b") == each, each.to_notation()


def _refused(input_str: str) -> MachineSyntaxError:
    with pytest.raises(MachineSyntaxError) as exc_info:
        parse_syntax(input_str)
    return exc_info.value


# TEST12736: what the text alone decides is refused by name, with the
# statement it is in: a constant that names no arg, a node named as a
# constant is, a second unnamed target, and a policy outside its table.
def test_12736_what_the_text_alone_refuses():
    for input_str in [
        "(prices, 20) -> rolling -> s",
        '("mean") -> rolling -> s',
        "(true) -> f -> y",
        "(a, [1]) -> f -> y",
    ]:
        assert isinstance(_refused(input_str), UnnamedConstantError), input_str
    unnamed = _refused("a -> f -> b\n(prices, 20) -> rolling -> s")
    assert isinstance(unnamed, UnnamedConstantError)
    assert "constant 20 in statement 1 " in str(unnamed)
    assert "name=20" in str(unnamed)

    for input_str, word in [
        ("true -> f -> y", "true"),
        ("x -> f -> null", "null"),
        ("x -> f -> (out=false)", "false"),
        ("x -> f -> (a, b=null)", "null"),
    ]:
        error = _refused(input_str)
        assert isinstance(error, ReservedNodeNameError), input_str
        assert f"'{word}'" in str(error), input_str
    # As a member's value those words are constants, which is what they are.
    assert _members(_one("(a=null) -> f -> y")) == [_named("a", "=null")]

    several = _refused("x -> f -> (a, b, c=d)")
    assert isinstance(several, SeveralUnnamedTargetsError)
    assert "(a, b)" in str(several)

    for input_str, said in [
        ("a -> f{retries=3} -> b", "retries"),
        ("a -> f{retry=-1} -> b", "-1"),
        ("a -> f{retry=1.5} -> b", "1.5"),
        ("a -> f{retry=many} -> b", "many"),
        ("a -> f{retry=4294967296} -> b", "4294967296"),
        ("a -> f{on_error=ignore} -> b", "ignore"),
        ("a -> f{on_error=3} -> b", "3"),
        ("a -> f{retry=1, retry=2} -> b", "twice"),
    ]:
        error = _refused(input_str)
        assert isinstance(error, InvalidPolicyError), input_str
        assert "step 'f'" in str(error), input_str
        assert said in str(error), input_str
    # The largest count a policy holds is read.
    assert _one("a -> f{retry=4294967295} -> b").policy.retry == 4294967295

    # What the grammar does not accept at all.
    for input_str in [
        "a -> f", "a -> -> b", "(a,) -> f -> b", "a -> f -> (b", "(a b) -> f -> c",
        "x machine clean", "(a=) -> f -> b",
        # A string that is not a JSON string: an escape JSON does not have,
        # and a raw line break.
        '(a="\\q") -> f -> b', '(a="x\ny") -> f -> b', 'x machine "bad \\q ref"',
        # A number no constant can hold.
        "(a=1e999) -> f -> b",
        # An escape that names half a character: text has no such thing.
        '(a="\\ud800") -> f -> b', '(a="\\udc00x") -> f -> b', '(a="\\ud83d\\ud83d") -> f -> b',
        '(a={"k\\ud800": 1}) -> f -> b', '(a=["\\udc00"]) -> f -> b', '(a={"k": "\\ud800"}) -> f -> b',
        'x machine "\\ud800"',
    ]:
        assert isinstance(_refused(input_str), ParseError), input_str
    # Both halves of a character, written as their two escapes, are it; and
    # an escaped backslash before a `u` is no escape of a character.
    assert _members(_one('(a="\\ud83d\\ude00") -> f -> b')) == [_named("a", '="\U0001F600"')]
    assert _members(_one('(a="\\\\ud800") -> f -> b')) == [_named("a", '="\\\\ud800"')]


# TEST12832: a constant has one text, the same in every implementation: an
# object's keys in order, a whole number without a point, a float with one
# (or an exponent beyond sixteen digits and below five zeros), and only the
# escapes JSON requires. Two constants are equal as JSON values: `1` and
# `1.0` are not, and an object's key order is not part of it.
def test_12832_a_constant_has_one_text():
    def text(written: str) -> str:
        return constant_text(decode_constant(written))

    # Each spelling below is what the reference writes for that text.
    for written, want in {
        "20": "20",
        "-7": "-7",
        "18446744073709551615": "18446744073709551615",
        "18446744073709551616": "1.8446744073709552e+19",
        "-9223372036854775809": "-9.223372036854776e+18",
        "1.0": "1.0",
        "1.50": "1.5",
        "-1.5e3": "-1500.0",
        "1e3": "1000.0",
        "0.0001": "0.0001",
        "0.00001": "0.00001",
        "0.000001": "1e-6",
        "1.25e-7": "1.25e-7",
        "1e15": "1000000000000000.0",
        "1e16": "1e+16",
        "1234567890123456.0": "1234567890123456.0",
        # Seventeen digits: the nearest float, not the one below it.
        "12345678901234567.0": "1.2345678901234568e+16",
        "1e21": "1e+21",
        "1.5e300": "1.5e+300",
        "5e-324": "5e-324",
        "0.0": "0.0",
        "-0.0": "-0.0",
        # A whole number has no sign to keep at zero: `-0` is the float.
        "0": "0",
        "-0": "-0.0",
        "-9223372036854775808": "-9223372036854775808",
        "1E3": "1000.0",
        "2.50e0": "2.5",
        "123.456": "123.456",
        '{"b": 1, "a": [true, null]}': '{"a":[true,null],"b":1}',
        '"a<b>&c é"': '"a<b>&c é"',
        '"tab\\there \\u0001 \\" \\\\ \\/ \\u007f"': '"tab\\there \\u0001 \\" \\\\ / \u007f"',
        '"line\\u2028sep"': '"line sep"',
    }.items():
        assert text(written) == want, written
        # The text reads back as the value it was written from.
        assert constants_equal(decode_constant(written), decode_constant(text(written))), written

    value = decode_constant
    assert constants_equal(value('{"a":1,"b":[2,"x"]}'), value('{"b":[2,"x"],"a":1}'))
    for left, right in [
        ("1", "1.0"), ("1", "2"), ('"1"', "1"), ("null", "false"), ("[1,2]", "[2,1]"),
        ("[1]", "[1,1]"), ('{"a":1}', '{"a":2}'), ('{"a":1}', '{"b":1}'),
        ('{"a":1}', '{"a":1,"b":2}'), ("true", "false"), ('"a"', '"b"'), ("1.5", "2.5"),
        ("null", "0"), ("true", "1"), ("false", "0"), ("true", "1.0"),
    ]:
        assert not constants_equal(value(left), value(right)), f"{left} and {right}"
        assert not constants_equal(value(right), value(left)), f"{right} and {left}"

    for refused in ["1 2", "1e999", "NaN", "Infinity", '"tab\tinside"', "", '"\ud800"']:
        with pytest.raises(ValueError):
            decode_constant(refused)
    # A value that is no JSON value has no text.
    with pytest.raises(TypeError):
        constant_text(object())
    with pytest.raises(ValueError):
        constant_text(float("inf"))
