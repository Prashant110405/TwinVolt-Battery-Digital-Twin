"""Unit tests for StateHistoryRepository and TwinStateRecord."""

from pathlib import Path
import tempfile
import unittest

from src.models.types import ModelState
from src.storage.base import StateHistoryRepository, TwinStateRecord
from src.storage.file_repository import FileAppendStateHistoryRepository
from src.storage.memory_repository import InMemoryStateHistoryRepository


class TestStateHistoryRepository(unittest.TestCase):
    """Test suite verifying in-memory and file-backed digital twin state history repositories."""

    def setUp(self) -> None:
        self.mem_repo = InMemoryStateHistoryRepository()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.file_repo = FileAppendStateHistoryRepository(base_directory=self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _create_record(self, system_id: str, timestamp_ns: int, soc: float = 0.9) -> TwinStateRecord:
        m_state = ModelState(soc_fraction=soc, temperature_c=25.0)
        return TwinStateRecord(
            record_id=f"{system_id}_{timestamp_ns}",
            system_id=system_id,
            timestamp_ns=timestamp_ns,
            model_state=m_state,
            residuals={"voltage_residual_v": 0.005, "temp_residual_c": 0.1},
        )

    def test_in_memory_state_history_operations(self) -> None:
        """Verify append, query by range, and query latest in-memory."""
        self.assertIsInstance(self.mem_repo, StateHistoryRepository)

        rec1 = self._create_record("twin_1", 1000, soc=0.95)
        rec2 = self._create_record("twin_1", 2000, soc=0.90)
        rec3 = self._create_record("twin_1", 3000, soc=0.85)

        self.mem_repo.append(rec1)
        self.mem_repo.append_many([rec2, rec3])

        self.assertEqual(self.mem_repo.count("twin_1"), 3)

        results = self.mem_repo.query_by_time_range("twin_1", start_time_ns=1500, end_time_ns=2500)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].timestamp_ns, 2000)
        self.assertAlmostEqual(results[0].model_state.soc_fraction, 0.90)

        latest = self.mem_repo.query_latest("twin_1")
        self.assertIsNotNone(latest)
        self.assertEqual(latest.timestamp_ns, 3000)

    def test_file_backed_state_history_operations(self) -> None:
        """Verify file-backed twin state history storage and retrieval."""
        self.assertIsInstance(self.file_repo, StateHistoryRepository)

        rec1 = self._create_record("twin_file", 1000, soc=0.95)
        rec2 = self._create_record("twin_file", 2000, soc=0.90)

        self.file_repo.append_many([rec1, rec2])
        self.assertEqual(self.file_repo.count("twin_file"), 2)

        results = self.file_repo.query_by_time_range("twin_file")
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].record_id, "twin_file_1000")


if __name__ == "__main__":
    unittest.main()
