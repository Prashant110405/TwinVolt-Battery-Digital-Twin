"""Unit tests for JSON Telemetry Ingestion Adapter."""

import json
import unittest

from src.ingestion.adapters.json_adapter import JSONTelemetryAdapter
from src.ingestion.base import PacketMetadata
from src.ingestion.exceptions import MalformedPayloadError
from src.telemetry.snapshots import TelemetrySnapshot


class TestJSONTelemetryAdapter(unittest.TestCase):
    """Test suite verifying JSON payload parsing, alias normalization, and error handling."""

    def setUp(self) -> None:
        self.adapter = JSONTelemetryAdapter()

    def test_supports_format(self) -> None:
        """Verify supported format strings."""
        self.assertTrue(self.adapter.supports_format("JSON"))
        self.assertTrue(self.adapter.supports_format("application/json"))
        self.assertTrue(self.adapter.supports_format("json_dict"))
        self.assertFalse(self.adapter.supports_format("CSV"))

    def test_parse_full_nested_json(self) -> None:
        """Parse complete nested JSON string."""
        payload = {
            "snapshot_id": "snap_001",
            "system_id": "batt_sys_01",
            "timestamp_ns": 1700000000000000000,
            "pack_voltage_v": 48.2,
            "pack_current_a": 12.5,
            "pack_power_w": 602.5,
            "ambient_temperature_c": 22.0,
            "soc_fraction": 0.85,
            "direct_cells": [
                {"cell_id": "cell_0", "voltage_v": 3.71, "temperature_c": 24.5},
                {"cell_id": "cell_1", "voltage_v": 3.70, "temperature_c": 24.6},
            ],
        }
        json_str = json.dumps(payload)
        snapshot = self.adapter.parse(json_str)

        self.assertIsInstance(snapshot, TelemetrySnapshot)
        self.assertEqual(snapshot.snapshot_id, "snap_001")
        self.assertEqual(snapshot.system_id, "batt_sys_01")
        self.assertEqual(snapshot.pack_voltage_v, 48.2)
        self.assertEqual(snapshot.pack_current_a, 12.5)
        self.assertEqual(len(snapshot.cell_telemetries), 2)
        self.assertEqual(snapshot.cell_telemetries[0].voltage_v, 3.71)

    def test_parse_flat_json_with_field_aliases(self) -> None:
        """Parse flat dictionary with aliases (voltage_v, current_a, timestamp_s)."""
        payload = {
            "voltage_v": 3.75,
            "current_a": -2.0,
            "temperature_c": 25.0,
            "timestamp_s": 1700000000.0,
        }
        meta = PacketMetadata(source_id="test_pack_1")
        snapshot = self.adapter.parse(payload, metadata=meta)

        self.assertEqual(snapshot.system_id, "test_pack_1")
        self.assertEqual(snapshot.timestamp_ns, 1700000000000000000)
        self.assertEqual(snapshot.pack_voltage_v, 3.75)
        self.assertEqual(snapshot.pack_current_a, -2.0)
        self.assertEqual(snapshot.ambient_temperature_c, 25.0)

    def test_missing_optional_fields_are_none_not_zero(self) -> None:
        """Verify strict absence semantics: missing power/soc is None, not 0.0."""
        payload = {
            "snapshot_id": "snap_min",
            "system_id": "sys_min",
            "timestamp_ns": 1000000,
            "pack_voltage_v": 3.65,
        }
        snapshot = self.adapter.parse(payload)
        self.assertIsNone(snapshot.pack_current_a)
        self.assertIsNone(snapshot.pack_power_w)
        self.assertIsNone(snapshot.soc_fraction)

    def test_malformed_json_raises_malformed_payload_error(self) -> None:
        """Corrupt JSON syntax must raise MalformedPayloadError."""
        bad_json = "{\"snapshot_id\": 'bad_quotes', broken"
        with self.assertRaises(MalformedPayloadError):
            self.adapter.parse(bad_json)


if __name__ == "__main__":
    unittest.main()
