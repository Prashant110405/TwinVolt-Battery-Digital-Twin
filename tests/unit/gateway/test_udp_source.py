"""Unit tests for UDP Socket Telemetry Source."""

import asyncio
import socket
import unittest
from src.gateway.base import GatewaySourceState
from src.gateway.udp_source import UdpConfig, UdpSocketSource


class TestUdpSocketSource(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying UDP socket datagram receiving and connectionless packet handling."""

    async def test_udp_datagram_reception(self) -> None:
        """UdpSocketSource receives connectionless datagram packets preserving sender address metadata."""
        # Find a free local UDP port
        sock_probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock_probe.bind(("127.0.0.1", 0))
        port = sock_probe.getsockname()[1]
        sock_probe.close()

        cfg = UdpConfig(host="127.0.0.1", port=port)
        source = UdpSocketSource(source_id="twin_udp_01", config=cfg)

        await source.start()
        self.assertEqual(source.state, GatewaySourceState.CONNECTED)

        # Send datagrams via client socket
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.sendto(b'{"voltage_v": 3.65, "current_a": 1.0}', ("127.0.0.1", port))
        client.sendto(b'{"voltage_v": 3.64, "current_a": 1.1}', ("127.0.0.1", port))
        client.close()

        # Read first datagram
        frame1 = await source.read_frame()
        self.assertIsNotNone(frame1)
        self.assertEqual(frame1.payload, '{"voltage_v": 3.65, "current_a": 1.0}')
        self.assertEqual(frame1.source_id, "twin_udp_01")
        self.assertEqual(frame1.transport_type, "UDP")
        self.assertIn("127.0.0.1", frame1.device_id)

        # Read second datagram
        frame2 = await source.read_frame()
        self.assertIsNotNone(frame2)
        self.assertEqual(frame2.payload, '{"voltage_v": 3.64, "current_a": 1.1}')

        await source.stop()
        self.assertEqual(source.state, GatewaySourceState.STOPPED)


if __name__ == "__main__":
    unittest.main()
