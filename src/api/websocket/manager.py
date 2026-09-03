"""WebSocket Connection and Real-Time Subscription Manager.

Provides thread-safe and async-safe multi-client connection management,
system_id topic routing, fault-isolated broadcasts, and event bus bridging.
"""

import asyncio
from typing import Any, Mapping, Optional, Set, Union
import uuid
from fastapi import WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from src.api.websocket.schemas import WSConnectedMessage, WSTwinEventMessage
from src.events.base import AbstractEventBus, TwinEvent


class WebSocketConnectionManager:
    """Thread-safe and async-safe manager for WebSocket connections and digital twin subscriptions.

    Coordinates client lifecycles, per-twin topic subscriptions, fault-isolated broadcasts,
    and event bus bridging without embedding domain/battery logic.
    """

    def __init__(self, event_bus: Optional[AbstractEventBus] = None) -> None:
        self._connections: dict[str, WebSocket] = {}
        self._subscriptions: dict[str, Set[str]] = {}  # system_id -> set of client_ids
        self._client_subscriptions: dict[str, Set[str]] = {}  # client_id -> set of system_ids
        self._event_bus = event_bus
        self._event_sub_id: Optional[str] = None
        self._lock = asyncio.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        if self._event_bus is not None:
            self._setup_event_bus_adapter()

    def _setup_event_bus_adapter(self) -> None:
        """Attaches an event listener to the event bus for real-time WebSocket bridging."""
        if self._event_bus is None:
            return

        def _on_event(event: TwinEvent) -> None:
            # Bridging sync event bus callback into async broadcast
            if self._loop and self._loop.is_running():
                sys_id = getattr(event, "system_id", None) or getattr(event, "source_id", None)
                if sys_id:
                    msg = WSTwinEventMessage(
                        system_id=sys_id,
                        event_type=event.event_type,
                        event_id=event.event_id,
                        timestamp_ns=event.timestamp_ns,
                        payload=dict(event.payload) if hasattr(event, "payload") else {},
                    )
                    asyncio.run_coroutine_threadsafe(
                        self.broadcast_to_twin(sys_id, msg),
                        self._loop,
                    )

        try:
            self._event_sub_id = self._event_bus.subscribe(
                event_type="*",
                handler=_on_event,
                priority=10,
            )
        except Exception:
            self._event_sub_id = None

    async def connect(
        self,
        websocket: WebSocket,
        client_id: Optional[str] = None,
        system_id: Optional[str] = None,
    ) -> str:
        """Accepts and registers a new WebSocket client, optionally subscribing it to a twin.

        Args:
            websocket: FastAPI WebSocket instance.
            client_id: Optional explicit client identifier.
            system_id: Optional twin system identifier to auto-subscribe.

        Returns:
            Assigned client_id.
        """
        await websocket.accept()
        cid = client_id or f"client_{uuid.uuid4().hex[:8]}"

        # Record active event loop for sync-to-async event bus bridging
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

        async with self._lock:
            self._connections[cid] = websocket
            self._client_subscriptions[cid] = set()

        if system_id:
            await self.subscribe(cid, system_id)

        # Send welcome message
        welcome = WSConnectedMessage(client_id=cid)
        await self.send_personal_message(cid, welcome)
        return cid

    async def disconnect(self, client_id: str) -> None:
        """Unregisters and cleans up a disconnected client."""
        async with self._lock:
            if client_id in self._connections:
                del self._connections[client_id]

            # Remove from client_subscriptions and twin subscriptions
            subscribed_twins = self._client_subscriptions.pop(client_id, set())
            for sys_id in subscribed_twins:
                if sys_id in self._subscriptions:
                    self._subscriptions[sys_id].discard(client_id)
                    if not self._subscriptions[sys_id]:
                        del self._subscriptions[sys_id]

    async def subscribe(self, client_id: str, system_id: str) -> None:
        """Subscribes a client to a digital twin's real-time updates.

        Args:
            client_id: Connected client identifier.
            system_id: Target battery digital twin system identifier.
        """
        async with self._lock:
            if client_id not in self._connections:
                return

            if system_id not in self._subscriptions:
                self._subscriptions[system_id] = set()
            self._subscriptions[system_id].add(client_id)

            if client_id not in self._client_subscriptions:
                self._client_subscriptions[client_id] = set()
            self._client_subscriptions[client_id].add(system_id)

    async def unsubscribe(self, client_id: str, system_id: str) -> None:
        """Unsubscribes a client from a digital twin stream.

        Args:
            client_id: Connected client identifier.
            system_id: Target battery digital twin system identifier.
        """
        async with self._lock:
            if system_id in self._subscriptions:
                self._subscriptions[system_id].discard(client_id)
                if not self._subscriptions[system_id]:
                    del self._subscriptions[system_id]

            if client_id in self._client_subscriptions:
                self._client_subscriptions[client_id].discard(system_id)

    async def send_personal_message(
        self,
        client_id: str,
        message: Union[dict[str, Any], BaseModel],
    ) -> bool:
        """Sends a JSON message to a single connected client with fault isolation.

        Args:
            client_id: Target client identifier.
            message: Dictionary or Pydantic message model.

        Returns:
            True if sent successfully, False otherwise.
        """
        ws: Optional[WebSocket] = None
        async with self._lock:
            ws = self._connections.get(client_id)

        if ws is None:
            return False

        payload = message.model_dump() if isinstance(message, BaseModel) else message
        try:
            await ws.send_json(payload)
            return True
        except (WebSocketDisconnect, RuntimeError, Exception):
            # Broken connection: remove client
            await self.disconnect(client_id)
            return False

    async def broadcast_to_twin(
        self,
        system_id: str,
        message: Union[dict[str, Any], BaseModel],
    ) -> int:
        """Broadcasts a message to all clients subscribed to a specific digital twin.

        Fault isolated: if sending to one client fails, other clients still receive
        the message without interruption.

        Args:
            system_id: Target digital twin system identifier.
            message: Message payload or Pydantic model.

        Returns:
            Count of clients that successfully received the broadcast.
        """
        async with self._lock:
            subscribers = set(self._subscriptions.get(system_id, set()))

        if not subscribers:
            return 0

        success_count = 0
        dead_clients: list[str] = []

        payload = message.model_dump() if isinstance(message, BaseModel) else message

        for cid in subscribers:
            async with self._lock:
                ws = self._connections.get(cid)

            if ws is None:
                dead_clients.append(cid)
                continue

            try:
                await ws.send_json(payload)
                success_count += 1
            except Exception:
                dead_clients.append(cid)

        # Clean up any dead clients
        for cid in dead_clients:
            await self.disconnect(cid)

        return success_count

    @property
    def total_connections(self) -> int:
        """Total number of active connected clients."""
        return len(self._connections)

    def get_subscriber_count(self, system_id: str) -> int:
        """Returns the number of clients subscribed to a specific twin."""
        return len(self._subscriptions.get(system_id, set()))
