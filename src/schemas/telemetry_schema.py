"""Telemetry Payload Validation Schemas.

Defines schemas and parsers validating raw dictionary/JSON telemetry payloads
and converting them into verified TelemetrySnapshot objects.
"""

from typing import Any, Mapping

from src.telemetry.enums import CurrentFlowDirection, TelemetryQuality
from src.telemetry.measurements import (
    CellTelemetry,
    ModuleTelemetry,
    TemperatureSensorTelemetry,
)
from src.telemetry.snapshots import TelemetrySnapshot
from src.schemas.exceptions import ConfigurationValidationError


def validate_telemetry_payload(data: Mapping[str, Any]) -> TelemetrySnapshot:
    """Validates a dictionary telemetry payload and parses it into a TelemetrySnapshot.

    Args:
        data: Raw dictionary payload containing telemetry fields.

    Returns:
        Validated TelemetrySnapshot domain object.

    Raises:
        ConfigurationValidationError: If mandatory fields are missing or data types are invalid.
    """
    if not isinstance(data, Mapping):
        raise ConfigurationValidationError(
            f"Telemetry payload must be a mapping/dict, got {type(data).__name__}."
        )

    for req_field in ["snapshot_id", "system_id", "timestamp_ns"]:
        if req_field not in data or data[req_field] is None:
            raise ConfigurationValidationError(
                f"Missing required telemetry field '{req_field}'.",
                details={"payload": data},
            )

    # Parse direct cells
    direct_cells = []
    for raw_cell in data.get("direct_cells", []):
        if not isinstance(raw_cell, Mapping) or "cell_id" not in raw_cell:
            raise ConfigurationValidationError(
                "Each direct cell entry must be a dictionary with a 'cell_id'.",
                details={"cell_entry": raw_cell},
            )
        quality = TelemetryQuality(raw_cell.get("quality", "VALID"))
        direct_cells.append(
            CellTelemetry(
                cell_id=raw_cell["cell_id"],
                voltage_v=raw_cell.get("voltage_v"),
                temperature_c=raw_cell.get("temperature_c"),
                internal_resistance_mohm=raw_cell.get("internal_resistance_mohm"),
                soc_fraction=raw_cell.get("soc_fraction"),
                quality=quality,
                metadata=raw_cell.get("metadata", {}),
            )
        )

    # Parse modules
    modules = []
    for raw_mod in data.get("modules", []):
        if not isinstance(raw_mod, Mapping) or "module_id" not in raw_mod:
            raise ConfigurationValidationError(
                "Each module entry must be a dictionary with a 'module_id'.",
                details={"module_entry": raw_mod},
            )
        mod_cells = [
            CellTelemetry(
                cell_id=c["cell_id"],
                voltage_v=c.get("voltage_v"),
                temperature_c=c.get("temperature_c"),
                quality=TelemetryQuality(c.get("quality", "VALID")),
            )
            for c in raw_mod.get("cells", [])
        ]
        mod_temps = [
            TemperatureSensorTelemetry(
                sensor_id=s["sensor_id"],
                temperature_c=s["temperature_c"],
                quality=TelemetryQuality(s.get("quality", "VALID")),
            )
            for s in raw_mod.get("temperature_sensors", [])
        ]
        modules.append(
            ModuleTelemetry(
                module_id=raw_mod["module_id"],
                voltage_v=raw_mod.get("voltage_v"),
                temperature_c=raw_mod.get("temperature_c"),
                cell_telemetries=tuple(mod_cells),
                temperature_sensors=tuple(mod_temps),
                quality=TelemetryQuality(raw_mod.get("quality", "VALID")),
            )
        )

    # Parse discrete temperature sensors
    discrete_temps = [
        TemperatureSensorTelemetry(
            sensor_id=s["sensor_id"],
            temperature_c=s["temperature_c"],
            quality=TelemetryQuality(s.get("quality", "VALID")),
        )
        for s in data.get("discrete_temperatures", [])
    ]

    flow_state = (
        CurrentFlowDirection(data["charge_discharge_state"])
        if data.get("charge_discharge_state")
        else None
    )

    quality = TelemetryQuality(data.get("quality", "VALID"))

    return TelemetrySnapshot(
        snapshot_id=data["snapshot_id"],
        system_id=data["system_id"],
        timestamp_ns=data["timestamp_ns"],
        observed_at_ns=data.get("observed_at_ns"),
        sequence_number=data.get("sequence_number"),
        pack_voltage_v=data.get("pack_voltage_v"),
        pack_current_a=data.get("pack_current_a"),
        pack_power_w=data.get("pack_power_w"),
        ambient_temperature_c=data.get("ambient_temperature_c"),
        max_cell_temperature_c=data.get("max_cell_temperature_c"),
        min_cell_temperature_c=data.get("min_cell_temperature_c"),
        avg_cell_temperature_c=data.get("avg_cell_temperature_c"),
        soc_fraction=data.get("soc_fraction"),
        soh_fraction=data.get("soh_fraction"),
        charge_discharge_state=flow_state,
        bms_operational_state=data.get("bms_operational_state"),
        remaining_capacity_ah=data.get("remaining_capacity_ah"),
        available_energy_wh=data.get("available_energy_wh"),
        cumulative_charge_ah=data.get("cumulative_charge_ah"),
        cumulative_discharge_ah=data.get("cumulative_discharge_ah"),
        cell_telemetries=tuple(direct_cells),
        modules=tuple(modules),
        discrete_temperatures=tuple(discrete_temps),
        quality=quality,
        metadata=data.get("metadata", {}),
    )


class TelemetryPayloadSchema:
    """Validator class for telemetry dictionary payloads."""

    @staticmethod
    def validate(data: Mapping[str, Any]) -> TelemetrySnapshot:
        """Validates and parses a raw mapping into a TelemetrySnapshot."""
        return validate_telemetry_payload(data)
