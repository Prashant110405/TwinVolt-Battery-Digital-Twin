"""Unit tests for Telemetry Ingestion Pipeline Orchestrator."""

import json
import time
import unittest

from src.ingestion.adapters.serial_frame_adapter import SerialFrameTelemetryAdapter
from src.ingestion.base import IngestionStatus
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.validation import IngestionFilterConfig


class TestIngestionPipeline(unittest.TestCase):
    """Test suite verifying end-to-end ingestion pipeline routing, rate limiting, and timestamp validation."""

    def setUp(self) -> None:
        self.config = IngestionFilterConfig(
            strict_monotonic_timestamps=True,
            max_samples_per_second=10.0,
            max_clock_drift_future_s=10.0,
        )
        self.pipeline = IngestionPipeline(filter_config=self.config)

    def test_ingest_valid_json_dict_success(self) -> None:
        """Pipeline ingests valid JSON dictionary payload with auto-detection."""
        payload = {
            "snapshot_id": "snap_100",
            "system_id": "pack_alpha",
            "timestamp_ns": 1700000000000000000,
            "voltage_v": 48.0,
            "current_a": 2.5,
        }
        res = self.pipeline.ingest(payload)

        self.assertTrue(res.is_success)
        self.assertEqual(res.status, IngestionStatus.SUCCESS)
        self.assertIsNotNone(res.snapshot)
        self.assertEqual(res.snapshot.pack_voltage_v, 48.0)
        self.assertGreaterEqual(res.processing_latency_ms, 0.0)

    def test_ingest_valid_csv_string_success(self) -> None:
        """Pipeline ingests valid CSV row."""
        csv_row = "timestamp_s,voltage_v,current_a\n100.0,47.8,5.0\n"
        res = self.pipeline.ingest(csv_row, format_identifier="CSV", source_id="pack_beta")

        self.assertTrue(res.is_success)
        self.assertEqual(res.status, IngestionStatus.SUCCESS)
        self.assertEqual(res.snapshot.pack_voltage_v, 47.8)
        self.assertEqual(res.snapshot.system_id, "pack_beta")

    def test_ingest_valid_serial_frame_success(self) -> None:
        """Pipeline auto-detects binary serial BMS frame via magic header 0xAA 0x55."""
        serial_adapter = SerialFrameTelemetryAdapter()
        frame = serial_adapter.encode_frame(
            sequence=1,
            timestamp_ms=1700000000000,
            pack_voltage_v=48.0,
            pack_current_a=0.0,
            soc_fraction=1.0,
            ambient_temp_c=25.0,
            max_cell_temp_c=25.0,
            cell_voltages_v=[3.7, 3.7],
        )

        res = self.pipeline.ingest(frame, source_id="serial_node")
        self.assertTrue(res.is_success)
        self.assertEqual(res.status, IngestionStatus.SUCCESS)
        self.assertEqual(res.snapshot.system_id, "serial_node")

    def test_rate_limiting_drops_excessive_packets(self) -> None:
        """Exceeding max_samples_per_second triggers IngestionStatus.DROPPED."""
        sys_id = "flood_system"
        # max_samples_per_second is set to 10 in setUp
        for i in range(10):
            res = self.pipeline.ingest(
                {"snapshot_id": f"s_{i}", "system_id": sys_id, "timestamp_ns": 1000 + i, "voltage_v": 3.7},
            )
            self.assertEqual(res.status, IngestionStatus.SUCCESS)

        # 11th packet in the same second must be dropped
        flood_res = self.pipeline.ingest(
            {"snapshot_id": "s_flood", "system_id": sys_id, "timestamp_ns": 2000, "voltage_v": 3.7},
        )
        self.assertEqual(flood_res.status, IngestionStatus.DROPPED)
        self.assertFalse(flood_res.is_success)
        self.assertIn("exceeded rate limit", flood_res.errors[0])

    def test_non_monotonic_timestamp_rejected(self) -> None:
        """Packet with non-monotonic backward timestamp is rejected."""
        sys_id = "mono_test"
        res1 = self.pipeline.ingest(
            {"snapshot_id": "s1", "system_id": sys_id, "timestamp_ns": 5000, "voltage_v": 3.7},
        )
        self.assertEqual(res1.status, IngestionStatus.SUCCESS)

        # Backward timestamp (4000 < 5000)
        res2 = self.pipeline.ingest(
            {"snapshot_id": "s2", "system_id": sys_id, "timestamp_ns": 4000, "voltage_v": 3.7},
        )
        self.assertEqual(res2.status, IngestionStatus.REJECTED)
        self.assertFalse(res2.is_success)
        self.assertIn("Non-monotonic timestamp", res2.errors[0])

    def test_malformed_json_rejected(self) -> None:
        """Corrupted JSON string is cleanly rejected with error explanation."""
        res = self.pipeline.ingest("{broken_json: 123", format_identifier="JSON")
        self.assertEqual(res.status, IngestionStatus.REJECTED)
        self.assertFalse(res.is_success)
        self.assertIn("Failed to decode JSON", res.errors[0])


if __name__ == "__main__":
    unittest.main()
