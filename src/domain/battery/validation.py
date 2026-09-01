"""Validation Routines for the Universal Battery Domain.

Contains pure validation functions enforcing physical and logical invariants
for electrical ratings, thermal limits, topologies, and identifiers.
"""

import re
from typing import Optional

from src.domain.exceptions import (
    InvalidBatteryIdentifierError,
    InvalidBatteryTopologyError,
    InvalidElectricalRatingsError,
    InvalidThermalLimitsError,
)

# Allowed identifier pattern: alphanumeric characters, hyphens, and underscores
_IDENTIFIER_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")

# Physical constants
ABSOLUTE_ZERO_CELSIUS: float = -273.15


def validate_battery_identifier(identifier: str, field_name: str = "identifier") -> None:
    """Validates that an identifier is non-empty and contains safe characters.

    Args:
        identifier: The identifier string to validate.
        field_name: The name of the field being validated (for error messages).

    Raises:
        InvalidBatteryIdentifierError: If the identifier is empty or malformed.
    """
    if not isinstance(identifier, str) or not identifier.strip():
        raise InvalidBatteryIdentifierError(
            f"Battery {field_name} must be a non-empty string.",
            details={"field_name": field_name, "value": identifier},
        )

    if not _IDENTIFIER_REGEX.match(identifier.strip()):
        raise InvalidBatteryIdentifierError(
            f"Battery {field_name} '{identifier}' is invalid. Must be 1-128 alphanumeric, "
            "hyphen, or underscore characters.",
            details={"field_name": field_name, "value": identifier},
        )


def validate_topology(
    series_count: int,
    parallel_count: int,
    total_cells: Optional[int] = None,
) -> None:
    """Validates that a battery topology has physically meaningful series/parallel counts.

    Args:
        series_count: Number of cells/modules connected in series ($N_s$).
        parallel_count: Number of cells/strings connected in parallel ($N_p$).
        total_cells: Optional total cell count to verify against ($N_s \times N_p$).

    Raises:
        InvalidBatteryTopologyError: If counts are $< 1$ or mismatched.
    """
    if not isinstance(series_count, int) or series_count < 1:
        raise InvalidBatteryTopologyError(
            f"Series count must be a positive integer >= 1, got {series_count}.",
            details={"series_count": series_count},
        )

    if not isinstance(parallel_count, int) or parallel_count < 1:
        raise InvalidBatteryTopologyError(
            f"Parallel count must be a positive integer >= 1, got {parallel_count}.",
            details={"parallel_count": parallel_count},
        )

    expected_total = series_count * parallel_count
    if total_cells is not None and total_cells != expected_total:
        raise InvalidBatteryTopologyError(
            f"Total cell count mismatch: declared {total_cells}, but "
            f"series_count ({series_count}) * parallel_count ({parallel_count}) = {expected_total}.",
            details={
                "series_count": series_count,
                "parallel_count": parallel_count,
                "declared_total": total_cells,
                "expected_total": expected_total,
            },
        )


def validate_voltage_limits(
    min_voltage_v: float,
    nominal_voltage_v: float,
    max_voltage_v: float,
) -> None:
    """Validates voltage limits ordering and positivity.

    Invariant: $0 < V_{min} \le V_{nominal} \le V_{max}$ and $V_{min} < V_{max}$.

    Args:
        min_voltage_v: Minimum operational cutoff voltage in Volts.
        nominal_voltage_v: Nominal operational voltage in Volts.
        max_voltage_v: Maximum operational upper cutoff voltage in Volts.

    Raises:
        InvalidElectricalRatingsError: If voltages are non-positive or disordered.
    """
    for name, v in [
        ("min_voltage_v", min_voltage_v),
        ("nominal_voltage_v", nominal_voltage_v),
        ("max_voltage_v", max_voltage_v),
    ]:
        if not isinstance(v, (int, float)) or v <= 0:
            raise InvalidElectricalRatingsError(
                f"{name} must be a positive number > 0, got {v}.",
                details={"field": name, "value": v},
            )

    if min_voltage_v >= max_voltage_v:
        raise InvalidElectricalRatingsError(
            f"min_voltage_v ({min_voltage_v}V) must be strictly less than max_voltage_v ({max_voltage_v}V).",
            details={"min_voltage_v": min_voltage_v, "max_voltage_v": max_voltage_v},
        )

    if not (min_voltage_v <= nominal_voltage_v <= max_voltage_v):
        raise InvalidElectricalRatingsError(
            f"nominal_voltage_v ({nominal_voltage_v}V) must be between "
            f"min_voltage_v ({min_voltage_v}V) and max_voltage_v ({max_voltage_v}V).",
            details={
                "min_voltage_v": min_voltage_v,
                "nominal_voltage_v": nominal_voltage_v,
                "max_voltage_v": max_voltage_v,
            },
        )


def validate_current_limits(
    max_continuous_charge_a: float,
    max_continuous_discharge_a: float,
    peak_charge_a: float,
    peak_discharge_a: float,
) -> None:
    """Validates that current limits are positive and peak >= continuous.

    Args:
        max_continuous_charge_a: Maximum continuous charge current in Amperes.
        max_continuous_discharge_a: Maximum continuous discharge current in Amperes.
        peak_charge_a: Peak pulse charge current in Amperes.
        peak_discharge_a: Peak pulse discharge current in Amperes.

    Raises:
        InvalidElectricalRatingsError: If currents are non-positive or peak < continuous.
    """
    for name, current in [
        ("max_continuous_charge_a", max_continuous_charge_a),
        ("max_continuous_discharge_a", max_continuous_discharge_a),
        ("peak_charge_a", peak_charge_a),
        ("peak_discharge_a", peak_discharge_a),
    ]:
        if not isinstance(current, (int, float)) or current <= 0:
            raise InvalidElectricalRatingsError(
                f"{name} must be a positive number > 0, got {current}.",
                details={"field": name, "value": current},
            )

    if peak_charge_a < max_continuous_charge_a:
        raise InvalidElectricalRatingsError(
            f"peak_charge_a ({peak_charge_a}A) cannot be less than "
            f"max_continuous_charge_a ({max_continuous_charge_a}A).",
            details={
                "peak_charge_a": peak_charge_a,
                "max_continuous_charge_a": max_continuous_charge_a,
            },
        )

    if peak_discharge_a < max_continuous_discharge_a:
        raise InvalidElectricalRatingsError(
            f"peak_discharge_a ({peak_discharge_a}A) cannot be less than "
            f"max_continuous_discharge_a ({max_continuous_discharge_a}A).",
            details={
                "peak_discharge_a": peak_discharge_a,
                "max_continuous_discharge_a": max_continuous_discharge_a,
            },
        )


def validate_temperature_limits(
    min_charge_temp_c: float,
    max_charge_temp_c: float,
    min_discharge_temp_c: float,
    max_discharge_temp_c: float,
    warning_temp_c: float,
    critical_temp_c: float,
) -> None:
    """Validates thermal limits ordering and physical boundaries.

    Invariants:
        1. All temperatures $> -273.15^\\circ C$ (Absolute Zero).
        2. $T_{min,charge} < T_{max,charge}$.
        3. $T_{min,discharge} < T_{max,discharge}$.
        4. $T_{min,discharge} \\le T_{min,charge}$ (electrochemistry: discharge window is broader).
        5. $T_{max,charge} \\le T_{max,discharge}$.
        6. $T_{warning} < T_{critical}$.
        7. $T_{warning} \\ge T_{max,discharge}$.

    Raises:
        InvalidThermalLimitsError: If any thermal invariant is breached.
    """
    temps = {
        "min_charge_temp_c": min_charge_temp_c,
        "max_charge_temp_c": max_charge_temp_c,
        "min_discharge_temp_c": min_discharge_temp_c,
        "max_discharge_temp_c": max_discharge_temp_c,
        "warning_temp_c": warning_temp_c,
        "critical_temp_c": critical_temp_c,
    }

    for name, t in temps.items():
        if not isinstance(t, (int, float)):
            raise InvalidThermalLimitsError(
                f"{name} must be a numeric value, got {type(t).__name__}.",
                details={"field": name, "value": t},
            )
        if t <= ABSOLUTE_ZERO_CELSIUS:
            raise InvalidThermalLimitsError(
                f"{name} ({t}°C) violates physical absolute zero (>{ABSOLUTE_ZERO_CELSIUS}°C).",
                details={"field": name, "value": t},
            )

    if min_charge_temp_c >= max_charge_temp_c:
        raise InvalidThermalLimitsError(
            f"min_charge_temp_c ({min_charge_temp_c}°C) must be strictly less than "
            f"max_charge_temp_c ({max_charge_temp_c}°C).",
            details=temps,
        )

    if min_discharge_temp_c >= max_discharge_temp_c:
        raise InvalidThermalLimitsError(
            f"min_discharge_temp_c ({min_discharge_temp_c}°C) must be strictly less than "
            f"max_discharge_temp_c ({max_discharge_temp_c}°C).",
            details=temps,
        )

    if min_discharge_temp_c > min_charge_temp_c:
        raise InvalidThermalLimitsError(
            f"min_discharge_temp_c ({min_discharge_temp_c}°C) cannot be warmer than "
            f"min_charge_temp_c ({min_charge_temp_c}°C).",
            details=temps,
        )

    if max_charge_temp_c > max_discharge_temp_c:
        raise InvalidThermalLimitsError(
            f"max_charge_temp_c ({max_charge_temp_c}°C) cannot exceed "
            f"max_discharge_temp_c ({max_discharge_temp_c}°C).",
            details=temps,
        )

    if warning_temp_c >= critical_temp_c:
        raise InvalidThermalLimitsError(
            f"warning_temp_c ({warning_temp_c}°C) must be strictly less than "
            f"critical_temp_c ({critical_temp_c}°C).",
            details=temps,
        )

    if warning_temp_c < max_discharge_temp_c:
        raise InvalidThermalLimitsError(
            f"warning_temp_c ({warning_temp_c}°C) cannot be less than "
            f"max_discharge_temp_c ({max_discharge_temp_c}°C).",
            details=temps,
        )
