"""Unit tests for Telemetry Ingestion REST API routes."""

import unittest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import create_default_services


class TestTelemetryAPI(unittest.TestCase):
    """Test suite verifying single and batch telemetry ingestion endpoints."""

    def setUp(self) -> None:
        self.services = create_default_services()
        self.app = create_app(services=self.services)
        self.client = TestClient(self.app)

        # Setup pack and twin
        pack_payload = {
            "schema_version": "1.0",
            "profile_id": "pack_tel_api",
            "display_name": "Telemetry API Pack",
            "chemistry": "LFP",
            "topology": {"series_count": 1, "parallel_count": 1},
            "cell_profile": {
                "cell_id": "cell_lfp",
                "chemistry": "LFP",
                "form_factor": "CYLINDRICAL",
                "nominal_voltage_v": 3.2,
                "min_voltage_v": 2.5,
                "max_voltage_v": 3.65,
                "nominal_capacity_ah": 2.5,
            },
            "ratings": {
                "nominal_pack_voltage_v": 3.2,
                "nominal_cell_voltage_v": 3.2,
                "nominal_capacity_ah": 2.5,
                "nominal_energy_wh": 8.0,
            },
            "voltage_limits": {
                "cell_min_cutoff_v": 2.5,
                "cell_max_cutoff_v": 3.65,
                "pack_min_cutoff_v": 2.5,
                "pack_max_cutoff_v": 3.65,
            },
            "current_limits": {
                "max_continuous_charge_a": 2.5,
                "max_continuous_discharge_a": 5.0,
                "peak_pulse_discharge_a": 10.0,
            },
            "thermal_limits": {
                "min_charge_temp_c": 0.0,
                "max_charge_temp_c": 45.0,
                "min_discharge_temp_c": -20.0,
                "max_discharge_temp_c": 60.0,
                "thermal_warning_temp_c": 60.0,
                "critical_thermal_runaway_temp_c": 80.0,
            },
        }
        self.client.post("/api/v1/packs", json=pack_payload)
        self.client.post(
            "/api/v1/twins",
            json={"system_id": "twin_tel_api", "pack_id": "pack_tel_api", "auto_initialize": True},
        )

    def test_ingest_raw_telemetry(self) -> None:
        """POST /api/v1/telemetry/ingest parses raw CSV and steps twin."""
        payload = {
            "system_id": "twin_tel_api",
            "raw_data": "timestamp_s,voltage_v,current_a,temperature_c\n0.0,3.60,1.0,25.0\n",
            "format_identifier": "CSV",
        }
        res = self.client.post("/api/v1/telemetry/ingest", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "INGESTED")
        self.assertTrue(data["stepped_twin"])
        self.assertIsNotNone(data["step_output"])
        self.assertEqual(data["step_output"]["step_index"], 1)

    def test_ingest_canonical_snapshot(self) -> None:
        """POST /api/v1/telemetry/ingest accepts canonical snapshot structure."""
        payload = {
            "system_id": "twin_tel_api",
            "pack_voltage_v": 3.59,
            "pack_current_a": 2.0,
            "ambient_temperature_c": 25.0,
            "timestamp_ns": 1_000_000_000,
        }
        res = self.client.post("/api/v1/telemetry/ingest", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["status"], "INGESTED")

    def test_ingest_batch(self) -> None:
        """POST /api/v1/telemetry/batch ingests sequential snapshots."""
        batch_payload = {
            "system_id": "twin_tel_api",
            "snapshots": [
                {"system_id": "twin_tel_api", "pack_voltage_v": 3.60, "pack_current_a": 1.0, "timestamp_ns": 1_000_000_000},
                {"system_id": "twin_tel_api", "pack_voltage_v": 3.58, "pack_current_a": 1.0, "timestamp_ns": 2_000_000_000},
            ],
        }
        res = self.client.post("/api/v1/telemetry/batch", json=batch_payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "BATCH_INGESTED")
        self.assertEqual(data["processed_count"], 2)


if __name__ == "__main__":
    unittest.main()
