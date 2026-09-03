"""Unit tests for TelemetryIngestService."""

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
from src.ingestion.pipeline import IngestionPipeline
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.ecm.parameters import GenericECMParameters
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.types import ModelMetadata
from src.services.exceptions import TwinNotFoundError
from src.services.telemetry_service import TelemetryIngestService
from src.services.twin_service import TwinApplicationService
from src.storage.memory_repository import InMemoryTelemetryRepository
from src.telemetry.snapshots import TelemetrySnapshot


class TestTelemetryIngestService(unittest.TestCase):
    """Test suite verifying telemetry routing, raw parsing delegation, and batch ingestion."""

    def setUp(self) -> None:
        self.telemetry_repo = InMemoryTelemetryRepository(max_records_per_system=200)
        self.pipeline = IngestionPipeline()
        self.twin_service = TwinApplicationService(
            telemetry_repo=self.telemetry_repo,
            ingestion_pipeline=self.pipeline,
        )

        self.service = TelemetryIngestService(
            ingestion_pipeline=self.pipeline,
            twin_service=self.twin_service,
            telemetry_repo=self.telemetry_repo,
        )

        # Setup test twin in twin service
        ident = BatteryIdentification(identifier="pack_ingest_test", display_name="Test Ingest Pack")
        cell_cfg = CellConfiguration(
            cell_id="cell_ingest",
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
            pack_id="pack_ingest_test",
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
        meta = ModelMetadata(model_id="ecm_ingest", name="Ingest ECM", paradigm="EQUIVALENT_CIRCUIT")
        model = GenericECMModel(metadata=meta, parameters=params, ocv_model=ocv)

        self.twin_service.create_twin("pack_ingest_test", battery_pack=pack, battery_model=model)
        self.twin_service.initialize_twin("pack_ingest_test")

    def test_ingest_raw_csv_routes_to_twin(self) -> None:
        """Raw CSV string payload is parsed and advances digital twin state."""
        csv_payload = (
            "timestamp_s,voltage_v,current_a,temperature_c\n"
            "0.0,3.60,1.5,25.0\n"
        )
        sync_out = self.service.ingest_raw(
            system_id="pack_ingest_test",
            raw_payload=csv_payload,
            format_identifier="CSV",
        )
        self.assertEqual(sync_out.step_index, 1)
        self.assertEqual(sync_out.telemetry.pack_voltage_v, 3.60)
        self.assertEqual(sync_out.telemetry.pack_current_a, 1.5)

    def test_ingest_snapshot_and_batch(self) -> None:
        """Canonical snapshot and batch ingestion advance digital twin state in order."""
        snap1 = TelemetrySnapshot(
            snapshot_id="snap_1",
            system_id="pack_ingest_test",
            timestamp_ns=1_000_000_000,
            pack_voltage_v=3.59,
            pack_current_a=2.0,
        )
        snap2 = TelemetrySnapshot(
            snapshot_id="snap_2",
            system_id="pack_ingest_test",
            timestamp_ns=2_000_000_000,
            pack_voltage_v=3.58,
            pack_current_a=2.0,
        )

        out1 = self.service.ingest_snapshot(snap1)
        self.assertIsNotNone(out1)
        self.assertEqual(out1.step_index, 1)

        batch_outs = self.service.ingest_batch("pack_ingest_test", [snap2])
        self.assertEqual(len(batch_outs), 1)
        self.assertEqual(batch_outs[0].step_index, 2)

    def test_ingest_to_missing_twin_raises(self) -> None:
        """Ingesting raw payload for an unregistered twin raises TwinNotFoundError."""
        with self.assertRaises(TwinNotFoundError):
            self.service.ingest_raw(
                system_id="nonexistent_twin",
                raw_payload="0.0,3.6,1.0\n",
                format_identifier="CSV",
            )


if __name__ == "__main__":
    unittest.main()
