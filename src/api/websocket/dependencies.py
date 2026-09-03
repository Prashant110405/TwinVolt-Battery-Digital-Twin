"""WebSocket Dependency Injection Providers."""

from fastapi import Request, WebSocket
from src.api.websocket.manager import WebSocketConnectionManager


def get_websocket_manager(websocket: WebSocket) -> WebSocketConnectionManager:
    """Retrieves or creates the WebSocketConnectionManager from FastAPI app state."""
    mgr = getattr(websocket.app.state, "ws_manager", None)
    if mgr is None:
        event_bus = getattr(getattr(websocket.app.state, "services", None), "event_bus", None)
        mgr = WebSocketConnectionManager(event_bus=event_bus)
        websocket.app.state.ws_manager = mgr
    return mgr
