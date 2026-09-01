"""Battery Profile Schemas for Declarative Configuration.

Defines strongly-typed, versioned declarative schemas for battery packs,
cells, electrical ratings, thermal limits, and their conversion into pure domain entities.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional

from src.domain.battery.entities import BatteryPack
from src.domain.battery.enums import BatteryChemistry, CellFormFactor
from src.domain.battery.validation import (
    ABSOLUTE_ZERO_CELSIUS,
    validate_battery_identifier,
)
from src.domain.battery.value_objects import (
    BatteryIdentification,
    BatteryTopology,
    CellConfiguration,
    ElectricalRatings,
    PackConfiguration,
    ThermalLimits,
)
from src.schemas.exceptions import (
    ConfigurationValidationError,
    InvalidBatteryProfileError,
    SchemaVersionMismatchError,
)

SUPPORTED_SCHEMA_VERSIONS = {"1.0", "1.0.0"}


@dataclass(frozen=True)
class TopologySchema:
    """Declarative topology schema."""

    series_count: int
    parallel_count: int
    total_cells: Optional[int] = None

    def __post_init__(self) -> None:
        if not isinstance(self.series_count, int) or self.series_count < 1:
            raise ConfigurationValidationError(
                f"series_count must be an integer >= 1, got {self.series_count}.",
                details={"series_count": self.series_count},
            )
        if not isinstance(self.parallel_count, int) or self.parallel_count < 1:
            raise ConfigurationValidationError(
                f"parallel_count must be an integer >= 1, got {self.parallel_count}.",
                details={"parallel_count": self.parallel_count},
            )
        expected_total = self.series_count * self.parallel_count
        if self.total_cells is not None and self.total_cells != expected_total:
            raise ConfigurationValidationError(
                f"total_cells ({self.total_cells}) does not match series_count * parallel_count ({expected_total}).",
                details={
                    "series_count": self.series_count,
                    "parallel_count": self.parallel_count,
                    "total_cells": self.total_cells,
                },
            )

    @property
    def computed_total_cells(self) -> int:
        """Returns the verified total cell count."""
        return self.series_count * self.parallel_count

    def to_dict(self) -> dict[str, Any]:
        """Serializes topology schema to dictionary."""
        return {
            "series_count": self.series_count,
            "parallel_count": self.parallel_count,
            "total_cells": self.computed_total_cells,
        }


@dataclass(frozen=True)
class CellProfileSchema:
    """Declarative cell configuration schema."""

    cell_id: str
    chemistry: str
    form_factor: str
    nominal_voltage_v: float
    min_voltage_v: float
    max_voltage_v: float
    nominal_capacity_ah: float
    nominal_internal_resistance_mohm: float = 0.0
    mass_kg: float = 0.0

    def __post_init__(self) -> None:
        validate_battery_identifier(self.cell_id, "cell_id")
        try:
            BatteryChemistry(self.chemistry.upper())
        except ValueError:
            raise ConfigurationValidationError(
                f"Unknown chemistry '{self.chemistry}'. Supported: {[c.value for c in BatteryChemistry]}.",
                details={"chemistry": self.chemistry},
            )

        try:
            CellFormFactor(self.form_factor.upper())
        except ValueError:
            raise ConfigurationValidationError(
                f"Unknown form_factor '{self.form_factor}'. Supported: {[f.value for f in CellFormFactor]}.",
                details={"form_factor": self.form_factor},
            )

        if not (0 < self.min_voltage_v <= self.nominal_voltage_v <= self.max_voltage_v):
            raise ConfigurationValidationError(
                f"Cell voltages must satisfy 0 < min ({self.min_voltage_v}V) <= nom ({self.nominal_voltage_v}V) <= max ({self.max_voltage_v}V).",
                details={
                    "min_voltage_v": self.min_voltage_v,
                    "nominal_voltage_v": self.nominal_voltage_v,
                    "max_voltage_v": self.max_voltage_v,
                },
            )

        if self.nominal_capacity_ah <= 0:
            raise ConfigurationValidationError(
                f"nominal_capacity_ah must be positive > 0, got {self.nominal_capacity_ah}.",
                details={"nominal_capacity_ah": self.nominal_capacity_ah},
            )

    def to_domain_cell_config(self) -> CellConfiguration:
        """Converts to domain CellConfiguration object."""
        return CellConfiguration(
            cell_id=self.cell_id,
            chemistry=BatteryChemistry(self.chemistry.upper()),
            form_factor=CellFormFactor(self.form_factor.upper()),
            nominal_voltage_v=self.nominal_voltage_v,
            min_voltage_v=self.min_voltage_v,
            max_voltage_v=self.max_voltage_v,
            nominal_capacity_ah=self.nominal_capacity_ah,
            nominal_internal_resistance_mohm=self.nominal_internal_resistance_mohm,
            mass_kg=self.mass_kg,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializes cell profile schema to dictionary."""
        return {
            "cell_id": self.cell_id,
            "chemistry": self.chemistry.upper(),
            "form_factor": self.form_factor.upper(),
            "nominal_voltage_v": self.nominal_voltage_v,
            "min_voltage_v": self.min_voltage_v,
            "max_voltage_v": self.max_voltage_v,
            "nominal_capacity_ah": self.nominal_capacity_ah,
            "nominal_internal_resistance_mohm": self.nominal_internal_resistance_mohm,
            "mass_kg": self.mass_kg,
        }


@dataclass(frozen=True)
class RatingsSchema:
    """Declarative electrical ratings schema."""

    nominal_pack_voltage_v: float
    nominal_cell_voltage_v: float
    nominal_capacity_ah: float
    nominal_energy_wh: float

    def __post_init__(self) -> None:
        for field_name, val in [
            ("nominal_pack_voltage_v", self.nominal_pack_voltage_v),
            ("nominal_cell_voltage_v", self.nominal_cell_voltage_v),
            ("nominal_capacity_ah", self.nominal_capacity_ah),
            ("nominal_energy_wh", self.nominal_energy_wh),
        ]:
            if not isinstance(val, (int, float)) or val <= 0:
                raise ConfigurationValidationError(
                    f"{field_name} must be a positive number > 0, got {val}.",
                    details={"field": field_name, "value": val},
                )

    def to_dict(self) -> dict[str, Any]:
        """Serializes ratings schema to dictionary."""
        return {
            "nominal_pack_voltage_v": self.nominal_pack_voltage_v,
            "nominal_cell_voltage_v": self.nominal_cell_voltage_v,
            "nominal_capacity_ah": self.nominal_capacity_ah,
            "nominal_energy_wh": self.nominal_energy_wh,
        }


@dataclass(frozen=True)
class VoltageLimitsSchema:
    """Declarative voltage boundaries schema."""

    cell_min_cutoff_v: float
    cell_max_cutoff_v: float
    pack_min_cutoff_v: float
    pack_max_cutoff_v: float

    def __post_init__(self) -> None:
        if not (0 < self.cell_min_cutoff_v < self.cell_max_cutoff_v):
            raise ConfigurationValidationError(
                f"Cell cutoff voltages invalid: min ({self.cell_min_cutoff_v}V) must be < max ({self.cell_max_cutoff_v}V).",
                details={"min": self.cell_min_cutoff_v, "max": self.cell_max_cutoff_v},
            )
        if not (0 < self.pack_min_cutoff_v < self.pack_max_cutoff_v):
            raise ConfigurationValidationError(
                f"Pack cutoff voltages invalid: min ({self.pack_min_cutoff_v}V) must be < max ({self.pack_max_cutoff_v}V).",
                details={"min": self.pack_min_cutoff_v, "max": self.pack_max_cutoff_v},
            )

    def to_dict(self) -> dict[str, Any]:
        """Serializes voltage limits schema to dictionary."""
        return {
            "cell_min_cutoff_v": self.cell_min_cutoff_v,
            "cell_max_cutoff_v": self.cell_max_cutoff_v,
            "pack_min_cutoff_v": self.pack_min_cutoff_v,
            "pack_max_cutoff_v": self.pack_max_cutoff_v,
        }


@dataclass(frozen=True)
class CurrentLimitsSchema:
    """Declarative current limits schema."""

    max_continuous_charge_a: float
    max_continuous_discharge_a: float
    peak_pulse_discharge_a: float
    peak_pulse_charge_a: Optional[float] = None

    def __post_init__(self) -> None:
        if self.max_continuous_charge_a <= 0 or self.max_continuous_discharge_a <= 0:
            raise ConfigurationValidationError(
                "Continuous current limits must be positive > 0.",
                details={
                    "max_continuous_charge_a": self.max_continuous_charge_a,
                    "max_continuous_discharge_a": self.max_continuous_discharge_a,
                },
            )
        if self.peak_pulse_discharge_a < self.max_continuous_discharge_a:
            raise ConfigurationValidationError(
                f"peak_pulse_discharge_a ({self.peak_pulse_discharge_a}A) cannot be less than continuous ({self.max_continuous_discharge_a}A).",
                details={"peak": self.peak_pulse_discharge_a, "continuous": self.max_continuous_discharge_a},
            )
        if self.peak_pulse_charge_a is not None and self.peak_pulse_charge_a < self.max_continuous_charge_a:
            raise ConfigurationValidationError(
                f"peak_pulse_charge_a ({self.peak_pulse_charge_a}A) cannot be less than continuous ({self.max_continuous_charge_a}A).",
                details={"peak": self.peak_pulse_charge_a, "continuous": self.max_continuous_charge_a},
            )

    @property
    def resolved_peak_charge_a(self) -> float:
        """Returns peak charge current, defaulting to continuous charge if unspecified."""
        return (
            self.peak_pulse_charge_a
            if self.peak_pulse_charge_a is not None
            else self.max_continuous_charge_a
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializes current limits schema to dictionary."""
        return {
            "max_continuous_charge_a": self.max_continuous_charge_a,
            "max_continuous_discharge_a": self.max_continuous_discharge_a,
            "peak_pulse_charge_a": self.resolved_peak_charge_a,
            "peak_pulse_discharge_a": self.peak_pulse_discharge_a,
        }


@dataclass(frozen=True)
class ThermalLimitsSchema:
    """Declarative thermal boundaries schema."""

    min_charge_temp_c: float
    max_charge_temp_c: float
    min_discharge_temp_c: float
    max_discharge_temp_c: float
    thermal_warning_temp_c: float
    critical_thermal_runaway_temp_c: float = 80.0

    def __post_init__(self) -> None:
        temps = [
            self.min_charge_temp_c,
            self.max_charge_temp_c,
            self.min_discharge_temp_c,
            self.max_discharge_temp_c,
            self.thermal_warning_temp_c,
            self.critical_thermal_runaway_temp_c,
        ]
        if any(t <= ABSOLUTE_ZERO_CELSIUS for t in temps):
            raise ConfigurationValidationError(
                f"Temperatures must be above absolute zero ({ABSOLUTE_ZERO_CELSIUS}°C).",
                details={"temperatures": temps},
            )
        if not (self.min_charge_temp_c < self.max_charge_temp_c):
            raise ConfigurationValidationError(
                f"min_charge_temp_c ({self.min_charge_temp_c}°C) must be < max_charge_temp_c ({self.max_charge_temp_c}°C)."
            )
        if not (self.min_discharge_temp_c < self.max_discharge_temp_c):
            raise ConfigurationValidationError(
                f"min_discharge_temp_c ({self.min_discharge_temp_c}°C) must be < max_discharge_temp_c ({self.max_discharge_temp_c}°C)."
            )
        if self.thermal_warning_temp_c < self.max_discharge_temp_c:
            raise ConfigurationValidationError(
                f"thermal_warning_temp_c ({self.thermal_warning_temp_c}°C) cannot be less than max_discharge_temp_c ({self.max_discharge_temp_c}°C)."
            )
        if self.thermal_warning_temp_c >= self.critical_thermal_runaway_temp_c:
            raise ConfigurationValidationError(
                f"thermal_warning_temp_c ({self.thermal_warning_temp_c}°C) must be < critical ({self.critical_thermal_runaway_temp_c}°C)."
            )

    def to_domain_thermal_limits(self) -> ThermalLimits:
        """Converts to domain ThermalLimits object."""
        return ThermalLimits(
            min_charge_temp_c=self.min_charge_temp_c,
            max_charge_temp_c=self.max_charge_temp_c,
            min_discharge_temp_c=self.min_discharge_temp_c,
            max_discharge_temp_c=self.max_discharge_temp_c,
            warning_temp_c=self.thermal_warning_temp_c,
            critical_temp_c=self.critical_thermal_runaway_temp_c,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializes thermal limits schema to dictionary."""
        return {
            "min_charge_temp_c": self.min_charge_temp_c,
            "max_charge_temp_c": self.max_charge_temp_c,
            "min_discharge_temp_c": self.min_discharge_temp_c,
            "max_discharge_temp_c": self.max_discharge_temp_c,
            "thermal_warning_temp_c": self.thermal_warning_temp_c,
            "critical_thermal_runaway_temp_c": self.critical_thermal_runaway_temp_c,
        }


@dataclass(frozen=True)
class BalancingConfigSchema:
    """Declarative cell balancing schema."""

    balancing_delta_v_threshold_mv: float = 10.0
    balancing_enabled: bool = True

    def __post_init__(self) -> None:
        if self.balancing_delta_v_threshold_mv <= 0:
            raise ConfigurationValidationError(
                f"balancing_delta_v_threshold_mv must be > 0, got {self.balancing_delta_v_threshold_mv}.",
                details={"threshold": self.balancing_delta_v_threshold_mv},
            )

    def to_dict(self) -> dict[str, Any]:
        """Serializes balancing schema to dictionary."""
        return {
            "balancing_delta_v_threshold_mv": self.balancing_delta_v_threshold_mv,
            "balancing_enabled": self.balancing_enabled,
        }


@dataclass(frozen=True)
class BatteryProfileSchema:
    """Master declarative battery profile schema matching the TwinVolt configuration contract."""

    profile_id: str
    display_name: str
    chemistry: str
    topology: TopologySchema
    cell_profile: CellProfileSchema
    ratings: RatingsSchema
    voltage_limits: VoltageLimitsSchema
    current_limits: CurrentLimitsSchema
    thermal_limits: ThermalLimitsSchema
    schema_version: str = "1.0"
    manufacturer: str = ""
    model_name: str = ""
    balancing: BalancingConfigSchema = field(default_factory=BalancingConfigSchema)
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise SchemaVersionMismatchError(
                f"Unsupported schema_version '{self.schema_version}'. Supported versions: {sorted(SUPPORTED_SCHEMA_VERSIONS)}.",
                details={"schema_version": self.schema_version},
            )

        validate_battery_identifier(self.profile_id, "profile_id")
        if not self.display_name.strip():
            raise ConfigurationValidationError("display_name cannot be empty.")

        # Cross-validation: Topology and Voltage consistency
        expected_nom_voltage = self.topology.series_count * self.ratings.nominal_cell_voltage_v
        if not math.isclose(self.ratings.nominal_pack_voltage_v, expected_nom_voltage, rel_tol=0.08):
            raise InvalidBatteryProfileError(
                f"Pack nominal voltage ({self.ratings.nominal_pack_voltage_v}V) is inconsistent with "
                f"series_count ({self.topology.series_count}) * cell nominal ({self.ratings.nominal_cell_voltage_v}V = {expected_nom_voltage}V).",
                details={
                    "pack_nominal_v": self.ratings.nominal_pack_voltage_v,
                    "expected_nominal_v": expected_nom_voltage,
                },
            )

    def to_domain_pack(self) -> BatteryPack:
        """Materializes this declarative profile into a verified BatteryPack domain object."""
        cell_cfg = self.cell_profile.to_domain_cell_config()
        domain_topology = BatteryTopology(
            series_count=self.topology.series_count,
            parallel_count=self.topology.parallel_count,
        )
        domain_ratings = ElectricalRatings(
            nominal_voltage_v=self.ratings.nominal_pack_voltage_v,
            min_voltage_v=self.voltage_limits.pack_min_cutoff_v,
            max_voltage_v=self.voltage_limits.pack_max_cutoff_v,
            nominal_capacity_ah=self.ratings.nominal_capacity_ah,
            nominal_energy_wh=self.ratings.nominal_energy_wh,
            max_continuous_charge_current_a=self.current_limits.max_continuous_charge_a,
            max_continuous_discharge_current_a=self.current_limits.max_continuous_discharge_a,
            peak_charge_current_a=self.current_limits.resolved_peak_charge_a,
            peak_discharge_current_a=self.current_limits.peak_pulse_discharge_a,
        )
        domain_thermal = self.thermal_limits.to_domain_thermal_limits()
        pack_cfg = PackConfiguration(
            pack_id=self.profile_id,
            topology=domain_topology,
            electrical_ratings=domain_ratings,
            thermal_limits=domain_thermal,
            balancing_delta_v_threshold_mv=self.balancing.balancing_delta_v_threshold_mv,
        )
        ident = BatteryIdentification(
            identifier=self.profile_id,
            display_name=self.display_name,
            manufacturer=self.manufacturer,
            model_name=self.model_name,
            metadata=dict(self.metadata),
        )
        return BatteryPack.create_monolithic_pack(
            identification=ident,
            configuration=pack_cfg,
            cell_config=cell_cfg,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializes battery profile to deterministic dictionary."""
        return {
            "schema_version": self.schema_version,
            "battery_profile": {
                "profile_id": self.profile_id,
                "display_name": self.display_name,
                "manufacturer": self.manufacturer,
                "model_name": self.model_name,
                "chemistry": self.chemistry,
                "topology": self.topology.to_dict(),
                "cell_profile": self.cell_profile.to_dict(),
                "ratings": self.ratings.to_dict(),
                "voltage_limits": self.voltage_limits.to_dict(),
                "current_limits": self.current_limits.to_dict(),
                "thermal_limits": self.thermal_limits.to_dict(),
                "balancing": self.balancing.to_dict(),
                "metadata": dict(self.metadata),
            },
        }
