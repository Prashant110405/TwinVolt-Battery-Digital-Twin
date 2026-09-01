"""Unit tests for Universal Battery Domain Entities."""

import unittest

from src.domain.battery.entities import (
    BatteryCell,
    BatteryModule,
    BatteryPack,
    BatterySystem,
)
from src.domain.battery.enums import (
    BatteryChemistry,
    BatteryHealthState,
    BatteryOperationalState,
    CellFormFactor,
)
from src.domain.battery.value_objects import (
    BatteryIdentification,
    BatteryTopology,
    CellConfiguration,
    ElectricalRatings,
    ModuleConfiguration,
    PackConfiguration,
    ThermalLimits,
)
from src.domain.exceptions import (
    DomainInvariantViolationError,
    InvalidModuleConfigurationError,
    InvalidPackConfigurationError,
)


class TestBatteryEntities(unittest.TestCase):
    """Unit tests covering domain entity structural hierarchy, invariants, and factory methods."""

    def setUp(self) -> None:
        """Set up reusable test configurations."""
        self.cell_config_nmc = CellConfiguration(
            cell_id="cell_nmc_2200",
            chemistry=BatteryChemistry.NMC,
            form_factor=CellFormFactor.CYLINDRICAL,
            nominal_voltage_v=3.7,
            min_voltage_v=3.0,
            max_voltage_v=4.2,
            nominal_capacity_ah=2.2,
            nominal_internal_resistance_mohm=25.0,
            mass_kg=0.045,
        )
        self.electrical_ratings_3s1p = ElectricalRatings(
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
        self.thermal_limits = ThermalLimits(
            min_charge_temp_c=0.0,
            max_charge_temp_c=45.0,
            min_discharge_temp_c=-20.0,
            max_discharge_temp_c=60.0,
            warning_temp_c=60.0,
            critical_temp_c=80.0,
        )
        self.ident_pack_a = BatteryIdentification(
            identifier="pack_prototype_01",
            display_name="3S1P NMC Test Pack",
            manufacturer="TwinVolt Prototype Bench",
        )

    # --------------------------------------------------------------------------
    # 1. BatteryCell Tests
    # --------------------------------------------------------------------------
    def test_battery_cell_properties(self) -> None:
        """Verify cell entity attributes and delegation to configuration."""
        cell = BatteryCell(cell_index=0, config=self.cell_config_nmc)
        self.assertEqual(cell.cell_index, 0)
        self.assertEqual(cell.cell_id, "cell_nmc_2200")
        self.assertEqual(cell.nominal_voltage_v, 3.7)
        self.assertEqual(cell.nominal_capacity_ah, 2.2)

    def test_battery_cell_negative_index_raises(self) -> None:
        """Negative cell index must raise DomainInvariantViolationError."""
        with self.assertRaises(DomainInvariantViolationError):
            BatteryCell(cell_index=-1, config=self.cell_config_nmc)

    # --------------------------------------------------------------------------
    # 2. BatteryModule Tests
    # --------------------------------------------------------------------------
    def test_battery_module_factory_creation(self) -> None:
        """Create module with 3S1P topology and auto-populated cells."""
        topology = BatteryTopology(series_count=3, parallel_count=1)
        mod_config = ModuleConfiguration(
            module_id="mod_3s_01",
            topology=topology,
            cell_config=self.cell_config_nmc,
            nominal_voltage_v=11.1,
            nominal_capacity_ah=2.2,
        )
        module = BatteryModule.create_with_cells(module_index=0, config=mod_config)
        self.assertEqual(module.module_index, 0)
        self.assertEqual(module.total_cells, 3)
        self.assertEqual(len(module.cells), 3)
        self.assertEqual(module.cells[0].cell_index, 0)
        self.assertEqual(module.cells[2].cell_index, 2)

    def test_battery_module_mismatched_cells_raises(self) -> None:
        """Providing fewer or more cells than declared topology must fail."""
        topology = BatteryTopology(series_count=3, parallel_count=1)
        mod_config = ModuleConfiguration(
            module_id="mod_3s_01",
            topology=topology,
            cell_config=self.cell_config_nmc,
            nominal_voltage_v=11.1,
            nominal_capacity_ah=2.2,
        )
        # Declared 3 cells, but only providing 2
        cells = (
            BatteryCell(cell_index=0, config=self.cell_config_nmc),
            BatteryCell(cell_index=1, config=self.cell_config_nmc),
        )
        with self.assertRaises(InvalidModuleConfigurationError):
            BatteryModule(module_index=0, config=mod_config, cells=cells)

    # --------------------------------------------------------------------------
    # 3. BatteryPack Tests
    # --------------------------------------------------------------------------
    def test_monolithic_pack_creation(self) -> None:
        """Create a monolithic 3S1P pack using factory method."""
        pack_config = PackConfiguration(
            pack_id="pack_3s1p_01",
            topology=BatteryTopology(series_count=3, parallel_count=1),
            electrical_ratings=self.electrical_ratings_3s1p,
            thermal_limits=self.thermal_limits,
        )
        pack = BatteryPack.create_monolithic_pack(
            identification=self.ident_pack_a,
            configuration=pack_config,
            cell_config=self.cell_config_nmc,
        )
        self.assertEqual(pack.pack_id, "pack_3s1p_01")
        self.assertEqual(pack.total_cell_count, 3)
        self.assertEqual(pack.total_module_count, 1)
        self.assertEqual(pack.series_count, 3)
        self.assertEqual(pack.parallel_count, 1)
        self.assertEqual(pack.nominal_voltage_v, 11.1)
        self.assertEqual(pack.nominal_capacity_ah, 2.2)
        self.assertEqual(pack.nominal_energy_wh, 24.42)

        # Query module and cells
        mod = pack.get_module(0)
        self.assertEqual(mod.total_cells, 3)
        self.assertEqual(mod.cells[1].cell_index, 1)

    def test_modular_multi_module_pack(self) -> None:
        """Create an 8S2P pack composed of two 4S2P modules."""
        pack_topology = BatteryTopology(series_count=8, parallel_count=2)  # 16 cells total
        module_topology = BatteryTopology(series_count=4, parallel_count=2)  # 8 cells each

        mod_cfg_1 = ModuleConfiguration(
            module_id="mod_sub_1",
            topology=module_topology,
            cell_config=self.cell_config_nmc,
            nominal_voltage_v=14.8,
            nominal_capacity_ah=4.4,
        )
        mod_cfg_2 = ModuleConfiguration(
            module_id="mod_sub_2",
            topology=module_topology,
            cell_config=self.cell_config_nmc,
            nominal_voltage_v=14.8,
            nominal_capacity_ah=4.4,
        )

        mod1 = BatteryModule.create_with_cells(module_index=0, config=mod_cfg_1)
        mod2 = BatteryModule.create_with_cells(module_index=1, config=mod_cfg_2)

        ratings_8s2p = ElectricalRatings(
            nominal_voltage_v=29.6,
            min_voltage_v=24.0,
            max_voltage_v=33.6,
            nominal_capacity_ah=4.4,
            nominal_energy_wh=130.24,
            max_continuous_charge_current_a=4.4,
            max_continuous_discharge_current_a=8.8,
            peak_charge_current_a=8.8,
            peak_discharge_current_a=17.6,
        )
        pack_cfg = PackConfiguration(
            pack_id="pack_8s2p_modular",
            topology=pack_topology,
            electrical_ratings=ratings_8s2p,
            thermal_limits=self.thermal_limits,
        )
        pack = BatteryPack(
            identification=self.ident_pack_a,
            configuration=pack_cfg,
            modules=(mod1, mod2),
        )
        self.assertEqual(pack.total_module_count, 2)
        self.assertEqual(pack.total_cell_count, 16)
        self.assertEqual(pack.get_module(0).module_id, "mod_sub_1")
        self.assertEqual(pack.get_module(1).module_id, "mod_sub_2")

    def test_pack_mismatched_cells_raises(self) -> None:
        """If sum of module cells != pack topology total, raise error."""
        pack_topology = BatteryTopology(series_count=6, parallel_count=1)  # 6 cells
        mod_topology = BatteryTopology(series_count=2, parallel_count=1)   # 2 cells

        mod_cfg = ModuleConfiguration(
            module_id="mod_0",
            topology=mod_topology,
            cell_config=self.cell_config_nmc,
            nominal_voltage_v=7.4,
            nominal_capacity_ah=2.2,
        )
        mod1 = BatteryModule.create_with_cells(module_index=0, config=mod_cfg)

        ratings = ElectricalRatings(
            nominal_voltage_v=22.2,
            min_voltage_v=18.0,
            max_voltage_v=25.2,
            nominal_capacity_ah=2.2,
            nominal_energy_wh=48.84,
            max_continuous_charge_current_a=2.2,
            max_continuous_discharge_current_a=4.4,
            peak_charge_current_a=4.4,
            peak_discharge_current_a=8.8,
        )
        pack_cfg = PackConfiguration(
            pack_id="pack_6s",
            topology=pack_topology,
            electrical_ratings=ratings,
            thermal_limits=self.thermal_limits,
        )
        # Pack declares 6 cells, but only 1 module of 2 cells is provided
        with self.assertRaises(InvalidPackConfigurationError):
            BatteryPack(
                identification=self.ident_pack_a,
                configuration=pack_cfg,
                modules=(mod1,),
            )

    def test_pack_out_of_bounds_module_query_raises(self) -> None:
        """Querying non-existent module index must raise DomainInvariantViolationError."""
        pack_config = PackConfiguration(
            pack_id="pack_3s1p_01",
            topology=BatteryTopology(series_count=3, parallel_count=1),
            electrical_ratings=self.electrical_ratings_3s1p,
            thermal_limits=self.thermal_limits,
        )
        pack = BatteryPack.create_monolithic_pack(
            identification=self.ident_pack_a,
            configuration=pack_config,
            cell_config=self.cell_config_nmc,
        )
        with self.assertRaises(DomainInvariantViolationError):
            pack.get_module(5)

    # --------------------------------------------------------------------------
    # 4. BatterySystem Tests
    # --------------------------------------------------------------------------
    def test_battery_system_aggregation(self) -> None:
        """Create multi-pack BatterySystem and verify aggregated metrics."""
        pack_cfg = PackConfiguration(
            pack_id="pack_1",
            topology=BatteryTopology(series_count=3, parallel_count=1),
            electrical_ratings=self.electrical_ratings_3s1p,
            thermal_limits=self.thermal_limits,
        )
        pack1 = BatteryPack.create_monolithic_pack(
            identification=BatteryIdentification(identifier="p1", display_name="Pack 1"),
            configuration=pack_cfg,
            cell_config=self.cell_config_nmc,
        )
        pack2 = BatteryPack.create_monolithic_pack(
            identification=BatteryIdentification(identifier="p2", display_name="Pack 2"),
            configuration=pack_cfg,
            cell_config=self.cell_config_nmc,
        )

        system = BatterySystem(
            system_id="bess_facility_01",
            system_name="Substation Battery Energy Storage System",
            packs=(pack1, pack2),
            operational_state=BatteryOperationalState.STANDBY,
            health_state=BatteryHealthState.HEALTHY,
        )
        self.assertEqual(system.total_pack_count, 2)
        self.assertEqual(system.total_cell_count, 6)
        self.assertAlmostEqual(system.total_nominal_energy_wh, 48.84, places=2)
        self.assertEqual(system.get_pack(0).pack_id, "pack_1")
        self.assertEqual(system.get_pack(1).pack_id, "pack_1")

    def test_battery_system_invalid_raises(self) -> None:
        """Empty system name or empty packs must raise error."""
        with self.assertRaises(DomainInvariantViolationError):
            BatterySystem(
                system_id="sys_empty",
                system_name="",
                packs=(),
            )


if __name__ == "__main__":
    unittest.main()
