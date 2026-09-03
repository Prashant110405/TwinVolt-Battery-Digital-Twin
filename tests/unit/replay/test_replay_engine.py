"""Unit tests for DriveCycleReplayEngine and ReplayResult."""

import unittest

from src.domain.battery.entities import BatteryPack
from src.domain.battery.enums import BatteryChemistry, CellFormFactor
from src.domain.battery.value_objects import (
    BatteryIdentification,
    BatteryTopology,
    CellConfiguration,
    ElectricalRatings,
    PackConfiguration,
    ThermalLimits,
)
from src.estimators.ekf import ExtendedKalmanFilter
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.ecm.parameters import GenericECMParameters, RCBranchParameters
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.types import ModelMetadata
from src.replay.engine import DriveCycleReplayEngine, ReplayConfig, ReplayResult
from src.replay.exceptions import InvalidProfileError, ReplayExecutionError
from src.replay.profiles import (
    create_constant_current_profile,
    create_pulse_discharge_profile,
    create_wltp_class3_profile,
)
from src.runtime.config import RuntimeConfig
from src.runtime.instance import DigitalTwinInstance
from src.runtime.synchronizer import TwinSyncOutput
from src.storage.memory_repository import (
    InMemoryStateHistoryRepository,
    InMemoryTelemetryRepository,
)
from src.telemetry.snapshots import TelemetrySnapshot


class TestDriveCycleReplayEngine(unittest.TestCase):
    """Test suite verifying end-to-end drive cycle replay, repository replay, CSV replay, and tracking metrics."""

    def setUp(self) -> None:
        # Domain Pack
        ident = BatteryIdentification(
            identifier="pack_replay_01",
            display_name="Replay Test Pack",
        )
        cell_cfg = CellConfiguration(
            cell_id="cell_replay",
            chemistry=BatteryChemistry.LFP,
            form_factor=CellFormFactor.CYLINDRICAL,
            nominal_voltage_v=3.2,
            min_voltage_v=2.5,
            max_voltage_v=3.65,
            nominal_capacity_ah=2.5,
        )
        ratings = ElectricalRatings(
            nominal_voltage_v=3.2,
            min_voltage_v=2.5,
            max_voltage_v=3.65,
            nominal_capacity_ah=2.5,
            nominal_energy_wh=8.0,
            max_continuous_charge_current_a=2.5,
            max_continuous_discharge_current_a=5.0,
            peak_charge_current_a=5.0,
            peak_discharge_current_a=10.0,
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
            pack_id="pack_replay_01",
            topology=BatteryTopology(series_count=1, parallel_count=1),
            electrical_ratings=ratings,
            thermal_limits=thermal,
        )
        self.pack = BatteryPack.create_monolithic_pack(
            identification=ident,
            configuration=pack_cfg,
            cell_config=cell_cfg,
        )

        # Mathematical Model & Estimator
        self.ocv = LinearOCVModel(v_min_v=2.5, v_max_v=3.65)
        self.params = GenericECMParameters(
            nominal_capacity_ah=2.5,
            nominal_voltage_v=3.2,
            series_resistance_r0_ohm=0.015,
            rc_branches=(RCBranchParameters(resistance_r_ohm=0.01, capacitance_c_farad=150.0),),
        )
        self.meta = ModelMetadata(
            model_id="ecm_replay",
            name="Replay ECM",
            paradigm="EQUIVALENT_CIRCUIT",
        )
        self.model = GenericECMModel(metadata=self.meta, parameters=self.params, ocv_model=self.ocv)
        self.estimator = ExtendedKalmanFilter(
            estimator_id="ekf_replay",
            parameters=self.params,
            ocv_model=self.ocv,
        )

        # Repositories & Runtime Instance
        self.telemetry_repo = InMemoryTelemetryRepository(max_records_per_system=500)
        self.state_repo = InMemoryStateHistoryRepository(max_records_per_system=500)
        self.config = RuntimeConfig(system_id="pack_replay_01", default_dt_s=1.0)

        self.instance = DigitalTwinInstance(
            battery_pack=self.pack,
            battery_model=self.model,
            state_estimator=self.estimator,
            telemetry_repo=self.telemetry_repo,
            state_repo=self.state_repo,
            config=self.config,
        )

        self.engine = DriveCycleReplayEngine()

    def test_replay_snapshots_full_execution(self) -> None:
        """Replay engine executes sequential snapshots, collects state history, and evaluates metrics."""
        snapshots = []
        for i in range(10):
            snap = TelemetrySnapshot(
                snapshot_id=f"snap_{i:04d}",
                system_id="pack_replay_01",
                timestamp_ns=1_000_000_000 * (i + 1),
                pack_voltage_v=3.60 - 0.01 * i,
                pack_current_a=2.0,
                avg_cell_temperature_c=25.0 + 0.1 * i,
                soc_fraction=1.0 - 0.01 * i,
            )
            snapshots.append(snap)

        progress_calls = []

        def on_progress(step: int, total: int, out: TwinSyncOutput) -> None:
            progress_calls.append((step, total))

        cfg = ReplayConfig(
            evaluate_metrics=True,
            target_voltage_rmse_v=0.10,
            progress_callback=on_progress,
        )

        res = self.engine.replay_snapshots(
            instance=self.instance,
            snapshots=snapshots,
            config=cfg,
            profile_name="test_stream",
        )

        self.assertIsInstance(res, ReplayResult)
        self.assertEqual(res.system_id, "pack_replay_01")
        self.assertEqual(res.total_samples, 10)
        self.assertEqual(res.executed_steps, 10)
        self.assertEqual(res.skipped_samples, 0)
        self.assertEqual(len(res.sync_outputs), 10)
        self.assertEqual(len(res.state_records), 10)
        self.assertEqual(len(progress_calls), 10)
        self.assertEqual(progress_calls[-1], (10, 10))

        # Metrics Report
        self.assertIsNotNone(res.metrics_report)
        self.assertTrue(res.is_passing)
        self.assertIsNotNone(res.metrics_report.voltage_metrics)
        self.assertLess(res.metrics_report.voltage_metrics.rmse, 0.10)

    def test_replay_drive_cycle_profile(self) -> None:
        """Replaying a WLTP profile runs smoothly through runtime."""
        wltp_profile = create_wltp_class3_profile(
            peak_current_a=25.0,
            time_scale_s=100.0,
            dt_s=1.0,
        )

        res = self.engine.replay_profile(
            instance=self.instance,
            profile=wltp_profile,
        )

        self.assertEqual(res.profile_name, wltp_profile.name)
        self.assertEqual(res.executed_steps, 101)
        self.assertEqual(len(res.sync_outputs), 101)
        self.assertAlmostEqual(self.instance.current_model_state.soc_fraction, res.sync_outputs[-1].model_output.state.soc_fraction, places=5)

    def test_replay_from_repository(self) -> None:
        """Replay retrieves snapshots from TelemetryRepository and executes replay."""
        # Populate repository with 5 snapshots
        for i in range(5):
            snap = TelemetrySnapshot(
                snapshot_id=f"repo_snap_{i}",
                system_id="pack_replay_01",
                timestamp_ns=1_000_000_000 * (i + 1),
                pack_voltage_v=3.55,
                pack_current_a=1.0,
            )
            self.telemetry_repo.append(snap)

        res = self.engine.replay_from_repository(
            instance=self.instance,
            repository=self.telemetry_repo,
            system_id="pack_replay_01",
        )

        self.assertEqual(res.executed_steps, 5)
        self.assertEqual(res.total_samples, 5)

    def test_replay_from_csv(self) -> None:
        """Replay parses CSV string dataset and executes co-simulation."""
        csv_data = (
            "timestamp_s,voltage_v,current_a,temperature_c\n"
            "0.0,3.60,0.0,25.0\n"
            "1.0,3.58,2.0,25.1\n"
            "2.0,3.56,2.0,25.2\n"
        )

        res = self.engine.replay_from_csv(
            instance=self.instance,
            csv_content_or_path=csv_data,
            profile_name="csv_test",
        )

        self.assertEqual(res.executed_steps, 3)
        self.assertEqual(res.profile_name, "csv_test")

    def test_replay_determinism_and_input_immutability(self) -> None:
        """Two replays of the same profile produce identical results and do not mutate input data."""
        pulse_profile = create_pulse_discharge_profile(
            pulse_current_a=5.0,
            pulse_duration_s=5.0,
            rest_duration_s=5.0,
            cycles=2,
            dt_s=1.0,
        )
        snapshots = pulse_profile.to_snapshots(system_id="pack_replay_01")
        original_voltages = [s.pack_voltage_v for s in snapshots]

        res1 = self.engine.replay_snapshots(self.instance, snapshots)
        res2 = self.engine.replay_snapshots(self.instance, snapshots)

        # Check determinism
        self.assertEqual(len(res1.sync_outputs), len(res2.sync_outputs))
        for o1, o2 in zip(res1.sync_outputs, res2.sync_outputs):
            self.assertEqual(o1.model_output.terminal_voltage_v, o2.model_output.terminal_voltage_v)
            self.assertEqual(o1.model_output.state.soc_fraction, o2.model_output.state.soc_fraction)

        # Verify input snapshots were not mutated
        current_voltages = [s.pack_voltage_v for s in snapshots]
        self.assertEqual(original_voltages, current_voltages)

    def test_replay_empty_snapshots_raises(self) -> None:
        """Replay rejects empty snapshot sequence."""
        with self.assertRaises(InvalidProfileError):
            self.engine.replay_snapshots(self.instance, [])


if __name__ == "__main__":
    unittest.main()
