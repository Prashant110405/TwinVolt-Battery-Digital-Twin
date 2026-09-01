"""Unit tests for Battery Profile Schemas and Domain Materialization."""

import unittest

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
from src.schemas.exceptions import (
    ConfigurationValidationError,
    InvalidBatteryProfileError,
    SchemaVersionMismatchError,
)


class TestBatteryProfileSchema(unittest.TestCase):
    """Unit tests for declarative battery profile schemas and domain object conversion."""

    def setUp(self) -> None:
        """Create valid baseline sub-schemas for testing."""
        self.topology = TopologySchema(series_count=3, parallel_count=1)
        self.cell_profile = CellProfileSchema(
            cell_id="cell_nmc_18650",
            chemistry="NMC",
            form_factor="CYLINDRICAL",
            nominal_voltage_v=3.7,
            min_voltage_v=3.0,
            max_voltage_v=4.2,
            nominal_capacity_ah=2.2,
            nominal_internal_resistance_mohm=25.0,
            mass_kg=0.045,
        )
        self.ratings = RatingsSchema(
            nominal_pack_voltage_v=11.1,
            nominal_cell_voltage_v=3.7,
            nominal_capacity_ah=2.2,
            nominal_energy_wh=24.42,
        )
        self.voltage_limits = VoltageLimitsSchema(
            cell_min_cutoff_v=3.0,
            cell_max_cutoff_v=4.2,
            pack_min_cutoff_v=9.0,
            pack_max_cutoff_v=12.6,
        )
        self.current_limits = CurrentLimitsSchema(
            max_continuous_charge_a=2.2,
            max_continuous_discharge_a=4.4,
            peak_pulse_charge_a=4.4,
            peak_pulse_discharge_a=8.8,
        )
        self.thermal_limits = ThermalLimitsSchema(
            min_charge_temp_c=0.0,
            max_charge_temp_c=45.0,
            min_discharge_temp_c=-20.0,
            max_discharge_temp_c=60.0,
            thermal_warning_temp_c=60.0,
            critical_thermal_runaway_temp_c=80.0,
        )
        self.balancing = BalancingConfigSchema(
            balancing_delta_v_threshold_mv=15.0,
            balancing_enabled=True,
        )

    def test_valid_battery_profile_creation(self) -> None:
        """Create a complete valid BatteryProfileSchema."""
        profile = BatteryProfileSchema(
            profile_id="batt_nmc_3s1p_ref",
            display_name="Reference 3S1P Pack",
            chemistry="NMC",
            topology=self.topology,
            cell_profile=self.cell_profile,
            ratings=self.ratings,
            voltage_limits=self.voltage_limits,
            current_limits=self.current_limits,
            thermal_limits=self.thermal_limits,
            balancing=self.balancing,
        )
        self.assertEqual(profile.profile_id, "batt_nmc_3s1p_ref")
        self.assertEqual(profile.schema_version, "1.0")
        self.assertEqual(profile.topology.computed_total_cells, 3)

    def test_to_domain_pack_materialization(self) -> None:
        """Verify that to_domain_pack() creates a fully functional, validated BatteryPack."""
        profile = BatteryProfileSchema(
            profile_id="batt_nmc_3s1p_ref",
            display_name="Reference 3S1P Pack",
            chemistry="NMC",
            topology=self.topology,
            cell_profile=self.cell_profile,
            ratings=self.ratings,
            voltage_limits=self.voltage_limits,
            current_limits=self.current_limits,
            thermal_limits=self.thermal_limits,
            balancing=self.balancing,
        )
        domain_pack = profile.to_domain_pack()
        self.assertEqual(domain_pack.pack_id, "batt_nmc_3s1p_ref")
        self.assertEqual(domain_pack.total_cell_count, 3)
        self.assertEqual(domain_pack.series_count, 3)
        self.assertEqual(domain_pack.parallel_count, 1)
        self.assertEqual(domain_pack.nominal_voltage_v, 11.1)
        self.assertEqual(domain_pack.nominal_capacity_ah, 2.2)
        self.assertEqual(domain_pack.total_module_count, 1)
        self.assertEqual(domain_pack.get_module(0).cells[0].cell_id, "cell_nmc_18650")

    def test_to_dict_serialization(self) -> None:
        """Verify serialization to dictionary."""
        profile = BatteryProfileSchema(
            profile_id="batt_nmc_3s1p_ref",
            display_name="Reference 3S1P Pack",
            chemistry="NMC",
            topology=self.topology,
            cell_profile=self.cell_profile,
            ratings=self.ratings,
            voltage_limits=self.voltage_limits,
            current_limits=self.current_limits,
            thermal_limits=self.thermal_limits,
            balancing=self.balancing,
        )
        data = profile.to_dict()
        self.assertEqual(data["schema_version"], "1.0")
        self.assertEqual(data["battery_profile"]["profile_id"], "batt_nmc_3s1p_ref")
        self.assertEqual(data["battery_profile"]["topology"]["series_count"], 3)

    def test_unsupported_schema_version_raises(self) -> None:
        """Reject unmigrated or unsupported schema versions."""
        with self.assertRaises(SchemaVersionMismatchError):
            BatteryProfileSchema(
                schema_version="9.9.9",
                profile_id="batt_test",
                display_name="Test",
                chemistry="NMC",
                topology=self.topology,
                cell_profile=self.cell_profile,
                ratings=self.ratings,
                voltage_limits=self.voltage_limits,
                current_limits=self.current_limits,
                thermal_limits=self.thermal_limits,
            )

    def test_inconsistent_voltage_and_series_count_raises(self) -> None:
        """Reject pack nominal voltage that strongly mismatches series_count * cell_nominal."""
        bad_ratings = RatingsSchema(
            nominal_pack_voltage_v=48.0,  # 3S * 3.7V = 11.1V != 48.0V
            nominal_cell_voltage_v=3.7,
            nominal_capacity_ah=2.2,
            nominal_energy_wh=105.6,
        )
        with self.assertRaises(InvalidBatteryProfileError):
            BatteryProfileSchema(
                profile_id="batt_bad_v",
                display_name="Inconsistent Pack",
                chemistry="NMC",
                topology=self.topology,
                cell_profile=self.cell_profile,
                ratings=bad_ratings,
                voltage_limits=self.voltage_limits,
                current_limits=self.current_limits,
                thermal_limits=self.thermal_limits,
            )

    def test_invalid_sub_schemas_raise(self) -> None:
        """Verify that sub-schema validations fail on invalid inputs."""
        # Zero series count
        with self.assertRaises(ConfigurationValidationError):
            TopologySchema(series_count=0, parallel_count=1)

        # Unknown chemistry
        with self.assertRaises(ConfigurationValidationError):
            CellProfileSchema(
                cell_id="c1",
                chemistry="UNOBTAINIUM",
                form_factor="CYLINDRICAL",
                nominal_voltage_v=3.7,
                min_voltage_v=3.0,
                max_voltage_v=4.2,
                nominal_capacity_ah=2.2,
            )

        # Inverted voltage limits
        with self.assertRaises(ConfigurationValidationError):
            VoltageLimitsSchema(
                cell_min_cutoff_v=4.2,
                cell_max_cutoff_v=3.0,
                pack_min_cutoff_v=9.0,
                pack_max_cutoff_v=12.6,
            )


if __name__ == "__main__":
    unittest.main()
