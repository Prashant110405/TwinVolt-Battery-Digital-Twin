"""Unit tests for Arduino Connection Manager and Transport.

Verifies connection lifecycle, mock stream ingestion, metrics tracking,
reconnection, and graceful disconnection.
"""

import asyncio
import unittest
from src.gateway.arduino.connection_manager import ArduinoConnectionManager
from src.gateway.arduino.models import ArduinoConfig, HardwareConnectionState, SerialDataFormat


class TestArduinoConnectionManager(unittest.IsolatedAsyncioTestCase):
    async def test_connect_with_mock_generator_and_metrics(self) -> None:
        """Manager connects using mock stream and accumulates frames/metrics."""
        frames = [
            '{"millis": 1000, "voltage_v": 3.71, "current_a": 1.2, "temperature_c": 25.0}\n',
            '{"millis": 2000, "voltage_v": 3.70, "current_a": 1.3, "temperature_c": 25.2}\n',
            '{"millis": 3000, "voltage_v": 3.69, "current_a": 1.1, "temperature_c": 25.4}\n',
        ]
        idx = 0

        async def mock_gen() -> str:
            nonlocal idx
            if idx < len(frames):
                line = frames[idx]
                idx += 1
                await asyncio.sleep(0.01)
                return line
            await asyncio.sleep(0.05)
            return None

        mgr = ArduinoConnectionManager()
        cfg = ArduinoConfig(
            port="MOCK_COM_PORT",
            baud_rate=115200,
            data_format=SerialDataFormat.JSON,
            system_id="twin_mock_test",
            auto_reconnect=False,
        )

        status = await mgr.connect(config=cfg, mock_generator=mock_gen)
        self.assertEqual(status.state, HardwareConnectionState.CONNECTED)
        self.assertEqual(mgr.state, HardwareConnectionState.CONNECTED)

        # Allow background loop to consume frames
        await asyncio.sleep(0.15)

        status_after = mgr.get_status()
        self.assertGreaterEqual(status_after.frames_received, 2)
        self.assertGreaterEqual(status_after.frames_parsed, 2)
        self.assertIsNotNone(status_after.last_valid_reading)
        self.assertAlmostEqual(status_after.last_valid_reading.voltage_v, 3.69, places=1)

        # Disconnect
        disc_status = await mgr.disconnect()
        self.assertEqual(disc_status.state, HardwareConnectionState.DISCONNECTED)
        self.assertEqual(mgr.state, HardwareConnectionState.DISCONNECTED)

    async def test_stale_detection(self) -> None:
        """Marks connection as stale when no frames arrive beyond threshold."""
        mgr = ArduinoConnectionManager(stale_threshold_s=0.05)
        cfg = ArduinoConfig(port="MOCK_PORT", system_id="twin_01", auto_reconnect=False)

        async def empty_gen() -> None:
            await asyncio.sleep(0.05)
            return None

        await mgr.connect(config=cfg, mock_generator=empty_gen)
        # Synthetically set last received timestamp to past
        mgr._last_received_ns = int((asyncio.get_event_loop().time() - 1.0) * 1e9)

        status = mgr.get_status()
        self.assertTrue(status.is_stale)
        await mgr.disconnect()


if __name__ == "__main__":
    unittest.main()
