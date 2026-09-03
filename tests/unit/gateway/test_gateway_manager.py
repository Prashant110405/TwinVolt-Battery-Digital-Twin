"""Unit tests for GatewayDaemonManager orchestration and ingestion dispatching."""

import asyncio
import unittest
from unittest.mock import MagicMock

from src.events.bus import DigitalTwinEventBus
from src.gateway.base import (
    BaseTelemetrySource,
    GatewayConfig,
    GatewayOverflowPolicy,
    GatewaySourceState,
    RawTelemetryFrame,
)
from src.gateway.can_source import CanConfig, SocketCanSource
from src.gateway.manager import GatewayDaemonManager
from src.gateway.serial_source import SerialConfig, SerialUartSource
from src.services.pack_service import PackManagementService
from src.services.telemetry_service import TelemetryIngestService
from src.services.twin_service import TwinApplicationService
from src.storage.memory_repository import InMemoryStateHistoryRepository, InMemoryTelemetryRepository


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
from src.models.ecm.parameters import GenericECMParameters, RCBranchParameters
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.types import ModelMetadata
from src.runtime.config import RuntimeConfig


class SyntheticMockSource(BaseTelemetrySource):
    """Deterministic synthetic source for testing queue and dispatcher mechanics."""

    def __init__(self, source_id: str) -> None:
        super().__init__(source_id=source_id, transport_type="SYNTHETIC")
        self._queue: asyncio.Queue[RawTelemetryFrame] = asyncio.Queue()

    async def start(self) -> None:
        self._state = GatewaySourceState.CONNECTED

    async def stop(self) -> None:
        self._state = GatewaySourceState.STOPPED

    def push(self, frame: RawTelemetryFrame) -> None:
        self._queue.put_nowait(frame)

    async def read_frame(self) -> RawTelemetryFrame:
        frame = await self._queue.get()
        self._frames_received += 1
        return frame


class TestGatewayDaemonManager(unittest.IsolatedAsyncioTestCase):
    """Test suite verifying multi-source management, backpressure policies, event bus integration, and ingestion dispatch."""

    async def asyncSetUp(self) -> None:
        self.event_bus = DigitalTwinEventBus()
        self.telemetry_repo = InMemoryTelemetryRepository()
        self.state_repo = InMemoryStateHistoryRepository()
        self.pack_service = PackManagementService()
        self.twin_service = TwinApplicationService(
            event_bus=self.event_bus,
            telemetry_repo=self.telemetry_repo,
            state_repo=self.state_repo,
        )
        self.telemetry_service = TelemetryIngestService(
            twin_service=self.twin_service,
            telemetry_repo=self.telemetry_repo,
        )

        # Register standard test pack and model
        ident = BatteryIdentification(identifier="pack_gw_test", display_name="Gateway Test Pack")
        cell_cfg = CellConfiguration(
            cell_id="cell_lfp",
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
            pack_id="pack_gw_test",
            topology=BatteryTopology(series_count=1, parallel_count=1),
            electrical_ratings=ratings,
            thermal_limits=thermal,
        )
        pack = BatteryPack.create_monolithic_pack(
            identification=ident,
            configuration=pack_cfg,
            cell_config=cell_cfg,
        )
        self.pack_service.register_pack(pack)

        ocv = LinearOCVModel(v_min_v=2.5, v_max_v=3.65)
        params = GenericECMParameters(
            nominal_capacity_ah=2.5,
            nominal_voltage_v=3.2,
            series_resistance_r0_ohm=0.015,
            rc_branches=(RCBranchParameters(resistance_r_ohm=0.01, capacitance_c_farad=100.0),),
        )
        model = GenericECMModel(
            metadata=ModelMetadata(model_id="ecm_gw_test", name="GatewayECM", paradigm="ECM"),
            parameters=params,
            ocv_model=ocv,
        )

        twin = self.twin_service.create_twin(
            system_id="twin_gw_alpha",
            battery_pack=pack,
            battery_model=model,
        )
        twin.initialize(initial_soc=1.0, temperature_c=25.0)

    async def test_manager_source_registration_and_status(self) -> None:
        """GatewayDaemonManager registers multiple heterogeneous sources and tracks unified status."""
        manager = GatewayDaemonManager(telemetry_service=self.telemetry_service, event_bus=self.event_bus)

        src1 = SyntheticMockSource("source_1")
        src2 = SyntheticMockSource("source_2")

        manager.register_source(src1)
        manager.register_source(src2)

        status = manager.get_status()
        self.assertEqual(status["sources_count"], 2)
        self.assertIn("source_1", status["sources"])
        self.assertIn("source_2", status["sources"])

        # Unregister
        unreg = manager.unregister_source("source_1")
        self.assertIsNotNone(unreg)
        self.assertEqual(manager.get_status()["sources_count"], 1)

    async def test_end_to_end_frame_ingestion_and_twin_stepping(self) -> None:
        """Frames arriving on a gateway source flow through the daemon queue and step the digital twin."""
        manager = GatewayDaemonManager(
            config=GatewayConfig(max_queue_size=10, worker_concurrency=1),
            telemetry_service=self.telemetry_service,
            event_bus=self.event_bus,
        )

        source = SyntheticMockSource("twin_gw_alpha")
        manager.register_source(source)

        await manager.start()
        self.assertTrue(manager.is_running)

        # Inject CSV frame
        frame = RawTelemetryFrame(
            payload="timestamp_s,voltage_v,current_a,temperature_c\n0.0,3.60,1.5,25.0\n",
            source_id="twin_gw_alpha",
            transport_type="SERIAL",
            format_identifier="CSV",
            sequence_number=1,
        )
        source.push(frame)

        # Give worker a moment to process frame
        await asyncio.sleep(0.1)

        # Verify twin was stepped
        twin = self.twin_service.get_twin("twin_gw_alpha")
        self.assertIsNotNone(twin)
        self.assertTrue(twin.is_initialized)

        await manager.stop()
        self.assertFalse(manager.is_running)

    async def test_overflow_policy_drop_oldest(self) -> None:
        """Bounded queue with DROP_OLDEST drops the oldest pending frame on saturation."""
        cfg = GatewayConfig(max_queue_size=2, overflow_policy=GatewayOverflowPolicy.DROP_OLDEST)
        manager = GatewayDaemonManager(config=cfg, telemetry_service=None, event_bus=self.event_bus)

        # Manually set running without starting consumer workers
        manager._running = True

        f1 = RawTelemetryFrame(payload="p1", source_id="src", transport_type="SYNTHETIC", sequence_number=1)
        f2 = RawTelemetryFrame(payload="p2", source_id="src", transport_type="SYNTHETIC", sequence_number=2)
        f3 = RawTelemetryFrame(payload="p3", source_id="src", transport_type="SYNTHETIC", sequence_number=3)

        await manager.enqueue_frame(f1)
        await manager.enqueue_frame(f2)
        self.assertEqual(manager.queue_depth, 2)

        # Enqueuing 3rd frame will drop f1
        await manager.enqueue_frame(f3)
        self.assertEqual(manager.queue_depth, 2)
        self.assertEqual(manager.get_status()["total_dropped"], 1)

        # Next frame popped should be f2 (since f1 was dropped)
        popped = await manager._queue.get()
        self.assertEqual(popped.sequence_number, 2)

    async def test_overflow_policy_drop_newest(self) -> None:
        """Bounded queue with DROP_NEWEST drops the incoming frame on saturation."""
        cfg = GatewayConfig(max_queue_size=2, overflow_policy=GatewayOverflowPolicy.DROP_NEWEST)
        manager = GatewayDaemonManager(config=cfg, telemetry_service=None, event_bus=self.event_bus)

        manager._running = True

        f1 = RawTelemetryFrame(payload="p1", source_id="src", transport_type="SYNTHETIC", sequence_number=1)
        f2 = RawTelemetryFrame(payload="p2", source_id="src", transport_type="SYNTHETIC", sequence_number=2)
        f3 = RawTelemetryFrame(payload="p3", source_id="src", transport_type="SYNTHETIC", sequence_number=3)

        await manager.enqueue_frame(f1)
        await manager.enqueue_frame(f2)

        # Enqueuing 3rd frame is rejected
        res = await manager.enqueue_frame(f3)
        self.assertFalse(res)
        self.assertEqual(manager.get_status()["total_dropped"], 1)


if __name__ == "__main__":
    unittest.main()
