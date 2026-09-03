"""Unit tests for Serial UART Telemetry Source."""

import asyncio
import unittest
from src.gateway.base import GatewaySourceState
from src.gateway.serial_source import SerialConfig, SerialUartSource


class TestSerialUartSource(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying Serial UART asynchronous frame reading, framing, and reconnection."""

    async def test_serial_read_frames_with_delimiter(self) -> None:
        """Serial source reads framed lines from stream reader and emits RawTelemetryFrame."""
        reader = asyncio.StreamReader()
        writer = None

        # Pre-feed lines into reader
        reader.feed_data(b"0.0,3.60,1.5,25.0\n0.1,3.59,1.5,25.1\n")
        reader.feed_eof()

        async def mock_stream_factory():
            return reader, writer

        cfg = SerialConfig(
            port="COM_MOCK",
            baud_rate=115200,
            delimiter=b"\n",
            auto_reconnect=False,
        )
        source = SerialUartSource(
            source_id="twin_serial_01",
            config=cfg,
            stream_factory=mock_stream_factory,
        )

        await source.start()
        self.assertEqual(source.state, GatewaySourceState.CONNECTED)

        # 1. Read first line
        frame1 = await source.read_frame()
        self.assertIsNotNone(frame1)
        self.assertEqual(frame1.payload, "0.0,3.60,1.5,25.0")
        self.assertEqual(frame1.sequence_number, 1)
        self.assertEqual(frame1.source_id, "twin_serial_01")
        self.assertEqual(frame1.transport_type, "SERIAL")

        # 2. Read second line
        frame2 = await source.read_frame()
        self.assertIsNotNone(frame2)
        self.assertEqual(frame2.payload, "0.1,3.59,1.5,25.1")
        self.assertEqual(frame2.sequence_number, 2)

        # 3. Stream EOF
        frame3 = await source.read_frame()
        self.assertIsNone(frame3)

        await source.stop()
        self.assertEqual(source.state, GatewaySourceState.STOPPED)

    async def test_serial_reconnect_behavior(self) -> None:
        """Serial source handles disconnect and reconnects using exponential backoff."""
        connection_attempts = 0

        async def failing_then_succeeding_factory():
            nonlocal connection_attempts
            connection_attempts += 1
            if connection_attempts == 1:
                # First attempt fails
                raise ConnectionError("COM port busy")
            reader = asyncio.StreamReader()
            reader.feed_data(b"timestamp_s,voltage_v\n1.0,3.65\n")
            reader.feed_eof()
            return reader, None

        cfg = SerialConfig(
            port="COM_RECONNECT",
            reconnect_initial_delay_s=0.01,
            reconnect_max_delay_s=0.1,
            auto_reconnect=True,
        )
        source = SerialUartSource(
            source_id="twin_serial_reconnect",
            config=cfg,
            stream_factory=failing_then_succeeding_factory,
        )

        # Start will encounter initial error
        await source.start()
        self.assertEqual(source.state, GatewaySourceState.ERROR)

        # read_frame triggers reconnect
        frame = await source.read_frame()
        self.assertIsNotNone(frame)
        self.assertEqual(frame.payload, "timestamp_s,voltage_v")
        self.assertGreaterEqual(source.get_status().reconnect_count, 1)

        await source.stop()


if __name__ == "__main__":
    unittest.main()
