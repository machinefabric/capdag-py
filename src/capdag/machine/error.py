"""Error types for machine notation parsing, resolution, and serialization"""


class MachineSyntaxError(Exception):
    """Base error for machine notation parsing failures."""
    pass


class EmptyMachineError(MachineSyntaxError):
    """Input string is empty or contains only whitespace."""

    def __init__(self):
        super().__init__("machine notation is empty")


class UnterminatedStatementError(MachineSyntaxError):
    """A statement bracket '[' was opened but never closed with ']'."""

    def __init__(self, position: int):
        self.position = position
        super().__init__(f"unterminated statement starting at byte {position}")


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


class InvalidWiringError(MachineSyntaxError):
    """A wiring statement has invalid structure or conflicting media types."""

    def __init__(self, position: int, details: str):
        self.position = position
        self.details = details
        super().__init__(f"invalid wiring at statement {position}: {details}")


class InvalidMediaUrnError(MachineSyntaxError):
    """A media URN referenced in a header failed to parse."""

    def __init__(self, alias: str, details: str):
        self.alias = alias
        self.details = details
        super().__init__(f"invalid media URN in cap '{alias}': {details}")


class InvalidHeaderError(MachineSyntaxError):
    """A header statement has invalid structure."""

    def __init__(self, position: int, details: str):
        self.position = position
        self.details = details
        super().__init__(f"invalid header at statement {position}: {details}")


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


# =============================================================================
# Resolution errors — raised during anchor-realization phase
# =============================================================================

class MachineAbstractionError(Exception):
    """Raised during anchor-realization (resolution) phase."""
    pass


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
    def __init__(self, strand_index: int, cap_urn: str):
        super().__init__(
            f"in strand {strand_index}, cap '{cap_urn}': source-to-cap-arg assignment is ambiguous "
            "(multiple minimum-cost matchings exist)"
        )
        self.strand_index = strand_index
        self.cap_urn = cap_urn


class CyclicMachineStrandError(MachineAbstractionError):
    def __init__(self, strand_index: int):
        super().__init__(f"strand {strand_index}: resolved data-flow graph contains a cycle")
        self.strand_index = strand_index


class RuntimeMediaInferenceError(MachineAbstractionError):
    """A cap could not be applied to the runtime input media flowing into it
    while realizing a strand — the declared input/output specs are
    incompatible with the concrete upstream media. Realization cannot invent
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


class NoStdinBindingError(MachineAbstractionError):
    """The resolver's source-to-arg assignment for a cap edge has no binding
    feeding the cap's stdin argument. The primary (main-input) source is
    missing — the wiring cannot be realized into a data-flow step."""

    def __init__(self, strand_index: int, cap_urn: str, stdin_arg: str):
        super().__init__(
            f"strand {strand_index}: cap '{cap_urn}' has no wiring source bound to "
            f"its stdin argument '{stdin_arg}'"
        )
        self.strand_index = strand_index
        self.cap_urn = cap_urn
        self.stdin_arg = stdin_arg


class NonProducerSecondaryArgError(MachineAbstractionError):
    """A non-primary (convergence) wiring source is NOT another cap's output.
    Only a cap output may be wired into a non-main argument; a raw input
    feeding a non-main argument is an argument VALUE (default / setting /
    config / user input), delivered through the argument value channel,
    never wired. Exposed hard rather than silently mis-routed."""

    def __init__(self, strand_index: int, cap_urn: str, arg_urn: str):
        super().__init__(
            f"strand {strand_index}: cap '{cap_urn}' arg '{arg_urn}' is wired from a "
            "source that is not a cap output; wire only cap outputs into non-main "
            "args, deliver everything else as an argument value"
        )
        self.strand_index = strand_index
        self.cap_urn = cap_urn
        self.arg_urn = arg_urn


class DisconnectedStrandError(MachineAbstractionError):
    """A strand's edges do not form a data-flow graph whose every source is
    reachable (an unreachable edge, or a source whose producer never becomes
    available)."""

    def __init__(self, strand_index: int):
        super().__init__(f"strand {strand_index}: edges do not form a connected data-flow graph")
        self.strand_index = strand_index


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
