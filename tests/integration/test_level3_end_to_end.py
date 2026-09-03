"""End-to-End Level 3 System Integration Test Suite.

Verifies the end-to-end integration across all five Level 3 subsystems:
1. Ingestion Pipeline & Protocol Adapters (Subtask 3.1)
2. Time-Series Persistence & Storage Repositories (Subtask 3.2)
3. Internal Event Bus & Observability Engine (Subtask 3.3)
4. Digital Twin Runtime Core & Real-Time Synchronizer (Subtask 3.4)
5. Drive-Cycle Replay & Tracking Evaluator (Subtask 3.5)
"""

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
from src.events.bus import DigitalTwinEventBus
from src.events.types import (
    BatteryAnomalyDetectedEvent,
    StateEstimatedEvent,
    TelemetryPersistedEvent,
    TelemetryReceivedEvent,
    ThermalAlertEvent,
    TwinSynchronizedEvent,
)
from src.ingestion.adapters.csv_adapter import CSVTelemetryAdapter
from src.ingestion.pipeline import IngestionPipeline
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.ecm.parameters import GenericECMParameters, RCBranchParameters
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.types import ModelMetadata
from src.replay.engine import DriveCycleReplayEngine, ReplayConfig
from src.replay.profiles import create_wltp_class3_profile
from src.runtime.config import AnomalyThresholds, ResidualTolerances, RuntimeConfig
from src.runtime.instance import DigitalTwinInstance
from src.storage.memory_repository import (
    InMemoryStateHistoryRepository,
    InMemoryTelemetryRepository,
)
from src.telemetry.snapshots import TelemetrySnapshot


class TestLevel3EndToEndIntegration(unittest.TestCase):
    """Formal Level 3 End-to-End Integration Verification Suite."""

    def setUp(self) -> None:
        # 1. Level 1 Domain Entities
        self.ident = BatteryIdentification(
            identifier="pack_l3_e2e",
            display_name="Level 3 Integration Pack",
            manufacturer="TwinVolt Systems",
            serial_number="TV-L3-E2E-001",
        )
        self.cell_cfg = CellConfiguration(
            cell_id="cell_lfp_integration",
            chemistry=BatteryChemistry.LFP,
            form_factor=CellFormFactor.CYLINDRICAL,
            nominal_voltage_v=3.2,
            min_voltage_v=2.5,
            max_voltage_v=3.65,
            nominal_capacity_ah=2.5,
            nominal_internal_resistance_mohm=15.0,
            mass_kg=0.07,
        )
        self.ratings = ElectricalRatings(
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
        self.thermal = ThermalLimits(
            min_charge_temp_c=0.0,
            max_charge_temp_c=45.0,
            min_discharge_temp_c=-20.0,
            max_discharge_temp_c=60.0,
            warning_temp_c=60.0,
            critical_temp_c=80.0,
        )
        self.pack_cfg = PackConfiguration(
            pack_id="pack_l3_e2e",
            topology=BatteryTopology(series_count=1, parallel_count=1),
            electrical_ratings=self.ratings,
            thermal_limits=self.thermal,
        )
        self.pack = BatteryPack.create_monolithic_pack(
            identification=self.ident,
            configuration=self.pack_cfg,
            cell_config=self.cell_cfg,
        )

        # 2. Level 2 Physical/Mathematical Models & Estimators
        self.ocv = LinearOCVModel(v_min_v=2.5, v_max_v=3.65)
        self.params = GenericECMParameters(
            nominal_capacity_ah=2.5,
            nominal_voltage_v=3.2,
            series_resistance_r0_ohm=0.015,
            rc_branches=(RCBranchParameters(resistance_r_ohm=0.01, capacitance_c_farad=150.0),),
        )
        self.meta = ModelMetadata(
            model_id="ecm_l3_e2e",
            name="Level 3 ECM",
            paradigm="EQUIVALENT_CIRCUIT",
        )
        self.model = GenericECMModel(metadata=self.meta, parameters=self.params, ocv_model=self.ocv)
        self.estimator = ExtendedKalmanFilter(
            estimator_id="ekf_l3_e2e",
            parameters=self.params,
            ocv_model=self.ocv,
        )

        # 3. Level 3 Subsystems (Ingestion, Storage, Event Bus, Runtime, Replay)
        self.event_bus = DigitalTwinEventBus()
        self.telemetry_repo = InMemoryTelemetryRepository(max_records_per_system=1000)
        self.state_repo = InMemoryStateHistoryRepository(max_records_per_system=1000)
        self.pipeline = IngestionPipeline()

        self.runtime_config = RuntimeConfig(
            system_id="pack_l3_e2e",
            default_dt_s=1.0,
            strict_monotonicity=True,
            auto_publish_events=True,
            auto_persist_records=True,
            enable_anomaly_detection=True,
            tolerances=ResidualTolerances(
                voltage_warning_threshold_v=0.05,
                voltage_critical_threshold_v=0.15,
                temperature_warning_threshold_c=3.0,
                temperature_critical_threshold_c=8.0,
            ),
            anomaly_thresholds=AnomalyThresholds(
                critical_thermal_cutoff_c=65.0,
                max_temperature_rate_c_per_s=0.5,
            ),
        )

        self.instance = DigitalTwinInstance(
            battery_pack=self.pack,
            battery_model=self.model,
            state_estimator=self.estimator,
            event_bus=self.event_bus,
            telemetry_repo=self.telemetry_repo,
            state_repo=self.state_repo,
            ingestion_pipeline=self.pipeline,
            config=self.runtime_config,
        )

        self.replay_engine = DriveCycleReplayEngine()

    def test_full_pipeline_ingestion_simulation_persistence_and_events(self) -> None:
        """Verifies full live ingestion -> event dispatch -> dual-track step -> state history persistence."""
        events_captured: list[object] = []

        # Subscribe to all published domain event types
        self.event_bus.subscribe("telemetry.received", lambda e: events_captured.append(e))
        self.event_bus.subscribe("telemetry.persisted", lambda e: events_captured.append(e))
        self.event_bus.subscribe("twin.synchronized", lambda e: events_captured.append(e))
        self.event_bus.subscribe("state.estimated", lambda e: events_captured.append(e))

        # 1. Initialize instance
        self.instance.initialize(initial_soc=1.0, temperature_c=25.0)

        # 2. Ingest raw CSV payloads via step_raw()
        csv_sample = (
            "timestamp_s,voltage_v,current_a,temperature_c\n"
            "0.0,3.60,0.0,25.0\n"
        )
        sync_out_1 = self.instance.step_raw(csv_sample, format_identifier="CSV")

        self.assertEqual(sync_out_1.step_index, 1)
        self.assertEqual(self.instance.total_steps, 1)

        # Ingest 2nd payload with active 2.0A discharge
        csv_sample_2 = (
            "timestamp_s,voltage_v,current_a,temperature_c\n"
            "1.0,3.57,2.0,25.1\n"
        )
        sync_out_2 = self.instance.step_raw(csv_sample_2, format_identifier="CSV")
        self.assertEqual(sync_out_2.step_index, 2)

        # 3. Verify event propagation
        telemetry_events = [e for e in events_captured if isinstance(e, TelemetryReceivedEvent)]
        sync_events = [e for e in events_captured if isinstance(e, TwinSynchronizedEvent)]
        est_events = [e for e in events_captured if isinstance(e, StateEstimatedEvent)]
        persist_events = [e for e in events_captured if isinstance(e, TelemetryPersistedEvent)]

        self.assertEqual(len(telemetry_events), 2)
        self.assertEqual(len(sync_events), 2)
        self.assertEqual(len(est_events), 2)
        self.assertEqual(len(persist_events), 2)

        # 4. Verify storage repository persistence
        stored_telemetry = self.telemetry_repo.query_by_time_range(system_id="pack_l3_e2e")
        stored_states = self.state_repo.query_by_time_range(system_id="pack_l3_e2e")

        self.assertEqual(len(stored_telemetry), 2)
        self.assertEqual(len(stored_states), 2)
        self.assertEqual(stored_states[-1].record_id, self.instance.latest_state_record.record_id)
        self.assertEqual(stored_states[-1].system_id, "pack_l3_e2e")

    def test_physics_anomaly_detection_and_thermal_alert_broadcasting(self) -> None:
        """Verifies physics anomaly detector broadcasts critical thermal alert events across the bus."""
        alerts_captured: list[ThermalAlertEvent] = []
        anomalies_captured: list[BatteryAnomalyDetectedEvent] = []

        self.event_bus.subscribe("alert.thermal", lambda e: alerts_captured.append(e) if isinstance(e, ThermalAlertEvent) else None)
        self.event_bus.subscribe("anomaly.detected", lambda e: anomalies_captured.append(e) if isinstance(e, BatteryAnomalyDetectedEvent) else None)

        self.instance.initialize(initial_soc=1.0, temperature_c=25.0)

        # Step 1: Nominal step
        snap_nom = TelemetrySnapshot(
            snapshot_id="snap_nom",
            system_id="pack_l3_e2e",
            timestamp_ns=1_000_000_000,
            pack_voltage_v=3.60,
            pack_current_a=0.0,
            avg_cell_temperature_c=25.0,
        )
        self.instance.step(snap_nom)
        self.assertEqual(len(alerts_captured), 0)
        self.assertEqual(len(anomalies_captured), 0)

        # Step 2: Critical temperature jump (70.0°C >= critical cutoff 65.0°C)
        snap_hot = TelemetrySnapshot(
            snapshot_id="snap_hot",
            system_id="pack_l3_e2e",
            timestamp_ns=2_000_000_000,
            pack_voltage_v=3.60,
            pack_current_a=0.0,
            avg_cell_temperature_c=70.0,
        )
        self.instance.step(snap_hot)

        self.assertGreater(len(alerts_captured), 0)
        self.assertGreater(len(anomalies_captured), 0)
        self.assertIn("EMERGENCY", [a.severity for a in alerts_captured])
        self.assertEqual(self.instance.total_anomalies, len(anomalies_captured))

    def test_drive_cycle_replay_with_tracking_evaluation_and_storage(self) -> None:
        """Verifies drive cycle replay runs standard WLTP profile, evaluates RMSE/MAE/R^2, and records state."""
        wltp_profile = create_wltp_class3_profile(
            peak_current_a=10.0,
            time_scale_s=120.0,
            dt_s=1.0,
        )

        replay_cfg = ReplayConfig(
            evaluate_metrics=True,
            target_voltage_rmse_v=0.10,
        )

        result = self.replay_engine.replay_profile(
            instance=self.instance,
            profile=wltp_profile,
            config=replay_cfg,
        )

        self.assertEqual(result.executed_steps, 121)
        self.assertEqual(result.total_samples, 121)
        self.assertEqual(len(result.sync_outputs), 121)
        self.assertEqual(len(result.state_records), 121)

        # Verify tracking error report
        self.assertIsNotNone(result.metrics_report)
        self.assertTrue(result.is_passing)

        # Verify state persistence query
        stored_states = self.state_repo.query_by_time_range(
            system_id="pack_l3_e2e",
            start_time_ns=result.start_timestamp_ns,
            end_time_ns=result.end_timestamp_ns,
        )
        self.assertEqual(len(stored_states), 121)

    def test_multi_system_isolation_in_shared_infrastructure(self) -> None:
        """Verifies two distinct battery systems run isolated instances over shared event bus and repositories."""
        # Setup second pack
        ident_beta = BatteryIdentification(identifier="pack_l3_beta", display_name="Pack Beta")
        pack_beta = BatteryPack.create_monolithic_pack(
            identification=ident_beta,
            configuration=self.pack_cfg,
            cell_config=self.cell_cfg,
        )
        model_beta = GenericECMModel(metadata=self.meta, parameters=self.params, ocv_model=self.ocv)
        estimator_beta = ExtendedKalmanFilter(estimator_id="ekf_beta", parameters=self.params, ocv_model=self.ocv)

        cfg_beta = RuntimeConfig(system_id="pack_l3_beta", default_dt_s=1.0)
        instance_beta = DigitalTwinInstance(
            battery_pack=pack_beta,
            battery_model=model_beta,
            state_estimator=estimator_beta,
            event_bus=self.event_bus,
            telemetry_repo=self.telemetry_repo,
            state_repo=self.state_repo,
            config=cfg_beta,
        )

        self.instance.initialize(initial_soc=1.0, temperature_c=25.0)
        instance_beta.initialize(initial_soc=0.80, temperature_c=30.0)

        # Step system Alpha
        snap_alpha = TelemetrySnapshot(
            snapshot_id="snap_a1",
            system_id="pack_l3_e2e",
            timestamp_ns=1_000_000_000,
            pack_voltage_v=3.60,
            pack_current_a=2.0,
        )
        self.instance.step(snap_alpha)

        # Step system Beta
        snap_beta = TelemetrySnapshot(
            snapshot_id="snap_b1",
            system_id="pack_l3_beta",
            timestamp_ns=1_000_000_000,
            pack_voltage_v=3.40,
            pack_current_a=4.0,
        )
        instance_beta.step(snap_beta)

        # Verify storage isolation
        alpha_records = self.state_repo.query_by_time_range(system_id="pack_l3_e2e")
        beta_records = self.state_repo.query_by_time_range(system_id="pack_l3_beta")

        self.assertEqual(len(alpha_records), 1)
        self.assertEqual(len(beta_records), 1)
        self.assertEqual(alpha_records[0].system_id, "pack_l3_e2e")
        self.assertEqual(beta_records[0].system_id, "pack_l3_beta")


if __name__ == "__main__":
    unittest.main()
