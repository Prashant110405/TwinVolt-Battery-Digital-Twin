"""Application Service Layer Exceptions.

Defines the exception hierarchy for service orchestration, entity lookups,
and lifecycle operations.
"""

from typing import Any, Mapping, Optional

from src.domain.exceptions import TwinVoltDomainError


class ServiceError(TwinVoltDomainError):
    """Base exception for all application service layer errors."""

    def __init__(
        self,
        message: str,
        service_name: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message, details=dict(details) if details else None)
        self.service_name = service_name

    def to_dict(self) -> dict[str, Any]:
        """Serializes service exception details to a dictionary."""
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "service_name": self.service_name,
            "details": self.details,
        }


class EntityNotFoundError(ServiceError):
    """Raised when a requested domain entity, twin, or configuration is not found."""


class PackNotFoundError(EntityNotFoundError):
    """Raised when a requested battery pack identifier does not exist in the pack registry."""


class TwinNotFoundError(EntityNotFoundError):
    """Raised when a requested digital twin instance does not exist in the twin registry."""


class DuplicateEntityError(ServiceError):
    """Raised when attempting to register a pack or twin with an identifier that already exists."""


class InvalidServiceOperationError(ServiceError):
    """Raised when an operation violates service lifecycle or state invariants."""
