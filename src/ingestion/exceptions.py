"""Ingestion Subsystem Exceptions.

Defines the error hierarchy for telemetry ingestion, parsing, validation,
rate limiting, and protocol adaptation.
"""

from typing import Any, Mapping, Optional

from src.domain.exceptions import TwinVoltDomainError


class IngestionError(TwinVoltDomainError):
    """Base exception for all errors encountered within the telemetry ingestion layer."""

    def __init__(
        self,
        message: str,
        source_id: Optional[str] = None,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.source_id = source_id
        self.details = dict(details) if details else {}

    def to_dict(self) -> dict[str, Any]:
        """Serializes exception details to dictionary."""
        return {
            "error_type": self.__class__.__name__,
            "message": str(self),
            "source_id": self.source_id,
            "details": self.details,
        }


class MalformedPayloadError(IngestionError):
    """Raised when an incoming raw payload has invalid syntax, malformed bytes, or corrupt structure."""


class IngestionValidationError(IngestionError):
    """Raised when an ingested telemetry payload violates data validation invariants or schemas."""


class RateLimitExceededError(IngestionError):
    """Raised when telemetry packet arrival frequency exceeds configured rate limits."""


class TimestampMonotonicityError(IngestionError):
    """Raised when an incoming telemetry packet violates timestamp monotonicity constraints."""


class AdapterNotFoundError(IngestionError):
    """Raised when no registered adapter can process a given telemetry payload format."""


class FrameChecksumError(IngestionError):
    """Raised when a binary serial/BMS frame fails checksum or CRC integrity validation."""
