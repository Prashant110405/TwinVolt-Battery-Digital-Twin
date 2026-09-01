"""Safe Configuration Profile Loaders.

Provides safe parsing for YAML, JSON, and dictionary configurations,
validating schemas and materializing domain objects.
"""

import json
from pathlib import Path
from typing import Any, Mapping, Union

try:
    import yaml
    _YAML_AVAILABLE = True
except ImportError:  # pragma: no cover
    _YAML_AVAILABLE = False

from src.domain.battery.entities import BatteryPack
from src.schemas.battery_profile import (
    BalancingConfigSchema,
    BatteryProfileSchema,
    CellProfileSchema,
    CurrentLimitsSchema,
    RatingsSchema,
    ThermalLimitsSchema,
    TopologySchema,
    VoltageLimitsSchema,
)
from src.schemas.exceptions import ConfigurationValidationError
from src.schemas.model_profile import (
    ECMParametersSchema,
    ModelConfigurationSchema,
    SamplingConfigSchema,
)


class BatteryProfileLoader:
    """Safe loader and parser for declarative battery profiles."""

    @classmethod
    def load_from_dict(cls, data: Mapping[str, Any]) -> BatteryProfileSchema:
        """Parses a dictionary into a validated BatteryProfileSchema."""
        if not isinstance(data, Mapping):
            raise ConfigurationValidationError(
                f"Battery profile data must be a dictionary/mapping, got {type(data).__name__}."
            )

        schema_version = str(data.get("schema_version", "1.0"))
        profile_data = data.get("battery_profile", data)

        for req in ["profile_id", "display_name", "chemistry", "topology", "cell_profile", "ratings", "voltage_limits", "current_limits", "thermal_limits"]:
            if req not in profile_data:
                raise ConfigurationValidationError(
                    f"Missing required section '{req}' in battery profile.",
                    details={"missing_field": req},
                )

        raw_topo = profile_data["topology"]
        topology = TopologySchema(
            series_count=raw_topo["series_count"],
            parallel_count=raw_topo["parallel_count"],
            total_cells=raw_topo.get("total_cells"),
        )

        raw_cell = profile_data["cell_profile"]
        cell_profile = CellProfileSchema(
            cell_id=raw_cell["cell_id"],
            chemistry=raw_cell["chemistry"],
            form_factor=raw_cell["form_factor"],
            nominal_voltage_v=raw_cell["nominal_voltage_v"],
            min_voltage_v=raw_cell["min_voltage_v"],
            max_voltage_v=raw_cell["max_voltage_v"],
            nominal_capacity_ah=raw_cell["nominal_capacity_ah"],
            nominal_internal_resistance_mohm=raw_cell.get("nominal_internal_resistance_mohm", 0.0),
            mass_kg=raw_cell.get("mass_kg", 0.0),
        )

        raw_ratings = profile_data["ratings"]
        ratings = RatingsSchema(
            nominal_pack_voltage_v=raw_ratings["nominal_pack_voltage_v"],
            nominal_cell_voltage_v=raw_ratings["nominal_cell_voltage_v"],
            nominal_capacity_ah=raw_ratings["nominal_capacity_ah"],
            nominal_energy_wh=raw_ratings["nominal_energy_wh"],
        )

        raw_v_limits = profile_data["voltage_limits"]
        v_limits = VoltageLimitsSchema(
            cell_min_cutoff_v=raw_v_limits["cell_min_cutoff_v"],
            cell_max_cutoff_v=raw_v_limits["cell_max_cutoff_v"],
            pack_min_cutoff_v=raw_v_limits["pack_min_cutoff_v"],
            pack_max_cutoff_v=raw_v_limits["pack_max_cutoff_v"],
        )

        raw_c_limits = profile_data["current_limits"]
        c_limits = CurrentLimitsSchema(
            max_continuous_charge_a=raw_c_limits["max_continuous_charge_a"],
            max_continuous_discharge_a=raw_c_limits["max_continuous_discharge_a"],
            peak_pulse_discharge_a=raw_c_limits["peak_pulse_discharge_a"],
            peak_pulse_charge_a=raw_c_limits.get("peak_pulse_charge_a"),
        )

        raw_t_limits = profile_data["thermal_limits"]
        t_limits = ThermalLimitsSchema(
            min_charge_temp_c=raw_t_limits["min_charge_temp_c"],
            max_charge_temp_c=raw_t_limits["max_charge_temp_c"],
            min_discharge_temp_c=raw_t_limits["min_discharge_temp_c"],
            max_discharge_temp_c=raw_t_limits["max_discharge_temp_c"],
            thermal_warning_temp_c=raw_t_limits["thermal_warning_temp_c"],
            critical_thermal_runaway_temp_c=raw_t_limits.get("critical_thermal_runaway_temp_c", 80.0),
        )

        raw_balancing = profile_data.get("balancing", {})
        balancing = BalancingConfigSchema(
            balancing_delta_v_threshold_mv=raw_balancing.get("balancing_delta_v_threshold_mv", 10.0),
            balancing_enabled=raw_balancing.get("balancing_enabled", True),
        )

        return BatteryProfileSchema(
            schema_version=schema_version,
            profile_id=profile_data["profile_id"],
            display_name=profile_data["display_name"],
            manufacturer=profile_data.get("manufacturer", ""),
            model_name=profile_data.get("model_name", ""),
            chemistry=profile_data["chemistry"],
            topology=topology,
            cell_profile=cell_profile,
            ratings=ratings,
            voltage_limits=v_limits,
            current_limits=c_limits,
            thermal_limits=t_limits,
            balancing=balancing,
            metadata=profile_data.get("metadata", {}),
        )

    @classmethod
    def load_from_json(cls, json_str: str) -> BatteryProfileSchema:
        """Parses a JSON string into a validated BatteryProfileSchema."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise ConfigurationValidationError(
                f"Failed to parse JSON battery profile: {exc.msg}",
                details={"json_error": str(exc)},
            ) from exc
        return cls.load_from_dict(data)

    @classmethod
    def load_from_yaml(cls, yaml_str: str) -> BatteryProfileSchema:
        """Safely parses a YAML string into a validated BatteryProfileSchema."""
        if not _YAML_AVAILABLE:  # pragma: no cover
            raise ConfigurationValidationError("PyYAML is not installed.")
        try:
            data = yaml.safe_load(yaml_str)
        except Exception as exc:
            raise ConfigurationValidationError(
                f"Failed to safely parse YAML battery profile: {exc}",
                details={"yaml_error": str(exc)},
            ) from exc
        return cls.load_from_dict(data)

    @classmethod
    def load_from_file(cls, file_path: Union[str, Path]) -> BatteryProfileSchema:
        """Loads and parses a battery profile file (.yaml, .yml, or .json)."""
        path = Path(file_path)
        if not path.is_file():
            raise ConfigurationValidationError(
                f"Battery profile file not found: {path.resolve()}",
                details={"file_path": str(path)},
            )
        content = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            return cls.load_from_json(content)
        return cls.load_from_yaml(content)

    @classmethod
    def create_domain_pack_from_file(cls, file_path: Union[str, Path]) -> BatteryPack:
        """Loads a file and directly materializes a validated BatteryPack domain entity."""
        schema = cls.load_from_file(file_path)
        return schema.to_domain_pack()


class ModelConfigurationLoader:
    """Safe loader and parser for declarative battery model configurations."""

    @classmethod
    def load_from_dict(cls, data: Mapping[str, Any]) -> ModelConfigurationSchema:
        """Parses a dictionary into a validated ModelConfigurationSchema."""
        if not isinstance(data, Mapping):
            raise ConfigurationValidationError(
                f"Model configuration must be a dictionary/mapping, got {type(data).__name__}."
            )

        schema_version = str(data.get("schema_version", "1.0"))
        model_data = data.get("model_configuration", data)

        for req in ["model_id", "paradigm"]:
            if req not in model_data:
                raise ConfigurationValidationError(
                    f"Missing required field '{req}' in model configuration.",
                    details={"missing_field": req},
                )

        raw_sampling = model_data.get("sampling", {})
        sampling = SamplingConfigSchema(
            simulation_step_ms=raw_sampling.get("simulation_step_ms", 100),
            solver_type=raw_sampling.get("solver_type", "explicit_rk4"),
        )

        raw_params = model_data.get("parameters", {})
        parameters = ECMParametersSchema(
            series_resistance_r0_mohm=raw_params.get("series_resistance_r0_mohm", 25.0),
            rc1_resistance_r1_mohm=raw_params.get("rc1_resistance_r1_mohm", 0.0),
            rc1_capacitance_c1_f=raw_params.get("rc1_capacitance_c1_f", 0.0),
            rc2_resistance_r2_mohm=raw_params.get("rc2_resistance_r2_mohm", 0.0),
            rc2_capacitance_c2_f=raw_params.get("rc2_capacitance_c2_f", 0.0),
            thermal_mass_j_per_k=raw_params.get("thermal_mass_j_per_k", 0.0),
            convective_heat_transfer_w_per_k=raw_params.get("convective_heat_transfer_w_per_k", 0.0),
        )

        return ModelConfigurationSchema(
            schema_version=schema_version,
            model_id=model_data["model_id"],
            paradigm=model_data["paradigm"],
            description=model_data.get("description", ""),
            sampling=sampling,
            parameters=parameters,
            custom_parameters=model_data.get("custom_parameters", {}),
        )

    @classmethod
    def load_from_yaml(cls, yaml_str: str) -> ModelConfigurationSchema:
        """Safely parses a YAML string into a ModelConfigurationSchema."""
        if not _YAML_AVAILABLE:  # pragma: no cover
            raise ConfigurationValidationError("PyYAML is not installed.")
        try:
            data = yaml.safe_load(yaml_str)
        except Exception as exc:
            raise ConfigurationValidationError(
                f"Failed to safely parse YAML model configuration: {exc}",
                details={"yaml_error": str(exc)},
            ) from exc
        return cls.load_from_dict(data)

    @classmethod
    def load_from_file(cls, file_path: Union[str, Path]) -> ModelConfigurationSchema:
        """Loads and parses a model configuration file (.yaml, .yml, or .json)."""
        path = Path(file_path)
        if not path.is_file():
            raise ConfigurationValidationError(
                f"Model configuration file not found: {path.resolve()}",
                details={"file_path": str(path)},
            )
        content = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            return cls.load_from_dict(json.loads(content))
        return cls.load_from_yaml(content)
