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
