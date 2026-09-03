"""Pydantic Transport DTOs for Battery Pack Endpoints."""

from typing import Any, Mapping, Optional
from pydantic import BaseModel, Field


class TopologyDTO(BaseModel):
    series_count: int = Field(..., ge=1, description="Number of cells in series")
    parallel_count: int = Field(..., ge=1, description="Number of strings in parallel")
    total_cells: Optional[int] = Field(None, ge=1)


class CellProfileDTO(BaseModel):
    cell_id: str
    chemistry: str
    form_factor: str
    nominal_voltage_v: float = Field(..., gt=0.0)
    min_voltage_v: float = Field(..., gt=0.0)
    max_voltage_v: float = Field(..., gt=0.0)
    nominal_capacity_ah: float = Field(..., gt=0.0)
    nominal_internal_resistance_mohm: float = Field(0.0, ge=0.0)
    mass_kg: float = Field(0.0, ge=0.0)


class RatingsDTO(BaseModel):
    nominal_pack_voltage_v: float = Field(..., gt=0.0)
    nominal_cell_voltage_v: float = Field(..., gt=0.0)
    nominal_capacity_ah: float = Field(..., gt=0.0)
    nominal_energy_wh: float = Field(..., gt=0.0)


class VoltageLimitsDTO(BaseModel):
    cell_min_cutoff_v: float = Field(..., gt=0.0)
    cell_max_cutoff_v: float = Field(..., gt=0.0)
    pack_min_cutoff_v: float = Field(..., gt=0.0)
    pack_max_cutoff_v: float = Field(..., gt=0.0)


class CurrentLimitsDTO(BaseModel):
    max_continuous_charge_a: float = Field(..., ge=0.0)
    max_continuous_discharge_a: float = Field(..., ge=0.0)
    peak_pulse_discharge_a: float = Field(..., ge=0.0)
    peak_pulse_charge_a: Optional[float] = None


class ThermalLimitsDTO(BaseModel):
    min_charge_temp_c: float
    max_charge_temp_c: float
    min_discharge_temp_c: float
    max_discharge_temp_c: float
    thermal_warning_temp_c: float
    critical_thermal_runaway_temp_c: float = 80.0


class BalancingConfigDTO(BaseModel):
    balancing_delta_v_threshold_mv: float = 10.0
    balancing_enabled: bool = True


class BatteryProfileCreateDTO(BaseModel):
    """Declarative battery profile payload for registering a new pack."""

    schema_version: str = "1.0"
    profile_id: str
    display_name: str
    manufacturer: str = ""
    model_name: str = ""
    chemistry: str
    topology: TopologyDTO
    cell_profile: CellProfileDTO
    ratings: RatingsDTO
    voltage_limits: VoltageLimitsDTO
    current_limits: CurrentLimitsDTO
    thermal_limits: ThermalLimitsDTO
    balancing: BalancingConfigDTO = Field(default_factory=BalancingConfigDTO)
    metadata: Mapping[str, Any] = Field(default_factory=dict)


class BatteryPackResponseDTO(BaseModel):
    """Structured response model representing a registered BatteryPack."""

    pack_id: str
    display_name: str
    manufacturer: str
    chemistry: str
    series_count: int
    parallel_count: int
    total_cell_count: int
    total_module_count: int
    nominal_voltage_v: float
    nominal_capacity_ah: float
    nominal_energy_wh: float
    min_pack_voltage_v: float
    max_pack_voltage_v: float


class PackListResponseDTO(BaseModel):
    """Collection response containing multiple battery packs."""

    packs: list[BatteryPackResponseDTO]
    total_count: int
