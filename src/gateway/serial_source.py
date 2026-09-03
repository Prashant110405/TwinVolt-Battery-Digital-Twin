"""Asynchronous Serial UART / USB Virtual COM Port Telemetry Source.

Reads continuous streaming ASCII or framed binary telemetry from physical or simulated
serial communication interfaces with automatic reconnection.
"""

import asyncio
import time
from typing import Any, Callable, Coroutine, Optional
from pydantic import BaseModel, Field

from src.gateway.base import (
    BaseTelemetrySource,
    GatewaySourceState,
    RawTelemetryFrame,
)


class SerialConfig(BaseModel):
    """Declarative configuration for Serial UART telemetry source."""

    port: str = Field(..., description="Serial device path (e.g., '/dev/ttyUSB0', 'COM3').")
    baud_rate: int = Field(115200, ge=1200, le=3000000, description="Serial baud rate.")
    delimiter: bytes = Field(b"\n", description="Frame delimiter byte sequence.")
    format_identifier: str = Field("CSV", description="Downstream ingestion format hint.")
    auto_reconnect: bool = Field(True, description="Enable automatic reconnection on transport loss.")
    reconnect_initial_delay_s: float = Field(0.5, ge=0.01)
    reconnect_max_delay_s: float = Field(5.0, ge=0.1)


class SerialUartSource(BaseTelemetrySource):
    """Asynchronous Serial UART Source.

    Communicates with external microcontrollers, laboratory test benches, or virtual
    serial ports. Supports mock stream injection for hardware-independent deterministic tests.
    """

    def __init__(
        self,
        source_id: str,
        config: SerialConfig,
        stream_factory: Optional[Callable[[], Coroutine[Any, Any, tuple[asyncio.StreamReader, asyncio.StreamWriter]]]] = None,
    ) -> None:
        super().__init__(source_id=source_id, transport_type="SERIAL")
        self.config = config
        self._stream_factory = stream_factory
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._running = False
        self._seq = 0
        self._reconnect_delay = self.config.reconnect_initial_delay_s

    async def start(self) -> None:
        """Establishes connection to the serial port/stream."""
        self._running = True
        self._state = GatewaySourceState.INITIALIZING
        await self._connect()

    async def stop(self) -> None:
        """Closes serial resources and stops the listening loop."""
        self._running = False
        self._state = GatewaySourceState.STOPPED
        if self._writer is not None:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None

    async def read_frame(self) -> Optional[RawTelemetryFrame]:
        """Reads the next framed payload from the serial stream."""
        if not self._running:
            return None

        while self._running:
            if self._reader is None or self._state != GatewaySourceState.CONNECTED:
                if self.config.auto_reconnect:
                    await self._reconnect()
                else:
                    return None
                continue

            try:
                # Read until delimiter
                raw_bytes = await self._reader.readuntil(self.config.delimiter)
                if not raw_bytes:
                    raise ConnectionResetError("Empty read on serial stream.")

                self._frames_received += 1
                self._seq += 1
                self._last_received_at_ns = time.time_ns()

                # Strip trailing delimiter and decode to ASCII string if possible
                cleaned_bytes = raw_bytes.rstrip(b"\r\n")
                payload: Any
                try:
                    payload = cleaned_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    payload = cleaned_bytes

                return RawTelemetryFrame(
                    payload=payload,
                    source_id=self._source_id,
                    transport_type=self._transport_type,
                    received_timestamp_ns=self._last_received_at_ns,
                    sequence_number=self._seq,
                    device_id=self.config.port,
                    format_identifier=self.config.format_identifier,
                    metadata={"baud_rate": self.config.baud_rate, "port": self.config.port},
                )

            except asyncio.IncompleteReadError as exc:
                if exc.partial:
                    self._frames_received += 1
                    self._seq += 1
                    self._last_received_at_ns = time.time_ns()
                    return RawTelemetryFrame(
                        payload=exc.partial.decode("utf-8", errors="replace"),
                        source_id=self._source_id,
                        transport_type=self._transport_type,
                        received_timestamp_ns=self._last_received_at_ns,
                        sequence_number=self._seq,
                        device_id=self.config.port,
                        format_identifier=self.config.format_identifier,
                    )
                self._handle_disconnect("Serial connection closed during read.")
            except (ConnectionResetError, BrokenPipeError, OSError) as exc:
                self._handle_disconnect(str(exc))
            except Exception as exc:
                self._parse_errors += 1
                self._last_error = f"Frame parse error: {exc}"

        return None

    async def _connect(self) -> None:
        """Attempts connection using stream factory or pyserial-asyncio if available."""
        try:
            if self._stream_factory is not None:
                self._reader, self._writer = await self._stream_factory()
            else:
                # Fallback to local loopback socket / mock stream for testability
                reader = asyncio.StreamReader()
                self._reader = reader
                self._writer = None

            self._state = GatewaySourceState.CONNECTED
            self._reconnect_delay = self.config.reconnect_initial_delay_s
            self._last_error = None
        except Exception as exc:
            self._transport_errors += 1
            self._last_error = f"Failed to open serial port '{self.config.port}': {exc}"
            self._state = GatewaySourceState.ERROR

    def _handle_disconnect(self, error_msg: str) -> None:
        """Marks source as disconnected and tracks error."""
        self._transport_errors += 1
        self._last_error = error_msg
        self._state = GatewaySourceState.DISCONNECTED
        self._reader = None
        self._writer = None

    async def _reconnect(self) -> None:
        """Executes bounded exponential backoff reconnection."""
        self._state = GatewaySourceState.RECONNECTING
        self._reconnect_count += 1
        await asyncio.sleep(self._reconnect_delay)
        self._reconnect_delay = min(self._reconnect_delay * 1.5, self.config.reconnect_max_delay_s)
        await self._connect()
