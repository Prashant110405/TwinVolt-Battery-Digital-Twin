"""Unit tests for Edge Telemetry Gateway base abstractions and data models."""

import unittest
from src.gateway.base import (
    BaseTelemetrySource,
    GatewayConfig,
    GatewayOverflowPolicy,
    GatewaySourceState,
    GatewaySourceStatus,
    RawTelemetryFrame,
)


class DummySource(BaseTelemetrySource):
    """Concrete implementation for testing base class behaviors."""

    def __init__(self, source_id: str = "dummy_src") -> None:
        super().__init__(source_id=source_id, transport_type="DUMMY")

    async def start(self) -> None:
        self._state = GatewaySourceState.CONNECTED

    async def stop(self) -> None:
        self._state = GatewaySourceState.STOPPED

    async def read_frame(self) -> RawTelemetryFrame:
        self._frames_received += 1
        return RawTelemetryFrame(
            payload="1.0,3.6,25.0",
            source_id=self._source_id,
            transport_type=self._transport_type,
            sequence_number=self._frames_received,
        )


class TestGatewayBase(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying base gateway data models, status tracking, and source contracts."""

    def test_raw_telemetry_frame_properties_and_immutability(self) -> None:
        """RawTelemetryFrame preserves provenance, timestamps, and prevents mutation."""
        frame = RawTelemetryFrame(
            payload={"voltage_v": 3.65, "current_a": 1.2},
            source_id="bms_test_01",
            transport_type="CAN",
            received_timestamp_ns=1_000_000_000,
            source_timestamp_ns=999_999_000,
            sequence_number=42,
            device_id="can0",
            format_identifier="JSON",
            metadata={"arbitration_id": "0x180"},
        )

        self.assertEqual(frame.source_id, "bms_test_01")
        self.assertEqual(frame.transport_type, "CAN")
        self.assertEqual(frame.received_timestamp_ns, 1_000_000_000)
        self.assertEqual(frame.source_timestamp_ns, 999_999_000)
        self.assertEqual(frame.sequence_number, 42)
        self.assertEqual(frame.device_id, "can0")
        self.assertEqual(frame.format_identifier, "JSON")
        self.assertEqual(frame.metadata["arbitration_id"], "0x180")

        # Immutability check
        with self.assertRaises(Exception):
            frame.source_id = "mutated"  # type: ignore

    def test_raw_telemetry_frame_validation(self) -> None:
        """RawTelemetryFrame validates non-empty source and transport identifiers."""
        with self.assertRaises(ValueError):
            RawTelemetryFrame(payload="test", source_id="", transport_type="SERIAL")

        with self.assertRaises(ValueError):
            RawTelemetryFrame(payload="test", source_id="src1", transport_type="")

        with self.assertRaises(ValueError):
            RawTelemetryFrame(payload="test", source_id="src1", transport_type="SERIAL", received_timestamp_ns=-1)

    def test_gateway_source_status_serialization(self) -> None:
        """GatewaySourceStatus serializes accurately to dictionary."""
        status = GatewaySourceStatus(
            source_id="src_01",
            transport_type="SERIAL",
            state=GatewaySourceState.CONNECTED,
            is_connected=True,
            frames_received=100,
            frames_dropped=2,
            parse_errors=1,
            transport_errors=0,
            reconnect_count=1,
            last_received_at_ns=5000,
            last_error=None,
            queue_depth=5,
        )
        d = status.to_dict()
        self.assertEqual(d["source_id"], "src_01")
        self.assertEqual(d["state"], "CONNECTED")
        self.assertTrue(d["is_connected"])
        self.assertEqual(d["frames_received"], 100)
        self.assertEqual(d["queue_depth"], 5)

    def test_gateway_config_defaults(self) -> None:
        """GatewayConfig defaults to bounded queue size and DROP_OLDEST policy."""
        cfg = GatewayConfig()
        self.assertEqual(cfg.max_queue_size, 1000)
        self.assertEqual(cfg.overflow_policy, GatewayOverflowPolicy.DROP_OLDEST)
        self.assertEqual(cfg.worker_concurrency, 1)

    async def test_dummy_source_lifecycle(self) -> None:
        """BaseTelemetrySource tracks status and handles start/stop lifecycle."""
        src = DummySource("bench_source_1")
        self.assertEqual(src.state, GatewaySourceState.INITIALIZING)
        self.assertEqual(src.get_status().frames_received, 0)

        await src.start()
        self.assertEqual(src.state, GatewaySourceState.CONNECTED)
        self.assertTrue(src.get_status().is_connected)

        frame = await src.read_frame()
        self.assertIsNotNone(frame)
        self.assertEqual(frame.sequence_number, 1)
        self.assertEqual(src.get_status().frames_received, 1)

        await src.stop()
        self.assertEqual(src.state, GatewaySourceState.STOPPED)
        self.assertFalse(src.get_status().is_connected)


if __name__ == "__main__":
    unittest.main()
