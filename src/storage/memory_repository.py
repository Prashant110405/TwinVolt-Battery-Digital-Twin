"""In-Memory Time-Series Storage Repositories.

Provides high-performance, thread-safe, bounded in-memory time-series repositories
with sub-millisecond logarithmic range lookups, FIFO eviction, and zero external dependencies.
"""

import bisect
from collections import deque
import threading
from typing import Optional, Sequence

from src.storage.base import (
    AbstractTelemetryRepository,
    StateHistoryRepository,
    TelemetryRepository,
    TwinStateRecord,
    validate_time_range,
)
from src.storage.exceptions import RepositoryCapacityError
from src.telemetry.snapshots import TelemetrySnapshot


class InMemoryTelemetryRepository(AbstractTelemetryRepository):
    """Thread-safe in-memory time-series repository for TelemetrySnapshot instances."""

    def __init__(self, max_records_per_system: Optional[int] = 100_000) -> None:
        if max_records_per_system is not None and max_records_per_system <= 0:
            raise RepositoryCapacityError(
                f"max_records_per_system must be positive, got {max_records_per_system}."
            )
        self._max_records = max_records_per_system
        self._storage: dict[str, list[TelemetrySnapshot]] = {}
        self._timestamps: dict[str, list[int]] = {}
        self._lock = threading.RLock()

    @property
    def max_records_per_system(self) -> Optional[int]:
        """Configured maximum capacity per battery system."""
        return self._max_records

    def append(self, snapshot: TelemetrySnapshot) -> None:
        """Appends a single telemetry snapshot, maintaining sorted chronological order."""
        if not isinstance(snapshot, TelemetrySnapshot):
            raise TypeError(f"Expected TelemetrySnapshot, got {type(snapshot).__name__}.")

        sys_id = snapshot.system_id
        ts = snapshot.timestamp_ns

        with self._lock:
            if sys_id not in self._storage:
                self._storage[sys_id] = []
                self._timestamps[sys_id] = []

            records = self._storage[sys_id]
            times = self._timestamps[sys_id]

            # Fast path: monotonically increasing arrival
            if not times or ts >= times[-1]:
                records.append(snapshot)
                times.append(ts)
            else:
                # Insert in sorted order
                idx = bisect.bisect_right(times, ts)
                records.insert(idx, snapshot)
                times.insert(idx, ts)

            # Apply FIFO eviction if capacity exceeded
            if self._max_records is not None and len(records) > self._max_records:
                records.pop(0)
                times.pop(0)

    def append_many(self, snapshots: Sequence[TelemetrySnapshot]) -> int:
        """Appends a batch of telemetry snapshots."""
        with self._lock:
            count = 0
            for s in snapshots:
                self.append(s)
                count += 1
            return count

    def query_by_time_range(
        self,
        system_id: str,
        start_time_ns: Optional[int] = None,
        end_time_ns: Optional[int] = None,
        limit: Optional[int] = None,
        descending: bool = False,
    ) -> tuple[TelemetrySnapshot, ...]:
        """Queries telemetry snapshots within a time interval using logarithmic binary search."""
        validate_time_range(start_time_ns, end_time_ns, system_id=system_id)

        with self._lock:
            if system_id not in self._storage or not self._storage[system_id]:
                return ()

            records = self._storage[system_id]
            times = self._timestamps[system_id]

            # Determine start index
            if start_time_ns is not None:
                start_idx = bisect.bisect_left(times, start_time_ns)
            else:
                start_idx = 0

            # Determine end index
            if end_time_ns is not None:
                end_idx = bisect.bisect_right(times, end_time_ns)
            else:
                end_idx = len(records)

            if start_idx >= end_idx:
                return ()

            result_slice = records[start_idx:end_idx]

            if descending:
                result_slice = list(reversed(result_slice))

            if limit is not None and limit > 0:
                result_slice = result_slice[:limit]

            return tuple(result_slice)

    def query_latest(self, system_id: str) -> Optional[TelemetrySnapshot]:
        """Retrieves the most recent telemetry snapshot for a given system."""
        with self._lock:
            records = self._storage.get(system_id)
            if records:
                return records[-1]
            return None

    def count(self, system_id: Optional[str] = None) -> int:
        """Returns the count of stored telemetry records."""
        with self._lock:
            if system_id is not None:
                return len(self._storage.get(system_id, []))
            return sum(len(r) for r in self._storage.values())

    def list_systems(self) -> tuple[str, ...]:
        """Lists all distinct system identifiers in the repository."""
        with self._lock:
            return tuple(sorted(self._storage.keys()))

    def clear(self, system_id: Optional[str] = None) -> None:
        """Clears records for a given system or all systems."""
        with self._lock:
            if system_id is not None:
                self._storage.pop(system_id, None)
                self._timestamps.pop(system_id, None)
            else:
                self._storage.clear()
                self._timestamps.clear()


class InMemoryStateHistoryRepository(StateHistoryRepository):
    """Thread-safe in-memory time-series repository for TwinStateRecord instances."""

    def __init__(self, max_records_per_system: Optional[int] = 100_000) -> None:
        if max_records_per_system is not None and max_records_per_system <= 0:
            raise RepositoryCapacityError(
                f"max_records_per_system must be positive, got {max_records_per_system}."
            )
        self._max_records = max_records_per_system
        self._storage: dict[str, list[TwinStateRecord]] = {}
        self._timestamps: dict[str, list[int]] = {}
        self._lock = threading.RLock()

    def append(self, record: TwinStateRecord) -> None:
        """Appends a digital twin state record."""
        if not isinstance(record, TwinStateRecord):
            raise TypeError(f"Expected TwinStateRecord, got {type(record).__name__}.")

        sys_id = record.system_id
        ts = record.timestamp_ns

        with self._lock:
            if sys_id not in self._storage:
                self._storage[sys_id] = []
                self._timestamps[sys_id] = []

            records = self._storage[sys_id]
            times = self._timestamps[sys_id]

            if not times or ts >= times[-1]:
                records.append(record)
                times.append(ts)
            else:
                idx = bisect.bisect_right(times, ts)
                records.insert(idx, record)
                times.insert(idx, ts)

            if self._max_records is not None and len(records) > self._max_records:
                records.pop(0)
                times.pop(0)

    def append_many(self, records: Sequence[TwinStateRecord]) -> int:
        """Appends a batch of state records."""
        with self._lock:
            count = 0
            for r in records:
                self.append(r)
                count += 1
            return count

    def query_by_time_range(
        self,
        system_id: str,
        start_time_ns: Optional[int] = None,
        end_time_ns: Optional[int] = None,
        limit: Optional[int] = None,
        descending: bool = False,
    ) -> tuple[TwinStateRecord, ...]:
        """Queries twin state records within a time range."""
        validate_time_range(start_time_ns, end_time_ns, system_id=system_id)

        with self._lock:
            if system_id not in self._storage or not self._storage[system_id]:
                return ()

            records = self._storage[system_id]
            times = self._timestamps[system_id]

            start_idx = bisect.bisect_left(times, start_time_ns) if start_time_ns is not None else 0
            end_idx = bisect.bisect_right(times, end_time_ns) if end_time_ns is not None else len(records)

            if start_idx >= end_idx:
                return ()

            result_slice = records[start_idx:end_idx]
            if descending:
                result_slice = list(reversed(result_slice))
            if limit is not None and limit > 0:
                result_slice = result_slice[:limit]

            return tuple(result_slice)

    def query_latest(self, system_id: str) -> Optional[TwinStateRecord]:
        """Retrieves the latest twin state record for a system."""
        with self._lock:
            records = self._storage.get(system_id)
            if records:
                return records[-1]
            return None

    def count(self, system_id: Optional[str] = None) -> int:
        """Counts stored state records."""
        with self._lock:
            if system_id is not None:
                return len(self._storage.get(system_id, []))
            return sum(len(r) for r in self._storage.values())

    def list_systems(self) -> tuple[str, ...]:
        """Lists system identifiers."""
        with self._lock:
            return tuple(sorted(self._storage.keys()))

    def clear(self, system_id: Optional[str] = None) -> None:
        """Clears state records."""
        with self._lock:
            if system_id is not None:
                self._storage.pop(system_id, None)
                self._timestamps.pop(system_id, None)
            else:
                self._storage.clear()
                self._timestamps.clear()
