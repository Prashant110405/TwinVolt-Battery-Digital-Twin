"""Unit tests for Canonical Telemetry Validation Routines."""

import math
import unittest

from src.telemetry.exceptions import (
    InvalidTelemetryTimestampError,
    InvalidTelemetryValueError,
)
from src.telemetry.validation import (
    validate_current_telemetry,
    validate_fraction_telemetry,
    validate_power_telemetry,
    validate_telemetry_timestamp,
    validate_temperature_telemetry,
    validate_voltage_telemetry,
)


class TestTelemetryValidation(unittest.TestCase):
    """Unit tests for telemetry value and timestamp validation."""

    # --------------------------------------------------------------------------
    # 1. Timestamp Validation Tests
    # --------------------------------------------------------------------------
    def test_valid_timestamps(self) -> None:
        """Valid epoch nanosecond timestamps and relative simulation step 0."""
        try:
            validate_telemetry_timestamp(0)
            validate_telemetry_timestamp(1_700_000_000_000_000_000)
        except InvalidTelemetryTimestampError:
            self.fail("Valid timestamps unexpectedly raised an error.")

    def test_invalid_timestamps_raise_error(self) -> None:
        """Negative timestamps, non-integers, or excessive future drift must fail."""
        with self.assertRaises(InvalidTelemetryTimestampError):
            validate_telemetry_timestamp(-1)

        with self.assertRaises(InvalidTelemetryTimestampError):
            validate_telemetry_timestamp(1700000000.5)  # type: ignore[arg-type]

        # Future drift check
        host_time_ns = 1_700_000_000_000_000_000
        future_time_ns = host_time_ns + 1_000_000_000_000  # 1000s in future (> 600s max drift)
        with self.assertRaises(InvalidTelemetryTimestampError):
            validate_telemetry_timestamp(future_time_ns, current_time_ns=host_time_ns)

    # --------------------------------------------------------------------------
    # 2. Voltage Validation Tests
    # --------------------------------------------------------------------------
    def test_valid_voltage(self) -> None:
        """Non-negative voltages and None pass."""
        try:
            validate_voltage_telemetry(None)
            validate_voltage_telemetry(0.0)
            validate_voltage_telemetry(3.7)
            validate_voltage_telemetry(400.0)
        except InvalidTelemetryValueError:
            self.fail("Valid voltages unexpectedly raised an error.")

    def test_invalid_voltage_raises(self) -> None:
        """Negative voltages, NaN, Inf, or non-numeric must fail."""
        for invalid_v in [-0.01, -3.7, float("nan"), float("inf"), float("-inf")]:
            with self.subTest(voltage=invalid_v):
                with self.assertRaises(InvalidTelemetryValueError):
                    validate_voltage_telemetry(invalid_v)

    # --------------------------------------------------------------------------
    # 3. Current Validation Tests
    # --------------------------------------------------------------------------
    def test_valid_current(self) -> None:
        """Both positive (discharge) and negative (charge) currents and zero pass."""
        try:
            validate_current_telemetry(None)
            validate_current_telemetry(0.0)
            validate_current_telemetry(10.5)
            validate_current_telemetry(-5.2)
        except InvalidTelemetryValueError:
            self.fail("Valid currents unexpectedly raised an error.")

    def test_invalid_current_raises(self) -> None:
        """NaN or Inf currents must fail."""
        for invalid_i in [float("nan"), float("inf"), float("-inf")]:
            with self.subTest(current=invalid_i):
                with self.assertRaises(InvalidTelemetryValueError):
                    validate_current_telemetry(invalid_i)

    # --------------------------------------------------------------------------
    # 4. Temperature Validation Tests
    # --------------------------------------------------------------------------
    def test_valid_temperature(self) -> None:
        """Temperatures above -273.15°C and None pass."""
        try:
            validate_temperature_telemetry(None)
            validate_temperature_telemetry(25.0)
            validate_temperature_telemetry(-40.0)
            validate_temperature_telemetry(120.0)
        except InvalidTelemetryValueError:
            self.fail("Valid temperatures unexpectedly raised an error.")

    def test_invalid_temperature_raises(self) -> None:
        """Temperatures below absolute zero, NaN, or Inf must fail."""
        for invalid_t in [-273.16, -300.0, float("nan"), float("inf")]:
            with self.subTest(temperature=invalid_t):
                with self.assertRaises(InvalidTelemetryValueError):
                    validate_temperature_telemetry(invalid_t)

    # --------------------------------------------------------------------------
    # 5. Fraction (SOC/SOH) Validation Tests
    # --------------------------------------------------------------------------
    def test_valid_fraction(self) -> None:
        """Values in [0.0, 1.0] and None pass."""
        try:
            validate_fraction_telemetry(None)
            validate_fraction_telemetry(0.0)
            validate_fraction_telemetry(0.85)
            validate_fraction_telemetry(1.0)
        except InvalidTelemetryValueError:
            self.fail("Valid fractions unexpectedly raised an error.")

    def test_invalid_fraction_raises(self) -> None:
        """Out of [0, 1] range, NaN, or Inf must fail."""
        for invalid_f in [-0.01, 1.01, 100.0, float("nan"), float("inf")]:
            with self.subTest(fraction=invalid_f):
                with self.assertRaises(InvalidTelemetryValueError):
                    validate_fraction_telemetry(invalid_f)


if __name__ == "__main__":
    unittest.main()
