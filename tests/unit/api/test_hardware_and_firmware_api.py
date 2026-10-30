"""Unit tests for Hardware, Firmware, and Mock REST API endpoints."""

import io
import unittest
from fastapi.testclient import TestClient
from src.api.app import create_app
from src.config.settings import AppSettings


class TestHardwareAndFirmwareAPI(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(settings=AppSettings(seed_defaults=True))
        self.client = TestClient(self.app)

    def test_list_serial_ports(self) -> None:
        """GET /api/v1/gateway/serial/ports enumerates COM ports without crashing."""
        res = self.client.get("/api/v1/gateway/serial/ports")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("ports", data)
        self.assertIsInstance(data["ports"], list)

    def test_arduino_hardware_status(self) -> None:
        """GET /api/v1/gateway/arduino/status returns hardware gateway state."""
        res = self.client.get("/api/v1/gateway/arduino/status")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("state", data)
        self.assertEqual(data["state"], "DISCONNECTED")

    def test_firmware_file_listing_and_read(self) -> None:
        """Lists firmware workspace files and reads source text."""
        res_list = self.client.get("/api/v1/firmware/files")
        self.assertEqual(res_list.status_code, 200)
        files = res_list.json()["files"]
        self.assertTrue(any(f["filename"] == "TwinVolt_Arduino_Example.ino" for f in files))

        # Read content
        res_content = self.client.get("/api/v1/firmware/files/TwinVolt_Arduino_Example.ino")
        self.assertEqual(res_content.status_code, 200)
        self.assertIn("Serial.begin", res_content.text)

    def test_firmware_verify_route(self) -> None:
        """POST /api/v1/firmware/verify executes static syntax checks."""
        res = self.client.post(
            "/api/v1/firmware/verify",
            json={"filename": "TwinVolt_Arduino_Example.ino", "board_fqbn": "arduino:avr:uno"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["is_valid"])
        self.assertTrue(data["static_checks"]["has_setup_function"])
        self.assertTrue(data["static_checks"]["has_loop_function"])
        self.assertTrue(data["static_checks"]["has_serial_begin"])
        self.assertEqual(data["static_checks"]["detected_baud_rate"], 115200)

    def test_firmware_save_route(self) -> None:
        """POST /api/v1/firmware/save safely persists updated source."""
        test_content = "// Test save\nvoid setup() { Serial.begin(9600); }\nvoid loop() {}\n"
        res = self.client.post(
            "/api/v1/firmware/save",
            json={"filename": "test_sketch.ino", "content": test_content},
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["filename"], "test_sketch.ino")

        # Verify it can be read back
        read_res = self.client.get("/api/v1/firmware/files/test_sketch.ino")
        self.assertEqual(read_res.status_code, 200)
        self.assertEqual(read_res.text, test_content)

    def test_firmware_upload_path_traversal_prevention(self) -> None:
        """Rejects path traversal attempts in uploaded filename."""
        file_payload = io.BytesIO(b"void setup(){}")
        res = self.client.post(
            "/api/v1/firmware/upload",
            files={"file": ("../../etc/passwd.ino", file_payload, "text/plain")},
        )
        self.assertEqual(res.status_code, 200)
        # Basename is sanitized to passwd.ino
        self.assertEqual(res.json()["filename"], "passwd.ino")

    def test_mock_generator_lifecycle_routes(self) -> None:
        """Controls mock generator via REST API endpoints."""
        # 1. Status
        res_status = self.client.get("/api/v1/mock/status")
        self.assertEqual(res_status.status_code, 200)
        self.assertFalse(res_status.json()["is_running"])

        # 2. Start
        res_start = self.client.post("/api/v1/mock/start")
        self.assertEqual(res_start.status_code, 200)
        self.assertTrue(res_start.json()["is_running"])

        # 3. Inject fault
        res_inject = self.client.post(
            "/api/v1/mock/inject-error",
            json={"error_type": "sensor_disconnect"},
        )
        self.assertEqual(res_inject.status_code, 200)
        self.assertFalse(res_inject.json()["injected_record"]["is_valid"])

        # 4. Stop
        res_stop = self.client.post("/api/v1/mock/stop")
        self.assertEqual(res_stop.status_code, 200)
        self.assertFalse(res_stop.json()["is_running"])


if __name__ == "__main__":
    unittest.main()
