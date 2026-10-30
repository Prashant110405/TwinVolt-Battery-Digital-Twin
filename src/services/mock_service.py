"""Isolated Mock Telemetry Generator and Testing Service.

Provides deterministic and configurable synthetic telemetry generation
for testing UI dashboards, state estimation, and alerting without physical
hardware. All frames are tagged with source_mode='MOCK'.
"""

from __future__ import annotations

import asyncio
from collections import deque
import json
import logging
import math
import random
import time
from typing import Optional

from pydantic import BaseModel, Field

from src.events.base import EventBus
from src.gateway.arduino.models import ParsedHardwareRecord
from src.services.telemetry_service import TelemetryIngestService

logger = logging.getLogger("twinvolt.services.mock")


class MockConfig(BaseModel):
    """Configuration for simulated battery telemetry generation."""

    system_id: str = Field(
        "twin_prototype_3s1p",
        description="Target digital twin identifier.",
    )
    sample_interval_ms: int = Field(
        500,
        ge=50,
        le=10000,
        description="Sampling period in milliseconds.",
    )
    min_voltage_v: float = Field(3.0, ge=1.0, le=1000.0)
    max_voltage_v: float = Field(4.2, ge=1.0, le=1000.0)
    min_temp_c: float = Field(20.0, ge=-40.0, le=120.0)
    max_temp_c: float = Field(35.0, ge=-40.0, le=120.0)
    current_amplitude_a: float = Field(2.5, ge=0.0, le=500.0)
    cell_count: int = Field(3, ge=1, le=192)
    random_seed: Optional[int] = Field(
        None,
        description="Optional seed for reproducible tests.",
    )
    simulate_noise: bool = Field(
        True,
        description="Add subtle Gaussian measurement noise.",
    )
    inject_malformed_frequency: int = Field(
        0,
        ge=0,
        le=100,
        description="Frequency percentage of invalid frames.",
    )


class MockGeneratorStatus(BaseModel):
    """Status of the isolated mock telemetry generator."""

    is_running: bool
    system_id: str
    sample_interval_ms: int
    samples_generated: int
    sample_rate_hz: float
    last_generated_record: Optional[ParsedHardwareRecord] = None
    config: MockConfig
    errors_injected: int = 0


class MockTelemetryService:
    """Independent mock telemetry generator and testing service."""

    def __init__(
        self,
        telemetry_service: Optional[TelemetryIngestService] = None,
        event_bus: Optional[EventBus] = None,
    ) -> None:
        self._telemetry_service = telemetry_service
        self._event_bus = event_bus

        self._config = MockConfig()
        self._is_running = False
        self._task: Optional[asyncio.Task] = None

        self._samples_generated = 0
        self._errors_injected = 0

        self._last_record: Optional[ParsedHardwareRecord] = None
        self._recent_records: deque[ParsedHardwareRecord] = deque(
            maxlen=50
        )
        self._timestamps_window: deque[float] = deque(maxlen=20)

        self._rng = random.Random()
        self._step_index = 0

    @property
    def is_running(self) -> bool:
        """Return whether the generator is running."""
        return self._is_running

    @property
    def config(self) -> MockConfig:
        """Return the current generator configuration."""
        return self._config

    def configure(self, config: MockConfig) -> MockGeneratorStatus:
        """Update generator parameters."""
        self._config = config

        if config.random_seed is not None:
            self._rng = random.Random(config.random_seed)

        return self.get_status()

    def get_status(self) -> MockGeneratorStatus:
        """Return the current operational status."""
        sample_rate_hz = 0.0

        if len(self._timestamps_window) >= 2:
            elapsed = (
                self._timestamps_window[-1]
                - self._timestamps_window[0]
            )

            if elapsed > 0:
                sample_rate_hz = (
                    len(self._timestamps_window) - 1
                ) / elapsed

        return MockGeneratorStatus(
            is_running=self._is_running,
            system_id=self._config.system_id,
            sample_interval_ms=self._config.sample_interval_ms,
            samples_generated=self._samples_generated,
            sample_rate_hz=round(sample_rate_hz, 2),
            last_generated_record=self._last_record,
            config=self._config,
            errors_injected=self._errors_injected,
        )

    def get_recent_records(self) -> list[ParsedHardwareRecord]:
        """Return a copy of the recent generated records."""
        return list(self._recent_records)

    async def start(self) -> MockGeneratorStatus:
        """Start the background telemetry generator."""
        if self._is_running:
            return self.get_status()

        if self._config.random_seed is not None:
            self._rng = random.Random(self._config.random_seed)

        self._is_running = True
        self._task = asyncio.create_task(self._generation_loop())

        logger.info(
            "Mock telemetry generator started for system '%s'",
            self._config.system_id,
        )

        self._publish_mock_event("mock.started")
        return self.get_status()

    async def stop(self) -> MockGeneratorStatus:
        """Stop the background telemetry generator."""
        self._is_running = False

        if self._task and not self._task.done():
            self._task.cancel()

            try:
                await self._task
            except asyncio.CancelledError:
                pass

        self._task = None

        logger.info("Mock telemetry generator stopped.")
        self._publish_mock_event("mock.stopped")

        return self.get_status()

    def reset(self) -> MockGeneratorStatus:
        """Reset generated sample counts and statistics."""
        self._samples_generated = 0
        self._errors_injected = 0
        self._step_index = 0

        self._last_record = None
        self._recent_records.clear()
        self._timestamps_window.clear()

        if self._config.random_seed is not None:
            self._rng = random.Random(self._config.random_seed)

        return self.get_status()

    def inject_error(
        self,
        error_type: str = "malformed",
    ) -> ParsedHardwareRecord:
        """Inject an invalid record for UI and QA testing."""
        self._samples_generated += 1
        self._errors_injected += 1

        now_ns = time.time_ns()

        record = ParsedHardwareRecord(
            source_id="mock_generator",
            source_mode="MOCK",
            sequence=self._samples_generated,
            received_timestamp_ns=now_ns,
            voltage_v=0.0,
            raw_payload=(
                f"[INJECTED_TEST_ERROR: {error_type}]"
            ),
            is_valid=False,
            errors=(
                f"Simulated injected error: {error_type}",
            ),
        )

        self._last_record = record
        self._recent_records.append(record)

        self._publish_mock_event("mock.error_injected")

        return record

    async def _generation_loop(self) -> None:
        """Generate synthetic telemetry at the configured interval.

        The first sample is generated immediately. Subsequent samples
        are generated after the configured sampling interval.
        """
        while self._is_running:
            try:
                dt_s = self._config.sample_interval_ms / 1000.0

                # Record generation timestamp.
                now_s = time.time()
                now_ns = int(now_s * 1e9)

                self._samples_generated += 1
                self._step_index += 1
                self._timestamps_window.append(now_s)

                # Generate synthetic battery voltage.
                t = self._step_index * dt_s

                voltage_mid = (
                    self._config.max_voltage_v
                    + self._config.min_voltage_v
                ) / 2.0

                voltage_amplitude = (
                    self._config.max_voltage_v
                    - self._config.min_voltage_v
                ) / 2.0

                base_voltage = voltage_mid + (
                    voltage_amplitude
                    * 0.7
                    * math.cos(t / 20.0)
                )

                voltage_noise = (
                    self._rng.gauss(0.0, 0.005)
                    if self._config.simulate_noise
                    else 0.0
                )

                voltage_v = round(
                    max(
                        self._config.min_voltage_v,
                        min(
                            self._config.max_voltage_v,
                            base_voltage + voltage_noise,
                        ),
                    ),
                    3,
                )

                # Generate synthetic current.
                base_current = (
                    self._config.current_amplitude_a
                    * math.sin(t / 15.0)
                )

                current_noise = (
                    self._rng.gauss(0.0, 0.02)
                    if self._config.simulate_noise
                    else 0.0
                )

                current_a = round(
                    base_current + current_noise,
                    3,
                )

                # Generate synthetic temperature.
                temperature_mid = (
                    self._config.max_temp_c
                    + self._config.min_temp_c
                ) / 2.0

                temperature_amplitude = (
                    self._config.max_temp_c
                    - self._config.min_temp_c
                ) / 2.0

                temperature_c = round(
                    temperature_mid
                    + temperature_amplitude
                    * 0.5
                    * math.sin(t / 30.0)
                    + abs(current_a) * 0.3,
                    2,
                )

                # Estimate state of charge.
                voltage_range = (
                    self._config.max_voltage_v
                    - self._config.min_voltage_v
                )

                if voltage_range > 0:
                    soc_fraction = round(
                        max(
                            0.05,
                            min(
                                0.99,
                                (
                                    voltage_v
                                    - self._config.min_voltage_v
                                ) / voltage_range,
                            ),
                        ),
                        3,
                    )
                else:
                    soc_fraction = 0.05

                # Generate simulated cell voltages.
                cell_voltages = []

                for cell_index in range(
                    self._config.cell_count
                ):
                    offset = (cell_index - 1) * 0.015

                    cell_voltage = round(
                        max(
                            2.5,
                            (
                                voltage_v
                                / self._config.cell_count
                            ) + offset,
                        ),
                        3,
                    )

                    cell_voltages.append(cell_voltage)

                # Calculate power.
                power_w = round(
                    voltage_v * current_a,
                    2,
                )

                # Construct the JSON payload.
                raw_payload = json.dumps(
                    {
                        "source": "mock",
                        "millis": int(t * 1000),
                        "voltage_v": voltage_v,
                        "current_a": current_a,
                        "temperature_c": temperature_c,
                        "soc": soc_fraction,
                    }
                )

                # Construct the telemetry record.
                record = ParsedHardwareRecord(
                    source_id="mock_generator",
                    source_mode="MOCK",
                    sequence=self._samples_generated,
                    source_timestamp_ns=now_ns,
                    received_timestamp_ns=now_ns,
                    voltage_v=voltage_v,
                    current_a=current_a,
                    power_w=power_w,
                    temperature_c=temperature_c,
                    soc_fraction=soc_fraction,
                    cell_voltages_v=tuple(cell_voltages),
                    raw_payload=raw_payload,
                    is_valid=True,
                )

                self._last_record = record
                self._recent_records.append(record)

                # Optionally pass the generated sample to telemetry
                # ingestion. This follows the ingest_raw interface used
                # by the version of the project this file was based on.
                if self._telemetry_service is not None:
                    try:
                        ingest_data = {
                            "system_id": self._config.system_id,
                            "source_mode": "MOCK",
                            "timestamp_s": now_s,
                            "voltage_v": voltage_v,
                            "current_a": current_a,
                            "temperature_c": temperature_c,
                            "soc_fraction": soc_fraction,
                        }

                        self._telemetry_service.ingest_raw(
                            system_id=self._config.system_id,
                            raw_payload=ingest_data,
                            format_identifier="JSON",
                            headers={
                                "X-TwinVolt-Source-Mode": "MOCK",
                            },
                        )

                    except Exception as exc:
                        logger.debug(
                            "Mock ingestion notice: %s",
                            exc,
                        )

                # IMPORTANT: wait after generating a sample.
                await asyncio.sleep(dt_s)

            except asyncio.CancelledError:
                break

            except Exception:
                logger.exception(
                    "Error in mock generator loop."
                )
                await asyncio.sleep(0.5)

    def _publish_mock_event(
        self,
        event_type: str,
    ) -> None:
        """Broadcast generator lifecycle events."""
        if self._event_bus is None:
            return

        try:
            from src.events.base import BaseEvent

            event = BaseEvent(
                event_type=event_type,
                system_id=self._config.system_id,
                payload={
                    "source_mode": "MOCK",
                    "samples": self._samples_generated,
                },
            )

            self._event_bus.publish(event)

        except Exception:
            logger.debug(
                "Unable to publish mock event '%s'.",
                event_type,
                exc_info=True,
            )