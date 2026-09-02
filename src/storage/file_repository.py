"""File-Backed Append-Only Time-Series Storage Repositories.

Provides durable, lightweight JSON-Lines persistence for telemetry snapshots
and digital twin state records with offset-index caching for fast time-range querying.
"""

import bisect
import json
import os
from pathlib import Path
import threading
from typing import Any, Optional, Sequence, Union

from src.models.types import ModelState
from src.schemas.telemetry_schema import validate_telemetry_payload
from src.storage.base import (
    AbstractTelemetryRepository,
    StateHistoryRepository,
    TelemetryRepository,
    TwinStateRecord,
    validate_time_range,
)
from src.storage.exceptions import StorageCorruptionError, StorageError
from src.telemetry.snapshots import TelemetrySnapshot


class FileAppendTelemetryRepository(AbstractTelemetryRepository):
    """Append-only JSON-Lines file storage repository for TelemetrySnapshot instances."""

    def __init__(self, base_directory: Union[str, Path], strict_parsing: bool = False) -> None:
        self._dir = Path(base_directory)
        self._strict = strict_parsing
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._index: dict[str, list[tuple[int, int]]] = {}  # system_id -> list of (timestamp_ns, file_offset)
        self._initialized_systems: set[str] = set()

    @property
    def base_directory(self) -> Path:
        """Configured base directory."""
        return self._dir

    def _get_system_file_path(self, system_id: str) -> Path:
        """Returns the file path for a given system's telemetry log."""
        # Sanitize system_id for filesystem safety
        safe_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in system_id)
        return self._dir / f"{safe_id}_telemetry.jsonl"

    def _ensure_indexed(self, system_id: str) -> None:
        """Reads file once to build in-memory timestamp offset index."""
        if system_id in self._initialized_systems:
            return

        file_path = self._get_system_file_path(system_id)
        self._index[system_id] = []

        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                offset = 0
                while True:
                    line_start = f.tell()
                    line = f.readline()
                    if not line:
                        break
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        record_dict = json.loads(line_str)
                        ts = int(record_dict.get("timestamp_ns", 0))
                        self._index[system_id].append((ts, line_start))
                    except Exception as exc:
                        if self._strict:
                            raise StorageCorruptionError(
                                f"Corrupted line at offset {line_start} in '{file_path}': {exc}",
                                system_id=system_id,
                            ) from exc

        self._initialized_systems.add(system_id)

    def append(self, snapshot: TelemetrySnapshot) -> None:
        """Appends a telemetry snapshot to the system's JSON-Lines file."""
        if not isinstance(snapshot, TelemetrySnapshot):
            raise TypeError(f"Expected TelemetrySnapshot, got {type(snapshot).__name__}.")

        sys_id = snapshot.system_id
        file_path = self._get_system_file_path(sys_id)
        serialized = json.dumps(snapshot.to_dict()) + "\n"

        with self._lock:
            self._ensure_indexed(sys_id)
            with open(file_path, "a", encoding="utf-8") as f:
                offset = f.tell()
                f.write(serialized)
                f.flush()

            self._index[sys_id].append((snapshot.timestamp_ns, offset))

    def append_many(self, snapshots: Sequence[TelemetrySnapshot]) -> int:
        """Appends a sequence of telemetry snapshots."""
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
        """Queries telemetry snapshots within a time range from file."""
        validate_time_range(start_time_ns, end_time_ns, system_id=system_id)

        with self._lock:
            self._ensure_indexed(system_id)
            entries = self._index.get(system_id, [])
            if not entries:
                return ()

            timestamps = [e[0] for e in entries]
            start_idx = bisect.bisect_left(timestamps, start_time_ns) if start_time_ns is not None else 0
            end_idx = bisect.bisect_right(timestamps, end_time_ns) if end_time_ns is not None else len(entries)

            if start_idx >= end_idx:
                return ()

            selected_entries = entries[start_idx:end_idx]
            if descending:
                selected_entries = list(reversed(selected_entries))

            if limit is not None and limit > 0:
                selected_entries = selected_entries[:limit]

            file_path = self._get_system_file_path(system_id)
            if not file_path.exists():
                return ()

            snapshots = []
            with open(file_path, "r", encoding="utf-8") as f:
                for _, offset in selected_entries:
                    f.seek(offset)
                    line = f.readline().strip()
                    if not line:
                        continue
                    try:
                        line_dict = json.loads(line)
                        snap = validate_telemetry_payload(line_dict)
                        snapshots.append(snap)
                    except Exception as exc:
                        if self._strict:
                            raise StorageCorruptionError(
                                f"Failed to parse snapshot at offset {offset}: {exc}",
                                system_id=system_id,
                            ) from exc

            return tuple(snapshots)

    def query_latest(self, system_id: str) -> Optional[TelemetrySnapshot]:
        """Retrieves the most recent telemetry snapshot for a system from file."""
        with self._lock:
            self._ensure_indexed(system_id)
            entries = self._index.get(system_id, [])
            if not entries:
                return None

            latest_offset = entries[-1][1]
            file_path = self._get_system_file_path(system_id)
            if not file_path.exists():
                return None

            with open(file_path, "r", encoding="utf-8") as f:
                f.seek(latest_offset)
                line = f.readline().strip()
                if line:
                    return validate_telemetry_payload(json.loads(line))
            return None

    def count(self, system_id: Optional[str] = None) -> int:
        """Returns the total number of stored records."""
        with self._lock:
            if system_id is not None:
                self._ensure_indexed(system_id)
                return len(self._index.get(system_id, []))

            # Count all systems
            total = 0
            for s in self.list_systems():
                self._ensure_indexed(s)
                total += len(self._index.get(s, []))
            return total

    def list_systems(self) -> tuple[str, ...]:
        """Lists all system identifiers that have files on disk."""
        with self._lock:
            systems = set(self._initialized_systems)
            if self._dir.exists():
                for p in self._dir.glob("*_telemetry.jsonl"):
                    sys_name = p.stem.replace("_telemetry", "")
                    systems.add(sys_name)
            return tuple(sorted(systems))

    def clear(self, system_id: Optional[str] = None) -> None:
        """Clears files on disk."""
        with self._lock:
            if system_id is not None:
                file_path = self._get_system_file_path(system_id)
                if file_path.exists():
                    file_path.unlink()
                self._index.pop(system_id, None)
                self._initialized_systems.discard(system_id)
            else:
                if self._dir.exists():
                    for p in self._dir.glob("*_telemetry.jsonl"):
                        p.unlink()
                self._index.clear()
                self._initialized_systems.clear()


class FileAppendStateHistoryRepository(StateHistoryRepository):
    """Append-only JSON-Lines storage for TwinStateRecord instances."""

    def __init__(self, base_directory: Union[str, Path]) -> None:
        self._dir = Path(base_directory)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._index: dict[str, list[tuple[int, int]]] = {}

    def _get_system_file_path(self, system_id: str) -> Path:
        safe_id = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in system_id)
        return self._dir / f"{safe_id}_state_history.jsonl"

    def append(self, record: TwinStateRecord) -> None:
        """Appends a twin state record to file."""
        if not isinstance(record, TwinStateRecord):
            raise TypeError(f"Expected TwinStateRecord, got {type(record).__name__}.")

        sys_id = record.system_id
        file_path = self._get_system_file_path(sys_id)
        serialized = json.dumps(record.to_dict()) + "\n"

        with self._lock:
            if sys_id not in self._index:
                self._index[sys_id] = []
            with open(file_path, "a", encoding="utf-8") as f:
                offset = f.tell()
                f.write(serialized)
                f.flush()
            self._index[sys_id].append((record.timestamp_ns, offset))

    def append_many(self, records: Sequence[TwinStateRecord]) -> int:
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
        validate_time_range(start_time_ns, end_time_ns, system_id=system_id)

        with self._lock:
            entries = self._index.get(system_id, [])
            if not entries:
                return ()

            timestamps = [e[0] for e in entries]
            start_idx = bisect.bisect_left(timestamps, start_time_ns) if start_time_ns is not None else 0
            end_idx = bisect.bisect_right(timestamps, end_time_ns) if end_time_ns is not None else len(entries)

            if start_idx >= end_idx:
                return ()

            selected = entries[start_idx:end_idx]
            if descending:
                selected = list(reversed(selected))
            if limit is not None and limit > 0:
                selected = selected[:limit]

            file_path = self._get_system_file_path(system_id)
            if not file_path.exists():
                return ()

            records_list = []
            with open(file_path, "r", encoding="utf-8") as f:
                for _, offset in selected:
                    f.seek(offset)
                    line = f.readline().strip()
                    if line:
                        d = json.loads(line)
                        # Reconstruct basic ModelState
                        m_state = d.get("model_state", {})
                        rec = TwinStateRecord(
                            record_id=d["record_id"],
                            system_id=d["system_id"],
                            timestamp_ns=d["timestamp_ns"],
                            model_state=m_state if isinstance(m_state, ModelState) else ModelState(
                                soc_fraction=m_state.get("soc_fraction", 1.0),
                                temperature_c=m_state.get("temperature_c", 25.0),
                            ),
                            residuals=d.get("residuals", {}),
                            quality=d.get("quality", "VALID"),
                            metadata=d.get("metadata", {}),
                        )
                        records_list.append(rec)
            return tuple(records_list)

    def query_latest(self, system_id: str) -> Optional[TwinStateRecord]:
        results = self.query_by_time_range(system_id=system_id, limit=1, descending=True)
        return results[0] if results else None

    def count(self, system_id: Optional[str] = None) -> int:
        with self._lock:
            if system_id is not None:
                return len(self._index.get(system_id, []))
            return sum(len(e) for e in self._index.values())

    def list_systems(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._index.keys()))

    def clear(self, system_id: Optional[str] = None) -> None:
        with self._lock:
            if system_id is not None:
                file_path = self._get_system_file_path(system_id)
                if file_path.exists():
                    file_path.unlink()
                self._index.pop(system_id, None)
            else:
                if self._dir.exists():
                    for p in self._dir.glob("*_state_history.jsonl"):
                        p.unlink()
                self._index.clear()
