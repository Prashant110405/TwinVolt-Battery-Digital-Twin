"""Unit tests for Telemetry Schema Validation."""

import unittest

from src.schemas.exceptions import ConfigurationValidationError
from src.schemas.telemetry_schema import (
    TelemetryPayloadSchema,
    validate_telemetry_payload,
)
from src.telemetry.enums import CurrentFlowDirection, TelemetryQuality


class TestTelemetrySchema(unittest.TestCase):
    """Unit tests for validating raw dictionary payloads against canonical telemetry schema."""

    def test_valid_telemetry_payload_parsing(self) -> None:
        """Parse complete valid dictionary payload into TelemetrySnapshot."""
        payload = {
            "snapshot_id": "snap_dict_01",
            "system_id": "pack_01",
            "timestamp_ns": 1700000000000000000,
            "pack_voltage_v": 11.12,
            "pack_current_a": 2.1,
            "charge_discharge_state": "DISCHARGING",
            "direct_cells": [
                {"cell_id": "cell_0", "voltage_v": 3.71, "temperature_c": 25.0},
                {"cell_id": "cell_1", "voltage_v": 3.70, "temperature_c": 25.1},
                {"cell_id": "cell_2", "voltage_v": 3.71, "temperature_c": 25.2},
            ],
            "discrete_temperatures": [
                {"sensor_id": "temp_inlet", "temperature_c": 22.0}
            ],
            "quality": "VALID",
        }

        snapshot = validate_telemetry_payload(payload)
        self.assertEqual(snapshot.snapshot_id, "snap_dict_01")
        self.assertEqual(snapshot.system_id, "pack_01")
        self.assertEqual(snapshot.pack_voltage_v, 11.12)
        self.assertEqual(snapshot.total_cell_count, 3)
        self.assertEqual(snapshot.charge_discharge_state, CurrentFlowDirection.DISCHARGING)
        self.assertEqual(len(snapshot.discrete_temperatures), 1)

    def test_missing_mandatory_fields_raises(self) -> None:
        """Payload missing snapshot_id, system_id, or timestamp_ns must fail."""
        payload = {"pack_voltage_v": 12.0}
        with self.assertRaises(ConfigurationValidationError):
            validate_telemetry_payload(payload)

    def test_schema_validator_class_wrapper(self) -> None:
        """Verify TelemetryPayloadSchema.validate() static method."""
        payload = {
            "snapshot_id": "s1",
            "system_id": "sys1",
            "timestamp_ns": 1700000000000000000,
            "pack_voltage_v": 3.7,
        }
        snap = TelemetryPayloadSchema.validate(payload)
        self.assertEqual(snap.snapshot_id, "s1")


if __name__ == "__main__":
    unittest.main()
