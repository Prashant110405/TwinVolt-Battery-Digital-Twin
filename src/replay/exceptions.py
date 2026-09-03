"""Drive Cycle Replay and Tracking Evaluation Exceptions.

Defines the specialized exception hierarchy for drive cycle profile errors,
metric evaluation anomalies, and replay execution failures.
"""

from typing import Any, Mapping, Optional

from src.domain.exceptions import TwinVoltDomainError


class ReplayError(TwinVoltDomainError):
    """Base exception for all errors originating within the drive cycle replay subsystem."""

    def __init__(
        self,
        message: str,
        profile_name: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message, details=dict(details) if details else None)
        self.profile_name = profile_name

    def to_dict(self) -> dict[str, Any]:
        """Serializes exception details to a dictionary."""
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "profile_name": self.profile_name,
            "details": self.details,
        }


class InvalidProfileError(ReplayError):
    """Raised when a drive cycle profile definition or time-series vector violates structural invariants."""


class EvaluationError(ReplayError):
    """Raised when metric evaluation encounters malformed inputs, mismatched lengths, or non-finite values."""


class ReplayExecutionError(ReplayError):
    """Raised when an unrecoverable failure occurs during drive cycle replay execution."""
