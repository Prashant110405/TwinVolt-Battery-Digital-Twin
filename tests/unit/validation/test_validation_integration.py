"""Integration tests for ModelValidationEngine with DigitalTwinInstance, REST API, EventBus, and Replay."""

import unittest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import get_twin_service
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
from src.events.bus import DigitalTwinEventBus
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.ecm.parameters import GenericECMParameters, RCBranchParameters
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.types import ModelMetadata
from src.replay.engine import DriveCycleReplayEngine, ReplayConfig
from src.replay.profiles import DriveCycleProfile, ProfilePoint
from src.runtime.instance import DigitalTwinInstance
from src.services.twin_service import TwinApplicationService
from src.telemetry.snapshots import TelemetrySnapshot
from src.validation.engine import ModelValidationEngine
from src.validation.events import BatteryValidationUpdatedEvent
from src.validation.types import ModelValidationState, ValidationConfig


def _create_test_pack(pack_id: str = "pack_val_test") -> BatteryPack:
    ident = BatteryIdentification(identifier=pack_id, display_name="Validation Test Pack")
    cell_cfg = CellConfiguration(
        cell_id="cell_nmc",
        chemistry=BatteryChemistry.NMC,
        form_factor=CellFormFactor.CYLINDRICAL,
        nominal_voltage_v=3.6,
        min_voltage_v=2.8,
        max_voltage_v=4.2,
        nominal_capacity_ah=2.5,
    )
    ratings = ElectricalRatings(
        nominal_voltage_v=3.6,
        min_voltage_v=2.8,
        max_voltage_v=4.2,
        nominal_capacity_ah=2.5,
        nominal_energy_wh=9.0,
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
        pack_id=pack_id,
        topology=BatteryTopology(series_count=1, parallel_count=1),
        electrical_ratings=ratings,
        thermal_limits=thermal,
    )
    return BatteryPack.create_monolithic_pack(
        identification=ident,
        configuration=pack_cfg,
        cell_config=cell_cfg,
    )


def _create_test_model(model_id: str = "model_val_test") -> GenericECMModel:
    meta = ModelMetadata(model_id=model_id, name="TestECM", paradigm="ECM")
    params = GenericECMParameters(
        nominal_capacity_ah=2.5,
        nominal_voltage_v=3.6,
        series_resistance_r0_ohm=0.025,
        rc_branches=(RCBranchParameters(resistance_r_ohm=0.015, capacitance_c_farad=1000.0),),
    )
    ocv = LinearOCVModel(v_min_v=2.8, v_max_v=4.2)
    return GenericECMModel(metadata=meta, parameters=params, ocv_model=ocv)


class TestValidationIntegration(unittest.TestCase):
    """Test suite verifying end-to-end integration across runtime, services, REST API, and replay isolation."""

    def setUp(self) -> None:
        self.pack = _create_test_pack()
        self.model = _create_test_model()
        self.event_bus = DigitalTwinEventBus()
        self.validation_engine = ModelValidationEngine(
            system_id=self.pack.pack_id,
            config=ValidationConfig(window_duration_s=5.0, min_samples_per_window=3),
        )
        self.service = TwinApplicationService(event_bus=self.event_bus)
        self.instance = self.service.create_twin(
            system_id=self.pack.pack_id,
            battery_pack=self.pack,
            battery_model=self.model,
            validation_engine=self.validation_engine,
        )
        self.instance.initialize(initial_soc=0.8, temperature_c=25.0)

        # Set up FastAPI test client
        self.app = create_app()
        self.app.dependency_overrides[get_twin_service] = lambda: self.service
        self.client = TestClient(self.app)

    def test_runtime_stepping_and_event_publishing(self) -> None:
        """Stepping instance updates validation engine and publishes BatteryValidationUpdatedEvent."""
        events: list[BatteryValidationUpdatedEvent] = []
        self.event_bus.subscribe(
            "twin.validation",
            lambda e: events.append(e) if isinstance(e, BatteryValidationUpdatedEvent) else None,
        )

        for i in range(10):
            snap = TelemetrySnapshot(
                system_id=self.pack.pack_id,
                snapshot_id=f"snap_{i}",
                timestamp_ns=i * 1_000_000_000,
                pack_current_a=2.0 if i % 2 == 0 else -1.0,
                pack_voltage_v=3.75,
            )
            self.instance.step(snap)

        report = self.instance.latest_validation_report
        self.assertIsNotNone(report)
        self.assertGreater(len(events), 0)
        self.assertEqual(events[0].event_type, "twin.validation")

    def test_rest_api_validation_endpoints(self) -> None:
        """Verifies GET /api/v1/twins/{id}/validation, /history, and /parameters endpoints."""
        for i in range(8):
            snap = TelemetrySnapshot(
                system_id=self.pack.pack_id,
                snapshot_id=f"snap_{i}",
                timestamp_ns=i * 1_000_000_000,
                pack_current_a=2.0 if i % 2 == 0 else -1.0,
                pack_voltage_v=3.75,
            )
            self.instance.step(snap)

        # 1. Validation Status Endpoint
        resp_val = self.client.get(f"/api/v1/twins/{self.pack.pack_id}/validation")
        self.assertEqual(resp_val.status_code, 200)
        data_val = resp_val.json()
        self.assertEqual(data_val["system_id"], self.pack.pack_id)
        self.assertIn("active_window", data_val)

        # 2. Validation History Endpoint
        resp_hist = self.client.get(f"/api/v1/twins/{self.pack.pack_id}/validation/history")
        self.assertEqual(resp_hist.status_code, 200)
        data_hist = resp_hist.json()
        self.assertIsInstance(data_hist, list)

        # 3. Parameter Validation Endpoint
        resp_params = self.client.get(f"/api/v1/twins/{self.pack.pack_id}/validation/parameters")
        self.assertEqual(resp_params.status_code, 200)
        data_params = resp_params.json()
        self.assertIn("tier", data_params)

    def test_replay_isolation_immutability(self) -> None:
        """Replay execution on separate instance does NOT mutate or contaminate live twin validation state."""
        # Initial live steps
        snap = TelemetrySnapshot(
            system_id=self.pack.pack_id,
            snapshot_id="snap_live_0",
            timestamp_ns=1_000_000_000,
            pack_current_a=2.0,
            pack_voltage_v=3.75,
        )
        self.instance.step(snap)
        live_sample_count = self.instance.latest_validation_report.active_window.sample_count

        # Create isolated replay twin and engine
        replay_model = _create_test_model(model_id="replay_model")
        replay_instance = DigitalTwinInstance(
            battery_pack=self.pack,
            battery_model=replay_model,
            validation_engine=ModelValidationEngine(system_id="replay_twin"),
        )
        replay_instance.initialize(initial_soc=0.8, temperature_c=25.0)

        profile = DriveCycleProfile(
            name="test_pulse",
            points=(
                ProfilePoint(time_s=1.0, current_a=2.0, voltage_v=3.75),
                ProfilePoint(time_s=2.0, current_a=-1.0, voltage_v=3.76),
                ProfilePoint(time_s=3.0, current_a=3.0, voltage_v=3.73),
            ),
        )
        replay_engine = DriveCycleReplayEngine()
        result = replay_engine.replay_profile(
            instance=replay_instance,
            profile=profile,
            config=ReplayConfig(),
        )

        self.assertTrue(result.is_passing)
        # Verify live twin validation state was NOT modified by replay
        self.assertEqual(
            self.instance.latest_validation_report.active_window.sample_count,
            live_sample_count,
        )


if __name__ == "__main__":
    unittest.main()
