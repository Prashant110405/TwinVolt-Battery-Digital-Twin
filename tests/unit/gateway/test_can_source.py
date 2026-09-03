"""Unit tests for SocketCAN and CAN Bus Telemetry Source."""

import unittest
from src.gateway.base import GatewaySourceState
from src.gateway.can_source import CanConfig, SocketCanSource


class TestSocketCanSource(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying SocketCAN frame reading, CAN 2.0 / CAN-FD handling, and metadata preservation."""

    async def test_can_frame_reading_and_metadata(self) -> None:
        """SocketCanSource captures injected CAN messages preserving arbitration ID and hex payload."""
        cfg = CanConfig(channel="vcan0", interface="virtual")
        source = SocketCanSource(source_id="twin_can_01", config=cfg)

        await source.start()
        self.assertEqual(source.state, GatewaySourceState.CONNECTED)

        # Inject standard CAN frame (11-bit ID 0x180)
        source.inject_mock_can_message(
            arbitration_id=0x180,
            data=bytes([0x0E, 0x10, 0x00, 0x96, 0x19, 0x00, 0x00, 0x00]),
            is_extended_id=False,
            is_fd=False,
        )

        frame = await source.read_frame()
        self.assertIsNotNone(frame)
        self.assertEqual(frame.source_id, "twin_can_01")
        self.assertEqual(frame.transport_type, "CAN")
        self.assertEqual(frame.device_id, "vcan0")
        self.assertEqual(frame.payload["arbitration_id"], 0x180)
        self.assertEqual(frame.payload["dlc"], 8)
        self.assertEqual(frame.payload["data_hex"], "0e10009619000000")
        self.assertFalse(frame.payload["is_extended_id"])

        await source.stop()
        self.assertEqual(source.state, GatewaySourceState.STOPPED)

    async def test_can_fd_extended_frame(self) -> None:
        """SocketCanSource handles 29-bit extended ID CAN-FD frames."""
        cfg = CanConfig(channel="can1", interface="socketcan")
        source = SocketCanSource(source_id="twin_can_fd", config=cfg)

        await source.start()

        # Extended ID (29-bit 0x18FF50E5)
        source.inject_mock_can_message(
            arbitration_id=0x18FF50E5,
            data=bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A]),
            is_extended_id=True,
            is_fd=True,
        )

        frame = await source.read_frame()
        self.assertIsNotNone(frame)
        self.assertEqual(frame.payload["arbitration_id"], 0x18FF50E5)
        self.assertTrue(frame.payload["is_extended_id"])
        self.assertTrue(frame.payload["is_fd"])
        self.assertEqual(frame.payload["dlc"], 10)

        await source.stop()


if __name__ == "__main__":
    unittest.main()
