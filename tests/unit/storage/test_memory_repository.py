"""Unit tests for InMemoryTelemetryRepository."""

from datetime import datetime, timezone
import unittest

from src.storage.base import (
    TelemetryRepository,
    datetime_to_timestamp_ns,
    timestamp_ns_to_datetime,
)
from src.storage.exceptions import InvalidTimeRangeError, RepositoryCapacityError
from src.storage.memory_repository import InMemoryTelemetryRepository
from src.telemetry.snapshots import TelemetrySnapshot


class TestInMemoryTelemetryRepository(unittest.TestCase):
    """Test suite verifying in-memory time-series storage, range queries, FIFO eviction, and multi-system isolation."""

    def _create_snapshot(self, system_id: str, timestamp_ns: int, voltage_v: float = 3.7) -> TelemetrySnapshot:
        return TelemetrySnapshot(
            snapshot_id=f"{system_id}_{timestamp_ns}",
            system_id=system_id,
            timestamp_ns=timestamp_ns,
            pack_voltage_v=voltage_v,
            pack_current_a=1.0,
        )

    def setUp(self) -> None:
        self.repo = InMemoryTelemetryRepository(max_records_per_system=100)

    def test_protocol_compliance(self) -> None:
        """Verify repository adheres to TelemetryRepository protocol."""
        self.assertIsInstance(self.repo, TelemetryRepository)

    def test_single_and_batch_append(self) -> None:
        """Verify appending single and multiple snapshots."""
        snap1 = self._create_snapshot("sys_1", 1000)
        snap2 = self._create_snapshot("sys_1", 2000)
        snap3 = self._create_snapshot("sys_1", 3000)

        self.repo.append(snap1)
        self.assertEqual(self.repo.count("sys_1"), 1)

        added = self.repo.append_many([snap2, snap3])
        self.assertEqual(added, 2)
        self.assertEqual(self.repo.count("sys_1"), 3)
        self.assertEqual(self.repo.count(), 3)

    def test_chronological_ordering_invariant(self) -> None:
        """Out-of-order appends are sorted deterministically by timestamp."""
        snap_mid = self._create_snapshot("sys_1", 2000)
        snap_last = self._create_snapshot("sys_1", 3000)
        snap_first = self._create_snapshot("sys_1", 1000)

        self.repo.append(snap_mid)
        self.repo.append(snap_last)
        self.repo.append(snap_first)

        results = self.repo.query_by_time_range("sys_1")
        self.assertEqual(len(results), 3)
        self.assertEqual([s.timestamp_ns for s in results], [1000, 2000, 3000])

    def test_time_range_queries(self) -> None:
        """Test bounded, open-ended, and empty range queries."""
        for ts in [1000, 2000, 3000, 4000, 5000]:
            self.repo.append(self._create_snapshot("sys_1", ts))

        # 1. Exact interval [2000, 4000]
        res = self.repo.query_by_time_range("sys_1", start_time_ns=2000, end_time_ns=4000)
        self.assertEqual([s.timestamp_ns for s in res], [2000, 3000, 4000])

        # 2. Open-ended start (<= 3000)
        res_open_start = self.repo.query_by_time_range("sys_1", end_time_ns=3000)
        self.assertEqual([s.timestamp_ns for s in res_open_start], [1000, 2000, 3000])

        # 3. Open-ended end (>= 3000)
        res_open_end = self.repo.query_by_time_range("sys_1", start_time_ns=3000)
        self.assertEqual([s.timestamp_ns for s in res_open_end], [3000, 4000, 5000])

        # 4. Limit and descending
        res_desc = self.repo.query_by_time_range("sys_1", limit=2, descending=True)
        self.assertEqual([s.timestamp_ns for s in res_desc], [5000, 4000])

        # 5. Empty interval
        res_empty = self.repo.query_by_time_range("sys_1", start_time_ns=6000, end_time_ns=7000)
        self.assertEqual(res_empty, ())

    def test_query_latest(self) -> None:
        """query_latest returns the most recent record or None."""
        self.assertIsNone(self.repo.query_latest("sys_1"))

        self.repo.append(self._create_snapshot("sys_1", 1000))
        self.repo.append(self._create_snapshot("sys_1", 2500))

        latest = self.repo.query_latest("sys_1")
        self.assertIsNotNone(latest)
        self.assertEqual(latest.timestamp_ns, 2500)

    def test_multi_system_isolation(self) -> None:
        """Queries for System A never leak System B records."""
        self.repo.append(self._create_snapshot("sys_A", 1000, voltage_v=3.6))
        self.repo.append(self._create_snapshot("sys_B", 1000, voltage_v=4.2))
        self.repo.append(self._create_snapshot("sys_A", 2000, voltage_v=3.7))

        self.assertEqual(self.repo.count("sys_A"), 2)
        self.assertEqual(self.repo.count("sys_B"), 1)
        self.assertEqual(self.repo.list_systems(), ("sys_A", "sys_B"))

        res_a = self.repo.query_by_time_range("sys_A")
        self.assertEqual(len(res_a), 2)
        self.assertTrue(all(s.system_id == "sys_A" for s in res_a))

    def test_bounded_fifo_capacity_eviction(self) -> None:
        """When capacity is exceeded, oldest records are evicted FIFO."""
        small_repo = InMemoryTelemetryRepository(max_records_per_system=3)
        for i in range(5):
            small_repo.append(self._create_snapshot("sys_1", 1000 * (i + 1)))

        self.assertEqual(small_repo.count("sys_1"), 3)
        res = small_repo.query_by_time_range("sys_1")
        # Should retain only timestamps 3000, 4000, 5000
        self.assertEqual([s.timestamp_ns for s in res], [3000, 4000, 5000])

    def test_invalid_time_range_raises(self) -> None:
        """Query with start_time_ns > end_time_ns must raise InvalidTimeRangeError."""
        with self.assertRaises(InvalidTimeRangeError):
            self.repo.query_by_time_range("sys_1", start_time_ns=5000, end_time_ns=1000)

        with self.assertRaises(InvalidTimeRangeError):
            self.repo.query_by_time_range("sys_1", start_time_ns=-100)

    def test_invalid_capacity_raises(self) -> None:
        """Initializing with non-positive capacity must raise RepositoryCapacityError."""
        with self.assertRaises(RepositoryCapacityError):
            InMemoryTelemetryRepository(max_records_per_system=0)

    def test_timezone_aware_datetime_conversion(self) -> None:
        """Verify datetime to timestamp_ns conversion roundtrip."""
        dt_utc = datetime(2026, 9, 2, 12, 0, 0, tzinfo=timezone.utc)
        ts_ns = datetime_to_timestamp_ns(dt_utc)
        dt_recovered = timestamp_ns_to_datetime(ts_ns)

        self.assertEqual(dt_utc, dt_recovered)


if __name__ == "__main__":
    unittest.main()
