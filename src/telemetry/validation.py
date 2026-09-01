"""Validation Routines for Canonical Telemetry.

Contains validation logic ensuring telemetry values obey fundamental physical laws,
finite floating-point constraints (no NaN/Inf), and valid time semantics.
"""

import math
from typing import Optional

from src.domain.battery.validation import ABSOLUTE_ZERO_CELSIUS, validate_battery_identifier
from src.telemetry.exceptions import (
    InvalidTelemetryTimestampError,
    InvalidTelemetryValueError,
)

# Minimum realistic timestamp: 2020-01-01T00:00:00Z in nanoseconds (1577836800000000000)
MIN_VALID_TIMESTAMP_NS: int = 1_577_836_800_000_000_000

# Maximum allowed future timestamp drift (default 10 minutes in nanoseconds)
MAX_FUTURE_DRIFT_NS: int = 600_000_000_000


def validate_telemetry_timestamp(
    timestamp_ns: int,
    current_time_ns: Optional[int] = None,
    allow_synthetic_zero: bool = True,
) -> None:
    """Validates that a telemetry timestamp is an integer and temporally plausible.

    Args:
        timestamp_ns: Timestamp in integer nanoseconds since UNIX epoch.
        current_time_ns: Optional host time in nanoseconds to check future bounds.
        allow_synthetic_zero: If True, permits relative simulation step 0 or positive monotonic relative steps.

    Raises:
        InvalidTelemetryTimestampError: If timestamp is negative or unphysical.
    """
    if not isinstance(timestamp_ns, int):
        raise InvalidTelemetryTimestampError(
            f"timestamp_ns must be an integer (nanoseconds), got {type(timestamp_ns).__name__}.",
            details={"timestamp_ns": timestamp_ns},
        )

    if timestamp_ns < 0:
        raise InvalidTelemetryTimestampError(
            f"timestamp_ns cannot be negative, got {timestamp_ns}.",
            details={"timestamp_ns": timestamp_ns},
        )

    # If timestamp looks like a full Unix epoch timestamp (>= 2020), verify future boundary
    if current_time_ns is not None and timestamp_ns > MIN_VALID_TIMESTAMP_NS:
        if timestamp_ns > (current_time_ns + MAX_FUTURE_DRIFT_NS):
            raise InvalidTelemetryTimestampError(
                f"timestamp_ns {timestamp_ns} is too far in the future compared to host time {current_time_ns}.",
                details={"timestamp_ns": timestamp_ns, "current_time_ns": current_time_ns},
            )


def validate_voltage_telemetry(
    voltage_v: Optional[float],
    field_name: str = "voltage_v",
) -> None:
    """Validates that a voltage measurement is a non-negative, finite number.

    Args:
        voltage_v: Voltage reading in Volts, or None if unavailable.
        field_name: Name of the field for error reporting.

    Raises:
        InvalidTelemetryValueError: If voltage is negative, NaN, or infinite.
    """
    if voltage_v is None:
        return

    if not isinstance(voltage_v, (int, float)):
        raise InvalidTelemetryValueError(
            f"{field_name} must be a numeric value or None, got {type(voltage_v).__name__}.",
            details={"field": field_name, "value": voltage_v},
        )

    if math.isnan(voltage_v) or math.isinf(voltage_v):
        raise InvalidTelemetryValueError(
            f"{field_name} must be a finite number, got {voltage_v}.",
            details={"field": field_name, "value": voltage_v},
        )

    if voltage_v < 0:
        raise InvalidTelemetryValueError(
            f"{field_name} cannot be negative in battery systems, got {voltage_v}V.",
            details={"field": field_name, "value": voltage_v},
        )


def validate_current_telemetry(
    current_a: Optional[float],
    field_name: str = "current_a",
) -> None:
    """Validates that a current measurement is finite. Current can be positive (discharge) or negative (charge).

    Raises:
        InvalidTelemetryValueError: If current is NaN or infinite.
    """
    if current_a is None:
        return

    if not isinstance(current_a, (int, float)):
        raise InvalidTelemetryValueError(
            f"{field_name} must be a numeric value or None, got {type(current_a).__name__}.",
            details={"field": field_name, "value": current_a},
        )

    if math.isnan(current_a) or math.isinf(current_a):
        raise InvalidTelemetryValueError(
            f"{field_name} must be a finite number, got {current_a}.",
            details={"field": field_name, "value": current_a},
        )


def validate_temperature_telemetry(
    temp_c: Optional[float],
    field_name: str = "temperature_c",
) -> None:
    """Validates that a temperature measurement is finite and above Absolute Zero (-273.15°C).

    Raises:
        InvalidTelemetryValueError: If temperature is below absolute zero, NaN, or infinite.
    """
    if temp_c is None:
        return

    if not isinstance(temp_c, (int, float)):
        raise InvalidTelemetryValueError(
            f"{field_name} must be a numeric value or None, got {type(temp_c).__name__}.",
            details={"field": field_name, "value": temp_c},
        )

    if math.isnan(temp_c) or math.isinf(temp_c):
        raise InvalidTelemetryValueError(
            f"{field_name} must be a finite number, got {temp_c}.",
            details={"field": field_name, "value": temp_c},
        )

    if temp_c <= ABSOLUTE_ZERO_CELSIUS:
        raise InvalidTelemetryValueError(
            f"{field_name} ({temp_c}°C) violates physical absolute zero (>{ABSOLUTE_ZERO_CELSIUS}°C).",
            details={"field": field_name, "value": temp_c},
        )


def validate_fraction_telemetry(
    fraction: Optional[float],
    field_name: str = "fraction",
) -> None:
    """Validates normalized fraction values (such as SOC or SOH) in [0.0, 1.0].

    Raises:
        InvalidTelemetryValueError: If fraction is out of [0.0, 1.0], NaN, or infinite.
    """
    if fraction is None:
        return

    if not isinstance(fraction, (int, float)):
        raise InvalidTelemetryValueError(
            f"{field_name} must be a numeric value or None, got {type(fraction).__name__}.",
            details={"field": field_name, "value": fraction},
        )

    if math.isnan(fraction) or math.isinf(fraction):
        raise InvalidTelemetryValueError(
            f"{field_name} must be a finite number, got {fraction}.",
            details={"field": field_name, "value": fraction},
        )

    if not (0.0 <= fraction <= 1.0):
        raise InvalidTelemetryValueError(
            f"{field_name} must be in range [0.0, 1.0], got {fraction}.",
            details={"field": field_name, "value": fraction},
        )


def validate_power_telemetry(
    power_w: Optional[float],
    field_name: str = "power_w",
) -> None:
    """Validates power measurement finiteness."""
    if power_w is None:
        return
    if not isinstance(power_w, (int, float)) or math.isnan(power_w) or math.isinf(power_w):
        raise InvalidTelemetryValueError(
            f"{field_name} must be a finite numeric value, got {power_w}.",
            details={"field": field_name, "value": power_w},
        )


def validate_non_negative_metric(
    value: Optional[float],
    field_name: str,
) -> None:
    """Validates that a metric (such as capacity or energy) is non-negative and finite."""
    if value is None:
        return
    if not isinstance(value, (int, float)) or math.isnan(value) or math.isinf(value) or value < 0:
        raise InvalidTelemetryValueError(
            f"{field_name} must be a non-negative finite number, got {value}.",
            details={"field": field_name, "value": value},
        )
