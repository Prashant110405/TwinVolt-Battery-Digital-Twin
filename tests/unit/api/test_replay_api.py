"""Unit tests for Drive-Cycle Replay REST API routes."""

import unittest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import create_default_services


class TestReplayAPI(unittest.TestCase):
    """Test suite verifying drive-cycle profile replay, CSV replay, and tracking accuracy API routes."""

    def setUp(self) -> None:
        self.services = create_default_services()
        self.app = create_app(services=self.services)
        self.client = TestClient(self.app)

        # Setup pack and twin
        pack_payload = {
            "schema_version": "1.0",
            "profile_id": "pack_rep_api",
            "display_name": "Replay API Pack",
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
            json={"system_id": "twin_rep_api", "pack_id": "pack_rep_api"},
        )

    def test_replay_standard_profile(self) -> None:
        """POST /api/v1/replay/{system_id}/profile executes simulation and returns error metrics."""
        payload = {
            "profile_type": "PULSE",
            "peak_current_a": 2.0,
            "cycles": 2,
            "dt_s": 1.0,
            "evaluate_metrics": True,
        }
        res = self.client.post("/api/v1/replay/twin_rep_api/profile", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["system_id"], "twin_rep_api")
        self.assertEqual(data["executed_steps"], 61)
        self.assertTrue(data["is_passing"])

        # Check latest replay query
        res_latest = self.client.get("/api/v1/replay/twin_rep_api/latest")
        self.assertEqual(res_latest.status_code, 200)
        self.assertEqual(res_latest.json()["executed_steps"], 61)

    def test_replay_csv_dataset(self) -> None:
        """POST /api/v1/replay/{system_id}/csv executes replay on CSV text."""
        payload = {
            "csv_data": "timestamp_s,voltage_v,current_a,temperature_c\n0.0,3.60,0.0,25.0\n1.0,3.58,1.0,25.1\n",
            "profile_name": "test_csv_api",
        }
        res = self.client.post("/api/v1/replay/twin_rep_api/csv", json=payload)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["executed_steps"], 2)
        self.assertEqual(data["profile_name"], "test_csv_api")

    def test_replay_missing_twin_returns_404(self) -> None:
        """Replaying against nonexistent twin returns 404 Not Found."""
        res = self.client.post(
            "/api/v1/replay/missing_twin/profile",
            json={"profile_type": "WLTP", "duration_s": 60.0},
        )
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error_type"], "TwinNotFoundError")


if __name__ == "__main__":
    unittest.main()
