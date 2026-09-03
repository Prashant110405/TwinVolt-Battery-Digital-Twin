"""WebSocket Real-Time Streaming Transport Package."""

from src.api.websocket.dependencies import get_websocket_manager
from src.api.websocket.handlers import router as websocket_router
from src.api.websocket.manager import WebSocketConnectionManager
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

__all__ = [
    # Router
    "websocket_router",
    # Manager
    "WebSocketConnectionManager",
    "get_websocket_manager",
    # Protocol Schemas
    "WSSubscribeMessage",
    "WSUnsubscribeMessage",
    "WSPingMessage",
    "WSTelemetryIngestMessage",
    "WSConnectedMessage",
    "WSPongMessage",
    "WSTelemetryAckMessage",
    "WSTwinStateMessage",
    "WSTwinEventMessage",
    "WSErrorMessage",
]
