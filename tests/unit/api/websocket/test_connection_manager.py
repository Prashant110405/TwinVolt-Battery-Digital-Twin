"""Unit tests for WebSocketConnectionManager."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from src.api.websocket.manager import WebSocketConnectionManager
from src.api.websocket.schemas import WSTwinStateMessage
from src.events.bus import DigitalTwinEventBus


class TestWebSocketConnectionManager(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying client registration, subscriptions, fault-isolated broadcasts, and cleanup."""

    async def asyncSetUp(self) -> None:
        self.event_bus = DigitalTwinEventBus()
        self.manager = WebSocketConnectionManager(event_bus=self.event_bus)

    async def test_connect_and_disconnect(self) -> None:
        """Connecting a websocket registers it and disconnecting cleans it up."""
        mock_ws = AsyncMock()
        mock_ws.accept = AsyncMock()
        mock_ws.send_json = AsyncMock()

        cid = await self.manager.connect(mock_ws, client_id="client_1", system_id="twin_1")
        self.assertEqual(cid, "client_1")
        self.assertEqual(self.manager.total_connections, 1)
        self.assertEqual(self.manager.get_subscriber_count("twin_1"), 1)

        # Verify welcome message was sent
        mock_ws.send_json.assert_awaited()

        # Disconnect
        await self.manager.disconnect("client_1")
        self.assertEqual(self.manager.total_connections, 0)
        self.assertEqual(self.manager.get_subscriber_count("twin_1"), 0)

    async def test_subscribe_and_unsubscribe(self) -> None:
        """Clients can subscribe and unsubscribe from twin topics."""
        mock_ws = AsyncMock()
        await self.manager.connect(mock_ws, client_id="client_sub")

        self.assertEqual(self.manager.get_subscriber_count("twin_alpha"), 0)
        await self.manager.subscribe("client_sub", "twin_alpha")
        self.assertEqual(self.manager.get_subscriber_count("twin_alpha"), 1)

        await self.manager.unsubscribe("client_sub", "twin_alpha")
        self.assertEqual(self.manager.get_subscriber_count("twin_alpha"), 0)

    async def test_broadcast_isolation_across_twins(self) -> None:
        """Broadcasts to twin_A are received only by twin_A subscribers, not twin_B subscribers."""
        ws_a = AsyncMock()
        ws_b = AsyncMock()

        await self.manager.connect(ws_a, client_id="client_a", system_id="twin_A")
        await self.manager.connect(ws_b, client_id="client_b", system_id="twin_B")

        # Reset mocks after connect welcome messages
        ws_a.send_json.reset_mock()
        ws_b.send_json.reset_mock()

        msg_a = WSTwinStateMessage(
            system_id="twin_A",
            step_index=1,
            timestamp_ns=1_000_000_000,
            dt_s=1.0,
            terminal_voltage_v=3.60,
            simulated_soc=0.99,
            temperature_c=25.0,
        )

        sent_count = await self.manager.broadcast_to_twin("twin_A", msg_a)
        self.assertEqual(sent_count, 1)
        ws_a.send_json.assert_awaited_once()
        ws_b.send_json.assert_not_awaited()

    async def test_broadcast_fault_isolation(self) -> None:
        """If one client fails during broadcast, other clients still receive message."""
        ws_good = AsyncMock()
        ws_bad = AsyncMock()
        ws_bad.send_json.side_effect = RuntimeError("Socket write failure")

        await self.manager.connect(ws_good, client_id="client_good", system_id="twin_shared")
        await self.manager.connect(ws_bad, client_id="client_bad", system_id="twin_shared")

        ws_good.send_json.reset_mock()

        msg = {"type": "twin_state", "system_id": "twin_shared"}
        sent_count = await self.manager.broadcast_to_twin("twin_shared", msg)
        self.assertEqual(sent_count, 1)
        ws_good.send_json.assert_awaited_once()

        # Bad client should have been cleaned up
        self.assertEqual(self.manager.get_subscriber_count("twin_shared"), 1)


if __name__ == "__main__":
    unittest.main()
