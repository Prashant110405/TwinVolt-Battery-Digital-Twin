"""Unit tests for WebSocket protocol message schemas."""

import unittest
from pydantic import ValidationError

from src.api.websocket.schemas import (
    WSConnectedMessage,
    WSErrorMessage,
    WSPingMessage,
    WSPongMessage,
    WSSubscribeMessage,
    WSTelemetryAckMessage,
    WSTelemetryIngestMessage,
    WSTwinEventMessage,
    WSTwinStateMessage,
    WSUnsubscribeMessage,
)


class TestWebSocketProtocol(unittest.TestCase):
    """Test suite verifying WebSocket protocol message parsing, serialization, and validation."""

    def test_inbound_subscribe_and_unsubscribe_schemas(self) -> None:
        """Subscribe and Unsubscribe message schemas validate correctly."""
        sub = WSSubscribeMessage(system_id="twin_01")
        self.assertEqual(sub.type, "subscribe")
        self.assertEqual(sub.system_id, "twin_01")

        unsub = WSUnsubscribeMessage(system_id="twin_01")
        self.assertEqual(unsub.type, "unsubscribe")

    def test_inbound_telemetry_ingest_schema(self) -> None:
        """Telemetry ingestion message parses raw and structured observations."""
        # Raw format
        raw_msg = WSTelemetryIngestMessage(
            system_id="twin_01",
            raw_data="0.0,3.6,1.0",
            format_identifier="CSV",
        )
        self.assertEqual(raw_msg.type, "telemetry_ingest")
        self.assertEqual(raw_msg.format_identifier, "CSV")

        # Structured format
        struct_msg = WSTelemetryIngestMessage(
            system_id="twin_01",
            pack_voltage_v=3.58,
            pack_current_a=2.0,
            soc_fraction=0.90,
        )
        self.assertEqual(struct_msg.pack_voltage_v, 3.58)

    def test_outbound_messages_serialization(self) -> None:
        """Outbound messages serialize correctly to dictionaries and JSON."""
        # Connected
        conn = WSConnectedMessage(client_id="c_123")
        self.assertEqual(conn.type, "connected")

        # Ping / Pong
        ping = WSPingMessage()
        pong = WSPongMessage()
        self.assertEqual(ping.type, "ping")
        self.assertEqual(pong.type, "pong")

        # Ack
        ack = WSTelemetryAckMessage(system_id="twin_01", status="ACK", stepped_twin=True, step_index=5)
        self.assertEqual(ack.step_index, 5)

        # Twin State
        state = WSTwinStateMessage(
            system_id="twin_01",
            step_index=1,
            timestamp_ns=1000,
            dt_s=1.0,
            terminal_voltage_v=3.60,
            simulated_soc=0.95,
            temperature_c=25.0,
            voltage_residual_v=0.01,
        )
        data = state.model_dump()
        self.assertEqual(data["type"], "twin_state")
        self.assertEqual(data["voltage_residual_v"], 0.01)

        # Twin Event
        evt = WSTwinEventMessage(
            system_id="twin_01",
            event_type="thermal.warning",
            event_id="evt_01",
            timestamp_ns=1000,
            payload={"temp_c": 62.0},
        )
        self.assertEqual(evt.event_type, "thermal.warning")

        # Error
        err = WSErrorMessage(code="TWIN_NOT_FOUND", message="Twin not found", details={"id": "twin_x"})
        self.assertEqual(err.code, "TWIN_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
