"""Time-Series Persistence and Storage Subsystem.

Provides repository abstractions, in-memory circular buffers, and append-only
file persistence for telemetry snapshots and digital twin state records.
"""

from src.storage.base import (
    AbstractStateHistoryRepository,
    AbstractTelemetryRepository,
    StateHistoryRepository,
    TelemetryRepository,
    TwinStateRecord,
    datetime_to_timestamp_ns,
    timestamp_ns_to_datetime,
    validate_time_range,
)
from src.storage.exceptions import (
    InvalidTimeRangeError,
    RecordNotFoundError,
    RepositoryCapacityError,
    StorageCorruptionError,
    StorageError,
)
from src.storage.file_repository import (
    FileAppendStateHistoryRepository,
    FileAppendTelemetryRepository,
)
from src.storage.memory_repository import (
    InMemoryStateHistoryRepository,
    InMemoryTelemetryRepository,
)

__all__ = [
    "TelemetryRepository",
    "StateHistoryRepository",
    "AbstractTelemetryRepository",
    "AbstractStateHistoryRepository",
    "InMemoryTelemetryRepository",
    "InMemoryStateHistoryRepository",
    "FileAppendTelemetryRepository",
    "FileAppendStateHistoryRepository",
    "TwinStateRecord",
    "datetime_to_timestamp_ns",
    "timestamp_ns_to_datetime",
    "validate_time_range",
    "StorageError",
    "InvalidTimeRangeError",
    "RepositoryCapacityError",
    "RecordNotFoundError",
    "StorageCorruptionError",
]
