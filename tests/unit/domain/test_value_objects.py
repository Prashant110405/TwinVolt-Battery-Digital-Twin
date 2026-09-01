"""Unit tests for Universal Battery Domain Value Objects."""

from dataclasses import FrozenInstanceError
import unittest

from src.domain.battery.enums import BatteryChemistry, CellFormFactor
from src.domain.battery.value_objects import (
    BatteryCapacity,
    BatteryIdentification,
    BatteryTopology,
    CellConfiguration,
    ElectricalRatings,
    ModuleConfiguration,
    OperatingLimits,
    PackConfiguration,
    ThermalLimits,
)
from src.domain.exceptions import (
    InvalidBatteryIdentifierError,
    InvalidCellConfigurationError,
    InvalidElectricalRatingsError,
    InvalidModuleConfigurationError,
    InvalidPackConfigurationError,
    InvalidThermalLimitsError,
)


class TestBatteryValueObjects(unittest.TestCase):
    """Unit tests covering immutable value objects, methods, and invariants."""

    # --------------------------------------------------------------------------
    # 1. BatteryIdentification Tests
    # --------------------------------------------------------------------------
    def test_battery_identification_creation(self) -> None:
        """Create valid identification with optional metadata."""
        ident = BatteryIdentification(
            identifier="pack-nmc-001",
            display_name="NMC Reference Pack",
            manufacturer="TwinVolt Labs",
            model_name="TV-NMC-3S",
            serial_number="SN-20260831-01",
            metadata={"batch": "2026-Q3", "chem_lot": "A12"},
        )
        self.assertEqual(ident.identifier, "pack-nmc-001")
        self.assertEqual(ident.display_name, "NMC Reference Pack")
        self.assertEqual(ident.manufacturer, "TwinVolt Labs")
        self.assertEqual(ident.metadata["batch"], "2026-Q3")

    def test_battery_identification_invalid_raises(self) -> None:
        """Malformed or empty identifiers must fail."""
        with self.assertRaises(InvalidBatteryIdentifierError):
            BatteryIdentification(identifier="", display_name="Invalid")

    def test_battery_identification_immutability(self) -> None:
        """Assert frozen dataclass prevents mutation."""
        ident = BatteryIdentification(identifier="pack-01", display_name="Pack 1")
        with self.assertRaises(FrozenInstanceError):
            ident.identifier = "new-id"  # type: ignore[misc]

    # --------------------------------------------------------------------------
    # 2. BatteryTopology Tests
    # --------------------------------------------------------------------------
    def test_topology_single_cell(self) -> None:
        """1S1P topology calculation."""
        topo = BatteryTopology(series_count=1, parallel_count=1)
        self.assertEqual(topo.series_count, 1)
        self.assertEqual(topo.parallel_count, 1)
        self.assertEqual(topo.total_cells, 1)
        self.assertEqual(topo.describe(), "1S1P")

    def test_topology_series_parallel(self) -> None:
        """Multi-cell configurations (3S1P, 4S2P, 12S2P)."""
        cases = [
            (3, 1, 3, "3S1P"),
            (4, 2, 8, "4S2P"),
            (12, 2, 24, "12S2P"),
            (96, 4, 384, "96S4P"),
        ]
        for s, p, expected_total, expected_desc in cases:
            with self.subTest(s=s, p=p):
                topo = BatteryTopology(series_count=s, parallel_count=p)
                self.assertEqual(topo.total_cells, expected_total)
                self.assertEqual(topo.describe(), expected_desc)

    # --------------------------------------------------------------------------
    # 3. BatteryCapacity Tests
    # --------------------------------------------------------------------------
    def test_battery_capacity_valid(self) -> None:
        """Valid capacity and energy values."""
        cap = BatteryCapacity(nominal_capacity_ah=2.2, nominal_energy_wh=24.42)
        self.assertEqual(cap.nominal_capacity_ah, 2.2)
        self.assertEqual(cap.nominal_energy_wh, 24.42)

    def test_battery_capacity_invalid_raises(self) -> None:
        """Zero or negative capacity/energy must fail."""
        with self.assertRaises(InvalidElectricalRatingsError):
            BatteryCapacity(nominal_capacity_ah=0.0, nominal_energy_wh=10.0)
        with self.assertRaises(InvalidElectricalRatingsError):
            BatteryCapacity(nominal_capacity_ah=2.2, nominal_energy_wh=-5.0)

    # --------------------------------------------------------------------------
    # 4. ElectricalRatings Tests
    # --------------------------------------------------------------------------
    def test_electrical_ratings_methods(self) -> None:
        """Verify voltage_range_v, c_rate_to_current, and current_to_c_rate calculations."""
        ratings = ElectricalRatings(
            nominal_voltage_v=11.1,
            min_voltage_v=9.0,
            max_voltage_v=12.6,
            nominal_capacity_ah=2.5,
            nominal_energy_wh=27.75,
            max_continuous_charge_current_a=2.5,
            max_continuous_discharge_current_a=5.0,
            peak_charge_current_a=5.0,
            peak_discharge_current_a=10.0,
        )
        self.assertAlmostEqual(ratings.voltage_range_v, 3.6, places=5)
        # 1C of 2.5 Ah = 2.5 A
        self.assertAlmostEqual(ratings.c_rate_to_current(1.0), 2.5, places=5)
        # 2C of 2.5 Ah = 5.0 A
        self.assertAlmostEqual(ratings.c_rate_to_current(2.0), 5.0, places=5)
        # 5.0 A on 2.5 Ah = 2.0 C
        self.assertAlmostEqual(ratings.current_to_c_rate(5.0), 2.0, places=5)

    # --------------------------------------------------------------------------
    # 5. ThermalLimits Tests
    # --------------------------------------------------------------------------
    def test_thermal_limits_operational_queries(self) -> None:
        """Verify charge, discharge, warning, and critical temperature queries."""
        limits = ThermalLimits(
            min_charge_temp_c=0.0,
            max_charge_temp_c=45.0,
            min_discharge_temp_c=-20.0,
            max_discharge_temp_c=60.0,
            warning_temp_c=60.0,
            critical_temp_c=80.0,
        )
        # Charging window (0°C to 45°C)
        self.assertTrue(limits.is_within_charge_window(25.0))
        self.assertTrue(limits.is_within_charge_window(0.0))
        self.assertTrue(limits.is_within_charge_window(45.0))
        self.assertFalse(limits.is_within_charge_window(-5.0))
        self.assertFalse(limits.is_within_charge_window(50.0))

        # Discharging window (-20°C to 60°C)
        self.assertTrue(limits.is_within_discharge_window(-10.0))
        self.assertTrue(limits.is_within_discharge_window(55.0))
        self.assertFalse(limits.is_within_discharge_window(-25.0))

        # Over-temperature warning (>= 60°C)
        self.assertFalse(limits.is_over_temperature(55.0))
        self.assertTrue(limits.is_over_temperature(60.0))
        self.assertTrue(limits.is_over_temperature(75.0))

        # Critical temperature (>= 80°C)
        self.assertFalse(limits.is_critical_temperature(75.0))
        self.assertTrue(limits.is_critical_temperature(80.0))
        self.assertTrue(limits.is_critical_temperature(85.0))

    # --------------------------------------------------------------------------
    # 6. CellConfiguration Tests
    # --------------------------------------------------------------------------
    def test_cell_configuration_nmc_and_lfp(self) -> None:
        """Create valid cell configurations for different chemistries."""
        # NMC 18650 cell
        cell_nmc = CellConfiguration(
            cell_id="cell_nmc_18650",
            chemistry=BatteryChemistry.NMC,
            form_factor=CellFormFactor.CYLINDRICAL,
            nominal_voltage_v=3.7,
            min_voltage_v=3.0,
            max_voltage_v=4.2,
            nominal_capacity_ah=2.2,
            nominal_internal_resistance_mohm=25.0,
            mass_kg=0.045,
        )
        self.assertEqual(cell_nmc.chemistry, BatteryChemistry.NMC)
        self.assertEqual(cell_nmc.nominal_voltage_v, 3.7)

        # LFP prismatic cell
        cell_lfp = CellConfiguration(
            cell_id="cell_lfp_prismatic",
            chemistry=BatteryChemistry.LFP,
            form_factor=CellFormFactor.PRISMATIC,
            nominal_voltage_v=3.2,
            min_voltage_v=2.5,
            max_voltage_v=3.65,
            nominal_capacity_ah=50.0,
            nominal_internal_resistance_mohm=0.8,
            mass_kg=1.2,
        )
        self.assertEqual(cell_lfp.chemistry, BatteryChemistry.LFP)
        self.assertEqual(cell_lfp.nominal_capacity_ah, 50.0)

    def test_cell_configuration_invalid_raises(self) -> None:
        """Negative resistance or mass must fail."""
        with self.assertRaises(InvalidCellConfigurationError):
            CellConfiguration(
                cell_id="cell_01",
                chemistry=BatteryChemistry.NMC,
                form_factor=CellFormFactor.CYLINDRICAL,
                nominal_voltage_v=3.7,
                min_voltage_v=3.0,
                max_voltage_v=4.2,
                nominal_capacity_ah=2.2,
                nominal_internal_resistance_mohm=-1.0,  # Negative resistance
            )

    # --------------------------------------------------------------------------
    # 7. ModuleConfiguration & PackConfiguration Tests
    # --------------------------------------------------------------------------
    def test_module_configuration_valid(self) -> None:
        """Valid module configuration."""
        cell_cfg = CellConfiguration(
            cell_id="cell_base",
            chemistry=BatteryChemistry.NMC,
            form_factor=CellFormFactor.CYLINDRICAL,
            nominal_voltage_v=3.7,
            min_voltage_v=3.0,
            max_voltage_v=4.2,
            nominal_capacity_ah=2.2,
        )
        mod_cfg = ModuleConfiguration(
            module_id="mod_01",
            topology=BatteryTopology(series_count=3, parallel_count=1),
            cell_config=cell_cfg,
            nominal_voltage_v=11.1,
            nominal_capacity_ah=2.2,
        )
        self.assertEqual(mod_cfg.module_id, "mod_01")
        self.assertEqual(mod_cfg.topology.total_cells, 3)

    def test_pack_configuration_valid(self) -> None:
        """Valid pack configuration with operating limits."""
        ratings = ElectricalRatings(
            nominal_voltage_v=11.1,
            min_voltage_v=9.0,
            max_voltage_v=12.6,
            nominal_capacity_ah=2.2,
            nominal_energy_wh=24.42,
            max_continuous_charge_current_a=2.2,
            max_continuous_discharge_current_a=4.4,
            peak_charge_current_a=4.4,
            peak_discharge_current_a=8.8,
        )
        thermal = ThermalLimits(
            min_charge_temp_c=0.0,
            max_charge_temp_c=45.0,
            min_discharge_temp_c=-20.0,
            max_discharge_temp_c=60.0,
            warning_temp_c=60.0,
            critical_temp_c=80.0,
        )
        pack_cfg = PackConfiguration(
            pack_id="pack_main",
            topology=BatteryTopology(series_count=3, parallel_count=1),
            electrical_ratings=ratings,
            thermal_limits=thermal,
            balancing_delta_v_threshold_mv=15.0,
        )
        self.assertEqual(pack_cfg.pack_id, "pack_main")
        self.assertEqual(pack_cfg.balancing_delta_v_threshold_mv, 15.0)

    def test_operating_limits_composition(self) -> None:
        """OperatingLimits aggregates electrical and thermal limits cleanly."""
        ratings = ElectricalRatings(
            nominal_voltage_v=3.7,
            min_voltage_v=3.0,
            max_voltage_v=4.2,
            nominal_capacity_ah=2.0,
            nominal_energy_wh=7.4,
            max_continuous_charge_current_a=1.0,
            max_continuous_discharge_current_a=2.0,
            peak_charge_current_a=2.0,
            peak_discharge_current_a=4.0,
        )
        thermal = ThermalLimits(
            min_charge_temp_c=0.0,
            max_charge_temp_c=45.0,
            min_discharge_temp_c=-20.0,
            max_discharge_temp_c=60.0,
            warning_temp_c=60.0,
            critical_temp_c=75.0,
        )
        op_limits = OperatingLimits(electrical_ratings=ratings, thermal_limits=thermal)
        self.assertEqual(op_limits.electrical_ratings.nominal_voltage_v, 3.7)
        self.assertEqual(op_limits.thermal_limits.critical_temp_c, 75.0)


if __name__ == "__main__":
    unittest.main()
