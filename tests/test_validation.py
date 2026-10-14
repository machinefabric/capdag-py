"""Tests for validation - mirroring capdag Rust tests

Tests use // TEST###: comments matching the Rust implementation for cross-tracking.
"""

import pytest
import tempfile
from pathlib import Path
from capdag import CapUrn, Cap, CapArg
from capdag.cap.definition import PositionSource, CliFlagSource, StdinSource
from capdag.media.spec import MediaDef
from capdag.media.registry import FabricRegistry
from capdag.cap.definition import CapOutput
from capdag.cap.validation import (
    validate_cap_args,
    validate_cap_definition,
    validate_cap_outputs,
    validate_positional_arguments,
    MissingRequiredArgumentError,
    InvalidArgumentTypeError,
    InvalidCapSchemaError,
    TooManyArgumentsError,
    RESERVED_CLI_FLAGS,
)
from capdag.urn.media_urn import MEDIA_STRING, MEDIA_INTEGER, MEDIA_VOID, MEDIA_OBJECT


@pytest.fixture
def registry():
    """A clean, in-memory FabricRegistry for tests to seed via ``add_spec``."""
    cache_dir = Path(tempfile.mkdtemp(prefix="capdag-fabric-"))
    return FabricRegistry.new_for_test(cache_dir)


def _test_urn(tags: str) -> str:
    """Helper to build cap URN with standard in/out for testing (void input)"""
    return f'cap:in="{MEDIA_VOID}";out="{MEDIA_OBJECT}";{tags}'


def _test_urn_with_input(tags: str) -> str:
    """Helper to build cap URN with non-void in= spec for testing stdin sources"""
    return f'cap:in="{MEDIA_STRING}";out="{MEDIA_OBJECT}";{tags}'


# TEST51: Test input validation succeeds with valid positional argument
@pytest.mark.asyncio
async def test_051_input_validation_success(registry):
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])

    # The unified registry resolves the arg's media URN at validation
    # time; seed the spec the cap references.
    registry.add_spec(MediaDef(
        urn=MEDIA_STRING,
        media_type="text/plain",
        title="String",
        profile_uri="https://capdag.com/schema/string",
        schema={"type": "string"},
    ).to_stored())

    arg = CapArg(MEDIA_STRING, "arg1", True, [PositionSource(0)])
    cap.add_arg(arg)

    input_args = ["/path/to/file.txt"]

    # Should succeed without raising
    await validate_positional_arguments(cap, input_args, registry)


# TEST52: Test input validation fails with MissingRequiredArgument when required arg missing
@pytest.mark.asyncio
async def test_052_input_validation_missing_required(registry):
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])

    arg = CapArg(MEDIA_STRING, "arg1", True, [PositionSource(0)])
    cap.add_arg(arg)

    input_args = []  # Missing required argument

    with pytest.raises(MissingRequiredArgumentError) as exc_info:
        await validate_positional_arguments(cap, input_args, registry)

    assert exc_info.value.argument_name == MEDIA_STRING
    assert exc_info.value.cap_urn == cap.urn_string()


# TEST6364: Input validation succeeds when optional positional argument is omitted
@pytest.mark.asyncio
async def test_6364_input_validation_optional_arg(registry):
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])

    arg = CapArg(MEDIA_STRING, "arg1", False, [PositionSource(0)])
    cap.add_arg(arg)

    input_args = []  # Not providing optional argument — must succeed
    await validate_positional_arguments(cap, input_args, registry)


# TEST6368: Input validation fails with TooManyArgumentsError when extra positional args supplied
@pytest.mark.asyncio
async def test_6368_input_validation_too_many_args(registry):
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])

    arg = CapArg(MEDIA_STRING, "arg1", True, [PositionSource(0)])
    cap.add_arg(arg)

    input_args = ["arg1", "arg2", "arg3"]  # Too many

    with pytest.raises(TooManyArgumentsError) as exc_info:
        await validate_positional_arguments(cap, input_args, registry)

    assert exc_info.value.max_expected == 1
    assert exc_info.value.actual_count == 3


# TEST53: Test input validation fails with InvalidArgumentType when wrong type provided
@pytest.mark.asyncio
async def test_053_input_validation_wrong_type(registry):
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    registry.add_spec(MediaDef(
        urn=MEDIA_INTEGER,
        media_type="text/plain",
        title="Integer",
        profile_uri="https://capdag.com/schema/integer",
        schema={"type": "integer"},
        description="Integer value",
    ).to_stored())
    cap.add_arg(CapArg(MEDIA_INTEGER, "arg1", True, [PositionSource(0)]))

    with pytest.raises(InvalidArgumentTypeError):
        await validate_positional_arguments(cap, ["not_a_number"], registry)


# TESTs 054/055/056 (XV5: inline media-def redefinition) were removed in the
# Rust regime: inline cap-local media defs no longer exist, so the situation
# the rule guarded against is structurally impossible. The corresponding tests
# are obsolete and intentionally left out.


# TEST578: RULE1 - duplicate media_urns rejected
def test_578_rule1_duplicate_media_urns():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "arg1", True, [PositionSource(0)]))
    cap.add_arg(CapArg(MEDIA_STRING, "arg2", True, [PositionSource(1)]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE1" in exc_info.value.issue


# TEST579: RULE2 - empty sources rejected
def test_579_rule2_empty_sources():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "arg1", True, []))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE2" in exc_info.value.issue


# TEST580: RULE3 - multiple stdin sources with different URNs rejected
def test_580_rule3_different_stdin_urns():
    urn = CapUrn.from_string(_test_urn_with_input("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "input", True, [StdinSource("media:enc=utf-8;ext=txt")]))
    cap.add_arg(CapArg(MEDIA_INTEGER, "arg1", True, [StdinSource("media:")]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE3" in exc_info.value.issue


# TEST581: RULE3 - two stdin args are rejected even when their stdin URNs are identical
#
# The rule used to allow this ("multiple stdin sources with the same URN is OK"), on the
# reasoning that one stdin stream can only be one type. A cap has one main input: two args
# that both claim it leave nothing to say which of them a piped value is.
def test_581_rule3_identical_stdin_urns_are_still_two_main_inputs():
    urn = CapUrn.from_string(_test_urn_with_input("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "input", True, [StdinSource(MEDIA_STRING)]))
    cap.add_arg(CapArg(MEDIA_INTEGER, "other", True, [StdinSource(MEDIA_STRING)]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE3" in exc_info.value.issue
    assert "both declare a stdin source" in exc_info.value.issue
    assert MEDIA_STRING in exc_info.value.issue and MEDIA_INTEGER in exc_info.value.issue


# TEST582: RULE4 - duplicate source type in single arg rejected
def test_582_rule4_duplicate_source_type():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "arg1", True, [PositionSource(0), PositionSource(1)]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE4" in exc_info.value.issue


# TEST583: RULE5 - duplicate position across args rejected
def test_583_rule5_duplicate_position():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "arg1", True, [PositionSource(0)]))
    cap.add_arg(CapArg(MEDIA_INTEGER, "arg2", True, [PositionSource(0)]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE5" in exc_info.value.issue


# TEST584: RULE6 - position gap rejected (0, 2 without 1)
def test_584_rule6_position_gap():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "arg1", True, [PositionSource(0)]))
    cap.add_arg(CapArg(MEDIA_INTEGER, "arg2", True, [PositionSource(2)]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE6" in exc_info.value.issue


# TEST585: RULE6 - sequential positions (0, 1, 2) pass
def test_585_rule6_sequential_ok():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "arg1", True, [PositionSource(0)]))
    cap.add_arg(CapArg(MEDIA_INTEGER, "arg2", True, [PositionSource(1)]))

    # Should succeed
    validate_cap_args(cap)


# TEST586: RULE7 - arg with both position and cli_flag rejected
def test_586_rule7_position_and_cli_flag():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "arg1", True, [PositionSource(0), CliFlagSource("--file")]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE7" in exc_info.value.issue


# TEST587: RULE9 - duplicate cli_flag across args rejected
def test_587_rule9_duplicate_cli_flag():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "arg1", True, [CliFlagSource("--file")]))
    cap.add_arg(CapArg(MEDIA_INTEGER, "arg2", True, [CliFlagSource("--file")]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE9" in exc_info.value.issue


# TEST588: RULE10 - reserved cli_flags rejected
def test_588_rule10_reserved_cli_flags():
    for reserved_flag in RESERVED_CLI_FLAGS:
        urn = CapUrn.from_string(_test_urn("type=test;cap"))
        cap = Cap(urn, "Test Capability", ["test-command"])
        cap.add_arg(CapArg(MEDIA_STRING, "arg1", True, [CliFlagSource(reserved_flag)]))

        with pytest.raises(InvalidCapSchemaError) as exc_info:
            validate_cap_args(cap)

        assert "RULE10" in exc_info.value.issue
        assert reserved_flag in exc_info.value.issue


# TEST589: valid cap args with mixed sources pass all rules
def test_589_all_rules_pass():
    urn = CapUrn.from_string(_test_urn_with_input("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "input", True, [PositionSource(0), StdinSource(MEDIA_STRING)]))
    cap.add_arg(CapArg(MEDIA_INTEGER, "arg1", False, [PositionSource(1)]))

    # Should succeed
    validate_cap_args(cap)


# TEST590: validate_cap_args accepts cap with only cli_flag sources (no positions)
def test_590_cli_flag_only_args():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "arg1", True, [CliFlagSource("--input")]))
    cap.add_arg(CapArg(MEDIA_INTEGER, "arg2", False, [CliFlagSource("--count")]))

    # Should succeed
    validate_cap_args(cap)


# TEST1294: RULE15 - void-input cap with stdin source rejected
def test_1294_rule15_void_input_with_stdin():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "input", True, [StdinSource("media:enc=utf-8;ext=txt")]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE15" in exc_info.value.issue
    assert "media:void" in exc_info.value.issue


# TEST1295: RULE15 - non-void-input cap without stdin source rejected
def test_1295_rule15_non_void_input_without_stdin():
    urn = CapUrn.from_string(_test_urn_with_input("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "arg1", True, [PositionSource(0)]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE15" in exc_info.value.issue
    assert MEDIA_STRING in exc_info.value.issue


# TEST1296: RULE15 - void-input cap with only cli_flag sources passes
def test_1296_rule15_void_input_cli_flag_only():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "arg1", True, [CliFlagSource("--input")]))

    # Should succeed - void input, no stdin sources
    validate_cap_args(cap)


# TEST1953: RULE14 — ``streaming=True`` is accepted on the main input (the
# stdin arg equivalent to ``in=``) and refused on any other argument: a side
# option has no wire stream, so it has nothing to consume incrementally, and
# the rule keeps the executor's hop rule one-dimensional.
def test_1953_rule14_streaming_only_on_main_input():
    urn = CapUrn.from_string(_test_urn_with_input("type=test;cap"))
    ok = Cap(urn, "Test Capability", ["test-command"])
    main = CapArg(MEDIA_STRING, "input", True, [StdinSource(MEDIA_STRING)])
    main.streaming = True
    ok.add_arg(main)
    validate_cap_args(ok)
    assert ok.streaming_shape() == (True, False)

    bad = Cap(CapUrn.from_string(_test_urn_with_input("type=test;cap")), "Test Capability", ["test-command"])
    bad.add_arg(CapArg(MEDIA_STRING, "arg1", True, [StdinSource(MEDIA_STRING)]))
    side = CapArg(MEDIA_INTEGER, "arg2", False, [CliFlagSource("--count")])
    side.streaming = True
    bad.add_arg(side)
    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(bad)
    assert "RULE14" in exc_info.value.issue
    assert MEDIA_INTEGER in exc_info.value.issue


# TEST1964: a definition field this capdag does not know is a NEWER fabric, not
# noise — parsing refuses it, naming the key, for arguments and outputs alike.
# The field being dropped is how a cartridge built on an older capdag once
# advertised a ``streaming`` input as bounded.
def test_1964_unknown_definition_field_is_refused():
    from capdag.cap.definition import CapOutput

    with pytest.raises(ValueError, match="chunking"):
        CapArg.from_dict({"media_urn": MEDIA_STRING, "name": "input", "required": True,
                          "sources": [{"stdin": MEDIA_STRING}], "chunking": "adaptive"})
    assert CapArg.from_dict({"media_urn": MEDIA_STRING, "name": "arg1", "required": True,
                             "sources": [{"stdin": MEDIA_STRING}], "streaming": True}).streaming
    with pytest.raises(ValueError, match="windowed"):
        CapOutput.from_dict({"media_urn": MEDIA_STRING, "name": "output", "output_description": "x", "windowed": True})


# TEST1297: RULE15 - non-void-input cap with stdin source passes
def test_1297_rule15_non_void_input_with_stdin():
    urn = CapUrn.from_string(_test_urn_with_input("type=test;cap"))
    cap = Cap(urn, "Test Capability", ["test-command"])
    cap.add_arg(CapArg(MEDIA_STRING, "input", True, [StdinSource(MEDIA_STRING)]))

    # Should succeed - non-void input with stdin source
    validate_cap_args(cap)


def _refused(check, cap) -> str:
    with pytest.raises(InvalidCapSchemaError) as exc_info:
        check(cap)
    assert cap.urn_string() in str(exc_info.value), "the refusal names the cap"
    return exc_info.value.issue


def _cap_with_args(cap_urn: str, args) -> Cap:
    cap = Cap(CapUrn.from_string(cap_urn), "Test Capability", ["test-command"])
    for arg in args:
        cap.add_arg(arg)
    return cap


# TEST12705: RULE15 - the stdin argument's URN is the cap's `in=`, as a
# tagged URN: the same tags in another order pass, another type does not.
def test_12705_rule15_the_stdin_argument_is_the_caps_input():
    def cap_of(stdin: str) -> Cap:
        return _cap_with_args(
            'cap:in="media:document;ext=pdf";test;out="media:record"',
            [CapArg("media:enc=utf-8;file-path", "document", True, [StdinSource(stdin)])],
        )

    validate_cap_args(cap_of("media:document;ext=pdf"))
    validate_cap_args(cap_of("media:ext=pdf;document"))  # tag order is not identity
    issue = _refused(validate_cap_args, cap_of("media:document"))
    assert "RULE15" in issue
    assert "media:document;ext=pdf" in issue


# TEST12706: RULE17 - every argument has a well-formed name, unique in its cap.
def test_12706_rule17_argument_names():
    def flag(media_urn: str, name: str, cli_flag: str) -> CapArg:
        return CapArg(media_urn, name, False, [CliFlagSource(cli_flag)])

    def cap_of(args) -> Cap:
        return _cap_with_args(_test_urn("type=test;cap"), args)

    # Two args, two names: fine. A name says nothing of the URN it labels.
    validate_cap_args(cap_of([
        flag(MEDIA_STRING, "window", "--a"),
        flag(MEDIA_INTEGER, "benchmark", "--b"),
    ]))

    issue = _refused(validate_cap_args, cap_of([flag(MEDIA_STRING, "", "--a")]))
    assert "RULE17" in issue
    assert "has no name" in issue
    for bad in ["9lives", "has space", "dotted.name", "a=b", "true", "false", "null", "-lead"]:
        issue = _refused(validate_cap_args, cap_of([flag(MEDIA_STRING, bad, "--a")]))
        assert "RULE17" in issue, bad
        assert "not a valid name" in issue, bad
    for good in ["x", "_x", "model-spec", "top_k", "A1"]:
        validate_cap_args(cap_of([flag(MEDIA_STRING, good, "--a")]))
    issue = _refused(
        validate_cap_args,
        cap_of([flag(MEDIA_STRING, "same", "--a"), flag(MEDIA_INTEGER, "same", "--b")]),
    )
    assert "RULE17" in issue
    assert "share the name 'same'" in issue
    assert MEDIA_STRING in issue and MEDIA_INTEGER in issue, "both args are named by URN"


# TEST12707: RULE18 - an argument says what it accepts in one place; and what
# it accepts is not what it is delivered under.
def test_12707_rule18_accepts_and_the_two_urns_of_an_argument():
    series = "media:fmt=json;list;record;time-series"
    benchmark = CapArg(
        "media:benchmark;fmt=json;list;record;time-series", "benchmark",
        True,
        [CliFlagSource("--benchmark")],
    ).accepting(series)
    # It accepts a plain series, and is delivered under its own URN: two
    # args accepting one type stay distinct on the wire.
    assert benchmark.accepted_urn() == series
    assert benchmark.stream_urn() == "media:benchmark;fmt=json;list;record;time-series"

    # The main input accepts, and is delivered under, its stdin URN.
    main = CapArg("media:enc=utf-8;file-path", "path", True, [StdinSource(series)])
    assert main.accepted_urn() == series
    assert main.stream_urn() == series

    # An arg with neither accepts its own URN.
    plain = CapArg(MEDIA_INTEGER, "window", False, [CliFlagSource("--window")])
    assert plain.accepted_urn() == MEDIA_INTEGER
    assert plain.stream_urn() == MEDIA_INTEGER

    cap_urn = f'cap:in="{series}";compare;out="media:record"'
    compare = _cap_with_args(cap_urn, [main, benchmark])
    validate_cap_args(compare)
    # A machine names an argument by its label.
    assert compare.arg_named("benchmark") is benchmark
    assert compare.arg_named("path") is main
    assert compare.arg_named("series") is None, "a name is not looked up in any URN"

    # `accepts` beside a stdin source says it twice.
    issue = _refused(validate_cap_args, _cap_with_args(cap_urn, [main.accepting(series)]))
    assert "RULE18" in issue
    assert "media:enc=utf-8;file-path" in issue
    # Declaring what one copy accepts does not change the argument it was made from.
    assert main.accepts is None

    # What an arg accepts is part of its definition on the wire, and only
    # when it declares it.
    assert benchmark.to_dict()["accepts"] == series
    assert CapArg.from_dict(benchmark.to_dict()).accepts == series
    assert "accepts" not in plain.to_dict()


def _cap_with_outputs(out_spec: str, outputs) -> Cap:
    cap = Cap(
        CapUrn.from_string(f'cap:in="media:enc=utf-8";test;out="{out_spec}"'), "Test", ["cmd"]
    )
    cap.set_outputs(outputs)
    return cap


# TEST12708: RULE19, RULE20 - outputs have well-formed, distinct names and
# distinct media URNs, compared as URNs.
def test_12708_rule19_rule20_output_names_and_identities():
    regression = "media:fmt=json;record;regression"
    residual = "media:fmt=json;list;record;residual"

    def fit() -> CapOutput:
        return CapOutput(regression, "fit", "the fit")

    validate_cap_outputs(_cap_with_outputs(regression, [fit(), CapOutput(residual, "residuals", "")]))

    def refused(outputs) -> str:
        return _refused(validate_cap_outputs, _cap_with_outputs(regression, outputs))

    issue = refused([fit(), CapOutput(residual, "", "")])
    assert "RULE19" in issue
    assert "has no name" in issue
    issue = refused([fit(), CapOutput(residual, "null", "")])
    assert "RULE19" in issue
    assert "not a valid name" in issue
    issue = refused([fit(), CapOutput(residual, "fit", "")])
    assert "RULE19" in issue
    assert "share the name 'fit'" in issue
    # The same URN with its tags in another order is the same output.
    issue = refused([fit(), CapOutput("media:regression;record;fmt=json", "again", "")])
    assert "RULE20" in issue


# TEST12709: RULE21 - exactly one output is the main one, the cap's `out=`;
# a cap whose `out=` is void declares none.
def test_12709_rule21_exactly_one_main_output():
    fit = "media:fmt=json;record;regression"
    none = _cap_with_outputs(fit, [CapOutput("media:fmt=json;list;record;residual", "residuals", "")])
    issue = _refused(validate_cap_outputs, none)
    assert "RULE21" in issue
    assert "0 outputs" in issue
    assert "RULE21" in _refused(validate_cap_outputs, _cap_with_outputs(fit, []))

    one = _cap_with_outputs(fit, [CapOutput("media:regression;fmt=json;record", "fit", "")])
    validate_cap_outputs(one)  # the main output is found by URN equivalence
    assert one.main_output() is not None
    assert one.main_output().name == "fit"

    void = _cap_with_outputs("media:void", [])
    validate_cap_outputs(void)
    assert void.main_output() is None
    issue = _refused(
        validate_cap_outputs,
        _cap_with_outputs("media:void", [CapOutput("media:enc=utf-8", "text", "")]),
    )
    assert "RULE21" in issue
    assert "media:void" in issue


# TEST12710: RULE22 - only a non-main output of a cap that takes an input
# may carry that input's type.
def test_12710_rule22_what_an_output_carries():
    router = _cap_with_outputs("media:enc=utf-8;kept", [
        CapOutput("media:enc=utf-8;kept", "yes", "").as_optional(True),
        CapOutput("media:enc=utf-8;dropped", "no", "").as_optional(True).carrying_input(),
    ])
    validate_cap_outputs(router)

    main_carries = _cap_with_outputs("media:enc=utf-8;kept", [
        CapOutput("media:enc=utf-8;kept", "yes", "").carrying_input(),
    ])
    issue = _refused(validate_cap_outputs, main_carries)
    assert "RULE22" in issue
    assert "main output" in issue

    source = Cap(
        CapUrn.from_string('cap:in="media:void";now;out="media:enc=utf-8;stamp"'), "Now", ["now"]
    )
    source.set_outputs([
        CapOutput("media:enc=utf-8;stamp", "stamp", ""),
        CapOutput("media:enc=utf-8;echo", "echo", "").carrying_input(),
    ])
    issue = _refused(validate_cap_outputs, source)
    assert "RULE22" in issue
    assert "takes none" in issue

    # What an output declares survives the wire: optional, and what it carries.
    back = [CapOutput.from_dict(output.to_dict()) for output in router.get_outputs()]
    assert [(o.name, o.optional, o.carries) for o in back] == [
        ("yes", True, None),
        ("no", True, "input"),
    ]
    assert router.get_outputs()[1].to_dict()["carries"] == "input"
    # An output carries its own type or the input's: nothing else is a definition.
    with pytest.raises(ValueError, match="carries"):
        CapOutput.from_dict({
            "media_urn": "media:enc=utf-8;dropped", "name": "no", "output_description": "",
            "carries": "output",
        })
    # Declaring a copy optional, or carrying, does not change the output it was made from.
    plain = CapOutput("media:enc=utf-8;kept", "yes", "")
    assert plain.as_optional(True).optional is True
    assert plain.carrying_input().carries == "input"
    assert (plain.optional, plain.carries) == (False, None)
