"""Unit tests for Battery Pack REST API routes."""

import unittest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import create_default_services


class TestPacksAPI(unittest.TestCase):
    """Test suite verifying battery pack registration, retrieval, listing, deletion, and error handling."""

    def setUp(self) -> None:
        self.services = create_default_services()
        self.app = create_app(services=self.services)
        self.client = TestClient(self.app)

        self.valid_profile = {
            "schema_version": "1.0",
            "profile_id": "pack_api_test",
            "display_name": "API Test Pack",
            "manufacturer": "TwinVolt Systems",
            "model_name": "TV-API-01",
            "chemistry": "LFP",
            "topology": {"series_count": 4, "parallel_count": 1},
            "cell_profile": {
                "cell_id": "cell_lfp_api",
                "chemistry": "LFP",
                "form_factor": "CYLINDRICAL",
                "nominal_voltage_v": 3.2,
                "min_voltage_v": 2.5,
                "max_voltage_v": 3.65,
                "nominal_capacity_ah": 2.5,
            },
            "ratings": {
                "nominal_pack_voltage_v": 12.8,
                "nominal_cell_voltage_v": 3.2,
                "nominal_capacity_ah": 2.5,
                "nominal_energy_wh": 32.0,
            },
            "voltage_limits": {
                "cell_min_cutoff_v": 2.5,
                "cell_max_cutoff_v": 3.65,
                "pack_min_cutoff_v": 10.0,
                "pack_max_cutoff_v": 14.6,
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

    def test_create_and_get_pack(self) -> None:
        """POST /api/v1/packs registers pack and GET /api/v1/packs/{pack_id} retrieves it."""
        # 1. Create Pack
        res = self.client.post("/api/v1/packs", json=self.valid_profile)
        self.assertEqual(res.status_code, 201)
        data = res.json()
        self.assertEqual(data["pack_id"], "pack_api_test")
        self.assertEqual(data["series_count"], 4)
        self.assertEqual(data["parallel_count"], 1)
        self.assertEqual(data["total_cell_count"], 4)

        # 2. Get Pack
        res_get = self.client.get("/api/v1/packs/pack_api_test")
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.json()["pack_id"], "pack_api_test")

    def test_duplicate_pack_returns_409_conflict(self) -> None:
        """POST /api/v1/packs with existing pack_id returns 409 Conflict."""
        self.client.post("/api/v1/packs", json=self.valid_profile)
        res_dup = self.client.post("/api/v1/packs", json=self.valid_profile)
        self.assertEqual(res_dup.status_code, 409)
        self.assertEqual(res_dup.json()["error_type"], "DuplicateEntityError")

    def test_get_nonexistent_pack_returns_404(self) -> None:
        """GET /api/v1/packs/{pack_id} for unknown pack returns 404 Not Found."""
        res = self.client.get("/api/v1/packs/nonexistent_pack")
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["error_type"], "PackNotFoundError")

    def test_list_and_delete_packs(self) -> None:
        """GET /api/v1/packs lists packs and DELETE /api/v1/packs/{pack_id} removes pack."""
        self.client.post("/api/v1/packs", json=self.valid_profile)

        # List
        res_list = self.client.get("/api/v1/packs")
        self.assertEqual(res_list.status_code, 200)
        self.assertEqual(res_list.json()["total_count"], 1)

        # Delete
        res_del = self.client.delete("/api/v1/packs/pack_api_test")
        self.assertEqual(res_del.status_code, 200)
        self.assertTrue(res_del.json()["deleted"])

        # Check not found
        res_check = self.client.get("/api/v1/packs/pack_api_test")
        self.assertEqual(res_check.status_code, 404)


if __name__ == "__main__":
    unittest.main()
