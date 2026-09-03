from typing import Any, Union
from fastapi import APIRouter, Depends, status

from src.api.dependencies import get_telemetry_service
from src.api.routes.twins import _serialize_sync_output
from src.api.schemas.telemetry import (
    TelemetryBatchIngestDTO,
    TelemetryIngestRawDTO,
    TelemetryIngestResponseDTO,
    TelemetrySnapshotDTO,
)
from src.services.telemetry_service import TelemetryIngestService
from src.telemetry.snapshots import TelemetrySnapshot

router = APIRouter(prefix="/api/v1/telemetry", tags=["Telemetry Ingestion"])


@router.post(
    "/ingest",
    response_model=TelemetryIngestResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Ingest Single Telemetry Frame (Raw or Canonical)",
)
async def ingest_telemetry(
    payload: Union[TelemetryIngestRawDTO, TelemetrySnapshotDTO],
    telemetry_service: TelemetryIngestService = Depends(get_telemetry_service),
) -> TelemetryIngestResponseDTO:
    """Ingests a raw CSV/JSON payload or canonical snapshot, advancing digital twin co-simulation."""
    if isinstance(payload, TelemetryIngestRawDTO):
        sync_out = telemetry_service.ingest_raw(
            system_id=payload.system_id,
            raw_payload=payload.raw_data,
            format_identifier=payload.format_identifier,
            headers=payload.headers,
        )
        return TelemetryIngestResponseDTO(
            status="INGESTED",
            system_id=payload.system_id,
            stepped_twin=True,
            step_output=_serialize_sync_output(sync_out),
        )

    # Canonical TelemetrySnapshotDTO
    snap = TelemetrySnapshot(
        snapshot_id=payload.snapshot_id or f"snap_{payload.system_id}",
        system_id=payload.system_id,
        timestamp_ns=payload.timestamp_ns,
        pack_voltage_v=payload.pack_voltage_v,
        pack_current_a=payload.pack_current_a,
        pack_power_w=payload.pack_power_w,
        ambient_temperature_c=payload.ambient_temperature_c,
        avg_cell_temperature_c=payload.avg_cell_temperature_c,
        max_cell_temperature_c=payload.max_cell_temperature_c,
        soc_fraction=payload.soc_fraction,
        soh_fraction=payload.soh_fraction,
    )
    sync_out = telemetry_service.ingest_snapshot(snap)
    return TelemetryIngestResponseDTO(
        status="INGESTED",
        system_id=payload.system_id,
        stepped_twin=sync_out is not None,
        step_output=_serialize_sync_output(sync_out) if sync_out is not None else None,
    )


@router.post(
    "/batch",
    summary="Ingest Batch of Telemetry Snapshots",
)
async def ingest_batch(
    payload: TelemetryBatchIngestDTO,
    telemetry_service: TelemetryIngestService = Depends(get_telemetry_service),
) -> dict[str, Any]:
    """Ingests an ordered batch sequence of telemetry observation snapshots."""
    snapshots = [
        TelemetrySnapshot(
            snapshot_id=s.snapshot_id or f"snap_{payload.system_id}_{idx}",
            system_id=payload.system_id,
            timestamp_ns=s.timestamp_ns,
            pack_voltage_v=s.pack_voltage_v,
            pack_current_a=s.pack_current_a,
            pack_power_w=s.pack_power_w,
            ambient_temperature_c=s.ambient_temperature_c,
            avg_cell_temperature_c=s.avg_cell_temperature_c,
            max_cell_temperature_c=s.max_cell_temperature_c,
            soc_fraction=s.soc_fraction,
            soh_fraction=s.soh_fraction,
        )
        for idx, s in enumerate(payload.snapshots)
    ]

    outs = telemetry_service.ingest_batch(payload.system_id, snapshots)
    return {
        "status": "BATCH_INGESTED",
        "system_id": payload.system_id,
        "processed_count": len(snapshots),
        "stepped_count": len(outs),
    }
