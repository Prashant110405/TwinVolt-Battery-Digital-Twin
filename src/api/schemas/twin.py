"""Pydantic Transport DTOs for Digital Twin Endpoints."""

from typing import Any, Mapping, Optional, Union
from pydantic import BaseModel, Field


class TwinCreateDTO(BaseModel):
    """Payload for assembling and registering a new Digital Twin instance."""

    system_id: str = Field(..., description="Unique digital twin system identifier")
    pack_id: str = Field(..., description="Identifier of an already registered BatteryPack")
    model_type: str = Field("ECM", description="Model paradigm ('ECM', 'PACK', 'PHYSICS')")
    estimator_type: Optional[str] = Field("EKF", description="Estimator type ('EKF', 'COULOMB_COUNTER', None)")
    default_dt_s: float = Field(1.0, gt=0.0, description="Default discrete simulation time step in seconds")
    initial_soc: float = Field(1.0, ge=0.0, le=1.0, description="Initial State of Charge fraction")
    initial_soh: float = Field(1.0, ge=0.0, le=1.0, description="Initial State of Health fraction")
    initial_temperature_c: float = Field(25.0, description="Initial battery temperature in Celsius")
    auto_initialize: bool = Field(True, description="Whether to automatically initialize upon creation")
    series_resistance_r0_ohm: Optional[float] = Field(None, ge=0.0)
    r1_ohm: Optional[float] = Field(None, ge=0.0)
    c1_farad: Optional[float] = Field(None, ge=0.0)


class TwinInitializeDTO(BaseModel):
    """Payload for initializing or re-initializing an active Digital Twin instance."""

    initial_soc: float = Field(1.0, ge=0.0, le=1.0)
    initial_soh: float = Field(1.0, ge=0.0, le=1.0)
    temperature_c: float = Field(25.0)


class TwinStepSnapshotDTO(BaseModel):
    """Observation payload for executing a discrete co-simulation step with canonical telemetry."""

    pack_voltage_v: Optional[float] = Field(None, gt=0.0)
    pack_current_a: Optional[float] = Field(None, description="Current in A (>0 discharge, <0 charge)")
    pack_power_w: Optional[float] = None
    ambient_temperature_c: Optional[float] = Field(25.0)
    avg_cell_temperature_c: Optional[float] = None
    max_cell_temperature_c: Optional[float] = None
    soc_fraction: Optional[float] = Field(None, ge=0.0, le=1.0)
    timestamp_ns: Optional[int] = Field(None, description="Sample epoch timestamp in nanoseconds")
    sequence_number: Optional[int] = None


class TwinStepRawDTO(BaseModel):
    """Observation payload for executing a step with raw unparsed text or JSON data."""

    raw_data: Union[str, dict[str, Any]] = Field(..., description="Raw CSV string, JSON string, or dict")
    format_identifier: Optional[str] = Field("CSV", description="Format tag ('CSV', 'JSON', 'SERIAL_FRAME')")
    headers: Optional[Mapping[str, str]] = None


class TwinSyncOutputResponseDTO(BaseModel):
    """Structured response from a single discrete digital twin co-simulation step."""

    step_index: int
    timestamp_ns: int
    dt_s: float
    terminal_voltage_v: float
    simulated_soc: float
    estimated_soc: Optional[float] = None
    temperature_c: float
    voltage_residual_v: Optional[float] = None
    temperature_residual_c: Optional[float] = None
    anomalies_count: int = 0
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class TwinStateRecordResponseDTO(BaseModel):
    """Historical persisted digital twin state record."""

    record_id: str
    system_id: str
    timestamp_ns: int
    soc_fraction: float
    temperature_c: float
    terminal_voltage_v: Optional[float] = None
    estimated_soc: Optional[float] = None
    residuals: dict[str, float] = Field(default_factory=dict)


class TwinStatusResponseDTO(BaseModel):
    """Status overview of an active Digital Twin instance."""

    system_id: str
    pack_id: str
    is_initialized: bool
    total_steps: int
    total_anomalies: int
    current_soc: Optional[float] = None
    current_voltage_v: Optional[float] = None
    current_temperature_c: Optional[float] = None
    model_name: str
