"""Unit tests for DigitalTwinInstance runtime coordinator."""

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
from src.events.base import TwinEvent
from src.events.bus import DigitalTwinEventBus
from src.events.types import (
    BatteryAnomalyDetectedEvent,
    StateEstimatedEvent,
    TelemetryReceivedEvent,
    ThermalAlertEvent,
    TwinSynchronizedEvent,
)
from src.ingestion.pipeline import IngestionPipeline
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.ecm.parameters import GenericECMParameters, RCBranchParameters
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.types import ModelMetadata
from src.runtime.config import AnomalyThresholds, ResidualTolerances, RuntimeConfig
from src.runtime.exceptions import (
    RuntimeExecutionError,
    RuntimeInitializationError,
    SynchronizationError,
)
from src.runtime.instance import DigitalTwinInstance
from src.storage.memory_repository import (
    InMemoryStateHistoryRepository,
    InMemoryTelemetryRepository,
)
from src.telemetry.snapshots import TelemetrySnapshot


class TestDigitalTwinInstance(unittest.TestCase):
    """Test suite verifying end-to-end runtime orchestration, co-simulation, events, and storage."""

    def setUp(self) -> None:
        # 1. Domain Pack
        self.ident = BatteryIdentification(
            identifier="pack_alpha",
            display_name="TwinVolt LFP 1S Pack",
            manufacturer="TwinVolt Systems",
            serial_number="TV-PACK-TEST-001",
        )
        self.cell_cfg = CellConfiguration(
            cell_id="cell_lfp_2500",
            chemistry=BatteryChemistry.LFP,
            form_factor=CellFormFactor.CYLINDRICAL,
            nominal_voltage_v=3.2,
            min_voltage_v=2.5,
            max_voltage_v=3.65,
            nominal_capacity_ah=2.5,
            nominal_internal_resistance_mohm=15.0,
            mass_kg=0.07,
        )
        self.electrical_ratings = ElectricalRatings(
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
        self.thermal_limits = ThermalLimits(
            min_charge_temp_c=0.0,
            max_charge_temp_c=45.0,
            min_discharge_temp_c=-20.0,
            max_discharge_temp_c=60.0,
            warning_temp_c=60.0,
            critical_temp_c=80.0,
        )
        self.pack_cfg = PackConfiguration(
            pack_id="pack_alpha",
            topology=BatteryTopology(series_count=1, parallel_count=1),
            electrical_ratings=self.electrical_ratings,
            thermal_limits=self.thermal_limits,
        )
        self.pack = BatteryPack.create_monolithic_pack(
            identification=self.ident,
            configuration=self.pack_cfg,
            cell_config=self.cell_cfg,
        )

        # 2. Mathematical Model
        self.ocv = LinearOCVModel(v_min_v=2.5, v_max_v=3.65)
        self.params = GenericECMParameters(
            nominal_capacity_ah=2.5,
            nominal_voltage_v=3.2,
            series_resistance_r0_ohm=0.015,
            rc_branches=(RCBranchParameters(resistance_r_ohm=0.01, capacitance_c_farad=200.0),),
        )
        self.meta = ModelMetadata(
            model_id="ecm_lfp_test",
            name="LFP ECM",
            paradigm="EQUIVALENT_CIRCUIT",
        )
        self.model = GenericECMModel(
            metadata=self.meta,
            parameters=self.params,
            ocv_model=self.ocv,
        )

        # 3. State Estimator
        self.estimator = ExtendedKalmanFilter(
            estimator_id="ekf_lfp_test",
            parameters=self.params,
            ocv_model=self.ocv,
        )

        # 4. Infrastructure (Event Bus, Repositories, Pipeline)
        self.event_bus = DigitalTwinEventBus()
        self.telemetry_repo = InMemoryTelemetryRepository(max_records_per_system=100)
        self.state_repo = InMemoryStateHistoryRepository(max_records_per_system=100)
        self.pipeline = IngestionPipeline()

        # 5. Configuration & Instance
        self.config = RuntimeConfig(
            system_id="pack_alpha",
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
            config=self.config,
        )

    def test_full_initialization_lifecycle(self) -> None:
        """Instance initializes models, estimators, and internal engines."""
        self.assertFalse(self.instance.is_initialized)
        self.instance.initialize(initial_soc=0.90, initial_soh=1.0, temperature_c=25.0)

        self.assertTrue(self.instance.is_initialized)
        self.assertEqual(self.instance.system_id, "pack_alpha")
        self.assertEqual(self.instance.current_model_state.soc_fraction, 0.90)
        self.assertIsNotNone(self.instance.current_estimation_state)
        self.assertEqual(self.instance.current_estimation_state.soc_fraction, 0.90)

    def test_step_execution_with_events_and_persistence(self) -> None:
        """Step execution correctly advances co-simulation, publishes events, and persists state."""
        events_received: list[TwinEvent] = []
        self.event_bus.subscribe("*", lambda e: events_received.append(e))

        self.instance.initialize(initial_soc=1.0, temperature_c=25.0)

        snap = TelemetrySnapshot(
            snapshot_id="snap_101",
            system_id="pack_alpha",
            timestamp_ns=1_000_000_000,
            pack_voltage_v=3.62,
            pack_current_a=1.5,
            avg_cell_temperature_c=25.2,
        )

        out = self.instance.step(snap)
        self.assertIsNotNone(out)
        self.assertEqual(self.instance.total_steps, 1)

        # Check latest state
        self.assertIsNotNone(self.instance.latest_sync_output)
        self.assertIsNotNone(self.instance.latest_state_record)
        self.assertEqual(self.instance.latest_state_record.system_id, "pack_alpha")

        # Check storage persistence
        self.assertEqual(self.telemetry_repo.count("pack_alpha"), 1)
        self.assertEqual(self.state_repo.count("pack_alpha"), 1)

        # Check event bus publications
        event_types = [e.event_type for e in events_received]
        self.assertIn("telemetry.received", event_types)
        self.assertIn("telemetry.persisted", event_types)
        self.assertIn("twin.synchronized", event_types)
        self.assertIn("state.estimated", event_types)

    def test_anomaly_and_thermal_alert_broadcasting(self) -> None:
        """Step with critical temperature triggers anomaly and thermal alert events."""
        anomalies_received: list[BatteryAnomalyDetectedEvent] = []
        thermal_alerts_received: list[ThermalAlertEvent] = []

        self.event_bus.subscribe(
            "anomaly.detected",
            lambda e: anomalies_received.append(e) if isinstance(e, BatteryAnomalyDetectedEvent) else None,
        )
        self.event_bus.subscribe(
            "alert.thermal",
            lambda e: thermal_alerts_received.append(e) if isinstance(e, ThermalAlertEvent) else None,
        )

        self.instance.initialize(initial_soc=1.0, temperature_c=25.0)

        # High temperature triggering thermal cutoff (68.0°C >= 65.0°C)
        snap_hot = TelemetrySnapshot(
            snapshot_id="snap_hot",
            system_id="pack_alpha",
            timestamp_ns=1_000_000_000,
            pack_voltage_v=3.60,
            pack_current_a=0.0,
            avg_cell_temperature_c=68.0,
        )

        self.instance.step(snap_hot)
        self.assertGreater(len(anomalies_received), 0)
        self.assertGreater(len(thermal_alerts_received), 0)
        severities = [a.severity for a in thermal_alerts_received]
        self.assertIn("EMERGENCY", severities)

    def test_step_raw_payload_ingestion(self) -> None:
        """Step raw processes JSON and CSV payloads through IngestionPipeline."""
        self.instance.initialize(initial_soc=1.0, temperature_c=25.0)

        # JSON dictionary payload
        json_payload = {
            "snapshot_id": "snap_raw_json",
            "system_id": "pack_alpha",
            "timestamp_ns": 1_000_000_000,
            "voltage_v": 3.60,
            "current_a": 2.0,
        }
        out_json = self.instance.step_raw(json_payload)
        self.assertEqual(out_json.step_index, 1)

        # CSV row payload
        csv_payload = "timestamp_s,voltage_v,current_a\n2.0,3.58,2.0\n"
        out_csv = self.instance.step_raw(
            csv_payload,
            format_identifier="CSV",
            source_id="pack_alpha",
        )
        self.assertEqual(out_csv.step_index, 2)
        self.assertEqual(self.instance.total_steps, 2)

    def test_step_raw_malformed_payload_raises(self) -> None:
        """Malformed payload raises SynchronizationError."""
        self.instance.initialize()
        with self.assertRaises(SynchronizationError):
            self.instance.step_raw("{invalid_json: true", format_identifier="JSON")

    def test_runtime_determinism_across_instances(self) -> None:
        """Two identical runtime instances produce identical state trajectories."""
        # Create second identical instance
        model2 = GenericECMModel(metadata=self.meta, parameters=self.params, ocv_model=self.ocv)
        est2 = ExtendedKalmanFilter(estimator_id="ekf_2", parameters=self.params, ocv_model=self.ocv)
        instance2 = DigitalTwinInstance(
            battery_pack=self.pack,
            battery_model=model2,
            state_estimator=est2,
            config=self.config,
        )

        self.instance.initialize(initial_soc=1.0, temperature_c=25.0)
        instance2.initialize(initial_soc=1.0, temperature_c=25.0)

        # Step both instances with identical synthetic snapshots
        for i in range(5):
            snap = TelemetrySnapshot(
                snapshot_id=f"s_{i}",
                system_id="pack_alpha",
                timestamp_ns=1_000_000_000 * (i + 1),
                pack_voltage_v=3.60 - (0.01 * i),
                pack_current_a=2.0,
                avg_cell_temperature_c=25.0 + (0.1 * i),
            )
            out1 = self.instance.step(snap)
            out2 = instance2.step(snap)

            self.assertEqual(out1.model_output.terminal_voltage_v, out2.model_output.terminal_voltage_v)
            self.assertEqual(out1.model_output.state.soc_fraction, out2.model_output.state.soc_fraction)
            self.assertEqual(
                out1.estimation_output.state.soc_fraction,
                out2.estimation_output.state.soc_fraction,
            )
            self.assertEqual(out1.residuals, out2.residuals)

    def test_minimal_instance_without_optional_components(self) -> None:
        """Minimal instance (only pack + model) operates cleanly."""
        minimal_instance = DigitalTwinInstance(
            battery_pack=self.pack,
            battery_model=self.model,
        )
        minimal_instance.initialize()

        snap = TelemetrySnapshot(
            snapshot_id="snap_min",
            system_id="pack_alpha",
            timestamp_ns=1_000_000_000,
            pack_voltage_v=3.60,
        )
        out = minimal_instance.step(snap)
        self.assertEqual(out.step_index, 1)
        self.assertIsNone(out.estimation_output)
        self.assertEqual(minimal_instance.total_steps, 1)

    def test_reset_clears_runtime_instance_state(self) -> None:
        """Reset clears step counter, state records, and flags instance as uninitialized."""
        self.instance.initialize()
        snap = TelemetrySnapshot(
            snapshot_id="snap_1",
            system_id="pack_alpha",
            timestamp_ns=1_000_000_000,
            pack_voltage_v=3.60,
        )
        self.instance.step(snap)
        self.assertEqual(self.instance.total_steps, 1)

        self.instance.reset()
        self.assertFalse(self.instance.is_initialized)
        self.assertEqual(self.instance.total_steps, 0)
        self.assertIsNone(self.instance.latest_sync_output)
        self.assertIsNone(self.instance.latest_state_record)


if __name__ == "__main__":
    unittest.main()
