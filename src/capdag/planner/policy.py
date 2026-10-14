"""What a step does when it fails.

It is written in notation on the step (``fetch{retry=3}``) and carried by the
step's node in a plan, so it lives where both can name it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

#: The run fails. The default.
ON_ERROR_FAIL = "fail"
#: The step's outputs are absent and the run goes on.
ON_ERROR_ABSENT = "absent"

_ON_ERROR_VALUES = (ON_ERROR_FAIL, ON_ERROR_ABSENT)

#: The largest count of further attempts a policy holds.
MAX_RETRY = 0xFFFF_FFFF


@dataclass(frozen=True)
class StepPolicy:
    """What a step does when it fails (capdag/docs/09-machine-notation.md
    §Step policy). The default — no policy written — is to fail the run at
    once."""

    #: Further attempts after a failure whose class is retryable.
    retry: int = 0
    #: What a failure that stands (after its retries) does to the run.
    on_error: str = ON_ERROR_FAIL

    def __post_init__(self) -> None:
        if isinstance(self.retry, bool) or not isinstance(self.retry, int):
            raise ValueError(f"retry is a whole number of further attempts, not {self.retry!r}")
        if not 0 <= self.retry <= MAX_RETRY:
            raise ValueError(f"retry is a whole number of further attempts, not {self.retry!r}")
        if self.on_error not in _ON_ERROR_VALUES:
            raise ValueError(f"unknown on_error: {self.on_error!r}")

    def is_default(self) -> bool:
        """Whether this is the policy of a step that wrote none."""
        return self == StepPolicy()

    def to_notation(self) -> str:
        """The policy as notation writes it after a step alias: ``{retry=3}``,
        ``{on_error=absent}``, both in that order, or nothing for the
        default."""
        entries = []
        if self.retry > 0:
            entries.append(f"retry={self.retry}")
        if self.on_error == ON_ERROR_ABSENT:
            entries.append("on_error=absent")
        if not entries:
            return ""
        return "{" + ", ".join(entries) + "}"

    def to_dict(self) -> Dict[str, Any]:
        """The policy as a plan carries it: both fields, always."""
        return {"retry": self.retry, "on_error": self.on_error}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StepPolicy":
        """Read a policy. A field left out is its default; an ``on_error``
        this library does not know is refused — a policy nobody here can
        follow is not a policy."""
        if not isinstance(data, dict):
            raise ValueError(f"a step policy is an object, not {data!r}")
        return cls(retry=data.get("retry", 0), on_error=data.get("on_error", ON_ERROR_FAIL))
