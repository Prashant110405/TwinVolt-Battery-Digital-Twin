"""Unit tests for ReplayService."""

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
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.ecm.parameters import GenericECMParameters
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.types import ModelMetadata
from src.replay.engine import ReplayConfig, ReplayResult
from src.replay.profiles import create_pulse_discharge_profile
from src.services.exceptions import TwinNotFoundError
from src.services.replay_service import ReplayService
from src.services.twin_service import TwinApplicationService
from src.storage.memory_repository import (
    InMemoryStateHistoryRepository,
    InMemoryTelemetryRepository,
)
from src.telemetry.snapshots import TelemetrySnapshot


class TestReplayService(unittest.TestCase):
    """Test suite verifying drive-cycle replay coordination, CSV replay, and result caching."""

    def setUp(self) -> None:
        self.telemetry_repo = InMemoryTelemetryRepository(max_records_per_system=500)
        self.state_repo = InMemoryStateHistoryRepository(max_records_per_system=500)
        self.twin_service = TwinApplicationService(
            telemetry_repo=self.telemetry_repo,
            state_repo=self.state_repo,
        )

        self.service = ReplayService(
            twin_service=self.twin_service,
            telemetry_repo=self.telemetry_repo,
        )

        # Register test twin
        ident = BatteryIdentification(identifier="pack_replay_svc", display_name="Replay Service Pack")
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
            pack_id="pack_replay_svc",
            topology=BatteryTopology(series_count=1, parallel_count=1),
            electrical_ratings=ratings,
            thermal_limits=thermal,
        )
        pack = BatteryPack.create_monolithic_pack(
            identification=ident,
            configuration=pack_cfg,
            cell_config=cell_cfg,
        )
        ocv = LinearOCVModel(v_min_v=2.5, v_max_v=3.65)
        params = GenericECMParameters(nominal_capacity_ah=2.5, nominal_voltage_v=3.2)
        meta = ModelMetadata(model_id="ecm_replay", name="Replay ECM", paradigm="EQUIVALENT_CIRCUIT")
        model = GenericECMModel(metadata=meta, parameters=params, ocv_model=ocv)

        self.twin_service.create_twin("pack_replay_svc", battery_pack=pack, battery_model=model)

    def test_replay_drive_cycle_profile(self) -> None:
        """Replaying a drive cycle profile executes co-simulation and caches the result."""
        pulse_prof = create_pulse_discharge_profile(
            pulse_current_a=2.0,
            pulse_duration_s=5.0,
            rest_duration_s=5.0,
            cycles=2,
            dt_s=1.0,
        )

        res = self.service.replay_profile("pack_replay_svc", pulse_prof)
        self.assertIsInstance(res, ReplayResult)
        self.assertEqual(res.system_id, "pack_replay_svc")
        self.assertEqual(res.executed_steps, 21)

        cached = self.service.get_last_replay_result("pack_replay_svc")
        self.assertEqual(cached, res)

    def test_replay_csv_dataset(self) -> None:
        """Replaying a CSV dataset executes co-simulation through the twin service."""
        csv_data = (
            "timestamp_s,voltage_v,current_a,temperature_c\n"
            "0.0,3.60,0.0,25.0\n"
            "1.0,3.58,2.0,25.1\n"
            "2.0,3.56,2.0,25.2\n"
        )
        res = self.service.replay_csv("pack_replay_svc", csv_data, profile_name="test_csv")
        self.assertEqual(res.executed_steps, 3)
        self.assertEqual(res.profile_name, "test_csv")

    def test_replay_repository_data(self) -> None:
        """Replaying snapshots stored in the repository advances twin state."""
        for i in range(3):
            snap = TelemetrySnapshot(
                snapshot_id=f"snap_{i}",
                system_id="pack_replay_svc",
                timestamp_ns=1_000_000_000 * (i + 1),
                pack_voltage_v=3.60,
                pack_current_a=1.0,
            )
            self.telemetry_repo.append(snap)

        res = self.service.replay_repository_data("pack_replay_svc")
        self.assertEqual(res.executed_steps, 3)

    def test_replay_for_missing_twin_raises(self) -> None:
        """Replaying for unregistered twin raises TwinNotFoundError."""
        pulse_prof = create_pulse_discharge_profile(pulse_current_a=1.0, cycles=1)
        with self.assertRaises(TwinNotFoundError):
            self.service.replay_profile("missing_twin", pulse_prof)


if __name__ == "__main__":
    unittest.main()
