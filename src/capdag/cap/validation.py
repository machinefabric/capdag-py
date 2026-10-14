"""Cap validation infrastructure

This module provides input/output validation for caps using schemas.
It validates arguments and outputs against their declared media URNs and schemas.
"""

import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


class ValidationError(Exception):
    """Base validation error"""
    pass


class MissingRequiredArgumentError(ValidationError):
    """Required argument missing"""
    def __init__(self, cap_urn: str, argument_name: str):
        super().__init__(f"Cap '{cap_urn}' requires argument '{argument_name}' but it was not provided")
        self.cap_urn = cap_urn
        self.argument_name = argument_name


class InvalidArgumentTypeError(ValidationError):
    """Invalid argument type"""
    def __init__(self, cap_urn: str, argument_name: str, expected: str, actual: Any, errors: List[str]):
        msg = f"Cap '{cap_urn}' argument '{argument_name}' expects '{expected}' but validation failed: {', '.join(errors)}"
        super().__init__(msg)
        self.cap_urn = cap_urn
        self.argument_name = argument_name
        self.expected_media_def = expected
        self.actual_value = actual
        self.schema_errors = errors


class TooManyArgumentsError(ValidationError):
    """Too many arguments"""
    def __init__(self, cap_urn: str, max_expected: int, actual_count: int):
        super().__init__(f"Cap '{cap_urn}' expects at most {max_expected} arguments but received {actual_count}")
        self.cap_urn = cap_urn
        self.max_expected = max_expected
        self.actual_count = actual_count


class InvalidCapSchemaError(ValidationError):
    """Invalid cap schema"""
    def __init__(self, cap_urn: str, issue: str):
        super().__init__(f"Cap '{cap_urn}' has invalid schema: {issue}")
        self.cap_urn = cap_urn
        self.issue = issue


class MediaDefValidationError(ValidationError):
    """Media def validation rule violation"""
    def __init__(self, cap_urn: str, argument_name: str, media_urn: str, rule: str, actual: Any):
        super().__init__(
            f"Cap '{cap_urn}' argument '{argument_name}' failed media def '{media_urn}' "
            f"validation rule '{rule}' with value: {actual}"
        )
        self.cap_urn = cap_urn
        self.argument_name = argument_name
        self.media_urn = media_urn
        self.validation_rule = rule
        self.actual_value = actual




# Reserved CLI flags that cannot be used
RESERVED_CLI_FLAGS = ["manifest", "--help", "--version", "-v", "-h"]


def is_valid_definition_name(name: str) -> bool:
    """Whether ``name`` can name an argument or an output (RULE17, RULE19):
    the lexical form of a notation alias, and none of the words notation
    reads as constants."""
    if name in ("", "true", "false", "null"):
        return False
    first, rest = name[0], name[1:]
    letters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if first not in letters and first != "_":
        return False
    return all(c in letters or c in "0123456789_-" for c in rest)


def validate_cap_definition(cap) -> None:
    """Hold a whole definition to the definition rules (RULE1-RULE22): its
    arguments, then its outputs. A definition is held to them wherever it
    crosses from one program to another."""
    validate_cap_args(cap)
    validate_cap_outputs(cap)


def validate_cap_outputs(cap) -> None:
    """Enforce the rules on a cap's outputs.

    - RULE19: Output names: required, well-formed, unique
    - RULE20: No duplicate output media_urns
    - RULE21: Exactly one main output, matching out= (none when out= is media:void)
    - RULE22: What an output carries
    """
    from capdag.urn.media_urn import MediaUrn, MEDIA_VOID

    cap_urn = cap.urn_string()

    def refuse(issue: str) -> InvalidCapSchemaError:
        return InvalidCapSchemaError(cap_urn, issue)

    void_media = MediaUrn.from_string(MEDIA_VOID)
    try:
        out_media = MediaUrn.from_string(cap.urn.out_spec())
    except Exception as e:
        raise refuse(f"RULE21: Failed to parse out= spec: {e}")
    try:
        in_media = MediaUrn.from_string(cap.urn.in_spec())
    except Exception as e:
        raise refuse(f"RULE22: Failed to parse in= spec: {e}")
    out_is_void = out_media.is_equivalent(void_media)
    in_is_void = in_media.is_equivalent(void_media)
    outputs = cap.get_outputs()

    # RULE19: names
    named: List[Any] = []
    for output in outputs:
        if not output.name:
            raise refuse(f"RULE19: Output '{output.media_urn}' has no name")
        if not is_valid_definition_name(output.name):
            raise refuse(f"RULE19: Output name '{output.name}' is not a valid name")
        for seen in named:
            if seen.name == output.name:
                raise refuse(
                    f"RULE19: Outputs '{seen.media_urn}' and '{output.media_urn}' "
                    f"share the name '{output.name}'"
                )
        named.append(output)

    # RULE20: identities, compared as media URNs (tag order is not identity)
    identities = []
    for output in outputs:
        try:
            output_urn = MediaUrn.from_string(output.media_urn)
        except Exception as e:
            raise refuse(f"RULE20: Output media_urn '{output.media_urn}' is not a media URN: {e}")
        if any(seen.is_equivalent(output_urn) for seen in identities):
            raise refuse(f"RULE20: Duplicate output media_urn '{output.media_urn}'")
        identities.append(output_urn)

    # RULE21: the main output
    if out_is_void:
        if outputs:
            raise refuse(f"RULE21: out= is 'media:void' but {len(outputs)} output(s) are declared")
        return
    main = [index for index, identity in enumerate(identities) if identity.is_equivalent(out_media)]
    if len(main) != 1:
        raise refuse(
            f"RULE21: out= is '{cap.urn.out_spec()}' but {len(main)} outputs are "
            "equivalent to it; exactly one must be"
        )

    # RULE22: what an output carries
    for index, output in enumerate(outputs):
        if output.carries is None:
            continue
        if index == main[0]:
            raise refuse(f"RULE22: The main output '{output.media_urn}' declares carries")
        if in_is_void:
            raise refuse(
                f"RULE22: Output '{output.media_urn}' carries the input but the cap takes none"
            )


def validate_cap_args(cap) -> None:
    """Enforce structural rules on a cap's argument definitions.

    Every rule is raised under the number the reference raises it under
    (capdag docs/10-validation-rules.md): a number names one rule.

    - RULE1: No duplicate media_urns
    - RULE2: sources must not be empty
    - RULE3: At most one arg declares a stdin source
    - RULE4: No arg may specify same source type more than once
    - RULE5: No two args may have same position
    - RULE6: Positions must be sequential (0-based, no gaps)
    - RULE7: No arg may have both position and cli_flag
    - RULE9: No two args may have same cli_flag
    - RULE10: Reserved cli_flags cannot be used
    - RULE14: Only the main input argument may declare streaming=true
    - RULE15: The main input matches in= (void input declares no stdin; any
      other declares one, equivalent to in=)
    - RULE17: Argument names: required, well-formed, unique
    - RULE18: ``accepts`` only without a stdin source
    """
    from capdag.cap.definition import PositionSource, CliFlagSource, StdinSource

    cap_urn = cap.urn_string()
    args = cap.get_args()

    # RULE1: No duplicate media_urns
    media_urns = set()
    for arg in args:
        if arg.media_urn in media_urns:
            raise InvalidCapSchemaError(cap_urn, f"RULE1: Duplicate media_urn '{arg.media_urn}'")
        media_urns.add(arg.media_urn)

    # RULE2: sources must not be empty
    for arg in args:
        if not arg.sources:
            raise InvalidCapSchemaError(cap_urn, f"RULE2: Argument '{arg.media_urn}' has empty sources")

    # Collect data for cross-arg validation
    stdin_urns = []
    positions = []
    cli_flags = []

    for arg in args:
        source_types = set()
        has_position = False
        has_cli_flag = False

        for source in arg.sources:
            source_type = type(source).__name__

            # RULE4: No arg may specify same source type more than once
            if source_type in source_types:
                raise InvalidCapSchemaError(
                    cap_urn,
                    f"RULE4: Argument '{arg.media_urn}' has duplicate source type '{source_type}'"
                )
            source_types.add(source_type)

            if isinstance(source, StdinSource):
                stdin_urns.append(source.stdin)
            elif isinstance(source, PositionSource):
                has_position = True
                positions.append((source.position, arg.media_urn))
            elif isinstance(source, CliFlagSource):
                has_cli_flag = True
                cli_flags.append((source.cli_flag, arg.media_urn))

                # RULE10: Reserved cli_flags
                if source.cli_flag in RESERVED_CLI_FLAGS:
                    raise InvalidCapSchemaError(
                        cap_urn,
                        f"RULE10: Argument '{arg.media_urn}' uses reserved cli_flag '{source.cli_flag}'"
                    )

        # RULE7: No arg may have both position and cli_flag
        if has_position and has_cli_flag:
            raise InvalidCapSchemaError(
                cap_urn,
                f"RULE7: Argument '{arg.media_urn}' has both position and cli_flag sources"
            )

    # RULE3: At most one arg declares a stdin source. ``stdin`` is a command
    # line's one piped input, and the arg that declares it is the main input.
    stdin_args = [arg.media_urn for arg in args if arg.has_stdin_source()]
    if len(stdin_args) > 1:
        raise InvalidCapSchemaError(
            cap_urn,
            f"RULE3: Arguments '{stdin_args[0]}' and '{stdin_args[1]}' both declare a stdin "
            "source; a cap has one main input"
        )

    # RULE17: names
    named: List[Any] = []
    for arg in args:
        if not arg.name:
            raise InvalidCapSchemaError(cap_urn, f"RULE17: Argument '{arg.media_urn}' has no name")
        if not is_valid_definition_name(arg.name):
            raise InvalidCapSchemaError(
                cap_urn, f"RULE17: Argument name '{arg.name}' is not a valid name"
            )
        for seen in named:
            if seen.name == arg.name:
                raise InvalidCapSchemaError(
                    cap_urn,
                    f"RULE17: Arguments '{seen.media_urn}' and '{arg.media_urn}' share the "
                    f"name '{arg.name}'"
                )
        named.append(arg)

    # RULE18: an arg says what it accepts in one place.
    for arg in args:
        if arg.accepts is not None and arg.has_stdin_source():
            raise InvalidCapSchemaError(
                cap_urn,
                f"RULE18: Argument '{arg.media_urn}' declares both a stdin source and accepts"
            )

    # RULE15: The main input matches in=. If in= is media:void, no arg may
    # have a stdin source (the cap takes no data-flow input). Otherwise
    # exactly one does (RULE3 caps it at one), and its URN is in=.
    from capdag.urn.media_urn import MediaUrn, MEDIA_VOID
    try:
        in_media = MediaUrn.from_string(cap.urn.in_spec())
    except Exception as e:
        raise InvalidCapSchemaError(cap_urn, f"RULE15: Failed to parse in= spec: {e}")
    void_media = MediaUrn.from_string(MEDIA_VOID)
    is_void_input = in_media.is_equivalent(void_media)
    if is_void_input and len(stdin_urns) > 0:
        raise InvalidCapSchemaError(
            cap_urn,
            f"RULE15: in= is 'media:void' but {len(stdin_urns)} arg(s) declare a stdin source"
        )
    if not is_void_input:
        # The stdin arg IS the main input, so its URN is ``in=`` — compared
        # as tagged URNs, never as strings.
        def is_in(stdin: str) -> bool:
            try:
                return MediaUrn.from_string(stdin).is_equivalent(in_media)
            except Exception:
                return False

        if not any(is_in(stdin) for stdin in stdin_urns):
            raise InvalidCapSchemaError(
                cap_urn,
                f"RULE15: in= is '{cap.urn.in_spec()}' but no arg declares a stdin source "
                "equivalent to it"
            )

    # RULE14: Only the main input may stream. ``streaming: true`` declares
    # that an argument is consumed without a length promise — a feed. Side
    # arguments (options, model specs, prompts alongside the main input) are
    # values the runtime demuxes whole; a feed there has no meaning and would
    # let an unbounded stream reach a collector that must refuse it (L16).
    for arg in cap.args:
        if arg.streaming and not arg.is_main_input(in_media):
            raise InvalidCapSchemaError(
                cap_urn,
                f"RULE14: Argument '{arg.media_urn}' declares streaming=true but is not"
                f" the main input (no stdin source equivalent to in='{cap.urn.in_spec()}')"
                " — only the main input may be consumed without a length promise"
            )

    # RULE5: No two args may have same position
    position_set = set()
    for position, media_urn in positions:
        if position in position_set:
            raise InvalidCapSchemaError(
                cap_urn,
                f"RULE5: Duplicate position {position} in argument '{media_urn}'"
            )
        position_set.add(position)

    # RULE6: Positions must be sequential (0-based, no gaps)
    if positions:
        sorted_positions = sorted(positions, key=lambda x: x[0])
        for i, (position, _) in enumerate(sorted_positions):
            if position != i:
                raise InvalidCapSchemaError(
                    cap_urn,
                    f"RULE6: Position gap - expected {i} but found {position}"
                )

    # RULE9: No two args may have same cli_flag
    flag_set = set()
    for flag, media_urn in cli_flags:
        if flag in flag_set:
            raise InvalidCapSchemaError(
                cap_urn,
                f"RULE9: Duplicate cli_flag '{flag}' in argument '{media_urn}'"
            )
        flag_set.add(flag)


def _matches_expected_type(expected: str, value: Any) -> bool:
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return (isinstance(value, int) or isinstance(value, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    return True


async def validate_positional_arguments(cap, arguments: List[Any], registry) -> None:
    """Validate positional arguments against the cap's argument definitions.

    Checks:
      - argument count matches the cap's positional arg count;
      - required arguments are provided;
      - each provided value matches the JSON Schema ``type`` declared
        on the registry-resolved spec for the argument's media URN.

    Type information comes from the registry — there is no built-in
    URN-to-type fallback. If the resolved spec carries a JSON
    Schema with a top-level ``type``, the value is checked against
    it. Specs without a schema or without a ``type`` produce no type
    constraint and the value passes through.
    """
    from capdag.cap.definition import PositionSource
    from capdag.media.spec import resolve_media_urn

    cap_urn = cap.urn_string()
    args = cap.get_args()

    positional_args = [
        (arg, source.position)
        for arg in args
        for source in arg.sources
        if isinstance(source, PositionSource)
    ]
    positional_args.sort(key=lambda x: x[1])

    if len(arguments) > len(positional_args):
        raise TooManyArgumentsError(cap_urn, len(positional_args), len(arguments))

    for index, (arg_def, _) in enumerate(positional_args):
        if index >= len(arguments):
            if arg_def.required:
                raise MissingRequiredArgumentError(cap_urn, arg_def.media_urn)
            continue

        value = arguments[index]
        if value is None and arg_def.required:
            raise MissingRequiredArgumentError(cap_urn, arg_def.media_urn)

        resolved = await resolve_media_urn(arg_def.media_urn, registry)
        schema = resolved.schema
        expected_type: Optional[str] = (
            schema.get("type") if isinstance(schema, dict) else None
        )
        if expected_type is not None and not _matches_expected_type(expected_type, value):
            actual_type = type(value).__name__
            raise InvalidArgumentTypeError(
                cap_urn,
                arg_def.media_urn,
                arg_def.media_urn,
                value,
                [f"expected {expected_type}, got {actual_type}"],
            )
