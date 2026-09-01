"""Model Configuration Schemas for Battery Simulation.

Defines strongly-typed declarative schemas for equivalent circuit models (ECM 1-RC/2-RC),
physics model parameters, solver time steps, and thermal parameters.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping

from src.domain.battery.validation import validate_battery_identifier
from src.schemas.exceptions import (
    ConfigurationValidationError,
    InvalidModelConfigurationError,
    SchemaVersionMismatchError,
)

SUPPORTED_MODEL_PARADIGMS = {
    "ECM_1RC",
    "ECM_2RC",
    "PHYSICS_PYBAMM_DFN",
    "PHYSICS_PYBAMM_SPM",
    "DATA_DRIVEN_NEURAL",
    "LOOKUP_TABLE",
}

SUPPORTED_SCHEMA_VERSIONS = {"1.0", "1.0.0"}


@dataclass(frozen=True)
class SamplingConfigSchema:
    """Simulation time-step and ODE solver configuration."""

    simulation_step_ms: int = 100
    solver_type: str = "explicit_rk4"

    def __post_init__(self) -> None:
        if not isinstance(self.simulation_step_ms, int) or self.simulation_step_ms <= 0:
            raise ConfigurationValidationError(
                f"simulation_step_ms must be an integer > 0, got {self.simulation_step_ms}.",
                details={"simulation_step_ms": self.simulation_step_ms},
            )
        if not self.solver_type.strip():
            raise ConfigurationValidationError("solver_type cannot be empty.")

    def to_dict(self) -> dict[str, Any]:
        """Serializes sampling config schema to dictionary."""
        return {
            "simulation_step_ms": self.simulation_step_ms,
            "solver_type": self.solver_type,
        }


@dataclass(frozen=True)
class ECMParametersSchema:
    """Equivalent circuit model physical parameters in explicit SI units."""

    series_resistance_r0_mohm: float = 25.0
    rc1_resistance_r1_mohm: float = 0.0
    rc1_capacitance_c1_f: float = 0.0
    rc2_resistance_r2_mohm: float = 0.0
    rc2_capacitance_c2_f: float = 0.0
    thermal_mass_j_per_k: float = 0.0
    convective_heat_transfer_w_per_k: float = 0.0

    def __post_init__(self) -> None:
        if self.series_resistance_r0_mohm < 0:
            raise ConfigurationValidationError(
                f"series_resistance_r0_mohm cannot be negative, got {self.series_resistance_r0_mohm}.",
                details={"r0": self.series_resistance_r0_mohm},
            )
        if self.rc1_resistance_r1_mohm < 0 or self.rc1_capacitance_c1_f < 0:
            raise ConfigurationValidationError(
                "RC1 parameters cannot be negative.",
                details={"r1": self.rc1_resistance_r1_mohm, "c1": self.rc1_capacitance_c1_f},
            )
        if self.rc2_resistance_r2_mohm < 0 or self.rc2_capacitance_c2_f < 0:
            raise ConfigurationValidationError(
                "RC2 parameters cannot be negative.",
                details={"r2": self.rc2_resistance_r2_mohm, "c2": self.rc2_capacitance_c2_f},
            )

    def to_dict(self) -> dict[str, Any]:
        """Serializes ECM parameters schema to dictionary."""
        return {
            "series_resistance_r0_mohm": self.series_resistance_r0_mohm,
            "rc1_resistance_r1_mohm": self.rc1_resistance_r1_mohm,
            "rc1_capacitance_c1_f": self.rc1_capacitance_c1_f,
            "rc2_resistance_r2_mohm": self.rc2_resistance_r2_mohm,
            "rc2_capacitance_c2_f": self.rc2_capacitance_c2_f,
            "thermal_mass_j_per_k": self.thermal_mass_j_per_k,
            "convective_heat_transfer_w_per_k": self.convective_heat_transfer_w_per_k,
        }


@dataclass(frozen=True)
class ModelConfigurationSchema:
    """Master declarative battery model configuration schema."""

    model_id: str
    paradigm: str
    schema_version: str = "1.0"
    description: str = ""
    sampling: SamplingConfigSchema = field(default_factory=SamplingConfigSchema)
    parameters: ECMParametersSchema = field(default_factory=ECMParametersSchema)
    custom_parameters: Mapping[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise SchemaVersionMismatchError(
                f"Unsupported schema_version '{self.schema_version}'. Supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}.",
                details={"schema_version": self.schema_version},
            )
        validate_battery_identifier(self.model_id, "model_id")

        normalized_paradigm = self.paradigm.upper().strip()
        if normalized_paradigm not in SUPPORTED_MODEL_PARADIGMS:
            raise InvalidModelConfigurationError(
                f"Unknown model paradigm '{self.paradigm}'. Supported: {sorted(SUPPORTED_MODEL_PARADIGMS)}.",
                details={"paradigm": self.paradigm},
            )

    def to_dict(self) -> dict[str, Any]:
        """Serializes model configuration to dictionary."""
        return {
            "schema_version": self.schema_version,
            "model_configuration": {
                "model_id": self.model_id,
                "paradigm": self.paradigm.upper().strip(),
                "description": self.description,
                "sampling": self.sampling.to_dict(),
                "parameters": self.parameters.to_dict(),
                "custom_parameters": dict(self.custom_parameters),
            },
        }
