"""Pydantic Transport Data Transfer Objects (DTOs)."""

from src.api.schemas.pack import (
    BalancingConfigDTO,
    BatteryPackResponseDTO,
    BatteryProfileCreateDTO,
    CellProfileDTO,
    CurrentLimitsDTO,
    PackListResponseDTO,
    RatingsDTO,
    ThermalLimitsDTO,
    TopologyDTO,
    VoltageLimitsDTO,
)
from src.api.schemas.replay import (
    ReplayCSVRequestDTO,
    ReplayProfileRequestDTO,
    ReplayResponseDTO,
    SignalMetricsDTO,
)
from src.api.schemas.telemetry import (
    TelemetryBatchIngestDTO,
    TelemetryIngestRawDTO,
    TelemetryIngestResponseDTO,
    TelemetrySnapshotDTO,
)
from src.api.schemas.twin import (
    TwinCreateDTO,
    TwinInitializeDTO,
    TwinStateRecordResponseDTO,
    TwinStatusResponseDTO,
    TwinStepRawDTO,
    TwinStepSnapshotDTO,
    TwinSyncOutputResponseDTO,
)

__all__ = [
    # Pack DTOs
    "TopologyDTO",
    "CellProfileDTO",
    "RatingsDTO",
    "VoltageLimitsDTO",
    "CurrentLimitsDTO",
    "ThermalLimitsDTO",
    "BalancingConfigDTO",
    "BatteryProfileCreateDTO",
    "BatteryPackResponseDTO",
    "PackListResponseDTO",
    # Twin DTOs
    "TwinCreateDTO",
    "TwinInitializeDTO",
    "TwinStepSnapshotDTO",
    "TwinStepRawDTO",
    "TwinSyncOutputResponseDTO",
    "TwinStateRecordResponseDTO",
    "TwinStatusResponseDTO",
    # Telemetry DTOs
    "TelemetryIngestRawDTO",
    "TelemetrySnapshotDTO",
    "TelemetryBatchIngestDTO",
    "TelemetryIngestResponseDTO",
    # Replay DTOs
    "ReplayProfileRequestDTO",
    "ReplayCSVRequestDTO",
    "SignalMetricsDTO",
    "ReplayResponseDTO",
]
