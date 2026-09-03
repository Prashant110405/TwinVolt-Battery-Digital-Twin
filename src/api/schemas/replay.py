"""Pydantic Transport DTOs for Drive-Cycle Replay Endpoints."""

from typing import Any, Mapping, Optional
from pydantic import BaseModel, Field


class ReplayProfileRequestDTO(BaseModel):
    """Configuration for executing a standard benchmark drive cycle replay."""

    profile_type: str = Field("WLTP", description="Standard profile ('WLTP', 'US06', 'DST', 'PULSE', 'CONSTANT_CURRENT')")
    peak_current_a: Optional[float] = Field(None, description="Peak current in Amperes")
    duration_s: Optional[float] = Field(None, gt=0.0, description="Profile duration in seconds")
    dt_s: float = Field(1.0, gt=0.0, description="Simulation time step in seconds")
    cycles: Optional[int] = Field(None, ge=1, description="Cycle repetitions for pulse or DST")
    evaluate_metrics: bool = Field(True, description="Whether to evaluate statistical tracking error metrics")
    target_voltage_rmse_v: Optional[float] = Field(None, gt=0.0)


class ReplayCSVRequestDTO(BaseModel):
    """Payload for executing a drive cycle replay from raw CSV data."""

    csv_data: str = Field(..., description="Raw CSV string or multi-line text with header")
    profile_name: str = Field("csv_replay", description="Profile label")
    evaluate_metrics: bool = Field(True)
    target_voltage_rmse_v: Optional[float] = None


class SignalMetricsDTO(BaseModel):
    """Statistical tracking error metrics for a single physical signal."""

    signal_name: str
    sample_count: int
    rmse: float
    mae: float
    max_error: float
    mean_bias_error: float
    r_squared: float
    nrmse: float


class ReplayResponseDTO(BaseModel):
    """Summary response from a completed drive-cycle replay run."""

    system_id: str
    profile_name: str
    total_samples: int
    executed_steps: int
    skipped_samples: int
    duration_seconds: float
    is_passing: bool
    anomalies_detected: int = 0
    signals: dict[str, SignalMetricsDTO] = Field(default_factory=dict)
