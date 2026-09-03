"""Unit tests for TwinApplicationService."""

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
from src.ingestion.pipeline import IngestionPipeline
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.ecm.parameters import GenericECMParameters, RCBranchParameters
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.types import ModelMetadata
from src.runtime.config import RuntimeConfig
from src.runtime.instance import DigitalTwinInstance
from src.services.exceptions import DuplicateEntityError, TwinNotFoundError
from src.services.twin_service import TwinApplicationService
from src.storage.memory_repository import (
    InMemoryStateHistoryRepository,
    InMemoryTelemetryRepository,
)
from src.telemetry.snapshots import TelemetrySnapshot


class TestTwinApplicationService(unittest.TestCase):
    """Test suite verifying Digital Twin instance creation, stepping, history lookups, and lifecycles."""

    def setUp(self) -> None:
        self.event_bus = DigitalTwinEventBus()
        self.telemetry_repo = InMemoryTelemetryRepository(max_records_per_system=500)
        self.state_repo = InMemoryStateHistoryRepository(max_records_per_system=500)
        self.pipeline = IngestionPipeline()

        self.service = TwinApplicationService(
            event_bus=self.event_bus,
            telemetry_repo=self.telemetry_repo,
            state_repo=self.state_repo,
            ingestion_pipeline=self.pipeline,
        )

        # Helper domain pack and model
        ident = BatteryIdentification(identifier="pack_twin_test", display_name="Test Pack")
        cell_cfg = CellConfiguration(
            cell_id="cell_twin",
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
            pack_id="pack_twin_test",
            topology=BatteryTopology(series_count=1, parallel_count=1),
            electrical_ratings=ratings,
            thermal_limits=thermal,
        )
        self.pack = BatteryPack.create_monolithic_pack(
            identification=ident,
            configuration=pack_cfg,
            cell_config=cell_cfg,
        )

        self.ocv = LinearOCVModel(v_min_v=2.5, v_max_v=3.65)
        self.params = GenericECMParameters(
            nominal_capacity_ah=2.5,
            nominal_voltage_v=3.2,
            series_resistance_r0_ohm=0.015,
            rc_branches=(RCBranchParameters(resistance_r_ohm=0.01, capacitance_c_farad=100.0),),
        )
        self.meta = ModelMetadata(model_id="ecm_twin_test", name="Twin ECM", paradigm="EQUIVALENT_CIRCUIT")
        self.model = GenericECMModel(metadata=self.meta, parameters=self.params, ocv_model=self.ocv)
        self.estimator = ExtendedKalmanFilter(estimator_id="ekf_twin_test", parameters=self.params, ocv_model=self.ocv)

    def test_create_and_get_twin(self) -> None:
        """Creating a twin registers it with injected infrastructure."""
        twin = self.service.create_twin(
            system_id="sys_alpha",
            battery_pack=self.pack,
            battery_model=self.model,
            state_estimator=self.estimator,
        )
        self.assertEqual(twin.system_id, "sys_alpha")
        self.assertEqual(self.service.count, 1)
        self.assertTrue(self.service.exists("sys_alpha"))

        retrieved = self.service.get_twin("sys_alpha")
        self.assertEqual(retrieved.system_id, "sys_alpha")

    def test_duplicate_twin_creation_raises(self) -> None:
        """Creating twin with existing system_id raises DuplicateEntityError."""
        self.service.create_twin(
            system_id="sys_alpha",
            battery_pack=self.pack,
            battery_model=self.model,
        )

        with self.assertRaises(DuplicateEntityError):
            self.service.create_twin(
                system_id="sys_alpha",
                battery_pack=self.pack,
                battery_model=self.model,
            )

    def test_get_nonexistent_twin_raises_not_found(self) -> None:
        """Retrieving missing twin raises TwinNotFoundError."""
        with self.assertRaises(TwinNotFoundError):
            self.service.get_twin("nonexistent_sys")

    def test_twin_lifecycle_initialize_and_step(self) -> None:
        """Initializing and stepping a twin executes co-simulation and persists history."""
        self.service.create_twin(
            system_id="sys_alpha",
            battery_pack=self.pack,
            battery_model=self.model,
            state_estimator=self.estimator,
        )

        self.service.initialize_twin("sys_alpha", initial_soc=0.90, temperature_c=25.0)
        twin = self.service.get_twin("sys_alpha")
        self.assertTrue(twin.is_initialized)

        # Step with snapshot
        snap = TelemetrySnapshot(
            snapshot_id="snap_01",
            system_id="sys_alpha",
            timestamp_ns=1_000_000_000,
            pack_voltage_v=3.58,
            pack_current_a=2.0,
            avg_cell_temperature_c=25.0,
        )
        sync_out = self.service.step_twin("sys_alpha", snap)
        self.assertEqual(sync_out.step_index, 1)
        self.assertAlmostEqual(sync_out.model_output.terminal_voltage_v, 3.58, delta=0.1)

        # Step raw with CSV
        csv_row = (
            "timestamp_s,voltage_v,current_a,temperature_c\n"
            "2.0,3.56,2.0,25.1\n"
        )
        sync_out_2 = self.service.step_raw_twin("sys_alpha", csv_row, format_identifier="CSV")
        self.assertEqual(sync_out_2.step_index, 2)

        # Verify history queries
        state_history = self.service.get_state_history("sys_alpha")
        telemetry_history = self.service.get_telemetry_history("sys_alpha")
        self.assertEqual(len(state_history), 2)
        self.assertEqual(len(telemetry_history), 2)

        # Verify latest state
        latest_record = self.service.get_latest_state("sys_alpha")
        self.assertIsNotNone(latest_record)
        self.assertEqual(latest_record.system_id, "sys_alpha")

    def test_reset_and_delete_twin(self) -> None:
        """Resetting and deleting twins works correctly."""
        self.service.create_twin(
            system_id="sys_alpha",
            battery_pack=self.pack,
            battery_model=self.model,
        )
        self.service.initialize_twin("sys_alpha", initial_soc=1.0)
        self.service.reset_twin("sys_alpha")

        self.assertEqual(len(self.service.list_active_twins()), 1)
        self.assertTrue(self.service.delete_twin("sys_alpha"))
        self.assertFalse(self.service.delete_twin("sys_alpha"))
        self.assertEqual(self.service.count, 0)


if __name__ == "__main__":
    unittest.main()
