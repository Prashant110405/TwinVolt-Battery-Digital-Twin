"""Unit tests for Canonical Telemetry Snapshot Model."""

from dataclasses import FrozenInstanceError
import json
import unittest

from src.domain.exceptions import InvalidBatteryIdentifierError
from src.telemetry.enums import (
    CurrentFlowDirection,
    MeasurementProvenance,
    TelemetryQuality,
)
from src.telemetry.exceptions import (
    InvalidTelemetryTimestampError,
    InvalidTelemetryValueError,
)
from src.telemetry.measurements import (
    CellTelemetry,
    ModuleTelemetry,
    TemperatureSensorTelemetry,
)
from src.telemetry.snapshots import TelemetrySnapshot


class TestTelemetrySnapshots(unittest.TestCase):
    """Comprehensive unit tests for TelemetrySnapshot instances and serialization."""

    # --------------------------------------------------------------------------
    # 1. Minimal & Partial Telemetry Tests
    # --------------------------------------------------------------------------
    def test_minimal_telemetry_voltage_current_only(self) -> None:
        """Verify valid snapshot with only macro voltage and current provided."""
        snapshot = TelemetrySnapshot(
            snapshot_id="snap_001",
            system_id="pack_min",
            timestamp_ns=1700000000000000000,
            pack_voltage_v=12.45,
            pack_current_a=1.5,
        )
        self.assertEqual(snapshot.snapshot_id, "snap_001")
        self.assertEqual(snapshot.pack_voltage_v, 12.45)
        self.assertEqual(snapshot.pack_current_a, 1.5)

        # Verify all missing measurements are strictly None (NOT ZERO!)
        self.assertIsNone(snapshot.pack_power_w)
        self.assertIsNone(snapshot.ambient_temperature_c)
        self.assertIsNone(snapshot.soc_fraction)
        self.assertIsNone(snapshot.soh_fraction)
        self.assertIsNone(snapshot.remaining_capacity_ah)
        self.assertIsNone(snapshot.available_energy_wh)
        self.assertEqual(len(snapshot.cell_telemetries), 0)
        self.assertEqual(len(snapshot.modules), 0)
        self.assertEqual(snapshot.total_cell_count, 0)

    # --------------------------------------------------------------------------
    # 2. Single-Cell & Multi-Cell Telemetry Tests
    # --------------------------------------------------------------------------
    def test_single_cell_telemetry_snapshot(self) -> None:
        """1S1P single cell testbench telemetry."""
        cell = CellTelemetry(cell_id="cell_single", voltage_v=3.85, temperature_c=24.2)
        snapshot = TelemetrySnapshot(
            snapshot_id="snap_single_01",
            system_id="bench_1s1p",
            timestamp_ns=1700000000000000000,
            pack_voltage_v=3.85,
            pack_current_a=-2.0,  # Charging current
            charge_discharge_state=CurrentFlowDirection.CHARGING,
            cell_telemetries=(cell,),
        )
        self.assertEqual(snapshot.total_cell_count, 1)
        self.assertEqual(snapshot.max_cell_voltage(), 3.85)
        self.assertEqual(snapshot.min_cell_voltage(), 3.85)
        self.assertEqual(snapshot.cell_voltage_delta_v(), 0.0)

    def test_multi_cell_direct_telemetry_snapshot(self) -> None:
        """3S1P direct pack telemetry (e.g. prototype testbench)."""
        cells = (
            CellTelemetry(cell_id="cell_0", voltage_v=3.70, temperature_c=25.0),
            CellTelemetry(cell_id="cell_1", voltage_v=3.72, temperature_c=25.2),
            CellTelemetry(cell_id="cell_2", voltage_v=3.68, temperature_c=24.9),
        )
        snapshot = TelemetrySnapshot(
            snapshot_id="snap_3s_01",
            system_id="prototype_3s1p",
            timestamp_ns=1700000000000000000,
            pack_voltage_v=11.10,
            pack_current_a=2.5,
            cell_telemetries=cells,
        )
        self.assertEqual(snapshot.total_cell_count, 3)
        self.assertAlmostEqual(snapshot.max_cell_voltage(), 3.72, places=5)
        self.assertAlmostEqual(snapshot.min_cell_voltage(), 3.68, places=5)
        self.assertAlmostEqual(snapshot.cell_voltage_delta_v(), 0.04, places=5)

        voltages = snapshot.get_all_cell_voltages()
        self.assertEqual(voltages["cell_0"], 3.70)
        self.assertEqual(voltages["cell_1"], 3.72)
        self.assertEqual(voltages["cell_2"], 3.68)

    # --------------------------------------------------------------------------
    # 3. Modular Multi-Module & Multi-Sensor Snapshots
    # --------------------------------------------------------------------------
    def test_modular_pack_with_arbitrary_modules_and_sensors(self) -> None:
        """8S2P pack composed of 2 modules with discrete temperature sensors."""
        mod1_cells = tuple(
            CellTelemetry(cell_id=f"m1_c{i}", voltage_v=3.70 + (i * 0.01)) for i in range(4)
        )
        mod2_cells = tuple(
            CellTelemetry(cell_id=f"m2_c{i}", voltage_v=3.71 + (i * 0.01)) for i in range(4)
        )

        mod1 = ModuleTelemetry(
            module_id="mod_1",
            voltage_v=14.86,
            cell_telemetries=mod1_cells,
            temperature_sensors=(
                TemperatureSensorTelemetry(sensor_id="t_mod1_in", temperature_c=23.5),
            ),
        )
        mod2 = ModuleTelemetry(
            module_id="mod_2",
            voltage_v=14.90,
            cell_telemetries=mod2_cells,
            temperature_sensors=(
                TemperatureSensorTelemetry(sensor_id="t_mod2_out", temperature_c=25.1),
            ),
        )

        discrete_pack_temp = TemperatureSensorTelemetry(sensor_id="t_ambient", temperature_c=21.0)

        snapshot = TelemetrySnapshot(
            snapshot_id="snap_modular_01",
            system_id="pack_8s2p",
            timestamp_ns=1700000000000000000,
            pack_voltage_v=29.76,
            pack_current_a=5.0,
            pack_power_w=148.8,
            soc_fraction=0.82,
            soh_fraction=0.98,
            charge_discharge_state=CurrentFlowDirection.DISCHARGING,
            modules=(mod1, mod2),
            discrete_temperatures=(discrete_pack_temp,),
        )

        self.assertEqual(snapshot.total_cell_count, 8)
        self.assertEqual(len(snapshot.modules), 2)
        self.assertEqual(len(snapshot.get_all_cell_voltages()), 8)
        self.assertAlmostEqual(snapshot.max_cell_voltage(), 3.74, places=5)
        self.assertAlmostEqual(snapshot.min_cell_voltage(), 3.70, places=5)

    # --------------------------------------------------------------------------
    # 4. Rich BMS Telemetry Snapshot
    # --------------------------------------------------------------------------
    def test_rich_bms_telemetry_snapshot(self) -> None:
        """Comprehensive BMS telemetry with capacity, energy, health, and status."""
        snapshot = TelemetrySnapshot(
            snapshot_id="snap_bms_rich_01",
            system_id="bess_rack_01",
            timestamp_ns=1700000000000000000,
            sequence_number=10425,
            pack_voltage_v=400.5,
            pack_current_a=-50.0,
            pack_power_w=-20025.0,
            ambient_temperature_c=22.0,
            max_cell_temperature_c=28.5,
            min_cell_temperature_c=24.1,
            avg_cell_temperature_c=26.3,
            soc_fraction=0.65,
            soh_fraction=0.95,
            charge_discharge_state=CurrentFlowDirection.CHARGING,
            bms_operational_state="NORMAL_RUN",
            remaining_capacity_ah=65.0,
            available_energy_wh=26032.5,
            cumulative_charge_ah=15420.0,
            cumulative_discharge_ah=15355.0,
            quality=TelemetryQuality.VALID,
            metadata={"bms_vendor": "OEM_A", "can_channel": "can0"},
        )
        self.assertEqual(snapshot.sequence_number, 10425)
        self.assertEqual(snapshot.remaining_capacity_ah, 65.0)
        self.assertEqual(snapshot.charge_discharge_state, CurrentFlowDirection.CHARGING)
        self.assertEqual(snapshot.metadata["bms_vendor"], "OEM_A")

    # --------------------------------------------------------------------------
    # 5. Invalid Values & Invariant Rejections
    # --------------------------------------------------------------------------
    def test_invalid_snapshot_parameters_raise(self) -> None:
        """Invalid negative voltages, bad timestamps, or bad IDs must fail."""
        # Negative pack voltage
        with self.assertRaises(InvalidTelemetryValueError):
            TelemetrySnapshot(
                snapshot_id="s1",
                system_id="sys1",
                timestamp_ns=1700000000000000000,
                pack_voltage_v=-5.0,
            )

        # Invalid timestamp (negative)
        with self.assertRaises(InvalidTelemetryTimestampError):
            TelemetrySnapshot(
                snapshot_id="s1",
                system_id="sys1",
                timestamp_ns=-100,
            )

        # Invalid identifier
        with self.assertRaises(InvalidBatteryIdentifierError):
            TelemetrySnapshot(
                snapshot_id="",
                system_id="sys1",
                timestamp_ns=1700000000000000000,
            )

        # Invalid SOC fraction (> 1.0)
        with self.assertRaises(InvalidTelemetryValueError):
            TelemetrySnapshot(
                snapshot_id="s1",
                system_id="sys1",
                timestamp_ns=1700000000000000000,
                soc_fraction=1.2,
            )

    # --------------------------------------------------------------------------
    # 6. Serialization Tests
    # --------------------------------------------------------------------------
    def test_deterministic_serialization_to_dict_and_json(self) -> None:
        """Verify that to_dict() produces valid, JSON-serializable primitives."""
        cells = (
            CellTelemetry(cell_id="c1", voltage_v=3.71, temperature_c=25.0),
            CellTelemetry(cell_id="c2", voltage_v=3.70, temperature_c=25.1),
        )
        snapshot = TelemetrySnapshot(
            snapshot_id="snap_json_01",
            system_id="pack_json",
            timestamp_ns=1700000000000000000,
            pack_voltage_v=7.41,
            pack_current_a=2.0,
            soc_fraction=0.80,
            charge_discharge_state=CurrentFlowDirection.DISCHARGING,
            cell_telemetries=cells,
        )

        data = snapshot.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["snapshot_id"], "snap_json_01")
        self.assertEqual(data["charge_discharge_state"], "DISCHARGING")
        self.assertEqual(len(data["direct_cells"]), 2)

        # Ensure json.dumps serializes without error
        json_str = json.dumps(data)
        self.assertIsInstance(json_str, str)
        self.assertIn('"snap_json_01"', json_str)
        self.assertIn('"DISCHARGING"', json_str)

    # --------------------------------------------------------------------------
    # 7. Immutability Tests
    # --------------------------------------------------------------------------
    def test_snapshot_immutability(self) -> None:
        """Verify that snapshot fields cannot be mutated at runtime."""
        snapshot = TelemetrySnapshot(
            snapshot_id="snap_immut",
            system_id="pack_01",
            timestamp_ns=1700000000000000000,
            pack_voltage_v=12.0,
        )
        with self.assertRaises(FrozenInstanceError):
            snapshot.pack_voltage_v = 15.0  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
