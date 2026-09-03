"""REST API Routes for Edge Telemetry Gateway Monitoring.

Exposes read-only operational telemetry, connection states, and throughput metrics
for external communication daemon sources.
"""

from typing import Any
from fastapi import APIRouter, HTTPException, Request

from src.gateway.manager import GatewayDaemonManager

router = APIRouter(prefix="/api/v1/gateway", tags=["Edge Telemetry Gateway"])


def _get_gateway_manager(request: Request) -> GatewayDaemonManager:
    """Helper to extract GatewayDaemonManager from FastAPI app state."""
    mgr = getattr(request.app.state, "gateway_manager", None)
    if mgr is None:
        # Create lightweight instance if not pre-attached
        services = getattr(request.app.state, "services", None)
        telemetry_svc = services.telemetry_service if services else None
        event_bus = services.event_bus if services else None
        mgr = GatewayDaemonManager(telemetry_service=telemetry_svc, event_bus=event_bus)
        request.app.state.gateway_manager = mgr
    return mgr


@router.get("/status", response_model=dict[str, Any])
def get_gateway_status(request: Request) -> dict[str, Any]:
    """Returns the operational status, queue depth, and source health metrics of the gateway."""
    manager = _get_gateway_manager(request)
    return manager.get_status()


@router.get("/sources", response_model=dict[str, Any])
def get_gateway_sources(request: Request) -> dict[str, Any]:
    """Returns status metrics for all registered external communication sources."""
    manager = _get_gateway_manager(request)
    status = manager.get_status()
    return {"sources": status.get("sources", {})}


@router.get("/sources/{source_id}", response_model=dict[str, Any])
def get_gateway_source_detail(request: Request, source_id: str) -> dict[str, Any]:
    """Returns detailed status metrics for a specific external communication source."""
    manager = _get_gateway_manager(request)
    source = manager.get_source(source_id)
    if source is None:
        raise HTTPException(
            status_code=404,
            detail=f"Gateway source '{source_id}' not found.",
        )
    return source.get_status().to_dict()
