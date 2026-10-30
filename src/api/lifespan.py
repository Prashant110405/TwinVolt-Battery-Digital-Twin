"""FastAPI Application Lifespan Context Manager.

Coordinates non-blocking startup and graceful shutdown of edge application services,
gateway daemon workers, and background subscriptions.
"""

from contextlib import asynccontextmanager
import logging
import time
from typing import AsyncIterator, Optional
from fastapi import FastAPI

from src.config.settings import AppSettings, get_settings
from src.gateway.manager import GatewayDaemonManager

logger = logging.getLogger("twinvolt.lifecycle")


def create_lifespan(settings: Optional[AppSettings] = None):
    """Factory returning an async lifespan context manager with injected operational settings."""
    app_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Manages application startup initialization and graceful shutdown."""
        # Record startup timestamp for liveness / uptime diagnostics
        app.state.start_time_ns = time.time_ns()
        app.state.settings = app_settings

        logger.info(
            "Starting TwinVolt Digital Twin Server on %s:%s (log_level=%s)",
            app_settings.host,
            app_settings.port,
            app_settings.log_level,
        )

        # 1. Reuse existing GatewayDaemonManager from app state
        gateway_mgr: Optional[GatewayDaemonManager] = getattr(app.state, "gateway_manager", None)

        if gateway_mgr is None and hasattr(app.state, "services") and app.state.services is not None:
            # Fallback attach if not pre-attached by factory
            gateway_mgr = GatewayDaemonManager(
                telemetry_service=app.state.services.telemetry_service,
                event_bus=app.state.services.event_bus,
            )
            app.state.gateway_manager = gateway_mgr

        # 2. Autostart gateway daemon if configured
        if gateway_mgr is not None and app_settings.gateway_autostart:
            logger.info("TWINVOLT_GATEWAY_AUTOSTART is enabled. Starting GatewayDaemonManager...")
            try:
                await gateway_mgr.start()
                logger.info("GatewayDaemonManager started successfully.")
            except Exception as exc:
                logger.error("Failed to autostart GatewayDaemonManager: %s", exc)
                # Allow server to run so health endpoints reflect the error

        # 3. Seed default battery pack profiles and digital twin if enabled
        if app_settings.seed_defaults and hasattr(app.state, "services") and app.state.services is not None:
            try:
                from src.runtime.seeder import seed_default_twins_and_packs
                seed_default_twins_and_packs(app.state.services)
            except Exception as exc:
                logger.warning("Failed to seed default battery profiles: %s", exc)

        try:
            yield
        finally:
            # 3. Graceful Shutdown
            logger.info("Shutting down TwinVolt Edge Server...")

            arduino_mgr = getattr(app.state, "arduino_manager", None)
            if arduino_mgr is not None and arduino_mgr.is_connected:
                logger.info("Stopping ArduinoConnectionManager...")
                try:
                    await arduino_mgr.disconnect()
                except Exception as exc:
                    logger.error("Error stopping ArduinoConnectionManager: %s", exc)

            mock_svc = getattr(app.state, "mock_service", None)
            if mock_svc is not None and mock_svc.is_running:
                logger.info("Stopping MockTelemetryService...")
                try:
                    await mock_svc.stop()
                except Exception as exc:
                    logger.error("Error stopping MockTelemetryService: %s", exc)

            if gateway_mgr is not None and gateway_mgr.is_running:
                logger.info("Stopping GatewayDaemonManager and releasing transport sockets...")
                try:
                    await gateway_mgr.stop()
                    logger.info("GatewayDaemonManager stopped cleanly.")
                except Exception as exc:
                    logger.error("Error during GatewayDaemonManager shutdown: %s", exc)

            logger.info("TwinVolt Edge Server shutdown complete.")

    return lifespan
