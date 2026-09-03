"""Unit and integration tests for State of Health (SOH) Estimator."""

import unittest
from fastapi.testclient import TestClient

from src.analytics.degradation import ArrheniusSEIEmpiricalDegradationModel, DegradationParameters
from src.analytics.events import BatteryHealthUpdatedEvent
from src.analytics.soh import ThroughputHealthEstimator
from src.analytics.types import CalibrationStatus
from src.api.app import create_app
from src.api.dependencies import create_default_services
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
from src.runtime.instance import DigitalTwinInstance
from src.storage.memory_repository import InMemoryStateHistoryRepository, InMemoryTelemetryRepository
from src.telemetry.snapshots import TelemetrySnapshot


class TestStateOfHealthEstimator(unittest.TestCase):
    """Test suite verifying ThroughputHealthEstimator SOH calculations and runtime/API integration."""

    def setUp(self) -> None:
        self.ident = BatteryIdentification(identifier="pack_soh_test", display_name="SOH Test Pack")
        self.cell_cfg = CellConfiguration(
            cell_id="cell_lfp",
            chemistry=BatteryChemistry.LFP,
            form_factor=CellFormFactor.CYLINDRICAL,
            nominal_voltage_v=3.2,
            min_voltage_v=2.5,
            max_voltage_v=3.65,
            nominal_capacity_ah=2.5,
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
            pack_id="pack_soh_test",
            topology=BatteryTopology(series_count=1, parallel_count=1),
            electrical_ratings=self.ratings,
            thermal_limits=self.thermal,
        )
        self.pack = BatteryPack.create_monolithic_pack(
            identification=self.ident,
            configuration=self.pack_cfg,
            cell_config=self.cell_cfg,
        )

    def test_initial_health_state(self) -> None:
        """Initial health state reports 1.0 SOH and UNCALIBRATED_PARAMETRIC_MODEL status."""
        estimator = ThroughputHealthEstimator(
            system_id="twin_01",
            nominal_capacity_ah=2.5,
            nominal_resistance_ohm=0.02,
        )

        s0 = TelemetrySnapshot(
            system_id="twin_01",
            snapshot_id="snap_00",
            timestamp_ns=1_000_000_000,
            pack_current_a=0.0,
            pack_voltage_v=3.3,
        )
        health = estimator.update(s0)

        self.assertEqual(health.soh_capacity_fraction, 1.0)
        self.assertEqual(health.soh_resistance_fraction, 1.0)
        self.assertEqual(health.soh_unified_fraction, 1.0)
        self.assertEqual(health.cumulative_throughput_ah, 0.0)
        self.assertEqual(health.equivalent_full_cycles, 0.0)
        self.assertEqual(health.calibration_status, CalibrationStatus.UNCALIBRATED_PARAMETRIC_MODEL)

    def test_degradation_over_cycling(self) -> None:
        """Estimator decreases SOH_Capacity and increases estimated R0 as cycling accumulates."""
        params = DegradationParameters(
            calendar_ref_rate_per_day=0.0,
            cycling_ref_rate_per_efc=0.001,       # 0.1% per EFC
            resistance_growth_rate_per_efc=0.002,  # 0.2% per EFC
            eol_resistance_growth_limit=1.0,
        )
        model = ArrheniusSEIEmpiricalDegradationModel(params)
        estimator = ThroughputHealthEstimator(
            system_id="twin_cycling",
            nominal_capacity_ah=2.0,
            nominal_resistance_ohm=0.015,
            degradation_model=model,
            max_integration_interval_s=7200.0,
        )

        # Simulate 100 Equivalent Full Cycles:
        # Total throughput = 100 * 2 * 2.0 = 400 Ah
        # Over 40 steps of 10 Ah each (dt = 3600s, I = 10A)
        for i in range(40):
            s = TelemetrySnapshot(
                system_id="twin_cycling",
                snapshot_id=f"snap_{i}",
                timestamp_ns=(i + 1) * 3600 * 1_000_000_000,
                pack_current_a=10.0,
                pack_voltage_v=3.2,
            )
            estimator.update(s, dt_s=3600.0)

        health = estimator.get_health_state()
        self.assertIsNotNone(health)

        # Total throughput = 40 * 10 Ah = 400 Ah -> EFC = 400 / (2 * 2.0) = 100 EFC
        self.assertAlmostEqual(health.equivalent_full_cycles, 100.0, places=3)

        # Capacity fade = 100 * 0.001 = 0.10 -> SOH_C = 0.90
        self.assertAlmostEqual(health.capacity_fade_fraction, 0.10, places=3)
        self.assertAlmostEqual(health.soh_capacity_fraction, 0.90, places=3)
        self.assertAlmostEqual(health.estimated_capacity_ah, 1.80, places=3)

        # Resistance growth = 100 * 0.002 = 0.20 (+20% R0) -> SOH_R = 0.80
        self.assertAlmostEqual(health.resistance_growth_fraction, 0.20, places=3)
        self.assertAlmostEqual(health.soh_resistance_fraction, 0.80, places=3)

        # Unified SOH = min(0.90, 0.80) = 0.80
        self.assertAlmostEqual(health.soh_unified_fraction, 0.80, places=3)

    def test_runtime_stepping_and_event_publishing(self) -> None:
        """DigitalTwinInstance step publishes BatteryHealthUpdatedEvent to EventBus when estimator is attached."""
        event_bus = DigitalTwinEventBus()
        received_health_events = []

        def handle_health_event(evt):
            if isinstance(evt, BatteryHealthUpdatedEvent):
                received_health_events.append(evt)

        event_bus.subscribe("*", handle_health_event)

        ocv = LinearOCVModel(v_min_v=2.5, v_max_v=3.65)
        params = GenericECMParameters(
            nominal_capacity_ah=2.5,
            nominal_voltage_v=3.2,
            series_resistance_r0_ohm=0.015,
            rc_branches=(RCBranchParameters(resistance_r_ohm=0.01, capacitance_c_farad=100.0),),
        )
        model = GenericECMModel(
            metadata=ModelMetadata(model_id="ecm_soh", name="SOHECM", paradigm="ECM"),
            parameters=params,
            ocv_model=ocv,
        )

        health_est = ThroughputHealthEstimator(
            system_id="twin_rt_soh",
            nominal_capacity_ah=2.5,
            nominal_resistance_ohm=0.015,
        )

        twin = DigitalTwinInstance(
            battery_pack=self.pack,
            battery_model=model,
            health_estimator=health_est,
            event_bus=event_bus,
        )
        twin.initialize(initial_soc=1.0, temperature_c=25.0)

        # Step twin
        snap = TelemetrySnapshot(
            system_id="twin_rt_soh",
            snapshot_id="snap_01",
            timestamp_ns=1_000_000_000,
            pack_current_a=2.5,
            pack_voltage_v=3.2,
        )
        twin.step(snap)

        self.assertIsNotNone(twin.latest_health_state)
        self.assertEqual(len(received_health_events), 1)
        self.assertEqual(received_health_events[0].event_type, "twin.health")
        self.assertEqual(received_health_events[0].source_id, "twin_rt_soh")

    def test_rest_api_health_endpoint(self) -> None:
        """GET /api/v1/twins/{system_id}/health returns detailed health DTO."""
        services = create_default_services()
        app = create_app(services=services)

        # Register pack and twin with health estimator
        services.pack_service.register_pack(self.pack)

        ocv = LinearOCVModel(v_min_v=2.5, v_max_v=3.65)
        params = GenericECMParameters(
            nominal_capacity_ah=2.5,
            nominal_voltage_v=3.2,
            series_resistance_r0_ohm=0.015,
            rc_branches=(RCBranchParameters(resistance_r_ohm=0.01, capacitance_c_farad=100.0),),
        )
        model = GenericECMModel(
            metadata=ModelMetadata(model_id="ecm_api_soh", name="SOHECM", paradigm="ECM"),
            parameters=params,
            ocv_model=ocv,
        )
        health_est = ThroughputHealthEstimator(
            system_id="twin_api_soh",
            nominal_capacity_ah=2.5,
            nominal_resistance_ohm=0.015,
        )

        twin = services.twin_service.create_twin(
            system_id="twin_api_soh",
            battery_pack=self.pack,
            battery_model=model,
            health_estimator=health_est,
        )
        twin.initialize(initial_soc=1.0, temperature_c=25.0)

        with TestClient(app) as client:
            res = client.get("/api/v1/twins/twin_api_soh/health")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertEqual(data["system_id"], "twin_api_soh")
            self.assertIn("soh_capacity_fraction", data)
            self.assertIn("soh_resistance_fraction", data)
            self.assertIn("soh_unified_fraction", data)
            self.assertIn("equivalent_full_cycles", data)
            self.assertEqual(data["calibration_status"], "UNCALIBRATED_PARAMETRIC_MODEL")


if __name__ == "__main__":
    unittest.main()
