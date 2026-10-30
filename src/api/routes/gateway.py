"""REST API Routes for Edge Telemetry Gateway & Arduino Hardware Monitoring.

Exposes operational telemetry, physical serial port discovery, Arduino lifecycle controls,
and throughput metrics for external communication sources.
"""

from typing import Any
from fastapi import APIRouter, HTTPException, Request

from src.gateway.arduino import (
    ArduinoConfig,
    ArduinoConnectionManager,
    HardwareGatewayStatus,
    HardwarePortInfo,
    list_available_ports,
)
from src.gateway.manager import GatewayDaemonManager

router = APIRouter(prefix="/api/v1/gateway", tags=["Edge Telemetry Gateway"])


def _get_gateway_manager(request: Request) -> GatewayDaemonManager:
    """Helper to extract GatewayDaemonManager from FastAPI app state."""
    mgr = getattr(request.app.state, "gateway_manager", None)
    if mgr is None:
        services = getattr(request.app.state, "services", None)
        telemetry_svc = services.telemetry_service if services else None
        event_bus = services.event_bus if services else None
        mgr = GatewayDaemonManager(telemetry_service=telemetry_svc, event_bus=event_bus)
        request.app.state.gateway_manager = mgr
    return mgr


def _get_arduino_manager(request: Request) -> ArduinoConnectionManager:
    """Helper to extract or create ArduinoConnectionManager from FastAPI app state."""
    arduino_mgr = getattr(request.app.state, "arduino_manager", None)
    if arduino_mgr is None:
        services = getattr(request.app.state, "services", None)
        telemetry_svc = services.telemetry_service if services else None
        event_bus = services.event_bus if services else None
        arduino_mgr = ArduinoConnectionManager(telemetry_service=telemetry_svc, event_bus=event_bus)
        request.app.state.arduino_manager = arduino_mgr
    return arduino_mgr


@router.get("/status", response_model=dict[str, Any])
def get_gateway_status(request: Request) -> dict[str, Any]:
    """Returns operational status, queue depth, and source health metrics of the gateway."""
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


# --------------------------------------------------------------------------
# Physical Serial & Arduino Hardware Integration Endpoints
# --------------------------------------------------------------------------

@router.get("/serial/ports", response_model=dict[str, Any])
def get_serial_ports() -> dict[str, Any]:
    """Discovers and enumerates available physical serial COM ports on the host system."""
    ports = list_available_ports()
    return {"ports": [p.model_dump() for p in ports]}


@router.post("/arduino/connect", response_model=HardwareGatewayStatus)
async def connect_arduino_hardware(config: ArduinoConfig, request: Request) -> HardwareGatewayStatus:
    """Connects to a physical Arduino / BMS microcontroller over USB Serial."""
    mgr = _get_arduino_manager(request)
    try:
        return await mgr.connect(config)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to connect to serial port '{config.port}': {exc}",
        )


@router.post("/arduino/disconnect", response_model=HardwareGatewayStatus)
async def disconnect_arduino_hardware(request: Request) -> HardwareGatewayStatus:
    """Closes the active serial connection to Arduino hardware."""
    mgr = _get_arduino_manager(request)
    return await mgr.disconnect()


@router.get("/arduino/status", response_model=HardwareGatewayStatus)
def get_arduino_hardware_status(request: Request) -> HardwareGatewayStatus:
    """Returns real-time health, frame counts, sample rate, and latest reading from Arduino."""
    mgr = _get_arduino_manager(request)
    return mgr.get_status()


@router.get("/arduino/records", response_model=dict[str, Any])
def get_arduino_recent_records(request: Request) -> dict[str, Any]:
    """Returns a sliding buffer of recent parsed records from the physical hardware."""
    mgr = _get_arduino_manager(request)
    records = mgr.get_recent_records()
    return {"records": [r.model_dump() for r in records]}
