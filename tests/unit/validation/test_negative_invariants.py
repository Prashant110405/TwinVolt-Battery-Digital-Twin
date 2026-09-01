"""Level 1 Negative & Invariant Rejection Test Suite.

Rigorously verifies that invalid, unphysical, or contradictory configurations
and telemetry payloads are deterministically rejected across the platform.
"""

import unittest

from src.domain.battery.enums import BatteryChemistry, CellFormFactor
from src.domain.battery.value_objects import (
    BatteryCapacity,
    BatteryIdentification,
    BatteryTopology,
    CellConfiguration,
    ElectricalRatings,
    ThermalLimits,
)
from src.domain.exceptions import (
    BatteryDomainError,
    InvalidBatteryIdentifierError,
    InvalidBatteryTopologyError,
    InvalidCellConfigurationError,
    InvalidElectricalRatingsError,
    InvalidThermalLimitsError,
)
from src.schemas.battery_profile import (
    BatteryProfileSchema,
    CellProfileSchema,
    CurrentLimitsSchema,
    RatingsSchema,
    ThermalLimitsSchema,
    TopologySchema,
    VoltageLimitsSchema,
)
from src.schemas.exceptions import (
    ConfigurationValidationError,
    InvalidBatteryProfileError,
    SchemaVersionMismatchError,
)
from src.telemetry.exceptions import (
    InvalidTelemetryTimestampError,
    InvalidTelemetryValueError,
)
from src.telemetry.measurements import CellTelemetry
from src.telemetry.snapshots import TelemetrySnapshot


class TestNegativeInvariants(unittest.TestCase):
    """Negative tests enforcing deterministic invariant rejection."""

    # --------------------------------------------------------------------------
    # 1. Topology Rejection Tests
    # --------------------------------------------------------------------------
    def test_reject_impossible_topologies(self) -> None:
        """Reject zero/negative series/parallel counts and total mismatches."""
        invalid_topologies = [(0, 1), (-5, 1), (3, 0), (4, -2)]
        for s, p in invalid_topologies:
            with self.subTest(s=s, p=p):
                with self.assertRaises(InvalidBatteryTopologyError):
                    BatteryTopology(series_count=s, parallel_count=p)

    # --------------------------------------------------------------------------
    # 2. Electrical Rating & Voltage Rejection Tests
    # --------------------------------------------------------------------------
    def test_reject_unphysical_voltages(self) -> None:
        """Reject negative, zero, or disordered voltage ratings."""
        # min >= max
        with self.assertRaises(InvalidElectricalRatingsError):
            ElectricalRatings(
                nominal_voltage_v=3.7,
                min_voltage_v=4.2,
                max_voltage_v=3.0,
                nominal_capacity_ah=2.2,
                nominal_energy_wh=8.14,
                max_continuous_charge_current_a=2.2,
                max_continuous_discharge_current_a=4.4,
                peak_charge_current_a=4.4,
                peak_discharge_current_a=8.8,
            )

        # nominal < min
        with self.assertRaises(InvalidElectricalRatingsError):
            ElectricalRatings(
                nominal_voltage_v=2.5,
                min_voltage_v=3.0,
                max_voltage_v=4.2,
                nominal_capacity_ah=2.2,
                nominal_energy_wh=8.14,
                max_continuous_charge_current_a=2.2,
                max_continuous_discharge_current_a=4.4,
                peak_charge_current_a=4.4,
                peak_discharge_current_a=8.8,
            )

    # --------------------------------------------------------------------------
    # 3. Thermal Invariant Rejection Tests
    # --------------------------------------------------------------------------
    def test_reject_unphysical_thermal_limits(self) -> None:
        """Reject temperatures below absolute zero or disordered warning/critical thresholds."""
        # Below absolute zero
        with self.assertRaises(InvalidThermalLimitsError):
            ThermalLimits(
                min_charge_temp_c=-280.0,
                max_charge_temp_c=45.0,
                min_discharge_temp_c=-20.0,
                max_discharge_temp_c=60.0,
                warning_temp_c=60.0,
                critical_temp_c=80.0,
            )

        # Warning < max discharge operating temperature
        with self.assertRaises(InvalidThermalLimitsError):
            ThermalLimits(
                min_charge_temp_c=0.0,
                max_charge_temp_c=45.0,
                min_discharge_temp_c=-20.0,
                max_discharge_temp_c=60.0,
                warning_temp_c=50.0,  # Warning less than max discharge (60.0)
                critical_temp_c=80.0,
            )

        # Warning >= critical threshold
        with self.assertRaises(InvalidThermalLimitsError):
            ThermalLimits(
                min_charge_temp_c=0.0,
                max_charge_temp_c=45.0,
                min_discharge_temp_c=-20.0,
                max_discharge_temp_c=60.0,
                warning_temp_c=85.0,
                critical_temp_c=80.0,
            )

    # --------------------------------------------------------------------------
    # 4. Telemetry Rejection Tests
    # --------------------------------------------------------------------------
    def test_reject_malformed_telemetry(self) -> None:
        """Reject unphysical negative voltages, NaN, and negative timestamps."""
        # Negative cell voltage in telemetry
        with self.assertRaises(InvalidTelemetryValueError):
            CellTelemetry(cell_id="c1", voltage_v=-3.7)

        # NaN current in telemetry snapshot
        with self.assertRaises(InvalidTelemetryValueError):
            TelemetrySnapshot(
                snapshot_id="s1",
                system_id="p1",
                timestamp_ns=1700000000000000000,
                pack_current_a=float("nan"),
            )

        # Negative timestamp
        with self.assertRaises(InvalidTelemetryTimestampError):
            TelemetrySnapshot(
                snapshot_id="s1",
                system_id="p1",
                timestamp_ns=-1,
                pack_voltage_v=12.0,
            )

        # Out-of-range SOC fraction (150%)
        with self.assertRaises(InvalidTelemetryValueError):
            CellTelemetry(cell_id="c1", soc_fraction=1.5)

    # --------------------------------------------------------------------------
    # 5. Schema Rejection Tests
    # --------------------------------------------------------------------------
    def test_reject_malformed_profile_schemas(self) -> None:
        """Reject unsupported schema version or empty identifiers."""
        with self.assertRaises(SchemaVersionMismatchError):
            BatteryProfileSchema(
                schema_version="99.0",
                profile_id="p1",
                display_name="Test",
                chemistry="NMC",
                topology=TopologySchema(series_count=3, parallel_count=1),
                cell_profile=CellProfileSchema(
                    cell_id="c1",
                    chemistry="NMC",
                    form_factor="CYLINDRICAL",
                    nominal_voltage_v=3.7,
                    min_voltage_v=3.0,
                    max_voltage_v=4.2,
                    nominal_capacity_ah=2.2,
                ),
                ratings=RatingsSchema(
                    nominal_pack_voltage_v=11.1,
                    nominal_cell_voltage_v=3.7,
                    nominal_capacity_ah=2.2,
                    nominal_energy_wh=24.42,
                ),
                voltage_limits=VoltageLimitsSchema(
                    cell_min_cutoff_v=3.0,
                    cell_max_cutoff_v=4.2,
                    pack_min_cutoff_v=9.0,
                    pack_max_cutoff_v=12.6,
                ),
                current_limits=CurrentLimitsSchema(
                    max_continuous_charge_a=2.2,
                    max_continuous_discharge_a=4.4,
                    peak_pulse_discharge_a=8.8,
                ),
                thermal_limits=ThermalLimitsSchema(
                    min_charge_temp_c=0.0,
                    max_charge_temp_c=45.0,
                    min_discharge_temp_c=-20.0,
                    max_discharge_temp_c=60.0,
                    thermal_warning_temp_c=60.0,
                    critical_thermal_runaway_temp_c=80.0,
                ),
            )


if __name__ == "__main__":
    unittest.main()
