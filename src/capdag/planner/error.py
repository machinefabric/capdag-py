"""Planner error types matching Rust's PlannerError enum."""

from __future__ import annotations


class PlannerError(Exception):
    """Base class for all planner errors."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class InvalidInputError(PlannerError):
    """Invalid input provided to the planner."""
    pass


class InternalError(PlannerError):
    """Internal planner logic error — indicates a bug."""
    pass


class NotFoundError(PlannerError):
    """Requested resource not found."""
    pass


class RegistryError(PlannerError):
    """Error from the capability registry."""
    pass


class ExecutionError(PlannerError):
    """Error during plan execution."""
    pass


class InvalidPathError(PlannerError):
    """Invalid capability chain path."""
    pass
