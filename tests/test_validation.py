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
from capdag.cap.validation import (
    validate_cap_args,
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


# TEST051: Test input validation succeeds with valid positional argument
@pytest.mark.asyncio
async def test_051_input_validation_success(registry):
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")

    # The unified registry resolves the arg's media URN at validation
    # time; seed the spec the cap references.
    registry.add_spec(MediaDef(
        urn=MEDIA_STRING,
        media_type="text/plain",
        title="String",
        profile_uri="https://capdag.com/schema/string",
        schema={"type": "string"},
    ).to_stored())

    arg = CapArg(MEDIA_STRING, True, [PositionSource(0)])
    cap.add_arg(arg)

    input_args = ["/path/to/file.txt"]

    # Should succeed without raising
    await validate_positional_arguments(cap, input_args, registry)


# TEST052: Test input validation fails with MissingRequiredArgument when required arg missing
@pytest.mark.asyncio
async def test_052_input_validation_missing_required(registry):
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")

    arg = CapArg(MEDIA_STRING, True, [PositionSource(0)])
    cap.add_arg(arg)

    input_args = []  # Missing required argument

    with pytest.raises(MissingRequiredArgumentError) as exc_info:
        await validate_positional_arguments(cap, input_args, registry)

    assert exc_info.value.argument_name == MEDIA_STRING
    assert exc_info.value.cap_urn == cap.urn_string()


# TEST131: Input validation succeeds when optional positional argument is omitted
@pytest.mark.asyncio
async def test_131_input_validation_optional_arg(registry):
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")

    arg = CapArg(MEDIA_STRING, False, [PositionSource(0)])
    cap.add_arg(arg)

    input_args = []  # Not providing optional argument — must succeed
    await validate_positional_arguments(cap, input_args, registry)


# TEST132: Input validation fails with TooManyArgumentsError when extra positional args supplied
@pytest.mark.asyncio
async def test_132_input_validation_too_many_args(registry):
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")

    arg = CapArg(MEDIA_STRING, True, [PositionSource(0)])
    cap.add_arg(arg)

    input_args = ["arg1", "arg2", "arg3"]  # Too many

    with pytest.raises(TooManyArgumentsError) as exc_info:
        await validate_positional_arguments(cap, input_args, registry)

    assert exc_info.value.max_expected == 1
    assert exc_info.value.actual_count == 3


# TEST053: Test input validation fails with InvalidArgumentType when wrong type provided
@pytest.mark.asyncio
async def test_053_input_validation_wrong_type(registry):
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    registry.add_spec(MediaDef(
        urn=MEDIA_INTEGER,
        media_type="text/plain",
        title="Integer",
        profile_uri="https://capdag.com/schema/integer",
        schema={"type": "integer"},
        description="Integer value",
    ).to_stored())
    cap.add_arg(CapArg(MEDIA_INTEGER, True, [PositionSource(0)]))

    with pytest.raises(InvalidArgumentTypeError):
        await validate_positional_arguments(cap, ["not_a_number"], registry)


# TESTs 054/055/056 (XV5: inline media-def redefinition) were removed in the
# Rust regime: inline cap-local media defs no longer exist, so the situation
# the rule guarded against is structurally impossible. The corresponding tests
# are obsolete and intentionally left out.


# TEST578: RULE1 - duplicate media_urns rejected
def test_578_rule1_duplicate_media_urns():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [PositionSource(0)]))
    cap.add_arg(CapArg(MEDIA_STRING, True, [PositionSource(1)]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE1" in exc_info.value.issue


# TEST579: RULE2 - empty sources rejected
def test_579_rule2_empty_sources():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, []))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE2" in exc_info.value.issue


# TEST580: RULE3 - multiple stdin sources with different URNs rejected
def test_580_rule3_different_stdin_urns():
    urn = CapUrn.from_string(_test_urn_with_input("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [StdinSource("media:textable;txt")]))
    cap.add_arg(CapArg(MEDIA_INTEGER, True, [StdinSource("media:")]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE3" in exc_info.value.issue


# TEST581: RULE3 - multiple stdin sources with same URN is OK
def test_581_rule3_same_stdin_urns_ok():
    urn = CapUrn.from_string(_test_urn_with_input("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [StdinSource("media:textable;txt")]))
    cap.add_arg(CapArg(MEDIA_INTEGER, True, [StdinSource("media:textable;txt")]))

    # Should succeed - same stdin URNs allowed
    validate_cap_args(cap)


# TEST582: RULE4 - duplicate source type in single arg rejected
def test_582_rule4_duplicate_source_type():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [PositionSource(0), PositionSource(1)]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE4" in exc_info.value.issue


# TEST583: RULE5 - duplicate position across args rejected
def test_583_rule5_duplicate_position():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [PositionSource(0)]))
    cap.add_arg(CapArg(MEDIA_INTEGER, True, [PositionSource(0)]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE5" in exc_info.value.issue


# TEST584: RULE6 - position gap rejected (0, 2 without 1)
def test_584_rule6_position_gap():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [PositionSource(0)]))
    cap.add_arg(CapArg(MEDIA_INTEGER, True, [PositionSource(2)]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE6" in exc_info.value.issue


# TEST585: RULE6 - sequential positions (0, 1, 2) pass
def test_585_rule6_sequential_ok():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [PositionSource(0)]))
    cap.add_arg(CapArg(MEDIA_INTEGER, True, [PositionSource(1)]))

    # Should succeed
    validate_cap_args(cap)


# TEST586: RULE7 - arg with both position and cli_flag rejected
def test_586_rule7_position_and_cli_flag():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [PositionSource(0), CliFlagSource("--file")]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE7" in exc_info.value.issue


# TEST587: RULE9 - duplicate cli_flag across args rejected
def test_587_rule9_duplicate_cli_flag():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [CliFlagSource("--file")]))
    cap.add_arg(CapArg(MEDIA_INTEGER, True, [CliFlagSource("--file")]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE9" in exc_info.value.issue


# TEST588: RULE10 - reserved cli_flags rejected
def test_588_rule10_reserved_cli_flags():
    for reserved_flag in RESERVED_CLI_FLAGS:
        urn = CapUrn.from_string(_test_urn("type=test;cap"))
        cap = Cap(urn, "Test Capability", "test-command")
        cap.add_arg(CapArg(MEDIA_STRING, True, [CliFlagSource(reserved_flag)]))

        with pytest.raises(InvalidCapSchemaError) as exc_info:
            validate_cap_args(cap)

        assert "RULE10" in exc_info.value.issue
        assert reserved_flag in exc_info.value.issue


# TEST589: valid cap args with mixed sources pass all rules
def test_589_all_rules_pass():
    urn = CapUrn.from_string(_test_urn_with_input("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [PositionSource(0), StdinSource("media:textable;txt")]))
    cap.add_arg(CapArg(MEDIA_INTEGER, False, [PositionSource(1)]))

    # Should succeed
    validate_cap_args(cap)


# TEST590: validate_cap_args accepts cap with only cli_flag sources (no positions)
def test_590_cli_flag_only_args():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [CliFlagSource("--input")]))
    cap.add_arg(CapArg(MEDIA_INTEGER, False, [CliFlagSource("--count")]))

    # Should succeed
    validate_cap_args(cap)


# TEST1294: RULE11 - void-input cap with stdin source rejected
def test_1294_rule11_void_input_with_stdin():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [StdinSource("media:textable;txt")]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE11" in exc_info.value.issue


# TEST1295: RULE11 - non-void-input cap without stdin source rejected
def test_1295_rule11_non_void_input_without_stdin():
    urn = CapUrn.from_string(_test_urn_with_input("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [PositionSource(0)]))

    with pytest.raises(InvalidCapSchemaError) as exc_info:
        validate_cap_args(cap)

    assert "RULE11" in exc_info.value.issue


# TEST1296: RULE11 - void-input cap with only cli_flag sources passes
def test_1296_rule11_void_input_cli_flag_only():
    urn = CapUrn.from_string(_test_urn("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [CliFlagSource("--input")]))

    # Should succeed - void input, no stdin sources
    validate_cap_args(cap)


# TEST1297: RULE11 - non-void-input cap with stdin source passes
def test_1297_rule11_non_void_input_with_stdin():
    urn = CapUrn.from_string(_test_urn_with_input("type=test;cap"))
    cap = Cap(urn, "Test Capability", "test-command")
    cap.add_arg(CapArg(MEDIA_STRING, True, [StdinSource("media:textable;txt")]))

    # Should succeed - non-void input with stdin source
    validate_cap_args(cap)
