"""Unit tests for Universal Battery Domain Validation Functions."""

import unittest

from src.domain.battery.validation import (
    validate_battery_identifier,
    validate_current_limits,
    validate_temperature_limits,
    validate_topology,
    validate_voltage_limits,
)
from src.domain.exceptions import (
    InvalidBatteryIdentifierError,
    InvalidBatteryTopologyError,
    InvalidElectricalRatingsError,
    InvalidThermalLimitsError,
)


class TestBatteryValidation(unittest.TestCase):
    """Unit tests for domain validation routines and physical invariants."""

    # --------------------------------------------------------------------------
    # 1. Identifier Validation Tests
    # --------------------------------------------------------------------------
    def test_valid_identifiers(self) -> None:
        """Valid alphanumeric, hyphen, and underscore identifiers pass."""
        valid_ids = ["pack_01", "batt-nmc-18650-3s1p", "Cell_1", "ModuleA-12", "SYSTEM-99_XYZ"]
        for valid_id in valid_ids:
            with self.subTest(identifier=valid_id):
                try:
                    validate_battery_identifier(valid_id)
                except InvalidBatteryIdentifierError:
                    self.fail(f"Valid identifier '{valid_id}' unexpectedly raised an error.")

    def test_invalid_identifiers_raise_error(self) -> None:
        """Empty, whitespace, and special-character identifiers are rejected."""
        invalid_ids = ["", "   ", "pack/01", "batt.nmc", "cell#1", "pack@home", "a" * 130]
        for invalid_id in invalid_ids:
            with self.subTest(identifier=invalid_id):
                with self.assertRaises(InvalidBatteryIdentifierError):
                    validate_battery_identifier(invalid_id)

    # --------------------------------------------------------------------------
    # 2. Topology Validation Tests
    # --------------------------------------------------------------------------
    def test_valid_topologies(self) -> None:
        """Single-cell (1S1P), series-only (3S1P), parallel-only (1S4P), and series-parallel (4S2P)."""
        valid_cases = [
            (1, 1, 1),
            (3, 1, 3),
            (1, 4, 4),
            (4, 2, 8),
            (96, 2, 192),
            (12, 1, None),  # Total cells optional
        ]
        for s, p, total in valid_cases:
            with self.subTest(series=s, parallel=p, total=total):
                try:
                    validate_topology(series_count=s, parallel_count=p, total_cells=total)
                except InvalidBatteryTopologyError:
                    self.fail(f"Valid topology {s}S{p}P unexpectedly failed validation.")

    def test_invalid_topologies_raise_error(self) -> None:
        """Zero or negative series/parallel counts and total cell mismatches must fail."""
        invalid_cases = [
            (0, 1, 0),       # Zero series
            (-1, 1, -1),     # Negative series
            (3, 0, 0),       # Zero parallel
            (3, -2, -6),     # Negative parallel
            (4, 2, 9),       # Total count mismatch (4*2=8 != 9)
            (3, 1, 2),       # Total count mismatch (3*1=3 != 2)
        ]
        for s, p, total in invalid_cases:
            with self.subTest(series=s, parallel=p, total=total):
                with self.assertRaises(InvalidBatteryTopologyError):
                    validate_topology(series_count=s, parallel_count=p, total_cells=total)

    # --------------------------------------------------------------------------
    # 3. Voltage Limits Validation Tests
    # --------------------------------------------------------------------------
    def test_valid_voltage_limits(self) -> None:
        """Valid voltage range 3.0V min <= 3.7V nom <= 4.2V max."""
        try:
            validate_voltage_limits(min_voltage_v=3.0, nominal_voltage_v=3.7, max_voltage_v=4.2)
            validate_voltage_limits(min_voltage_v=9.0, nominal_voltage_v=11.1, max_voltage_v=12.6)
            validate_voltage_limits(min_voltage_v=2.5, nominal_voltage_v=3.2, max_voltage_v=3.65)  # LFP
        except InvalidElectricalRatingsError:
            self.fail("Valid voltage limits unexpectedly raised an error.")

    def test_invalid_voltage_limits_raise_error(self) -> None:
        """Negative, zero, inverted, or out-of-range voltages must raise InvalidElectricalRatingsError."""
        invalid_cases = [
            (0.0, 3.7, 4.2),    # Zero min voltage
            (-3.0, 3.7, 4.2),   # Negative min voltage
            (3.0, 0.0, 4.2),    # Zero nominal voltage
            (3.0, 3.7, 0.0),    # Zero max voltage
            (4.2, 3.7, 3.0),    # Inverted min and max
            (3.5, 3.0, 4.2),    # Nominal less than min
            (3.0, 4.5, 4.2),    # Nominal greater than max
            (4.0, 4.0, 4.0),    # Min equals max (flat zero span)
        ]
        for min_v, nom_v, max_v in invalid_cases:
            with self.subTest(min_v=min_v, nom_v=nom_v, max_v=max_v):
                with self.assertRaises(InvalidElectricalRatingsError):
                    validate_voltage_limits(min_v, nom_v, max_v)

    # --------------------------------------------------------------------------
    # 4. Current Limits Validation Tests
    # --------------------------------------------------------------------------
    def test_valid_current_limits(self) -> None:
        """Valid continuous and peak currents."""
        try:
            validate_current_limits(
                max_continuous_charge_a=2.0,
                max_continuous_discharge_a=5.0,
                peak_charge_a=4.0,
                peak_discharge_a=10.0,
            )
            # Equal peak and continuous is allowed
            validate_current_limits(2.0, 5.0, 2.0, 5.0)
        except InvalidElectricalRatingsError:
            self.fail("Valid current limits unexpectedly raised an error.")

    def test_invalid_current_limits_raise_error(self) -> None:
        """Non-positive currents or peak < continuous must fail."""
        invalid_cases = [
            (0.0, 5.0, 4.0, 10.0),   # Zero charge current
            (-1.0, 5.0, 4.0, 10.0),  # Negative charge current
            (2.0, -5.0, 4.0, 10.0),  # Negative discharge current
            (5.0, 5.0, 2.0, 10.0),   # Peak charge (2A) < Continuous charge (5A)
            (2.0, 10.0, 4.0, 5.0),   # Peak discharge (5A) < Continuous discharge (10A)
        ]
        for c_chg, c_dis, p_chg, p_dis in invalid_cases:
            with self.subTest(c_chg=c_chg, c_dis=c_dis, p_chg=p_chg, p_dis=p_dis):
                with self.assertRaises(InvalidElectricalRatingsError):
                    validate_current_limits(c_chg, c_dis, p_chg, p_dis)

    # --------------------------------------------------------------------------
    # 5. Thermal Limits Validation Tests
    # --------------------------------------------------------------------------
    def test_valid_thermal_limits(self) -> None:
        """Standard automotive / consumer battery thermal operating windows."""
        try:
            validate_temperature_limits(
                min_charge_temp_c=0.0,
                max_charge_temp_c=45.0,
                min_discharge_temp_c=-20.0,
                max_discharge_temp_c=60.0,
                warning_temp_c=60.0,
                critical_temp_c=80.0,
            )
        except InvalidThermalLimitsError:
            self.fail("Valid thermal limits unexpectedly raised an error.")

    def test_invalid_thermal_limits_raise_error(self) -> None:
        """Disordered, unphysical (below absolute zero), or inverted temperatures."""
        invalid_cases = [
            (-280.0, 45.0, -20.0, 60.0, 60.0, 80.0),  # Below absolute zero (-273.15°C)
            (45.0, 0.0, -20.0, 60.0, 60.0, 80.0),    # min_charge > max_charge
            (0.0, 45.0, 60.0, -20.0, 60.0, 80.0),    # min_discharge > max_discharge
            (0.0, 45.0, 5.0, 60.0, 60.0, 80.0),      # min_discharge (5°C) > min_charge (0°C)
            (0.0, 70.0, -20.0, 60.0, 60.0, 80.0),    # max_charge (70°C) > max_discharge (60°C)
            (0.0, 45.0, -20.0, 60.0, 85.0, 80.0),    # warning (85°C) > critical (80°C)
            (0.0, 45.0, -20.0, 60.0, 50.0, 80.0),    # warning (50°C) < max_discharge (60°C)
        ]
        for min_chg, max_chg, min_dis, max_dis, warn, crit in invalid_cases:
            with self.subTest(min_chg=min_chg, max_chg=max_chg, warn=warn):
                with self.assertRaises(InvalidThermalLimitsError):
                    validate_temperature_limits(min_chg, max_chg, min_dis, max_dis, warn, crit)


if __name__ == "__main__":
    unittest.main()
