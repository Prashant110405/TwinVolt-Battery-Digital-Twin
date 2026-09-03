"""Integration tests for Online Parameter Identification, Runtime, Event Bus, REST API, and Replay Isolation."""

import unittest
from fastapi.testclient import TestClient

from src.api.app import create_app
from src.api.dependencies import create_default_services
from src.calibration.events import ParameterIdentificationUpdatedEvent
from src.calibration.rls import RLSParameterIdentifier
from src.calibration.types import ParameterStateClassification, RLSConfig
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
from src.replay.profiles import DriveCycleProfile
from src.runtime.instance import DigitalTwinInstance
from src.telemetry.snapshots import TelemetrySnapshot


class TestCalibrationIntegration(unittest.TestCase):
    """Test suite verifying end-to-end parameter identification runtime, REST, events, and replay isolation."""

    def setUp(self) -> None:
        self.ident = BatteryIdentification(identifier="pack_cal_test", display_name="Calibration Test Pack")
        self.cell_cfg = CellConfiguration(
            cell_id="cell_nmc",
            chemistry=BatteryChemistry.NMC,
            form_factor=CellFormFactor.CYLINDRICAL,
            nominal_voltage_v=3.6,
            min_voltage_v=2.8,
            max_voltage_v=4.2,
            nominal_capacity_ah=2.5,
        )
        self.ratings = ElectricalRatings(
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
        self.thermal = ThermalLimits(
            min_charge_temp_c=0.0,
            max_charge_temp_c=45.0,
            min_discharge_temp_c=-20.0,
            max_discharge_temp_c=60.0,
            warning_temp_c=60.0,
            critical_temp_c=80.0,
        )
        self.pack_cfg = PackConfiguration(
            pack_id="pack_cal_test",
            topology=BatteryTopology(series_count=1, parallel_count=1),
            electrical_ratings=self.ratings,
            thermal_limits=self.thermal,
        )
        self.pack = BatteryPack.create_monolithic_pack(
            identification=self.ident,
            configuration=self.pack_cfg,
            cell_config=self.cell_cfg,
        )

    def _build_model(self, r0: float = 0.025, r1: float = 0.015, c1: float = 1000.0) -> GenericECMModel:
        ocv = LinearOCVModel(v_min_v=2.8, v_max_v=4.2)
        params = GenericECMParameters(
            nominal_capacity_ah=2.5,
            nominal_voltage_v=3.6,
            series_resistance_r0_ohm=r0,
            rc_branches=(RCBranchParameters(resistance_r_ohm=r1, capacitance_c_farad=c1),),
        )
        return GenericECMModel(
            metadata=ModelMetadata(model_id="ecm_cal", name="CalECM", paradigm="ECM"),
            parameters=params,
            ocv_model=ocv,
        )

    def test_runtime_stepping_and_zero_model_mutation(self) -> None:
        """DigitalTwinInstance step executes RLS identification without mutating active model parameters."""
        event_bus = DigitalTwinEventBus()
        received_events = []

        event_bus.subscribe(
            "*",
            lambda evt: received_events.append(evt) if isinstance(evt, ParameterIdentificationUpdatedEvent) else None,
        )

        model = self._build_model(r0=0.025)
        identifier = RLSParameterIdentifier(
            system_id="twin_cal_rt",
            nominal_r0_ohm=0.025,
            nominal_r1_ohm=0.015,
            nominal_c1_farad=1000.0,
        )

        twin = DigitalTwinInstance(
            battery_pack=self.pack,
            battery_model=model,
            parameter_identifier=identifier,
            event_bus=event_bus,
        )
        twin.initialize(initial_soc=0.8, temperature_c=25.0)

        # Step 1: Initial step populates regressors
        s0 = TelemetrySnapshot(
            system_id="twin_cal_rt",
            snapshot_id="snap_0",
            timestamp_ns=0,
            pack_current_a=3.0,
            pack_voltage_v=3.9,
        )
        twin.step(s0)

        # Step 2: Second step with dynamic current
        s1 = TelemetrySnapshot(
            system_id="twin_cal_rt",
            snapshot_id="snap_1",
            timestamp_ns=1_000_000_000,
            pack_current_a=-2.0,
            pack_voltage_v=4.0,
        )
        twin.step(s1)

        self.assertIsNotNone(twin.latest_identified_parameters)
        self.assertEqual(twin.latest_identified_parameters.classification, ParameterStateClassification.ONLINE_IDENTIFIED)

        # CRITICAL: Verify active model parameters were NOT mutated in-place
        self.assertEqual(model.ecm_parameters.series_resistance_r0_ohm, 0.025)
        self.assertEqual(model.ecm_parameters.rc_branches[0].resistance_r_ohm, 0.015)
        self.assertEqual(model.ecm_parameters.rc_branches[0].capacitance_c_farad, 1000.0)

    def test_event_throttling_policy(self) -> None:
        """ParameterIdentificationUpdatedEvent throttles events when R0 change is below 1%."""
        event_bus = DigitalTwinEventBus()
        published_events = []

        event_bus.subscribe(
            "*",
            lambda evt: published_events.append(evt) if isinstance(evt, ParameterIdentificationUpdatedEvent) else None,
        )

        model = self._build_model()
        identifier = RLSParameterIdentifier(
            system_id="twin_throttle",
            nominal_r0_ohm=0.025,
        )
        twin = DigitalTwinInstance(
            battery_pack=self.pack,
            battery_model=model,
            parameter_identifier=identifier,
            event_bus=event_bus,
        )
        twin.initialize(initial_soc=0.8, temperature_c=25.0)

        # First valid update step emits an event
        for i in range(15):
            s = TelemetrySnapshot(
                system_id="twin_throttle",
                snapshot_id=f"snap_{i}",
                timestamp_ns=(i + 1) * 1_000_000_000,
                pack_current_a=2.0 if i % 2 == 0 else 2.005,  # Sub-1% variation
                pack_voltage_v=3.85,
            )
            twin.step(s)

        # Assert events are throttled and not emitted every single step (e.g. <= 3 for 15 steps)
        self.assertLessEqual(len(published_events), 3)

    def test_rest_api_calibration_endpoint(self) -> None:
        """GET /api/v1/twins/{system_id}/calibration returns 200 OK and serialized calibration metrics."""
        services = create_default_services()
        app = create_app(services=services)

        services.pack_service.register_pack(self.pack)
        model = self._build_model()
        identifier = RLSParameterIdentifier(system_id="twin_api_cal", nominal_r0_ohm=0.025)

        twin = services.twin_service.create_twin(
            system_id="twin_api_cal",
            battery_pack=self.pack,
            battery_model=model,
            parameter_identifier=identifier,
        )
        twin.initialize(initial_soc=0.8, temperature_c=25.0)

        with TestClient(app) as client:
            # Query unstepped initial state
            res = client.get("/api/v1/twins/twin_api_cal/calibration")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["system_id"], "twin_api_cal")
            self.assertEqual(data["classification"], "CONFIGURED_NOMINAL")
            self.assertEqual(data["gating_status"], "UNSTEPPED")

            # Step twin with telemetry
            s0 = TelemetrySnapshot(
                system_id="twin_api_cal",
                snapshot_id="s0",
                timestamp_ns=1_000_000_000,
                pack_current_a=3.0,
                pack_voltage_v=3.9,
            )
            twin.step(s0)

            res_stepped = client.get("/api/v1/twins/twin_api_cal/calibration")
            self.assertEqual(res_stepped.status_code, 200)
            data_stepped = res_stepped.json()
            self.assertEqual(data_stepped["classification"], "ONLINE_IDENTIFIED")
            self.assertIn("r0_ohm", data_stepped)
            self.assertIn("coefficient_covariance_diagonal", data_stepped)

    def test_replay_state_isolation(self) -> None:
        """Drive cycle replay operates in isolation and does NOT mutate live operational twin calibration state."""
        # 1. Operational live twin
        from src.runtime.synchronizer import RuntimeConfig
        model_live = self._build_model(r0=0.025)
        identifier_live = RLSParameterIdentifier(system_id="twin_live", nominal_r0_ohm=0.025)
        twin_live = DigitalTwinInstance(
            battery_pack=self.pack,
            battery_model=model_live,
            parameter_identifier=identifier_live,
            config=RuntimeConfig(system_id="twin_live"),
        )
        twin_live.initialize(initial_soc=0.8, temperature_c=25.0)

        # Set initial live step
        s_live = TelemetrySnapshot(
            system_id="twin_live",
            snapshot_id="s_live",
            timestamp_ns=1_000_000_000,
            pack_current_a=2.0,
            pack_voltage_v=3.9,
        )
        twin_live.step(s_live)
        initial_live_r0 = twin_live.latest_identified_parameters.r0_ohm

        # 2. Replay twin with synthetic profile
        model_replay = self._build_model(r0=0.050)
        identifier_replay = RLSParameterIdentifier(system_id="twin_replay", nominal_r0_ohm=0.050)
        twin_replay = DigitalTwinInstance(
            battery_pack=self.pack,
            battery_model=model_replay,
            parameter_identifier=identifier_replay,
            config=RuntimeConfig(system_id="twin_replay"),
        )
        twin_replay.initialize(initial_soc=0.8, temperature_c=25.0)

        replay_engine = DriveCycleReplayEngine()
        from src.replay.profiles import ProfilePoint
        profile = DriveCycleProfile(
            name="test_replay_cal",
            points=(
                ProfilePoint(time_s=1.0, current_a=5.0, voltage_v=3.7),
                ProfilePoint(time_s=2.0, current_a=-3.0, voltage_v=4.1),
            ),
        )
        result = replay_engine.replay_profile(instance=twin_replay, profile=profile, config=ReplayConfig())

        self.assertTrue(result.is_passing)

        # Assert replay twin has its own distinct identified state
        self.assertIsNotNone(twin_replay.latest_identified_parameters)
        # Assert live operational twin state was NOT modified by replay
        self.assertEqual(twin_live.latest_identified_parameters.r0_ohm, initial_live_r0)
        self.assertEqual(twin_live.system_id, "twin_live")


if __name__ == "__main__":
    unittest.main()
