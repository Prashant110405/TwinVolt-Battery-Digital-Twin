"""Value Objects for the Universal Battery Domain.

Defines immutable, self-validating value objects encapsulating battery topology,
electrical limits, thermal operating windows, configurations, and identities.
"""

from dataclasses import dataclass, field
from typing import Mapping

from src.domain.battery.enums import BatteryChemistry, CellFormFactor
from src.domain.battery.validation import (
    validate_battery_identifier,
    validate_current_limits,
    validate_temperature_limits,
    validate_topology,
    validate_voltage_limits,
)
from src.domain.exceptions import (
    InvalidCellConfigurationError,
    InvalidElectricalRatingsError,
    InvalidModuleConfigurationError,
    InvalidPackConfigurationError,
)


@dataclass(frozen=True)
class BatteryIdentification:
    """Immutable identification metadata for a battery entity."""

    identifier: str
    display_name: str
    manufacturer: str = ""
    model_name: str = ""
    serial_number: str = ""
    hardware_version: str = ""
    firmware_version: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        validate_battery_identifier(self.identifier, "identifier")
        if not isinstance(self.display_name, str) or not self.display_name.strip():
            raise InvalidCellConfigurationError(
                "display_name must be a non-empty string.",
                details={"identifier": self.identifier},
            )


@dataclass(frozen=True)
class BatteryTopology:
    """Series-Parallel arrangement of cells or modules within a battery assembly."""

    series_count: int
    parallel_count: int
    total_cells: int = field(init=False)

    def __init__(self, series_count: int, parallel_count: int) -> None:
        validate_topology(series_count, parallel_count)
        object.__setattr__(self, "series_count", series_count)
        object.__setattr__(self, "parallel_count", parallel_count)
        object.__setattr__(self, "total_cells", series_count * parallel_count)

    def describe(self) -> str:
        """Returns standard notation (e.g., '3S1P', '12S2P', '1S1P')."""
        return f"{self.series_count}S{self.parallel_count}P"


@dataclass(frozen=True)
class BatteryCapacity:
    """Electrical charge and energy capacity ratings."""

    nominal_capacity_ah: float
    nominal_energy_wh: float

    def __post_init__(self) -> None:
        if not isinstance(self.nominal_capacity_ah, (int, float)) or self.nominal_capacity_ah <= 0:
            raise InvalidElectricalRatingsError(
                f"nominal_capacity_ah must be a positive number > 0, got {self.nominal_capacity_ah}.",
                details={"nominal_capacity_ah": self.nominal_capacity_ah},
            )
        if not isinstance(self.nominal_energy_wh, (int, float)) or self.nominal_energy_wh <= 0:
            raise InvalidElectricalRatingsError(
                f"nominal_energy_wh must be a positive number > 0, got {self.nominal_energy_wh}.",
                details={"nominal_energy_wh": self.nominal_energy_wh},
            )


@dataclass(frozen=True)
class ElectricalRatings:
    """Comprehensive voltage, current, and capacity boundaries for a pack or cell."""

    nominal_voltage_v: float
    min_voltage_v: float
    max_voltage_v: float
    nominal_capacity_ah: float
    nominal_energy_wh: float
    max_continuous_charge_current_a: float
    max_continuous_discharge_current_a: float
    peak_charge_current_a: float
    peak_discharge_current_a: float

    def __post_init__(self) -> None:
        validate_voltage_limits(self.min_voltage_v, self.nominal_voltage_v, self.max_voltage_v)
        validate_current_limits(
            self.max_continuous_charge_current_a,
            self.max_continuous_discharge_current_a,
            self.peak_charge_current_a,
            self.peak_discharge_current_a,
        )
        if self.nominal_capacity_ah <= 0:
            raise InvalidElectricalRatingsError(
                f"nominal_capacity_ah must be positive, got {self.nominal_capacity_ah}.",
                details={"nominal_capacity_ah": self.nominal_capacity_ah},
            )
        if self.nominal_energy_wh <= 0:
            raise InvalidElectricalRatingsError(
                f"nominal_energy_wh must be positive, got {self.nominal_energy_wh}.",
                details={"nominal_energy_wh": self.nominal_energy_wh},
            )

    @property
    def voltage_range_v(self) -> float:
        """Returns the operational voltage span ($V_{max} - V_{min}$)."""
        return self.max_voltage_v - self.min_voltage_v

    def c_rate_to_current(self, c_rate: float) -> float:
        """Converts a C-rate to equivalent current in Amperes ($I = C_{rate} \\times C_{nom}$)."""
        return c_rate * self.nominal_capacity_ah

    def current_to_c_rate(self, current_a: float) -> float:
        """Converts a current in Amperes to equivalent C-rate ($C_{rate} = I / C_{nom}$)."""
        return current_a / self.nominal_capacity_ah


@dataclass(frozen=True)
class ThermalLimits:
    """Safe thermal operating windows and critical safety thresholds in Celsius."""

    min_charge_temp_c: float
    max_charge_temp_c: float
    min_discharge_temp_c: float
    max_discharge_temp_c: float
    warning_temp_c: float
    critical_temp_c: float

    def __post_init__(self) -> None:
        validate_temperature_limits(
            self.min_charge_temp_c,
            self.max_charge_temp_c,
            self.min_discharge_temp_c,
            self.max_discharge_temp_c,
            self.warning_temp_c,
            self.critical_temp_c,
        )

    def is_within_charge_window(self, temp_c: float) -> bool:
        """Checks if a temperature is within the permissible charging window."""
        return self.min_charge_temp_c <= temp_c <= self.max_charge_temp_c

    def is_within_discharge_window(self, temp_c: float) -> bool:
        """Checks if a temperature is within the permissible discharging window."""
        return self.min_discharge_temp_c <= temp_c <= self.max_discharge_temp_c

    def is_over_temperature(self, temp_c: float) -> bool:
        """Checks if a temperature exceeds the warning threshold."""
        return temp_c >= self.warning_temp_c

    def is_critical_temperature(self, temp_c: float) -> bool:
        """Checks if a temperature breaches the critical runaway threshold."""
        return temp_c >= self.critical_temp_c


@dataclass(frozen=True)
class OperatingLimits:
    """Consolidated electrical and thermal operational boundary contracts."""

    electrical_ratings: ElectricalRatings
    thermal_limits: ThermalLimits


@dataclass(frozen=True)
class CellConfiguration:
    """Specifications and electrochemical properties of an individual cell type."""

    cell_id: str
    chemistry: BatteryChemistry
    form_factor: CellFormFactor
    nominal_voltage_v: float
    min_voltage_v: float
    max_voltage_v: float
    nominal_capacity_ah: float
    nominal_internal_resistance_mohm: float = 0.0
    mass_kg: float = 0.0

    def __post_init__(self) -> None:
        validate_battery_identifier(self.cell_id, "cell_id")
        validate_voltage_limits(self.min_voltage_v, self.nominal_voltage_v, self.max_voltage_v)
        if self.nominal_capacity_ah <= 0:
            raise InvalidCellConfigurationError(
                f"nominal_capacity_ah must be positive, got {self.nominal_capacity_ah}.",
                details={"cell_id": self.cell_id, "nominal_capacity_ah": self.nominal_capacity_ah},
            )
        if self.nominal_internal_resistance_mohm < 0:
            raise InvalidCellConfigurationError(
                f"nominal_internal_resistance_mohm cannot be negative, got {self.nominal_internal_resistance_mohm}.",
                details={"cell_id": self.cell_id, "resistance": self.nominal_internal_resistance_mohm},
            )
        if self.mass_kg < 0:
            raise InvalidCellConfigurationError(
                f"mass_kg cannot be negative, got {self.mass_kg}.",
                details={"cell_id": self.cell_id, "mass_kg": self.mass_kg},
            )


@dataclass(frozen=True)
class ModuleConfiguration:
    """Specifications and topology of an intermediate battery module."""

    module_id: str
    topology: BatteryTopology
    cell_config: CellConfiguration
    nominal_voltage_v: float
    nominal_capacity_ah: float

    def __post_init__(self) -> None:
        validate_battery_identifier(self.module_id, "module_id")
        if self.nominal_voltage_v <= 0:
            raise InvalidModuleConfigurationError(
                f"nominal_voltage_v must be positive, got {self.nominal_voltage_v}.",
                details={"module_id": self.module_id, "nominal_voltage_v": self.nominal_voltage_v},
            )
        if self.nominal_capacity_ah <= 0:
            raise InvalidModuleConfigurationError(
                f"nominal_capacity_ah must be positive, got {self.nominal_capacity_ah}.",
                details={"module_id": self.module_id, "nominal_capacity_ah": self.nominal_capacity_ah},
            )


@dataclass(frozen=True)
class PackConfiguration:
    """Specifications, topology, and operational boundaries for an assembled pack."""

    pack_id: str
    topology: BatteryTopology
    electrical_ratings: ElectricalRatings
    thermal_limits: ThermalLimits
    balancing_delta_v_threshold_mv: float = 10.0

    def __post_init__(self) -> None:
        validate_battery_identifier(self.pack_id, "pack_id")
        if self.balancing_delta_v_threshold_mv <= 0:
            raise InvalidPackConfigurationError(
                f"balancing_delta_v_threshold_mv must be positive, got {self.balancing_delta_v_threshold_mv}.",
                details={"pack_id": self.pack_id, "threshold": self.balancing_delta_v_threshold_mv},
            )
