"""Level 1 Universality Test Matrix.

Validates that TwinVolt's domain entities, canonical telemetry model,
and declarative profile schemas seamlessly support the entire matrix of battery
chemistries, pack scales (1S to 192S+), topologies, and operational domains.
"""

from pathlib import Path
import unittest

from src.domain.battery.entities import BatteryPack, BatterySystem
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
    PackConfiguration,
    ThermalLimits,
)
from src.schemas.loader import BatteryProfileLoader
from src.telemetry.enums import CurrentFlowDirection, TelemetryQuality
from src.telemetry.measurements import CellTelemetry, ModuleTelemetry
from src.telemetry.snapshots import TelemetrySnapshot


class TestUniversalityMatrix(unittest.TestCase):
    """Test suite executing the full Level 1 Universality & Cross-Model Matrix."""

    def setUp(self) -> None:
        """Locate configuration profiles directory."""
        self.project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.battery_config_dir = self.project_root / "config" / "battery_profiles"

    # --------------------------------------------------------------------------
    # 1. Complete Chemistry Coverage Matrix
    # --------------------------------------------------------------------------
    def test_all_chemistries_supported_in_domain_and_schemas(self) -> None:
        """Verify that every supported chemistry can be configured into valid packs."""
        chemistries_to_test = [
            (BatteryChemistry.NMC, 3.7, 3.0, 4.2, 2.2),
            (BatteryChemistry.LFP, 3.2, 2.5, 3.65, 100.0),
            (BatteryChemistry.LCO, 3.8, 3.0, 4.35, 1.8),
            (BatteryChemistry.NCA, 3.6, 2.8, 4.2, 50.0),
            (BatteryChemistry.LTO, 2.3, 1.5, 2.8, 10.0),
            (BatteryChemistry.SODIUM_ION, 3.1, 2.0, 3.9, 20.0),
            (BatteryChemistry.SOLID_STATE, 3.85, 3.0, 4.4, 30.0),
            (BatteryChemistry.NIMH, 1.2, 1.0, 1.45, 2.5),
            (BatteryChemistry.LEAD_ACID, 2.0, 1.75, 2.4, 60.0),
            (BatteryChemistry.OTHER, 3.0, 2.0, 3.5, 15.0),
        ]

        for chem, nom_v, min_v, max_v, cap in chemistries_to_test:
            with self.subTest(chemistry=chem.value):
                cell_cfg = CellConfiguration(
                    cell_id=f"cell_{chem.value.lower()}",
                    chemistry=chem,
                    form_factor=CellFormFactor.CYLINDRICAL,
                    nominal_voltage_v=nom_v,
                    min_voltage_v=min_v,
                    max_voltage_v=max_v,
                    nominal_capacity_ah=cap,
                )
                ratings = ElectricalRatings(
                    nominal_voltage_v=nom_v * 4,
                    min_voltage_v=min_v * 4,
                    max_voltage_v=max_v * 4,
                    nominal_capacity_ah=cap,
                    nominal_energy_wh=nom_v * 4 * cap,
                    max_continuous_charge_current_a=cap,
                    max_continuous_discharge_current_a=cap * 2,
                    peak_charge_current_a=cap * 2,
                    peak_discharge_current_a=cap * 4,
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
                    pack_id=f"pack_4s1p_{chem.value.lower()}",
                    topology=BatteryTopology(series_count=4, parallel_count=1),
                    electrical_ratings=ratings,
                    thermal_limits=thermal,
                )
                pack = BatteryPack.create_monolithic_pack(
                    identification=BatteryIdentification(
                        identifier=f"pack_{chem.value.lower()}",
                        display_name=f"Generic {chem.value} 4S1P Pack",
                    ),
                    configuration=pack_cfg,
                    cell_config=cell_cfg,
                )
                self.assertEqual(pack.total_cell_count, 4)
                self.assertEqual(pack.series_count, 4)
                self.assertEqual(pack.get_module(0).cells[0].config.chemistry, chem)

    # --------------------------------------------------------------------------
    # 2. Structural Scale & Topology Matrix
    # --------------------------------------------------------------------------
    def test_single_cell_scale(self) -> None:
        """1S1P single cell testbench verification."""
        p = BatteryProfileLoader.create_domain_pack_from_file(
            self.battery_config_dir / "batt_nmc_18650_1s1p.yaml"
        )
        self.assertEqual(p.total_cell_count, 1)
        self.assertEqual(p.series_count, 1)
        self.assertEqual(p.parallel_count, 1)
        self.assertEqual(p.nominal_voltage_v, 3.7)

    def test_prototype_3s1p_bench_scale(self) -> None:
        """3S1P user prototype bench validation."""
        p = BatteryProfileLoader.create_domain_pack_from_file(
            self.battery_config_dir / "batt_nmc_3s1p_prototype.yaml"
        )
        self.assertEqual(p.total_cell_count, 3)
        self.assertEqual(p.series_count, 3)
        self.assertEqual(p.parallel_count, 1)
        self.assertEqual(p.nominal_voltage_v, 11.1)

    def test_automotive_ev_scale(self) -> None:
        """96S2P 400V EV traction pack scale (192 total cells)."""
        p = BatteryProfileLoader.create_domain_pack_from_file(
            self.battery_config_dir / "batt_nmc_96s2p_ev.yaml"
        )
        self.assertEqual(p.total_cell_count, 192)
        self.assertEqual(p.series_count, 96)
        self.assertEqual(p.parallel_count, 2)
        self.assertAlmostEqual(p.nominal_voltage_v, 355.2, places=1)
        self.assertAlmostEqual(p.nominal_energy_wh, 35520.0, places=1)

    def test_grid_scale_bess_multi_pack_aggregation(self) -> None:
        """Multi-pack BatterySystem aggregation (4 rack packs of 16S1P LFP)."""
        bess_pack = BatteryProfileLoader.create_domain_pack_from_file(
            self.battery_config_dir / "batt_lfp_16s1p_bess.yaml"
        )
        system = BatterySystem(
            system_id="bess_grid_01",
            system_name="4-Rack 200kWh Substation Energy Storage",
            packs=(bess_pack, bess_pack, bess_pack, bess_pack),
            operational_state=BatteryOperationalState.STANDBY,
            health_state=BatteryHealthState.HEALTHY,
        )
        self.assertEqual(system.total_pack_count, 4)
        self.assertEqual(system.total_cell_count, 64)
        self.assertAlmostEqual(system.total_nominal_energy_wh, 20480.0, places=1)

    # --------------------------------------------------------------------------
    # 3. Cross-Model End-to-End Flow (Profile -> Domain -> Telemetry)
    # --------------------------------------------------------------------------
    def test_end_to_end_cross_model_consistency(self) -> None:
        """Declarative YAML Profile -> Domain BatteryPack -> Synchronized TelemetrySnapshot."""
        # 1. Load declarative profile
        pack = BatteryProfileLoader.create_domain_pack_from_file(
            self.battery_config_dir / "batt_nmc_3s1p_prototype.yaml"
        )

        # 2. Construct matching Canonical Telemetry observation
        cells_telemetry = tuple(
            CellTelemetry(
                cell_id=f"cell_{i}",
                voltage_v=3.70 + (i * 0.02),
                temperature_c=25.0 + (i * 0.5),
                soc_fraction=0.80 - (i * 0.01),
                quality=TelemetryQuality.VALID,
            )
            for i in range(pack.total_cell_count)
        )

        snapshot = TelemetrySnapshot(
            snapshot_id="snap_e2e_001",
            system_id=pack.pack_id,
            timestamp_ns=1700000000000000000,
            pack_voltage_v=sum(c.voltage_v for c in cells_telemetry if c.voltage_v is not None),
            pack_current_a=2.0,
            charge_discharge_state=CurrentFlowDirection.DISCHARGING,
            cell_telemetries=cells_telemetry,
        )

        # 3. Cross-validate consistency
        self.assertEqual(snapshot.system_id, pack.pack_id)
        self.assertEqual(snapshot.total_cell_count, pack.total_cell_count)
        self.assertAlmostEqual(snapshot.pack_voltage_v, 11.16, places=5)
        self.assertAlmostEqual(snapshot.cell_voltage_delta_v(), 0.04, places=5)
        self.assertAlmostEqual(snapshot.max_cell_voltage(), 3.74, places=5)
        self.assertAlmostEqual(snapshot.min_cell_voltage(), 3.70, places=5)


if __name__ == "__main__":
    unittest.main()
