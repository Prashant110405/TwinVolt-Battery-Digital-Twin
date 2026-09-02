"""Unit tests for FileAppendTelemetryRepository."""

from pathlib import Path
import tempfile
import unittest

from src.storage.exceptions import InvalidTimeRangeError
from src.storage.file_repository import FileAppendTelemetryRepository
from src.telemetry.snapshots import TelemetrySnapshot


class TestFileAppendTelemetryRepository(unittest.TestCase):
    """Test suite verifying durable file append persistence, recovery across instances, and time queries."""

    def _create_snapshot(self, system_id: str, timestamp_ns: int, voltage_v: float = 3.7) -> TelemetrySnapshot:
        return TelemetrySnapshot(
            snapshot_id=f"{system_id}_{timestamp_ns}",
            system_id=system_id,
            timestamp_ns=timestamp_ns,
            pack_voltage_v=voltage_v,
            pack_current_a=1.0,
        )

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = FileAppendTelemetryRepository(base_directory=self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_append_and_query(self) -> None:
        """Verify appending records to file and querying by range."""
        snap1 = self._create_snapshot("file_sys_1", 1000, voltage_v=3.7)
        snap2 = self._create_snapshot("file_sys_1", 2000, voltage_v=3.8)
        snap3 = self._create_snapshot("file_sys_1", 3000, voltage_v=3.9)

        self.repo.append(snap1)
        self.repo.append_many([snap2, snap3])

        self.assertEqual(self.repo.count("file_sys_1"), 3)

        results = self.repo.query_by_time_range("file_sys_1", start_time_ns=1500, end_time_ns=2500)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].timestamp_ns, 2000)
        self.assertEqual(results[0].pack_voltage_v, 3.8)

    def test_persistence_recovery_across_instances(self) -> None:
        """A new repository instance pointing to the same directory reloads the index and data."""
        self.repo.append(self._create_snapshot("persist_sys", 1000, voltage_v=3.7))
        self.repo.append(self._create_snapshot("persist_sys", 2000, voltage_v=3.8))

        # Create new repository instance pointing to same path
        reloaded_repo = FileAppendTelemetryRepository(base_directory=self.temp_dir.name)
        self.assertEqual(reloaded_repo.count("persist_sys"), 2)

        latest = reloaded_repo.query_latest("persist_sys")
        self.assertIsNotNone(latest)
        self.assertEqual(latest.timestamp_ns, 2000)

    def test_clear_deletes_files(self) -> None:
        """clear() removes files on disk."""
        self.repo.append(self._create_snapshot("clean_sys", 1000))
        self.assertEqual(self.repo.count("clean_sys"), 1)

        self.repo.clear("clean_sys")
        self.assertEqual(self.repo.count("clean_sys"), 0)


if __name__ == "__main__":
    unittest.main()
