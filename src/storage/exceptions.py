"""Storage Subsystem Exceptions.

Defines the specialized exception hierarchy for time-series persistence,
query validation, repository capacity constraints, and file integrity errors.
"""

from typing import Any, Mapping, Optional

from src.domain.exceptions import TwinVoltDomainError


class StorageError(TwinVoltDomainError):
    """Base exception for all errors originating within the storage subsystem."""

    def __init__(
        self,
        message: str,
        system_id: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.system_id = system_id
        self.details = dict(details) if details else {}

    def to_dict(self) -> dict[str, Any]:
        """Serializes exception details to a dictionary."""
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "system_id": self.system_id,
            "details": self.details,
        }


class InvalidTimeRangeError(StorageError):
    """Raised when a time-range query specifies an invalid interval (e.g., start > end or negative bounds)."""


class RepositoryCapacityError(StorageError):
    """Raised when repository capacity configuration or buffer allocation is invalid."""


class RecordNotFoundError(StorageError):
    """Raised when an explicit lookup for a required telemetry or state record fails."""


class StorageCorruptionError(StorageError):
    """Raised when a persistence file or log entry is corrupted or fails integrity validation."""
