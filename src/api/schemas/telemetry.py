"""Pydantic Transport DTOs for Telemetry Ingestion Endpoints."""

from typing import Any, Mapping, Optional, Union
from pydantic import BaseModel, Field

from src.api.schemas.twin import TwinSyncOutputResponseDTO


class TelemetryIngestRawDTO(BaseModel):
    """Payload for ingesting raw unparsed telemetry."""

    system_id: str
    raw_data: Union[str, dict[str, Any]]
    format_identifier: Optional[str] = Field("JSON", description="Format tag ('JSON', 'CSV', 'SERIAL_FRAME')")
    headers: Optional[Mapping[str, str]] = None


class TelemetrySnapshotDTO(BaseModel):
    """Canonical telemetry observation snapshot payload."""

    system_id: str
    snapshot_id: Optional[str] = None
    timestamp_ns: Optional[int] = None
    pack_voltage_v: Optional[float] = None
    pack_current_a: Optional[float] = None
    pack_power_w: Optional[float] = None
    ambient_temperature_c: Optional[float] = 25.0
    avg_cell_temperature_c: Optional[float] = None
    max_cell_temperature_c: Optional[float] = None
    soc_fraction: Optional[float] = None
    soh_fraction: Optional[float] = None


class TelemetryBatchIngestDTO(BaseModel):
    """Batch payload containing multiple sequential telemetry snapshots."""

    system_id: str
    snapshots: list[TelemetrySnapshotDTO]


class TelemetryIngestResponseDTO(BaseModel):
    """Response confirming telemetry ingestion and returning any generated twin sync output."""

    status: str = "INGESTED"
    system_id: str
    stepped_twin: bool = False
    step_output: Optional[TwinSyncOutputResponseDTO] = None
