"""Event Subsystem Exceptions.

Defines the specialized exception hierarchy for event creation, bus subscription,
and handler dispatch errors.
"""

from typing import Any, Mapping, Optional

from src.domain.exceptions import TwinVoltDomainError


class EventError(TwinVoltDomainError):
    """Base exception for all errors originating within the event and observability subsystem."""

    def __init__(
        self,
        message: str,
        event_type: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.event_type = event_type
        self.details = dict(details) if details else {}

    def to_dict(self) -> dict[str, Any]:
        """Serializes exception details to a dictionary."""
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "event_type": self.event_type,
            "details": self.details,
        }


class InvalidEventError(EventError):
    """Raised when an event payload or metadata violates structural invariants or timestamps."""


class SubscriptionError(EventError):
    """Raised when an event subscription configuration or callback signature is invalid."""


class HandlerExecutionError(EventError):
    """Raised when a subscriber handler raises an unhandled exception during event processing."""

    def __init__(
        self,
        message: str,
        handler_name: str,
        event_type: Optional[str] = None,
        cause: Optional[Exception] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message, event_type=event_type, details=details)
        self.handler_name = handler_name
        self.cause = cause
