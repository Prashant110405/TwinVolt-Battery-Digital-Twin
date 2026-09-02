"""Base Contracts, Protocols, and Models for Time-Series Storage.

Defines the repository protocols for telemetry snapshots and digital twin state records,
alongside timezone-aware datetime conversion utilities.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
import time
from typing import Any, Mapping, Optional, Protocol, Sequence, Union, runtime_checkable

from src.estimators.base import EstimationState
from src.models.types import ModelState
from src.storage.exceptions import InvalidTimeRangeError
from src.telemetry.snapshots import TelemetrySnapshot


# ------------------------------------------------------------------------------
# Timezone-Aware Timestamp Conversion Utilities
# ------------------------------------------------------------------------------
def datetime_to_timestamp_ns(dt: Union[datetime, int, float]) -> int:
    """Converts a timezone-aware or naive datetime (assumed UTC) into integer nanoseconds since UNIX epoch.

    Args:
        dt: Python datetime object, or numeric epoch seconds/nanoseconds.

    Returns:
        Integer nanoseconds since UNIX epoch (1970-01-01T00:00:00Z).
    """
    if isinstance(dt, (int, float)):
        val = float(dt)
        # If timestamp is in seconds (< 1e11), convert to ns
        if val < 1e11:
            return int(val * 1_000_000_000)
        return int(val)

    if not isinstance(dt, datetime):
        raise TypeError(f"Expected datetime or numeric timestamp, got {type(dt).__name__}.")

    # Default naive datetime to UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    epoch_seconds = dt.timestamp()
    return int(epoch_seconds * 1_000_000_000)


def timestamp_ns_to_datetime(ts_ns: int, tz: timezone = timezone.utc) -> datetime:
    """Converts integer nanoseconds since UNIX epoch into a timezone-aware datetime.

    Args:
        ts_ns: Timestamp in integer nanoseconds.
        tz: Target timezone (defaults to UTC).

    Returns:
        Timezone-aware datetime object.
    """
    if not isinstance(ts_ns, int):
        raise TypeError(f"ts_ns must be an integer, got {type(ts_ns).__name__}.")
    epoch_seconds = ts_ns / 1_000_000_000.0
    return datetime.fromtimestamp(epoch_seconds, tz=tz)


def validate_time_range(
    start_time_ns: Optional[int],
    end_time_ns: Optional[int],
    system_id: Optional[str] = None,
) -> None:
    """Validates that a query time interval is non-negative and monotonically ordered.

    Raises:
        InvalidTimeRangeError: If start_time_ns > end_time_ns or bounds are negative.
    """
    if start_time_ns is not None and start_time_ns < 0:
        raise InvalidTimeRangeError(
            f"start_time_ns cannot be negative, got {start_time_ns}.",
            system_id=system_id,
            details={"start_time_ns": start_time_ns},
        )
    if end_time_ns is not None and end_time_ns < 0:
        raise InvalidTimeRangeError(
            f"end_time_ns cannot be negative, got {end_time_ns}.",
            system_id=system_id,
            details={"end_time_ns": end_time_ns},
        )
    if start_time_ns is not None and end_time_ns is not None:
        if start_time_ns > end_time_ns:
            raise InvalidTimeRangeError(
                f"Query time range is inverted: start_time_ns={start_time_ns} > end_time_ns={end_time_ns}.",
                system_id=system_id,
                details={"start_time_ns": start_time_ns, "end_time_ns": end_time_ns},
            )


# ------------------------------------------------------------------------------
# Digital Twin State History Record
# ------------------------------------------------------------------------------
@dataclass(frozen=True)
class TwinStateRecord:
    """Immutable time-series record representing the co-simulated state of a Digital Twin."""

    record_id: str
    system_id: str
    timestamp_ns: int
    model_state: ModelState
    estimation_state: Optional[EstimationState] = None
    residuals: Mapping[str, float] = field(default_factory=dict)
    quality: str = "VALID"
    metadata: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes record to a dictionary."""
        return {
            "record_id": self.record_id,
            "system_id": self.system_id,
            "timestamp_ns": self.timestamp_ns,
            "model_state": self.model_state.to_dict() if hasattr(self.model_state, "to_dict") else {
                "soc_fraction": self.model_state.soc_fraction,
                "temperature_c": self.model_state.temperature_c,
            },
            "estimation_state": self.estimation_state.to_dict() if self.estimation_state else None,
            "residuals": dict(self.residuals),
            "quality": self.quality,
            "metadata": dict(self.metadata),
        }


# ------------------------------------------------------------------------------
# Storage Repository Protocols
# ------------------------------------------------------------------------------
@runtime_checkable
class TelemetryRepository(Protocol):
    """Protocol defining persistence and retrieval operations for TelemetrySnapshot instances."""

    def append(self, snapshot: TelemetrySnapshot) -> None:
        """Appends a single telemetry snapshot to the repository."""
        ...

    def append_many(self, snapshots: Sequence[TelemetrySnapshot]) -> int:
        """Appends a batch of telemetry snapshots to the repository.

        Returns:
            Count of successfully stored snapshots.
        """
        ...

    def query_by_time_range(
        self,
        system_id: str,
        start_time_ns: Optional[int] = None,
        end_time_ns: Optional[int] = None,
        limit: Optional[int] = None,
        descending: bool = False,
    ) -> tuple[TelemetrySnapshot, ...]:
        """Queries telemetry records for a given system within an optional timestamp interval."""
        ...

    def query_latest(self, system_id: str) -> Optional[TelemetrySnapshot]:
        """Retrieves the most recent telemetry snapshot for a given system, or None."""
        ...

    def count(self, system_id: Optional[str] = None) -> int:
        """Returns the total number of stored records for a given system, or all systems."""
        ...

    def list_systems() -> tuple[str, ...]:
        """Lists all distinct system identifiers present in the repository."""
        ...

    def clear(self, system_id: Optional[str] = None) -> None:
        """Deletes all records for a given system or clears the entire repository."""
        ...


@runtime_checkable
class StateHistoryRepository(Protocol):
    """Protocol defining persistence and retrieval operations for TwinStateRecord instances."""

    def append(self, record: TwinStateRecord) -> None:
        """Appends a single digital twin state record."""
        ...

    def append_many(self, records: Sequence[TwinStateRecord]) -> int:
        """Appends a batch of digital twin state records."""
        ...

    def query_by_time_range(
        self,
        system_id: str,
        start_time_ns: Optional[int] = None,
        end_time_ns: Optional[int] = None,
        limit: Optional[int] = None,
        descending: bool = False,
    ) -> tuple[TwinStateRecord, ...]:
        """Queries twin state records for a given system within an optional timestamp interval."""
        ...

    def query_latest(self, system_id: str) -> Optional[TwinStateRecord]:
        """Retrieves the most recent twin state record for a given system, or None."""
        ...

    def count(self, system_id: Optional[str] = None) -> int:
        """Returns the total number of stored state records."""
        ...

    def list_systems() -> tuple[str, ...]:
        """Lists all distinct system identifiers present in the repository."""
        ...

    def clear(self, system_id: Optional[str] = None) -> None:
        """Deletes all records for a given system or clears the entire repository."""
        ...


class AbstractTelemetryRepository(ABC, TelemetryRepository):
    """Abstract base class for telemetry repositories."""

    @abstractmethod
    def append(self, snapshot: TelemetrySnapshot) -> None:
        """Appends a single telemetry snapshot."""
        ...

    def append_many(self, snapshots: Sequence[TelemetrySnapshot]) -> int:
        """Default batch append looping over append."""
        count = 0
        for s in snapshots:
            self.append(s)
            count += 1
        return count

    @abstractmethod
    def query_by_time_range(
        self,
        system_id: str,
        start_time_ns: Optional[int] = None,
        end_time_ns: Optional[int] = None,
        limit: Optional[int] = None,
        descending: bool = False,
    ) -> tuple[TelemetrySnapshot, ...]:
        """Queries telemetry snapshots by time range."""
        ...

    @abstractmethod
    def query_latest(self, system_id: str) -> Optional[TelemetrySnapshot]:
        """Queries latest snapshot."""
        ...

    @abstractmethod
    def count(self, system_id: Optional[str] = None) -> int:
        """Counts stored records."""
        ...

    @abstractmethod
    def list_systems(self) -> tuple[str, ...]:
        """Lists system identifiers."""
        ...

    @abstractmethod
    def clear(self, system_id: Optional[str] = None) -> None:
        """Clears records."""
        ...


class AbstractStateHistoryRepository(ABC, StateHistoryRepository):
    """Abstract base class for state history repositories."""

    @abstractmethod
    def append(self, record: TwinStateRecord) -> None:
        """Appends a single digital twin state record."""
        ...

    def append_many(self, records: Sequence[TwinStateRecord]) -> int:
        """Default batch append looping over append."""
        count = 0
        for r in records:
            self.append(r)
            count += 1
        return count

    @abstractmethod
    def query_by_time_range(
        self,
        system_id: str,
        start_time_ns: Optional[int] = None,
        end_time_ns: Optional[int] = None,
        limit: Optional[int] = None,
        descending: bool = False,
    ) -> tuple[TwinStateRecord, ...]:
        """Queries twin state records within a time range."""
        ...

    @abstractmethod
    def query_latest(self, system_id: str) -> Optional[TwinStateRecord]:
        """Queries latest state record."""
        ...

    @abstractmethod
    def count(self, system_id: Optional[str] = None) -> int:
        """Counts stored state records."""
        ...

    @abstractmethod
    def list_systems(self) -> tuple[str, ...]:
        """Lists system identifiers."""
        ...

    @abstractmethod
    def clear(self, system_id: Optional[str] = None) -> None:
        """Clears state records."""
        ...
