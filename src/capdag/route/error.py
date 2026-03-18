"""Error types for machine notation parsing and serialization"""


class MachineSyntaxError(Exception):
    """Base error for machine notation parsing failures."""
    pass


class EmptyRouteError(MachineSyntaxError):
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
    """A wiring statement references an alias that was never defined in a header."""

    def __init__(self, alias: str):
        self.alias = alias
        super().__init__(f"wiring references undefined alias '{alias}'")


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
    """The parsed route graph has no edges (headers were defined but no wirings)."""

    def __init__(self):
        super().__init__("route has headers but no wirings — define at least one edge")


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
