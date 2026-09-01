"""Mathematical Core Data Types and State Space Vectors.

Defines strongly-typed, immutable value containers for state vectors (x[k]),
input vectors (u[k]), output vectors (y[k]), model metadata, and physical parameters.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional

from src.models.exceptions import (
    InvalidModelInputError,
    InvalidModelParametersError,
    InvalidModelStateError,
)

ABSOLUTE_ZERO_CELSIUS = -273.15


@dataclass(frozen=True)
class ModelMetadata:
    """Descriptive metadata and versioning for a mathematical model."""

    model_id: str
    name: str
    paradigm: str
    version: str = "1.0.0"
    description: str = ""
    author: str = "TwinVolt Engine"
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.model_id.strip():
            raise InvalidModelParametersError("model_id cannot be empty.")
        if not self.paradigm.strip():
            raise InvalidModelParametersError("paradigm cannot be empty.")

    def to_dict(self) -> dict[str, Any]:
        """Serializes metadata to dictionary."""
        return {
            "model_id": self.model_id,
            "name": self.name,
            "paradigm": self.paradigm,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "schema_version": self.schema_version,
        }


@dataclass(frozen=True)
class ModelState:
    """State vector container (x[k]) representing the internal physical state of a battery.

    All physical quantities use explicit SI units:
    - soc_fraction: Dimensionless State of Charge in range [0.0, 1.0].
    - soh_fraction: Dimensionless State of Health in range [0.0, 1.0].
    - temperature_c: Core/bulk temperature in degrees Celsius (> -273.15°C).
    - surface_temperature_c: Optional surface temperature in degrees Celsius (> -273.15°C).
    - polarization_voltages_v: Transient RC branch voltages in Volts.
    - hysteresis_voltage_v: Dynamic hysteresis overpotential in Volts.
    - custom_states: Arbitrary additional continuous states (e.g. concentration gradients).
    - timestamp_ns: Epoch nanoseconds corresponding to this state snapshot.
    """

    soc_fraction: float
    soh_fraction: float = 1.0
    temperature_c: float = 25.0
    surface_temperature_c: Optional[float] = None
    polarization_voltages_v: tuple[float, ...] = ()
    hysteresis_voltage_v: float = 0.0
    custom_states: Mapping[str, float] = field(default_factory=dict)
    timestamp_ns: Optional[int] = None

    def __post_init__(self) -> None:
        # SOC Validation
        if not isinstance(self.soc_fraction, (int, float)) or math.isnan(self.soc_fraction) or math.isinf(self.soc_fraction):
            raise InvalidModelStateError(
                f"soc_fraction must be a finite float, got {self.soc_fraction}.",
                details={"soc": self.soc_fraction},
            )
        if not (0.0 <= self.soc_fraction <= 1.0):
            raise InvalidModelStateError(
                f"soc_fraction must be in range [0.0, 1.0], got {self.soc_fraction}.",
                details={"soc": self.soc_fraction},
            )

        # SOH Validation
        if not isinstance(self.soh_fraction, (int, float)) or math.isnan(self.soh_fraction) or math.isinf(self.soh_fraction):
            raise InvalidModelStateError(
                f"soh_fraction must be a finite float, got {self.soh_fraction}.",
                details={"soh": self.soh_fraction},
            )
        if not (0.0 <= self.soh_fraction <= 1.0):
            raise InvalidModelStateError(
                f"soh_fraction must be in range [0.0, 1.0], got {self.soh_fraction}.",
                details={"soh": self.soh_fraction},
            )

        # Temperature Validation
        if not isinstance(self.temperature_c, (int, float)) or math.isnan(self.temperature_c) or math.isinf(self.temperature_c):
            raise InvalidModelStateError(
                f"temperature_c must be a finite float, got {self.temperature_c}.",
                details={"temperature_c": self.temperature_c},
            )
        if self.temperature_c <= ABSOLUTE_ZERO_CELSIUS:
            raise InvalidModelStateError(
                f"temperature_c must be above absolute zero ({ABSOLUTE_ZERO_CELSIUS}°C), got {self.temperature_c}°C.",
                details={"temperature_c": self.temperature_c},
            )

        if self.surface_temperature_c is not None:
            if not isinstance(self.surface_temperature_c, (int, float)) or math.isnan(self.surface_temperature_c) or math.isinf(self.surface_temperature_c):
                raise InvalidModelStateError(
                    f"surface_temperature_c must be a finite float, got {self.surface_temperature_c}.",
                    details={"surface_temperature_c": self.surface_temperature_c},
                )
            if self.surface_temperature_c <= ABSOLUTE_ZERO_CELSIUS:
                raise InvalidModelStateError(
                    f"surface_temperature_c must be above absolute zero ({ABSOLUTE_ZERO_CELSIUS}°C), got {self.surface_temperature_c}°C.",
                    details={"surface_temperature_c": self.surface_temperature_c},
                )

        # Polarization Voltages Validation
        for idx, v_rc in enumerate(self.polarization_voltages_v):
            if not isinstance(v_rc, (int, float)) or math.isnan(v_rc) or math.isinf(v_rc):
                raise InvalidModelStateError(
                    f"polarization_voltage[{idx}] must be a finite float, got {v_rc}.",
                    details={"index": idx, "v_rc": v_rc},
                )

        if self.timestamp_ns is not None:
            if not isinstance(self.timestamp_ns, int) or self.timestamp_ns < 0:
                raise InvalidModelStateError(
                    f"timestamp_ns must be a non-negative integer, got {self.timestamp_ns}.",
                    details={"timestamp_ns": self.timestamp_ns},
                )

    def with_updates(self, **kwargs: Any) -> "ModelState":
        """Creates a new ModelState with specified updated fields."""
        current_data = {
            "soc_fraction": self.soc_fraction,
            "soh_fraction": self.soh_fraction,
            "temperature_c": self.temperature_c,
            "surface_temperature_c": self.surface_temperature_c,
            "polarization_voltages_v": self.polarization_voltages_v,
            "hysteresis_voltage_v": self.hysteresis_voltage_v,
            "custom_states": dict(self.custom_states),
            "timestamp_ns": self.timestamp_ns,
        }
        current_data.update(kwargs)
        return ModelState(**current_data)

    def to_dict(self) -> dict[str, Any]:
        """Serializes state vector to dictionary."""
        return {
            "soc_fraction": self.soc_fraction,
            "soh_fraction": self.soh_fraction,
            "temperature_c": self.temperature_c,
            "surface_temperature_c": self.surface_temperature_c,
            "polarization_voltages_v": list(self.polarization_voltages_v),
            "hysteresis_voltage_v": self.hysteresis_voltage_v,
            "custom_states": dict(self.custom_states),
            "timestamp_ns": self.timestamp_ns,
        }


@dataclass(frozen=True)
class ModelInput:
    """Input vector container (u[k]) driving the mathematical state-space step.

    All physical quantities use explicit SI units:
    - current_a: Load/charge current in Amperes (>0 for discharge, <0 for charge, 0 for rest).
    - dt_s: Discrete time-step duration in seconds (> 0.0).
    - ambient_temperature_c: Ambient ambient environment temperature in Celsius (> -273.15°C).
    - coolant_temperature_c: Optional coolant inlet temperature in Celsius.
    - coolant_flow_rate_m3_per_s: Optional coolant volume flow rate in m³/s.
    - timestamp_ns: Epoch nanosecond timestamp of the input observation.
    - metadata: Optional supplemental input dictionary.
    """

    current_a: float
    dt_s: float
    ambient_temperature_c: float = 25.0
    coolant_temperature_c: Optional[float] = None
    coolant_flow_rate_m3_per_s: Optional[float] = None
    timestamp_ns: Optional[int] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.current_a, (int, float)) or math.isnan(self.current_a) or math.isinf(self.current_a):
            raise InvalidModelInputError(
                f"current_a must be a finite float, got {self.current_a}.",
                details={"current_a": self.current_a},
            )

        if not isinstance(self.dt_s, (int, float)) or math.isnan(self.dt_s) or math.isinf(self.dt_s):
            raise InvalidModelInputError(
                f"dt_s must be a finite float, got {self.dt_s}.",
                details={"dt_s": self.dt_s},
            )
        if self.dt_s <= 0.0:
            raise InvalidModelInputError(
                f"dt_s must be strictly positive (> 0.0 s), got {self.dt_s}.",
                details={"dt_s": self.dt_s},
            )

        if not isinstance(self.ambient_temperature_c, (int, float)) or math.isnan(self.ambient_temperature_c) or math.isinf(self.ambient_temperature_c):
            raise InvalidModelInputError(
                f"ambient_temperature_c must be a finite float, got {self.ambient_temperature_c}.",
                details={"ambient_temperature_c": self.ambient_temperature_c},
            )
        if self.ambient_temperature_c <= ABSOLUTE_ZERO_CELSIUS:
            raise InvalidModelInputError(
                f"ambient_temperature_c must be above absolute zero ({ABSOLUTE_ZERO_CELSIUS}°C), got {self.ambient_temperature_c}°C.",
                details={"ambient_temperature_c": self.ambient_temperature_c},
            )

        if self.coolant_temperature_c is not None:
            if not isinstance(self.coolant_temperature_c, (int, float)) or math.isnan(self.coolant_temperature_c) or math.isinf(self.coolant_temperature_c):
                raise InvalidModelInputError(
                    f"coolant_temperature_c must be a finite float, got {self.coolant_temperature_c}."
                )
            if self.coolant_temperature_c <= ABSOLUTE_ZERO_CELSIUS:
                raise InvalidModelInputError(
                    f"coolant_temperature_c must be above absolute zero ({ABSOLUTE_ZERO_CELSIUS}°C), got {self.coolant_temperature_c}°C."
                )

        if self.coolant_flow_rate_m3_per_s is not None:
            if not isinstance(self.coolant_flow_rate_m3_per_s, (int, float)) or self.coolant_flow_rate_m3_per_s < 0.0:
                raise InvalidModelInputError(
                    f"coolant_flow_rate_m3_per_s must be a non-negative float, got {self.coolant_flow_rate_m3_per_s}."
                )

        if self.timestamp_ns is not None:
            if not isinstance(self.timestamp_ns, int) or self.timestamp_ns < 0:
                raise InvalidModelInputError(
                    f"timestamp_ns must be a non-negative integer, got {self.timestamp_ns}."
                )

    def to_dict(self) -> dict[str, Any]:
        """Serializes input vector to dictionary."""
        return {
            "current_a": self.current_a,
            "dt_s": self.dt_s,
            "ambient_temperature_c": self.ambient_temperature_c,
            "coolant_temperature_c": self.coolant_temperature_c,
            "coolant_flow_rate_m3_per_s": self.coolant_flow_rate_m3_per_s,
            "timestamp_ns": self.timestamp_ns,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ModelOutput:
    """Output vector container (y[k]) computed from state and input vectors.

    All physical quantities use explicit SI units:
    - terminal_voltage_v: Predicted terminal voltage across the cell/pack terminals in Volts.
    - open_circuit_voltage_v: Internal equilibrium open-circuit voltage $V_{oc}(SOC, T)$ in Volts.
    - state: The updated ModelState vector $x[k+1]$ resulting from this evaluation.
    - heat_generation_w: Total thermal dissipation rate (Joule + entropic) in Watts ($\ge 0.0$).
    - internal_resistance_mohm: Equivalent instantaneous DC series resistance in m$\Omega$ ($\ge 0.0$).
    - derivatives: Optional instantaneous state derivative estimates ($\dot{x}$).
    - metadata: Optional computational diagnostics (solver iterations, residual error).
    """

    terminal_voltage_v: float
    open_circuit_voltage_v: float
    state: ModelState
    heat_generation_w: float = 0.0
    internal_resistance_mohm: float = 0.0
    derivatives: Mapping[str, float] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.terminal_voltage_v, (int, float)) or math.isnan(self.terminal_voltage_v) or math.isinf(self.terminal_voltage_v):
            raise InvalidModelParametersError(
                f"terminal_voltage_v must be a finite float, got {self.terminal_voltage_v}."
            )
        if not isinstance(self.open_circuit_voltage_v, (int, float)) or math.isnan(self.open_circuit_voltage_v) or math.isinf(self.open_circuit_voltage_v):
            raise InvalidModelParametersError(
                f"open_circuit_voltage_v must be a finite float, got {self.open_circuit_voltage_v}."
            )
        if self.heat_generation_w < 0.0 or math.isnan(self.heat_generation_w) or math.isinf(self.heat_generation_w):
            raise InvalidModelParametersError(
                f"heat_generation_w must be a non-negative finite float, got {self.heat_generation_w}."
            )
        if self.internal_resistance_mohm < 0.0 or math.isnan(self.internal_resistance_mohm) or math.isinf(self.internal_resistance_mohm):
            raise InvalidModelParametersError(
                f"internal_resistance_mohm must be a non-negative finite float, got {self.internal_resistance_mohm}."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serializes output vector to dictionary."""
        return {
            "terminal_voltage_v": self.terminal_voltage_v,
            "open_circuit_voltage_v": self.open_circuit_voltage_v,
            "state": self.state.to_dict(),
            "heat_generation_w": self.heat_generation_w,
            "internal_resistance_mohm": self.internal_resistance_mohm,
            "derivatives": dict(self.derivatives),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ModelParameters:
    """Generic base parameter container for mathematical battery models.

    All physical parameters use explicit SI units:
    - nominal_capacity_ah: Nominal charge capacity in Ampere-hours ($> 0.0$).
    - nominal_voltage_v: Nominal cell/pack voltage in Volts ($> 0.0$).
    - cell_mass_kg: Cell mass in kilograms ($> 0.0$).
    - specific_heat_capacity_j_per_kg_k: Specific heat capacity ($C_p$) in J/(kg·K) ($> 0.0$).
    - convective_heat_transfer_w_per_k: Convective cooling coefficient ($hA$) in W/K ($\ge 0.0$).
    - custom_parameters: Subclass-specific mathematical parameters (e.g. $R_0, R_1, C_1$).
    """

    nominal_capacity_ah: float
    nominal_voltage_v: float
    cell_mass_kg: float = 0.045
    specific_heat_capacity_j_per_kg_k: float = 1000.0
    convective_heat_transfer_w_per_k: float = 1.0
    custom_parameters: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.nominal_capacity_ah <= 0.0 or math.isnan(self.nominal_capacity_ah) or math.isinf(self.nominal_capacity_ah):
            raise InvalidModelParametersError(
                f"nominal_capacity_ah must be positive, got {self.nominal_capacity_ah}."
            )
        if self.nominal_voltage_v <= 0.0 or math.isnan(self.nominal_voltage_v) or math.isinf(self.nominal_voltage_v):
            raise InvalidModelParametersError(
                f"nominal_voltage_v must be positive, got {self.nominal_voltage_v}."
            )
        if self.cell_mass_kg <= 0.0 or math.isnan(self.cell_mass_kg) or math.isinf(self.cell_mass_kg):
            raise InvalidModelParametersError(
                f"cell_mass_kg must be positive, got {self.cell_mass_kg}."
            )
        if self.specific_heat_capacity_j_per_kg_k <= 0.0 or math.isnan(self.specific_heat_capacity_j_per_kg_k) or math.isinf(self.specific_heat_capacity_j_per_kg_k):
            raise InvalidModelParametersError(
                f"specific_heat_capacity_j_per_kg_k must be positive, got {self.specific_heat_capacity_j_per_kg_k}."
            )
        if self.convective_heat_transfer_w_per_k < 0.0 or math.isnan(self.convective_heat_transfer_w_per_k) or math.isinf(self.convective_heat_transfer_w_per_k):
            raise InvalidModelParametersError(
                f"convective_heat_transfer_w_per_k must be non-negative, got {self.convective_heat_transfer_w_per_k}."
            )

    @property
    def thermal_mass_j_per_k(self) -> float:
        """Computed lumped thermal capacitance $C_{th} = m \cdot C_p$ in J/K."""
        return self.cell_mass_kg * self.specific_heat_capacity_j_per_kg_k

    def to_dict(self) -> dict[str, Any]:
        """Serializes parameters to dictionary."""
        return {
            "nominal_capacity_ah": self.nominal_capacity_ah,
            "nominal_voltage_v": self.nominal_voltage_v,
            "cell_mass_kg": self.cell_mass_kg,
            "specific_heat_capacity_j_per_kg_k": self.specific_heat_capacity_j_per_kg_k,
            "convective_heat_transfer_w_per_k": self.convective_heat_transfer_w_per_k,
            "thermal_mass_j_per_k": self.thermal_mass_j_per_k,
            "custom_parameters": dict(self.custom_parameters),
        }
