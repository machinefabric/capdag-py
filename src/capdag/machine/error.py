"""Error types for machine notation parsing, resolution, and serialization.

Notation is read in two phases, each with its own error family: what the
text alone decides (`MachineSyntaxError`), and what takes the cap
definitions to decide (`MachineAbstractionError`). `MachineParseError` is
what `parse_machine` raises, wrapping one or the other.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple


# =============================================================================
# Syntax errors — what the text alone decides
# =============================================================================

class MachineSyntaxError(Exception):
    """Base error for machine notation parsing failures."""
    pass


class EmptyMachineError(MachineSyntaxError):
    """Input string is empty or contains only whitespace."""

    def __init__(self):
        super().__init__("machine notation is empty")


class InvalidCapUrnError(MachineSyntaxError):
    """A cap URN in a header statement failed to parse."""

    def __init__(self, alias: str, details: str):
        self.alias = alias
        self.details = details
        super().__init__(f"invalid cap URN in header '{alias}': {details}")


class UndefinedAliasError(MachineSyntaxError):
    """A wiring's cap-position name is neither a local header nor a registered
    cap alias in the fabric registry."""

    def __init__(self, alias: str):
        self.alias = alias
        super().__init__(
            f"wiring references undefined alias '{alias}' "
            f"(not a local header and not a registered cap alias)"
        )


class AliasNotACapError(MachineSyntaxError):
    """A wiring's cap-position name resolved to a fabric alias whose target is
    a media URN, not a cap. The cap position requires a cap."""

    def __init__(self, alias: str, target: str):
        self.alias = alias
        self.target = target
        super().__init__(
            f"alias '{alias}' in cap position resolves to a media URN ('{target}'), "
            f"but a cap is required there"
        )


class DuplicateAliasError(MachineSyntaxError):
    """Two header statements define the same alias."""

    def __init__(self, alias: str, first_position: int):
        self.alias = alias
        self.first_position = first_position
        super().__init__(
            f"duplicate alias '{alias}' (first defined at statement {first_position})"
        )


class InvalidMediaUrnError(MachineSyntaxError):
    """A media URN referenced in a header failed to parse."""

    def __init__(self, alias: str, details: str):
        self.alias = alias
        self.details = details
        super().__init__(f"invalid media URN in cap '{alias}': {details}")


class NoEdgesError(MachineSyntaxError):
    """The parsed machine graph has no edges (headers were defined but no wirings)."""

    def __init__(self):
        super().__init__("machine has headers but no wirings — define at least one edge")


class NodeAliasCollisionError(MachineSyntaxError):
    """A wiring references an alias used as a node name that collides with a header alias."""

    def __init__(self, name: str, alias: str):
        self.name = name
        self.alias = alias
        super().__init__(f"node name '{name}' collides with cap alias '{alias}'")


class ParseError(MachineSyntaxError):
    """PEG parse error from the pest grammar."""

    def __init__(self, details: str):
        self.details = details
        super().__init__(f"parse error: {details}")


class MachineReferenceWithoutSourceError(MachineSyntaxError):
    """A machine header names another machine, and the notation is read with
    nothing to resolve it against."""

    def __init__(self, alias: str, reference: str):
        self.alias = alias
        self.reference = reference
        super().__init__(
            f"machine header '{alias}' refers to \"{reference}\", and no machine source "
            "was given to resolve it"
        )


class UnnamedConstantError(MachineSyntaxError):
    """A constant appears as a member without a name."""

    def __init__(self, constant: str, position: int):
        self.constant = constant
        self.position = position
        super().__init__(
            f"constant {constant} in statement {position} names no arg — "
            f"write it as name={constant}"
        )


class ReservedNodeNameError(MachineSyntaxError):
    """A node is named `true`, `false` or `null`."""

    def __init__(self, name: str, position: int):
        self.name = name
        self.position = position
        super().__init__(f"'{name}' in statement {position} is a constant, not a node name")


class SeveralUnnamedTargetsError(MachineSyntaxError):
    """More than one target of a wiring is unnamed."""

    def __init__(self, position: int, targets: List[str]):
        self.position = position
        self.targets = list(targets)
        super().__init__(
            f"statement {position} has several unnamed targets ({', '.join(targets)}) — "
            "only the main output is taken without a name"
        )


class InvalidPolicyError(MachineSyntaxError):
    """A step policy has an unknown key, a repeated key, or a value outside
    the table."""

    def __init__(self, step: str, position: int, details: str):
        self.step = step
        self.position = position
        self.details = details
        super().__init__(f"invalid policy on step '{step}' in statement {position}: {details}")


# =============================================================================
# Resolution errors — what takes the cap definitions to decide
# =============================================================================

class MachineAbstractionError(Exception):
    """Raised during the resolution phase."""
    pass


@dataclass(frozen=True)
class UndecidedMember:
    """A member of a wiring whose arg the types alone do not decide."""

    #: The node, as the notation named it. Empty where no notation is at hand
    #: (a strand resolved from a planner path): the member is then known by
    #: its type alone.
    node: str
    #: The media URN the member holds.
    source_urn: str
    #: The args — or, for a machine in step position, the inputs — it could go
    #: to, by name, in the order the definition declares them.
    could_be: Tuple[str, ...]

    def __str__(self) -> str:
        who = f"a member of type '{self.source_urn}'"
        if self.node:
            who = f"'{self.node}' ({self.source_urn})"
        return who + " could be " + " or ".join(self.could_be)


def _undecided_list(members) -> str:
    return "; ".join(str(member) for member in members)


class NoCapabilityStepsError(MachineAbstractionError):
    def __init__(self):
        super().__init__("strand or wiring set contains no capability steps")


class UnknownCapError(MachineAbstractionError):
    def __init__(self, cap_urn: str):
        super().__init__(f"cap URN '{cap_urn}' is not in the cap registry cache")
        self.cap_urn = cap_urn


class UnmatchedSourceInCapArgsError(MachineAbstractionError):
    def __init__(self, strand_index: int, cap_urn: str, source_urn: str):
        super().__init__(
            f"in strand {strand_index}, cap '{cap_urn}': source URN '{source_urn}' "
            "does not conform to any of the cap's input arguments"
        )
        self.strand_index = strand_index
        self.cap_urn = cap_urn
        self.source_urn = source_urn


class AmbiguousMachineNotationError(MachineAbstractionError):
    """The types do not say which arg some unnamed member is for."""

    def __init__(self, strand_index: int, cap_urn: str, members: List[UndecidedMember]):
        super().__init__(
            f"in strand {strand_index}, cap '{cap_urn}': the types do not say which arg "
            f"these members are for — name them: {_undecided_list(members)}"
        )
        self.strand_index = strand_index
        self.cap_urn = cap_urn
        #: The members to name, each with what it could be for.
        self.members = list(members)


class CyclicMachineStrandError(MachineAbstractionError):
    def __init__(self, strand_index: int):
        super().__init__(f"strand {strand_index}: resolved data-flow graph contains a cycle")
        self.strand_index = strand_index


class RuntimeMediaInferenceError(MachineAbstractionError):
    """A cap could not be applied to the runtime input media flowing into it
    while resolving a strand — the declared input/output specs are
    incompatible with the concrete upstream media. Resolution cannot invent
    a valid data type, so it fails hard rather than guessing."""

    def __init__(self, strand_index: int, cap_urn: str, runtime_input: str, reason: str):
        super().__init__(
            f"strand {strand_index}: cap '{cap_urn}' cannot be applied to runtime "
            f"input '{runtime_input}': {reason}"
        )
        self.strand_index = strand_index
        self.cap_urn = cap_urn
        self.runtime_input = runtime_input
        self.reason = reason


class CapDoesNotDeclareInputError(MachineAbstractionError):
    """A cap does not declare its input: no argument declares a `Stdin`
    source whose URN is the cap's `in=`. The main input is the value piped in
    on stdin, so the main arg always declares a stdin source carrying `in=`
    (its declared slot URN may differ — e.g. a file-path slot whose piped
    content is `in=`). A cap without such an arg cannot receive its input to
    thread the strand's runtime media."""

    def __init__(self, strand_index: int, cap_urn: str):
        super().__init__(
            f"strand {strand_index}: cap '{cap_urn}' does not declare its input "
            "(no argument declares a stdin source whose URN is its in=)"
        )
        self.strand_index = strand_index
        self.cap_urn = cap_urn


class DisconnectedStrandError(MachineAbstractionError):
    """A strand's edges do not form a data-flow graph whose every source is
    reachable (an unreachable edge, or a source whose producer never becomes
    available)."""

    def __init__(self, strand_index: int):
        super().__init__(f"strand {strand_index}: edges do not form a connected data-flow graph")
        self.strand_index = strand_index


class _InStrand(MachineAbstractionError):
    """An error of one strand: its message opens with the strand it is in."""

    def __init__(self, strand_index: int, message: str):
        super().__init__(f"strand {strand_index}: {message}")
        self.strand_index = strand_index


class _AtStatement(MachineAbstractionError):
    """An error of one statement: its message opens with the statement."""

    def __init__(self, position: int, message: str):
        super().__init__(f"statement {position}: {message}")
        self.position = position


class UnknownArgNameError(_InStrand):
    """A member names an arg the step's cap does not declare."""

    def __init__(self, strand_index: int, cap_urn: str, name: str, declared: List[str]):
        super().__init__(
            strand_index,
            f"cap '{cap_urn}' declares no arg named '{name}' (it declares: {', '.join(declared)})",
        )
        self.cap_urn = cap_urn
        self.name = name
        self.declared = list(declared)


class UnknownOutputNameError(_InStrand):
    """A target names an output the step's cap does not declare."""

    def __init__(self, strand_index: int, cap_urn: str, name: str, declared: List[str]):
        super().__init__(
            strand_index,
            f"cap '{cap_urn}' declares no output named '{name}' "
            f"(it declares: {', '.join(declared)})",
        )
        self.cap_urn = cap_urn
        self.name = name
        self.declared = list(declared)


class UnknownStrandOutputError(_InStrand):
    """A strand step takes, by media URN, an output its cap does not declare
    as another output."""

    def __init__(self, strand_index: int, cap_urn: str, output_urn: str, declared: List[str]):
        super().__init__(
            strand_index,
            f"cap '{cap_urn}' declares no other output '{output_urn}' "
            f"(it declares: {', '.join(declared)})",
        )
        self.cap_urn = cap_urn
        self.output_urn = output_urn
        self.declared = list(declared)


class SourceDoesNotConformToArgError(_InStrand):
    """A named member's URN does not conform to the type that arg accepts."""

    def __init__(self, strand_index: int, cap_urn: str, name: str, accepts: str, source_urn: str):
        super().__init__(
            strand_index,
            f"cap '{cap_urn}' arg '{name}' accepts '{accepts}', and its source is '{source_urn}'",
        )
        self.cap_urn = cap_urn
        self.name = name
        self.accepts = accepts
        self.source_urn = source_urn


class ConstantFailsValidationError(_InStrand):
    """A constant does not satisfy the validation of the arg it is bound to."""

    def __init__(self, strand_index: int, cap_urn: str, name: str, constant: str, reason: str):
        super().__init__(
            strand_index,
            f"cap '{cap_urn}' arg '{name}' refuses the constant {constant}: {reason}",
        )
        self.cap_urn = cap_urn
        self.name = name
        self.constant = constant
        self.reason = reason


class ArgBoundTwiceError(_InStrand):
    """An arg that takes one value is named by two members."""

    def __init__(self, strand_index: int, cap_urn: str, name: str, count: int):
        super().__init__(
            strand_index,
            f"cap '{cap_urn}' arg '{name}' takes one value and is named by {count} members",
        )
        self.cap_urn = cap_urn
        self.name = name
        self.count = count


class MainInputUnboundError(_InStrand):
    """A step whose cap takes an input is given no member for it."""

    def __init__(self, strand_index: int, cap_urn: str, main_input: str):
        super().__init__(
            strand_index,
            f"cap '{cap_urn}' takes an input ('{main_input}') and no member of the wiring "
            "is bound to it",
        )
        self.cap_urn = cap_urn
        self.main_input = main_input


class OutputTakenTwiceError(_InStrand):
    """Two targets of one wiring take the same output."""

    def __init__(self, strand_index: int, cap_urn: str, output: str):
        super().__init__(
            strand_index, f"cap '{cap_urn}' output '{output}' is taken twice in one wiring"
        )
        self.cap_urn = cap_urn
        self.output = output


class NoMainOutputError(_InStrand):
    """An unnamed target takes the main output of a step whose cap has none."""

    def __init__(self, strand_index: int, cap_urn: str):
        super().__init__(
            strand_index,
            f"cap '{cap_urn}' has no main output to take (its out= is media:void)",
        )
        self.cap_urn = cap_urn


class UntypedMachineInputError(_AtStatement):
    """A wiring holds an unnamed member that nothing produces and whose arg
    nothing decides."""

    def __init__(self, position: int, cap_urn: str, members: List[str]):
        super().__init__(
            position,
            f"cap '{cap_urn}' is given unnamed machine inputs whose arg nothing decides "
            f"({', '.join(members)}) — name them",
        )
        self.cap_urn = cap_urn
        self.members = list(members)


class UnknownMachineReferenceError(MachineAbstractionError):
    """A machine header's reference does not resolve."""

    def __init__(self, alias: str, reference: str, details: str):
        super().__init__(
            f"machine header '{alias}' refers to \"{reference}\", which does not resolve: {details}"
        )
        self.alias = alias
        self.reference = reference
        self.details = details


class CyclicMachineReferenceError(MachineAbstractionError):
    """A machine includes itself."""

    def __init__(self, chain: List[str]):
        super().__init__("a machine includes itself: " + " -> ".join(chain))
        #: Every machine on the way round, from the first to the one that
        #: closes the circle.
        self.chain = list(chain)


class InvalidIncludedMachineError(MachineAbstractionError):
    """A machine named in a header is not itself a valid machine."""

    def __init__(self, alias: str, reference: str, cause: "MachineParseError"):
        super().__init__(f"machine '{alias}' (\"{reference}\") is not a valid machine: {cause}")
        self.alias = alias
        self.reference = reference
        #: Why the included machine is not a valid machine.
        self.cause = cause


class PolicyOnMachineError(_AtStatement):
    """A policy is written on a step that is another machine."""

    def __init__(self, position: int, alias: str):
        super().__init__(
            position,
            f"'{alias}' is a machine, and a policy is written on it — "
            "write it on the steps inside",
        )
        self.alias = alias


class UnknownMachineInputError(_AtStatement):
    """A member names an input the machine in step position does not have."""

    def __init__(self, position: int, alias: str, name: str, declared: List[str]):
        super().__init__(
            position,
            f"machine '{alias}' has no input named '{name}' (its inputs: {', '.join(declared)})",
        )
        self.alias = alias
        self.name = name
        self.declared = list(declared)


class UnknownMachineOutputError(_AtStatement):
    """A target names an output the machine in step position does not have."""

    def __init__(self, position: int, alias: str, name: str, declared: List[str]):
        super().__init__(
            position,
            f"machine '{alias}' has no output named '{name}' (its outputs: {', '.join(declared)})",
        )
        self.alias = alias
        self.name = name
        self.declared = list(declared)


class MachineInputBindingError(_AtStatement):
    """An input of a machine in step position is not bound by exactly one
    member."""

    def __init__(self, position: int, alias: str, input_name: str, count: int):
        super().__init__(
            position,
            f"input '{input_name}' of machine '{alias}' is given {count} members — "
            "every input of a machine takes exactly one",
        )
        self.alias = alias
        self.input_name = input_name
        self.count = count


class MachineOutputTakenTwiceError(_AtStatement):
    """Two targets of one wiring take the same output of a machine."""

    def __init__(self, position: int, alias: str, output: str):
        super().__init__(
            position, f"output '{output}' of machine '{alias}' is taken twice in one wiring"
        )
        self.alias = alias
        self.output = output


class UnnamedMachineTargetError(_AtStatement):
    """An unnamed target of a machine step, where the other targets leave
    more than one output, or none."""

    def __init__(self, position: int, alias: str, left: List[str]):
        super().__init__(
            position,
            f"an unnamed target of machine '{alias}' has {len(left)} output(s) left to take "
            f"({', '.join(left)}) — name it",
        )
        self.alias = alias
        self.left = list(left)


class UntypedMachineMemberError(_AtStatement):
    """An unnamed member of a machine step that nothing gives a type."""

    def __init__(self, position: int, alias: str, members: List[str]):
        super().__init__(
            position,
            f"machine '{alias}' is given unnamed members that have no type to be matched by "
            f"({', '.join(members)}) — name them",
        )
        self.alias = alias
        self.members = list(members)


class UnmatchedMachineMemberError(_AtStatement):
    """An unnamed member of a machine step conforms to no input left for it."""

    def __init__(self, position: int, alias: str, source_urn: str):
        super().__init__(
            position, f"a member of type '{source_urn}' fits no input left of machine '{alias}'"
        )
        self.alias = alias
        self.source_urn = source_urn


class AmbiguousMachineMembersError(_AtStatement):
    """The unnamed members of a machine step fit its inputs in more than one
    way."""

    def __init__(self, position: int, alias: str, members: List[UndecidedMember]):
        super().__init__(
            position,
            f"the types do not say which input of machine '{alias}' these members are for — "
            f"name them: {_undecided_list(members)}",
        )
        self.alias = alias
        #: The members to name, each with what it could be for.
        self.members = list(members)


class SourceDoesNotConformToMachineInputError(_AtStatement):
    """A named member's URN does not conform to the type of the machine input
    it names."""

    def __init__(self, position: int, alias: str, name: str, accepts: str, source_urn: str):
        super().__init__(
            position,
            f"input '{name}' of machine '{alias}' holds '{accepts}', and its source is "
            f"'{source_urn}'",
        )
        self.alias = alias
        self.name = name
        self.accepts = accepts
        self.source_urn = source_urn


class UncachedMediaDefError(MachineAbstractionError):
    """A node's media has no cached definition: the render payload has no
    title for it, and a title is never made up from a URN."""

    def __init__(self, media_urn: str):
        super().__init__(
            f"media URN '{media_urn}' has no cached spec — cannot emit a display title for render payload"
        )
        self.media_urn = media_urn


class UncachedCapError(MachineAbstractionError):
    """A step's cap has no cached definition: the render payload has no title
    for it."""

    def __init__(self, cap_urn: str):
        super().__init__(
            f"cap URN '{cap_urn}' has no cached definition — cannot emit a display title for render payload"
        )
        self.cap_urn = cap_urn


class NodeMediaConflictError(MachineAbstractionError):
    """The wirings that touch a node give it URNs that are not on one
    specialization chain."""

    def __init__(self, node: str, first: str, second: str):
        super().__init__(
            f"node '{node}' is given media URNs that are not on one specialization chain: "
            f"'{first}' and '{second}'"
        )
        self.node = node
        self.first = first
        self.second = second


class MachineParseError(Exception):
    """Combined error from parse_machine. Wraps either a MachineSyntaxError or
    MachineAbstractionError."""

    def __init__(self, cause: Exception):
        super().__init__(str(cause))
        self.cause = cause

    @property
    def is_syntax_error(self) -> bool:
        return isinstance(self.cause, MachineSyntaxError)

    @property
    def is_abstraction_error(self) -> bool:
        return isinstance(self.cause, MachineAbstractionError)
