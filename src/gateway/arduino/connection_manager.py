"""Arduino Hardware Gateway Connection Manager.

Supervises physical serial transport, frame decoding, telemetry ingestion,
heartbeat monitoring, reconnection backoff, and event dispatching.
"""

from __future__ import annotations

import asyncio
from collections import deque
import logging
import time
from typing import Any, Callable, Coroutine, Optional

from src.events.base import EventBus
from src.gateway.arduino.frame_parser import ArduinoFrameParser
from src.gateway.arduino.models import (
    ArduinoConfig,
    HardwareConnectionState,
    HardwareGatewayStatus,
    ParsedHardwareRecord,
    SerialDataFormat,
)
from src.gateway.arduino.serial_transport import ArduinoSerialTransport
from src.services.telemetry_service import TelemetryIngestService

logger = logging.getLogger("twinvolt.gateway.arduino.manager")


class ArduinoConnectionManager:
    """Manages the lifecycle of an Arduino or Physical BMS hardware connection."""

    def __init__(
        self,
        telemetry_service: Optional[TelemetryIngestService] = None,
        event_bus: Optional[EventBus] = None,
        stale_threshold_s: float = 5.0,
    ) -> None:
        self._telemetry_service = telemetry_service
        self._event_bus = event_bus
        self._stale_threshold_s = stale_threshold_s

        self._config: Optional[ArduinoConfig] = None
        self._transport: Optional[ArduinoSerialTransport] = None
        self._parser: Optional[ArduinoFrameParser] = None

        self._state = HardwareConnectionState.DISCONNECTED
        self._listen_task: Optional[asyncio.Task] = None
        self._running = False

        # Metrics and Status Tracking
        self._frames_received = 0
        self._frames_parsed = 0
        self._parse_errors = 0
        self._transport_errors = 0
        self._reconnect_attempts = 0
        self._last_received_ns: Optional[int] = None
        self._last_valid_reading: Optional[ParsedHardwareRecord] = None
        self._last_error: Optional[str] = None
        self._timestamps_window: deque[float] = deque(maxlen=20)
        self._recent_records: deque[ParsedHardwareRecord] = deque(maxlen=50)

    @property
    def state(self) -> HardwareConnectionState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state == HardwareConnectionState.CONNECTED

    @property
    def config(self) -> Optional[ArduinoConfig]:
        return self._config

    def get_status(self) -> HardwareGatewayStatus:
        """Returns the current operational status and telemetry health."""
        now_ns = time.time_ns()
        is_stale = False
        if self._last_received_ns is not None:
            elapsed_s = (now_ns - self._last_received_ns) / 1e9
            if elapsed_s > self._stale_threshold_s and self._state == HardwareConnectionState.CONNECTED:
                is_stale = True

        # Calculate sample rate in Hz over sliding window
        hz = 0.0
        if len(self._timestamps_window) >= 2:
            dt = self._timestamps_window[-1] - self._timestamps_window[0]
            if dt > 0.0:
                hz = (len(self._timestamps_window) - 1) / dt

        return HardwareGatewayStatus(
            state=self._state,
            port=self._config.port if self._config else None,
            baud_rate=self._config.baud_rate if self._config else None,
            data_format=self._config.data_format if self._config else SerialDataFormat.AUTO,
            system_id=self._config.system_id if self._config else None,
            frames_received=self._frames_received,
            frames_parsed=self._frames_parsed,
            parse_errors=self._parse_errors,
            transport_errors=self._transport_errors,
            sample_rate_hz=round(hz, 2),
            last_received_timestamp_ns=self._last_received_ns,
            last_valid_reading=self._last_valid_reading,
            last_error=self._last_error,
            reconnect_attempts=self._reconnect_attempts,
            is_stale=is_stale,
        )

    def get_recent_records(self) -> list[ParsedHardwareRecord]:
        """Returns sliding window of recent telemetry records."""
        return list(self._recent_records)

    async def connect(
        self,
        config: ArduinoConfig,
        mock_generator: Optional[Callable[[], Coroutine[Any, Any, Optional[str]]]] = None,
    ) -> HardwareGatewayStatus:
        """Initiates serial connection with Arduino hardware."""
        if self._running:
            await self.disconnect()

        self._config = config
        self._parser = ArduinoFrameParser(config=config)
        self._transport = ArduinoSerialTransport(
            config=config,
            mock_line_generator=mock_generator,
        )
        self._state = HardwareConnectionState.CONNECTING
        self._last_error = None
        self._running = True

        try:
            await self._transport.open()
            self._state = HardwareConnectionState.CONNECTED
            self._reconnect_attempts = 0
            logger.info("Successfully connected to Arduino on port '%s'", config.port)
            self._publish_state_event("CONNECTED")
        except Exception as exc:
            self._state = HardwareConnectionState.ERROR
            self._last_error = f"Connection failed: {exc}"
            self._transport_errors += 1
            self._running = False
            self._publish_state_event("ERROR")
            raise

        # Start background non-blocking listener
        self._listen_task = asyncio.create_task(self._listen_loop())
        return self.get_status()

    async def disconnect(self) -> HardwareGatewayStatus:
        """Disconnects serial port and halts listener loop."""
        self._running = False
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None

        if self._transport:
            try:
                await self._transport.close()
            except Exception as exc:
                logger.warning("Error closing serial transport: %s", exc)
            self._transport = None

        self._state = HardwareConnectionState.DISCONNECTED
        self._publish_state_event("DISCONNECTED")
        logger.info("Arduino hardware connection closed.")
        return self.get_status()

    async def _listen_loop(self) -> None:
        """Continuous background loop reading and ingesting frames."""
        reconnect_delay = 1.0

        while self._running:
            try:
                if self._transport is None or not self._transport.is_open:
                    if self._config and self._config.auto_reconnect:
                        self._state = HardwareConnectionState.RECONNECTING
                        self._reconnect_attempts += 1
                        self._publish_state_event("RECONNECTING")
                        logger.info(
                            "Attempting reconnection to '%s' (attempt %d)...",
                            self._config.port,
                            self._reconnect_attempts,
                        )
                        await asyncio.sleep(reconnect_delay)
                        reconnect_delay = min(reconnect_delay * 1.5, 10.0)
                        try:
                            if self._transport:
                                await self._transport.open()
                            self._state = HardwareConnectionState.CONNECTED
                            reconnect_delay = 1.0
                            self._publish_state_event("CONNECTED")
                        except Exception as exc:
                            self._last_error = f"Reconnection error: {exc}"
                            continue
                    else:
                        break

                raw_line = await self._transport.readline()
                if raw_line is None:
                    # Read timeout or empty cycle
                    await asyncio.sleep(0.01)
                    continue

                now_s = time.time()
                now_ns = int(now_s * 1e9)
                self._frames_received += 1
                self._last_received_ns = now_ns
                self._timestamps_window.append(now_s)

                # Parse frame
                record = self._parser.parse_line(raw_line, received_timestamp_ns=now_ns)
                self._recent_records.append(record)

                if record.is_valid:
                    self._frames_parsed += 1
                    self._last_valid_reading = record
                    self._last_error = None

                    # Ingest into Telemetry Service if available
                    if self._telemetry_service is not None and self._config:
                        try:
                            # Forward as raw JSON payload for seamless ingestion pipeline execution
                            ingest_payload = {
                                "system_id": self._config.system_id,
                                "timestamp_s": (record.source_timestamp_ns or now_ns) / 1e9,
                                "voltage_v": record.voltage_v,
                                "current_a": record.current_a or 0.0,
                                "temperature_c": record.temperature_c or 25.0,
                                "source": "LIVE_HARDWARE",
                            }
                            if record.soc_fraction is not None:
                                ingest_payload["soc_fraction"] = record.soc_fraction
                            if record.cell_voltages_v:
                                for idx, cv in enumerate(record.cell_voltages_v, start=1):
                                    ingest_payload[f"{self._config.cell_prefix}{idx}"] = cv

                            self._telemetry_service.ingest_raw(
                                system_id=self._config.system_id,
                                raw_payload=ingest_payload,
                                format_identifier="JSON",
                                headers={"source": "LIVE_HARDWARE"},
                            )
                        except Exception as ingest_exc:
                            logger.debug("Telemetry ingestion notice: %s", ingest_exc)
                else:
                    self._parse_errors += 1
                    if record.errors:
                        self._last_error = record.errors[0]

            except (ConnectionResetError, ConnectionError) as conn_exc:
                self._transport_errors += 1
                self._last_error = str(conn_exc)
                logger.warning("Serial connection interrupted: %s", conn_exc)
                if self._transport:
                    await self._transport.close()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                self._transport_errors += 1
                self._last_error = f"Unexpected loop error: {exc}"
                logger.error("Exception in Arduino listener loop: %s", exc)
                await asyncio.sleep(0.1)

    def _publish_state_event(self, state_str: str) -> None:
        """Dispatches gateway lifecycle notifications to the event bus if available."""
        if self._event_bus is None or self._config is None:
            return
        try:
            from src.events.base import BaseEvent
            event = BaseEvent(
                event_type=f"gateway.arduino.{state_str.lower()}",
                system_id=self._config.system_id,
                payload={
                    "state": state_str,
                    "port": self._config.port,
                    "baud_rate": self._config.baud_rate,
                },
            )
            self._event_bus.publish(event)
        except Exception:
            pass
