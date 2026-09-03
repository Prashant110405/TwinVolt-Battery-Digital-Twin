"""Health, Liveness, and Readiness API Routes.

Provides operational health probes for Kubernetes, Docker, systemd, and local monitoring.
"""

import time
from typing import Any, Optional
from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(tags=["Health"])


@router.get("/health", summary="General Service Health Check")
async def health_check() -> dict[str, str]:
    """Returns the general operational status and version of the TwinVolt REST API."""
    return {
        "status": "healthy",
        "service": "twinvolt-api",
        "version": "1.0.0",
    }


@router.get("/health/live", summary="Process Liveness Probe")
async def liveness_probe() -> dict[str, str]:
    """Liveness probe confirming the ASGI event loop and HTTP server are responsive.

    Does NOT require active batteries, twins, or physical hardware.
    """
    return {
        "status": "alive",
        "service": "twinvolt-api",
    }


@router.get("/health/ready", summary="System Readiness Probe")
async def readiness_probe(request: Request) -> dict[str, Any]:
    """Readiness probe verifying core internal infrastructure is initialized and ready for requests.

    Zero active twins is a valid READY state.
    """
    services = getattr(request.app.state, "services", None)
    services_initialized = services is not None

    event_bus_ready = False
    if services is not None and getattr(services, "event_bus", None) is not None:
        event_bus_ready = True

    gateway_ready = True
    gateway_mgr = getattr(request.app.state, "gateway_manager", None)
    settings = getattr(request.app.state, "settings", None)

    if settings is not None and getattr(settings, "gateway_autostart", False):
        if gateway_mgr is None or not gateway_mgr.is_running:
            gateway_ready = False

    is_ready = services_initialized and event_bus_ready and gateway_ready

    result = {
        "status": "ready" if is_ready else "not_ready",
        "service": "twinvolt-api",
        "services_initialized": services_initialized,
        "event_bus_ready": event_bus_ready,
        "gateway_ready": gateway_ready,
    }

    if not is_ready:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=result,
        )

    return result


@router.get("/health/details", summary="Diagnostic Health and Uptime Telemetry")
async def health_details(request: Request) -> dict[str, Any]:
    """Returns deep diagnostic telemetry and subsystem health without disclosing sensitive configuration."""
    start_time_ns = getattr(request.app.state, "start_time_ns", None)
    uptime_s = (time.time_ns() - start_time_ns) / 1e9 if start_time_ns else 0.0

    services = getattr(request.app.state, "services", None)
    active_twins_count = 0
    registered_packs_count = 0

    if services is not None:
        if getattr(services, "twin_service", None) is not None:
            active_twins_count = services.twin_service.count
        if getattr(services, "pack_service", None) is not None:
            registered_packs_count = services.pack_service.count

    gateway_mgr = getattr(request.app.state, "gateway_manager", None)
    gateway_status = gateway_mgr.get_status() if gateway_mgr is not None else None

    return {
        "status": "healthy",
        "service": "twinvolt-api",
        "version": "1.0.0",
        "uptime_seconds": round(uptime_s, 2),
        "active_twins_count": active_twins_count,
        "registered_packs_count": registered_packs_count,
        "gateway": gateway_status,
        "event_bus_ready": services is not None and getattr(services, "event_bus", None) is not None,
    }
