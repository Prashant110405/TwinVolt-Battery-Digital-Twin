"""Unit tests for Isolated Mock Telemetry Service.

Verifies start/stop lifecycle, deterministic output with random seeds,
fault injection, and source mode isolation.
"""

import asyncio
import unittest
from src.services.mock_service import MockConfig, MockTelemetryService


class TestMockTelemetryService(unittest.IsolatedAsyncioTestCase):
    async def test_start_stop_lifecycle_and_generation(self) -> None:
        """Starts generator, verifies periodic frame generation, and stops cleanly."""
        svc = MockTelemetryService()
        cfg = MockConfig(
            system_id="test_mock_twin",
            sample_interval_ms=50,
            random_seed=42,
        )
        svc.configure(cfg)

        status_start = await svc.start()
        self.assertTrue(status_start.is_running)
        self.assertTrue(svc.is_running)

        await asyncio.sleep(0.18)

        status_mid = svc.get_status()
        self.assertGreaterEqual(status_mid.samples_generated, 2)
        self.assertIsNotNone(status_mid.last_generated_record)
        self.assertEqual(status_mid.last_generated_record.source_mode, "MOCK")

        status_stop = await svc.stop()
        self.assertFalse(status_stop.is_running)
        self.assertFalse(svc.is_running)

    async def test_deterministic_generation_with_seed(self) -> None:
        """Generates identical sample sequence when initialized with same random seed."""
        svc1 = MockTelemetryService()
        svc1.configure(MockConfig(sample_interval_ms=50, random_seed=12345))
        await svc1.start()
        await asyncio.sleep(0.12)
        await svc1.stop()
        records1 = [r.voltage_v for r in svc1.get_recent_records()]

        svc2 = MockTelemetryService()
        svc2.configure(MockConfig(sample_interval_ms=50, random_seed=12345))
        await svc2.start()
        await asyncio.sleep(0.12)
        await svc2.stop()
        records2 = [r.voltage_v for r in svc2.get_recent_records()]

        self.assertGreaterEqual(len(records1), 2)
        self.assertEqual(records1[:2], records2[:2])

    def test_fault_injection_and_reset(self) -> None:
        """Injects test malformed frames for QA testing and resets counters."""
        svc = MockTelemetryService()
        injected = svc.inject_error("malformed_test_packet")

        self.assertFalse(injected.is_valid)
        self.assertEqual(injected.source_mode, "MOCK")
        self.assertEqual(svc.get_status().errors_injected, 1)

        status_reset = svc.reset()
        self.assertEqual(status_reset.samples_generated, 0)
        self.assertEqual(status_reset.errors_injected, 0)


if __name__ == "__main__":
    unittest.main()
