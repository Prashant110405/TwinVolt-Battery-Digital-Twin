"""REST API Routes for Isolated Mock Telemetry Mode.

Controls the synthetic telemetry generator for hardware-independent validation.
Ensures mock data cannot overwrite physical twin state or contaminate live hardware telemetry.
"""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.services.mock_service import MockConfig, MockGeneratorStatus, MockTelemetryService

router = APIRouter(prefix="/api/v1/mock", tags=["Mock Telemetry Mode"])


def _get_mock_service(request: Request) -> MockTelemetryService:
    """Helper to extract or initialize MockTelemetryService from app state."""
    svc = getattr(request.app.state, "mock_service", None)
    if svc is None:
        services = getattr(request.app.state, "services", None)
        telemetry_svc = services.telemetry_service if services else None
        event_bus = services.event_bus if services else None
        svc = MockTelemetryService(telemetry_service=telemetry_svc, event_bus=event_bus)
        request.app.state.mock_service = svc
    return svc


@router.get("/status", response_model=MockGeneratorStatus)
def get_mock_status(request: Request) -> MockGeneratorStatus:
    """Returns the current operational status of the mock generator."""
    return _get_mock_service(request).get_status()


@router.post("/start", response_model=MockGeneratorStatus)
async def start_mock_generator(request: Request) -> MockGeneratorStatus:
    """Starts generating synthetic telemetry."""
    return await _get_mock_service(request).start()


@router.post("/stop", response_model=MockGeneratorStatus)
async def stop_mock_generator(request: Request) -> MockGeneratorStatus:
    """Halts synthetic telemetry generation."""
    return await _get_mock_service(request).stop()


@router.post("/configure", response_model=MockGeneratorStatus)
def configure_mock_generator(config: MockConfig, request: Request) -> MockGeneratorStatus:
    """Updates mock generator settings."""
    return _get_mock_service(request).configure(config)


@router.post("/reset", response_model=MockGeneratorStatus)
def reset_mock_generator(request: Request) -> MockGeneratorStatus:
    """Resets mock statistics and sample counters."""
    return _get_mock_service(request).reset()


class ErrorInjectRequest(BaseModel):
    error_type: str = "malformed_frame"


@router.post("/inject-error", response_model=dict[str, Any])
def inject_test_error(req: ErrorInjectRequest, request: Request) -> dict[str, Any]:
    """Injects a simulated invalid or malformed frame for UI/QA testing."""
    rec = _get_mock_service(request).inject_error(req.error_type)
    return {"injected_record": rec.model_dump()}


@router.get("/records", response_model=dict[str, Any])
def get_mock_recent_records(request: Request) -> dict[str, Any]:
    """Returns sliding window of recent generated records."""
    records = _get_mock_service(request).get_recent_records()
    return {"records": [r.model_dump() for r in records]}
