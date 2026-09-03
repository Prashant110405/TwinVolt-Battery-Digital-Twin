"""Unit tests for WebSocket Endpoints using FastAPI TestClient."""

import unittest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import create_default_services


class TestWebSocketEndpoints(unittest.TestCase):
    """Test suite verifying WebSocket session lifecycles, streaming ingestion, broadcasts, and error handling."""

    def setUp(self) -> None:
        self.services = create_default_services()
        self.app = create_app(services=self.services)
        self.client = TestClient(self.app)

        # Setup pack and twin for tests
        pack_payload = {
            "schema_version": "1.0",
            "profile_id": "pack_ws_test",
            "display_name": "WebSocket API Pack",
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
            json={"system_id": "twin_ws_alpha", "pack_id": "pack_ws_test", "auto_initialize": True},
        )

    def test_dedicated_twin_websocket_connection_and_ping(self) -> None:
        """Connecting to /api/v1/ws/twins/{system_id} auto-subscribes client and responds to ping."""
        with self.client.websocket_connect("/api/v1/ws/twins/twin_ws_alpha") as ws:
            # 1. Receive connected welcome message
            welcome = ws.receive_json()
            self.assertEqual(welcome["type"], "connected")
            self.assertIn("client_id", welcome)

            # 2. Send ping -> receive pong
            ws.send_json({"type": "ping"})
            pong = ws.receive_json()
            self.assertEqual(pong["type"], "pong")

    def test_telemetry_ingest_and_twin_state_broadcast(self) -> None:
        """Ingesting telemetry via WebSocket produces ACK and state broadcast to subscribers."""
        with self.client.websocket_connect("/api/v1/ws/twins/twin_ws_alpha") as ws:
            # Welcome message
            ws.receive_json()

            # Ingest raw CSV telemetry
            ingest_msg = {
                "type": "telemetry_ingest",
                "system_id": "twin_ws_alpha",
                "raw_data": "timestamp_s,voltage_v,current_a,temperature_c\n0.0,3.60,1.5,25.0\n",
                "format_identifier": "CSV",
            }
            ws.send_json(ingest_msg)

            # 1. Receive Telemetry ACK
            ack = ws.receive_json()
            self.assertEqual(ack["type"], "telemetry_ack")
            self.assertEqual(ack["system_id"], "twin_ws_alpha")
            self.assertTrue(ack["stepped_twin"])
            self.assertEqual(ack["step_index"], 1)

            # 2. Receive Twin State Broadcast
            state_msg = ws.receive_json()
            self.assertEqual(state_msg["type"], "twin_state")
            self.assertEqual(state_msg["system_id"], "twin_ws_alpha")
            self.assertEqual(state_msg["step_index"], 1)
            self.assertAlmostEqual(state_msg["terminal_voltage_v"], 3.60, delta=0.1)

    def test_multiplexed_gateway_subscribe_and_ingest(self) -> None:
        """Gateway endpoint /api/v1/ws supports dynamic subscribe command and routing."""
        with self.client.websocket_connect("/api/v1/ws") as ws:
            # Welcome message
            ws.receive_json()

            # Subscribe to twin_ws_alpha
            ws.send_json({"type": "subscribe", "system_id": "twin_ws_alpha"})
            sub_ack = ws.receive_json()
            self.assertEqual(sub_ack["type"], "subscribed")
            self.assertEqual(sub_ack["system_id"], "twin_ws_alpha")

            # Ingest structured snapshot
            snap_msg = {
                "type": "telemetry_ingest",
                "system_id": "twin_ws_alpha",
                "pack_voltage_v": 3.59,
                "pack_current_a": 1.0,
                "ambient_temperature_c": 25.0,
                "timestamp_ns": 1_000_000_000,
            }
            ws.send_json(snap_msg)

            ack = ws.receive_json()
            self.assertEqual(ack["type"], "telemetry_ack")

            state_msg = ws.receive_json()
            self.assertEqual(state_msg["type"], "twin_state")

    def test_malformed_json_and_unsupported_type_errors(self) -> None:
        """Malformed JSON or unsupported message types return structured error messages without crashing."""
        with self.client.websocket_connect("/api/v1/ws") as ws:
            ws.receive_json()  # Welcome

            # Send non-JSON text
            ws.send_text("not-a-json-string")
            err_json = ws.receive_json()
            self.assertEqual(err_json["type"], "error")
            self.assertEqual(err_json["code"], "MALFORMED_JSON")

            # Send unsupported message type
            ws.send_json({"type": "unsupported_command"})
            err_type = ws.receive_json()
            self.assertEqual(err_type["type"], "error")
            self.assertEqual(err_type["code"], "UNSUPPORTED_MESSAGE_TYPE")

    def test_subscribe_unknown_twin_returns_error(self) -> None:
        """Subscribing to a nonexistent twin returns TWIN_NOT_FOUND error."""
        with self.client.websocket_connect("/api/v1/ws") as ws:
            ws.receive_json()  # Welcome

            ws.send_json({"type": "subscribe", "system_id": "nonexistent_twin"})
            err = ws.receive_json()
            self.assertEqual(err["type"], "error")
            self.assertEqual(err["code"], "TWIN_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
