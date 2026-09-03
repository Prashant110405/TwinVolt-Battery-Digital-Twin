"""Runtime Core and Synchronization Exceptions.

Defines the specialized exception hierarchy for digital twin runtime lifecycle,
synchronization errors, clock skew, stale telemetry, and anomaly detection failures.
"""

from typing import Any, Mapping, Optional

from src.domain.exceptions import TwinVoltDomainError


class RuntimeCoreError(TwinVoltDomainError):
    """Base exception for all errors originating within the Digital Twin runtime engine."""

    def __init__(
        self,
        message: str,
        system_id: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message, details=dict(details) if details else None)
        self.system_id = system_id

    def to_dict(self) -> dict[str, Any]:
        """Serializes exception details to a dictionary."""
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "system_id": self.system_id,
            "details": self.details,
        }


class RuntimeInitializationError(RuntimeCoreError):
    """Raised when the digital twin runtime instance fails to initialize its components."""


class RuntimeExecutionError(RuntimeCoreError):
    """Raised when an unrecoverable execution failure occurs during a simulation step."""


class SynchronizationError(RuntimeCoreError):
    """Raised when synchronization between incoming telemetry and digital twin models fails."""


class StaleTelemetryError(SynchronizationError):
    """Raised when an incoming telemetry observation is older than the configured staleness timeout."""


class ClockSkewError(SynchronizationError):
    """Raised when incoming telemetry violates monotonic timestamp ordering or future drift limits."""


class InvalidRuntimeStateError(RuntimeCoreError):
    """Raised when an operation is attempted on an uninitialized or corrupted digital twin state."""


class AnomalyDetectionError(RuntimeCoreError):
    """Raised when an error occurs during physics-informed anomaly evaluation."""
