"""Unit tests for TCP Socket Telemetry Source."""

import asyncio
import unittest
from src.gateway.base import GatewaySourceState
from src.gateway.tcp_source import TcpConfig, TcpSocketSource


class TestTcpSocketSource(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying TCP socket streaming, line framing, and connection handling."""

    async def test_tcp_streaming_with_local_server(self) -> None:
        """TcpSocketSource connects to a TCP server and streams framed lines."""
        received_clients = []

        async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            received_clients.append((reader, writer))
            writer.write(b'{"voltage_v": 3.65, "current_a": 2.0}\n{"voltage_v": 3.64, "current_a": 2.1}\n')
            await writer.drain()

        # Start ephemeral local TCP server
        server = await asyncio.start_server(handle_client, host="127.0.0.1", port=0)
        port = server.sockets[0].getsockname()[1]

        cfg = TcpConfig(host="127.0.0.1", port=port, auto_reconnect=False)
        source = TcpSocketSource(source_id="twin_tcp_01", config=cfg)

        await source.start()
        self.assertEqual(source.state, GatewaySourceState.CONNECTED)

        # 1. Read first frame
        frame1 = await source.read_frame()
        self.assertIsNotNone(frame1)
        self.assertEqual(frame1.payload, '{"voltage_v": 3.65, "current_a": 2.0}')
        self.assertEqual(frame1.source_id, "twin_tcp_01")
        self.assertEqual(frame1.transport_type, "TCP")

        # 2. Read second frame
        frame2 = await source.read_frame()
        self.assertIsNotNone(frame2)
        self.assertEqual(frame2.payload, '{"voltage_v": 3.64, "current_a": 2.1}')

        await source.stop()
        server.close()
        await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
