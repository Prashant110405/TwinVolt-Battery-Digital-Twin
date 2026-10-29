from pathlib import Path
from typing import Optional
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.api.dependencies import ServiceContainer, create_default_services
from src.api.exceptions import register_exception_handlers
from src.api.lifespan import create_lifespan
from src.api.routes.benchmarks import router as benchmarks_router
from src.api.routes.gateway import router as gateway_router
from src.api.routes.health import router as health_router
from src.api.routes.packs import router as packs_router
from src.api.routes.replay import router as replay_router
from src.api.routes.telemetry import router as telemetry_router
from src.api.routes.datasets import router as datasets_router
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
    app.include_router(datasets_router)
    app.include_router(replay_router)
    app.include_router(benchmarks_router)
    app.include_router(websocket_router)
    app.include_router(gateway_router)

    # Robust UI Static Files Resolution across local, Docker, and Vercel Serverless layouts
    candidates = [
        Path(__file__).resolve().parent.parent / "ui",
        Path.cwd() / "src" / "ui",
        Path.cwd() / "ui",
        Path(__file__).resolve().parents[2] / "src" / "ui" if len(Path(__file__).resolve().parents) > 2 else Path.cwd() / "src" / "ui",
    ]
    ui_dir = next((p for p in candidates if (p / "index.html").is_file()), None)

    if ui_dir is not None:
        app.mount("/ui", StaticFiles(directory=str(ui_dir), html=True), name="ui")
        if (ui_dir / "css").is_dir():
            app.mount("/css", StaticFiles(directory=str(ui_dir / "css")), name="css_static")
        if (ui_dir / "js").is_dir():
            app.mount("/js", StaticFiles(directory=str(ui_dir / "js")), name="js_static")
        if (ui_dir / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=str(ui_dir / "assets")), name="assets_static")

    @app.get("/favicon.ico", include_in_schema=False)
    async def serve_favicon():
        if ui_dir is not None:
            logo_path = ui_dir / "assets" / "logo.svg"
            if logo_path.is_file():
                return FileResponse(str(logo_path), media_type="image/svg+xml")
            if (ui_dir / "index.html").is_file():
                return FileResponse(str(ui_dir / "index.html"))
        return JSONResponse({"status": "no favicon"}, status_code=204)

    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    async def serve_root():
        if ui_dir is not None and (ui_dir / "index.html").is_file():
            return FileResponse(str(ui_dir / "index.html"))
        return JSONResponse(
            status_code=200,
            content={
                "name": title,
                "status": "online",
                "version": version,
                "description": description,
                "docs_url": "/docs",
                "health_url": "/health",
                "api_prefix": "/api/v1",
            },
        )

    # Client-side SPA navigation routes — define each handler explicitly to avoid closure capture bug
    async def _spa_handler():
        if ui_dir is not None and (ui_dir / "index.html").is_file():
            return FileResponse(str(ui_dir / "index.html"))
        return JSONResponse({"status": "online"})

    for _view in [
        "overview", "telemetry", "twin", "estimation",
        "replay", "events", "diagnostics", "benchmarking", "datasets",
    ]:
        app.add_api_route(f"/{_view}", _spa_handler, include_in_schema=False, response_model=None)
        app.add_api_route(f"/ui/{_view}", _spa_handler, include_in_schema=False, response_model=None)

    # Explicit API discovery endpoints
    @app.get("/api", tags=["System"])
    @app.get("/api/", tags=["System"])
    @app.get("/api/index", include_in_schema=False)
    @app.get("/api/index.py", include_in_schema=False)
    async def serve_api_root():
        return {
            "name": title,
            "status": "online",
            "version": version,
            "docs_url": "/docs",
            "health_url": "/health",
            "endpoints": {
                "health": "/health",
                "packs": "/api/v1/packs",
                "twins": "/api/v1/twins",
                "telemetry": "/api/v1/telemetry",
                "datasets": "/api/v1/datasets",
                "replay": "/api/v1/replay",
                "benchmarks": "/api/v1/benchmarks",
                "gateway": "/api/v1/gateway",
            },
        }

    return app
