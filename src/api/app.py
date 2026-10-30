import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.api.dependencies import ServiceContainer, create_default_services
from src.api.exceptions import register_exception_handlers
from src.api.lifespan import create_lifespan
from src.api.routes.benchmarks import router as benchmarks_router
from src.api.routes.firmware import router as firmware_router
from src.api.routes.gateway import router as gateway_router
from src.api.routes.health import router as health_router
from src.api.routes.mock import router as mock_router
from src.api.routes.packs import router as packs_router
from src.api.routes.replay import router as replay_router
from src.api.routes.telemetry import router as telemetry_router
from src.api.routes.datasets import router as datasets_router
from src.api.routes.twins import router as twins_router
from src.api.websocket.handlers import router as websocket_router
from src.api.websocket.manager import WebSocketConnectionManager
from src.config.settings import AppSettings
from src.gateway.arduino import ArduinoConnectionManager
from src.gateway.manager import GatewayDaemonManager
from src.services.mock_service import MockTelemetryService


def _build_cors_origins() -> list[str]:
    """Builds the list of allowed CORS origins from environment variables.

    In local development, localhost origins are always permitted.
    In production, set the CORS_ORIGINS environment variable to a
    comma-separated list of allowed frontend origins, e.g.:

        CORS_ORIGINS=https://twinvolt.vercel.app,https://twinvolt-preview.vercel.app

    A wildcard '*' is also accepted (not recommended for authenticated APIs).
    """
    env_origins = os.environ.get("CORS_ORIGINS", "")
    origins: list[str] = []

    # Always permit local development origins
    origins += [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://127.0.0.1:3000",
    ]

    if env_origins.strip():
        for o in env_origins.split(","):
            o = o.strip()
            if o and o not in origins:
                origins.append(o)

    return origins


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

    # ── CORS Middleware ────────────────────────────────────────────────────────
    # Required when the Vercel-hosted frontend calls this backend from a different
    # origin (e.g. https://twinvolt.vercel.app → https://backend.railway.app).
    # In same-origin deployments (local dev / Docker) CORS is still registered
    # but all requests are same-origin so the middleware is effectively a no-op.
    cors_origins = _build_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=r"https://.*\.vercel\.app",  # permit all Vercel preview URLs
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # ── Service Container ──────────────────────────────────────────────────────
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

    # Attach Hardware Arduino Connection Manager
    app.state.arduino_manager = ArduinoConnectionManager(
        telemetry_service=active_services.telemetry_service,
        event_bus=active_services.event_bus,
    )

    # Attach Isolated Mock Telemetry Generator
    app.state.mock_service = MockTelemetryService(
        telemetry_service=active_services.telemetry_service,
        event_bus=active_services.event_bus,
    )

    # Register Domain & Service Exception Handlers
    register_exception_handlers(app)

    # ── API Route Blueprints ───────────────────────────────────────────────────
    app.include_router(health_router)
    app.include_router(packs_router)
    app.include_router(twins_router)
    app.include_router(telemetry_router)
    app.include_router(datasets_router)
    app.include_router(replay_router)
    app.include_router(benchmarks_router)
    app.include_router(websocket_router)
    app.include_router(gateway_router)
    app.include_router(firmware_router)
    app.include_router(mock_router)

    # ── Static UI Files & Client-Side SPA Routes ─────────────────────────────
    # Resolves UI static files across local dev, Docker, and Vercel layouts.
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
            logo_path = ui_dir / "assets" / "logo.svg"
            if logo_path.is_file():
                return FileResponse(str(logo_path), media_type="image/svg+xml")
            return FileResponse(str(ui_dir / "index.html"))

        @app.get("/", include_in_schema=False)
        @app.get("/index.html", include_in_schema=False)
        async def serve_root():
            return FileResponse(str(ui_dir / "index.html"))

        # Client-side SPA navigation routes
        spa_views = [
            "overview",
            "telemetry",
            "hardware",
            "mock",
            "twin",
            "estimation",
            "replay",
            "events",
            "diagnostics",
            "benchmarking",
            "datasets",
        ]
        for view in spa_views:
            @app.get(f"/{view}", include_in_schema=False)
            @app.get(f"/ui/{view}", include_in_schema=False)
            async def serve_spa_view():
                return FileResponse(str(ui_dir / "index.html"))

    return app
