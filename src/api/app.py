from pathlib import Path
from typing import Optional
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.dependencies import ServiceContainer, create_default_services
from src.api.exceptions import register_exception_handlers
from src.api.lifespan import create_lifespan
from src.api.routes.gateway import router as gateway_router
from src.api.routes.health import router as health_router
from src.api.routes.packs import router as packs_router
from src.api.routes.replay import router as replay_router
from src.api.routes.telemetry import router as telemetry_router
from src.api.routes.twins import router as twins_router
from src.api.websocket.handlers import router as websocket_router
from src.api.websocket.manager import WebSocketConnectionManager
from src.config.settings import AppSettings
from src.gateway.manager import GatewayDaemonManager


def create_app(
    services: Optional[ServiceContainer] = None,
    settings: Optional[AppSettings] = None,
    title: str = "TwinVolt Digital Twin REST API",
    version: str = "1.0.0",
    description: str = "Production REST API for the TwinVolt Universal Battery Digital Twin Platform.",
) -> FastAPI:
    """Application factory assembling the FastAPI ASGI application.

    Args:
        services: Optional pre-configured ServiceContainer for custom dependency injection.
        settings: Optional pre-configured AppSettings for operational environment tuning.
        title: OpenAPI documentation title.
        version: API semantic version.
        description: OpenAPI description.

    Returns:
        Configured FastAPI application instance.
    """
    app = FastAPI(
        title=title,
        version=version,
        description=description,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=create_lifespan(settings=settings),
    )

    # Attach Service Container
    active_services = services or create_default_services()
    app.state.services = active_services

    # Attach WebSocket Manager
    app.state.ws_manager = WebSocketConnectionManager(event_bus=active_services.event_bus)

    # Attach Gateway Daemon Manager
    app.state.gateway_manager = GatewayDaemonManager(
        telemetry_service=active_services.telemetry_service,
        event_bus=active_services.event_bus,
    )

    # Register Domain & Service Exception Handlers
    register_exception_handlers(app)

    # Register Route Blueprints
    app.include_router(health_router)
    app.include_router(packs_router)
    app.include_router(twins_router)
    app.include_router(telemetry_router)
    app.include_router(replay_router)
    app.include_router(websocket_router)
    app.include_router(gateway_router)

    # Mount UI Static Files
    ui_dir = Path(__file__).resolve().parent.parent / "ui"
    if ui_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")

        @app.get("/", include_in_schema=False)
        async def serve_root():
            return FileResponse(str(ui_dir / "index.html"))

    return app
