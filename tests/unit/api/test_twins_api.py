"""Unit tests for Digital Twin REST API routes."""

import unittest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import create_default_services


class TestTwinsAPI(unittest.TestCase):
    """Test suite verifying digital twin creation, lifecycle, stepping, history queries, and error handling."""

    def setUp(self) -> None:
        self.services = create_default_services()
        self.app = create_app(services=self.services)
        self.client = TestClient(self.app)

        # Register a base pack first
        pack_payload = {
            "schema_version": "1.0",
            "profile_id": "pack_twin_api",
            "display_name": "API Twin Test Pack",
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

    def test_create_and_get_twin(self) -> None:
        """POST /api/v1/twins creates twin and GET /api/v1/twins/{system_id} retrieves status."""
        twin_payload = {
            "system_id": "twin_alpha",
            "pack_id": "pack_twin_api",
            "model_type": "ECM",
            "estimator_type": "EKF",
            "initial_soc": 0.95,
            "initial_temperature_c": 25.0,
            "auto_initialize": True,
        }

        res = self.client.post("/api/v1/twins", json=twin_payload)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["system_id"], "twin_alpha")
        self.assertEqual(data["pack_id"], "pack_twin_api")
        self.assertTrue(data["is_initialized"])
        self.assertEqual(data["current_soc"], 0.95)

        # Get Status
        res_get = self.client.get("/api/v1/twins/twin_alpha")
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.json()["system_id"], "twin_alpha")

    def test_create_twin_with_nonexistent_pack_returns_404(self) -> None:
        """POST /api/v1/twins with missing pack_id returns 404 Not Found."""
        res = self.client.post("/api/v1/twins", json={"system_id": "twin_bad", "pack_id": "missing_pack"})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error_type"], "PackNotFoundError")

    def test_step_twin_and_query_history(self) -> None:
        """POST /api/v1/twins/{id}/step executes step and history endpoints retrieve records."""
        # Create twin
        self.client.post(
            "/api/v1/twins",
            json={"system_id": "twin_step_test", "pack_id": "pack_twin_api", "auto_initialize": True},
        )

        # Step with snapshot
        step_payload = {
            "pack_voltage_v": 3.60,
            "pack_current_a": 2.0,
            "ambient_temperature_c": 25.0,
            "timestamp_ns": 1_000_000_000,
            "sequence_number": 1,
        }
        res_step = self.client.post("/api/v1/twins/twin_step_test/step", json=step_payload)
        self.assertEqual(res_step.status_code, 200)
        data_step = res_step.json()
        self.assertEqual(data_step["step_index"], 1)
        self.assertAlmostEqual(data_step["terminal_voltage_v"], 3.60, delta=0.1)

        # Step raw with CSV
        raw_payload = {
            "raw_data": "timestamp_s,voltage_v,current_a,temperature_c\n2.0,3.58,2.0,25.1\n",
            "format_identifier": "CSV",
        }
        res_raw = self.client.post("/api/v1/twins/twin_step_test/step/raw", json=raw_payload)
        self.assertEqual(res_raw.status_code, 200)
        self.assertEqual(res_raw.json()["step_index"], 2)

        # Query State History
        res_hist = self.client.get("/api/v1/twins/twin_step_test/state/history")
        self.assertEqual(res_hist.status_code, 200)
        self.assertEqual(len(res_hist.json()), 2)

        # Query Telemetry History
        res_tel = self.client.get("/api/v1/twins/twin_step_test/telemetry/history")
        self.assertEqual(res_tel.status_code, 200)
        self.assertEqual(len(res_tel.json()), 2)

        # Query Latest State
        res_latest = self.client.get("/api/v1/twins/twin_step_test/state")
        self.assertEqual(res_latest.status_code, 200)
        self.assertEqual(res_latest.json()["system_id"], "twin_step_test")

    def test_reset_and_delete_twin(self) -> None:
        """Resetting and deleting twins operates as expected."""
        self.client.post(
            "/api/v1/twins",
            json={"system_id": "twin_del_test", "pack_id": "pack_twin_api"},
        )
        # Reset
        res_reset = self.client.post("/api/v1/twins/twin_del_test/reset")
        self.assertEqual(res_reset.status_code, 200)

        # List
        res_list = self.client.get("/api/v1/twins")
        self.assertIn("twin_del_test", res_list.json()["twins"])

        # Delete
        res_del = self.client.delete("/api/v1/twins/twin_del_test")
        self.assertEqual(res_del.status_code, 200)
        self.assertTrue(res_del.json()["deleted"])


if __name__ == "__main__":
    unittest.main()
