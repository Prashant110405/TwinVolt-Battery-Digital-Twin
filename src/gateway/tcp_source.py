"""Asynchronous TCP Socket Telemetry Source.

Streams line-delimited or framed telemetry from laboratory equipment, power cyclers,
or remote edge gateways over TCP/IP sockets.
"""

import asyncio
import time
from typing import Optional
from pydantic import BaseModel, Field

from src.gateway.base import (
    BaseTelemetrySource,
    GatewaySourceState,
    RawTelemetryFrame,
)


class TcpConfig(BaseModel):
    """Declarative configuration for TCP socket telemetry source."""

    host: str = Field("127.0.0.1", description="Remote or local target host IP/domain.")
    port: int = Field(9000, ge=1, le=65535, description="Target TCP port.")
    delimiter: bytes = Field(b"\n", description="Frame delimiter byte sequence.")
    format_identifier: str = Field("JSON", description="Format identifier hint ('JSON', 'CSV').")
    auto_reconnect: bool = Field(True, description="Enable automatic reconnection.")
    reconnect_initial_delay_s: float = Field(0.5, ge=0.01)
    reconnect_max_delay_s: float = Field(5.0, ge=0.1)


class TcpSocketSource(BaseTelemetrySource):
    """Asynchronous TCP Socket Source."""

    def __init__(self, source_id: str, config: TcpConfig) -> None:
        super().__init__(source_id=source_id, transport_type="TCP")
        self.config = config
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._running = False
        self._seq = 0
        self._reconnect_delay = self.config.reconnect_initial_delay_s

    async def start(self) -> None:
        """Establishes TCP connection."""
        self._running = True
        self._state = GatewaySourceState.INITIALIZING
        await self._connect()

    async def stop(self) -> None:
        """Closes TCP socket connection."""
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
        """Reads the next framed payload from the TCP socket."""
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
                raw_bytes = await self._reader.readuntil(self.config.delimiter)
                if not raw_bytes:
                    raise ConnectionResetError("Empty read on TCP socket stream.")

                self._frames_received += 1
                self._seq += 1
                self._last_received_at_ns = time.time_ns()

                cleaned = raw_bytes.rstrip(b"\r\n")
                payload = cleaned.decode("utf-8", errors="replace")

                return RawTelemetryFrame(
                    payload=payload,
                    source_id=self._source_id,
                    transport_type=self._transport_type,
                    received_timestamp_ns=self._last_received_at_ns,
                    sequence_number=self._seq,
                    device_id=f"{self.config.host}:{self.config.port}",
                    format_identifier=self.config.format_identifier,
                    metadata={"host": self.config.host, "port": self.config.port},
                )

            except (ConnectionResetError, BrokenPipeError, OSError, asyncio.IncompleteReadError) as exc:
                self._handle_disconnect(f"TCP socket disconnected: {exc}")
            except Exception as exc:
                self._parse_errors += 1
                self._last_error = f"TCP parse error: {exc}"

        return None

    async def _connect(self) -> None:
        """Connects to target TCP endpoint."""
        try:
            self._reader, self._writer = await asyncio.open_connection(
                host=self.config.host,
                port=self.config.port,
            )
            self._state = GatewaySourceState.CONNECTED
            self._reconnect_delay = self.config.reconnect_initial_delay_s
            self._last_error = None
        except Exception as exc:
            self._transport_errors += 1
            self._last_error = f"Failed to connect to TCP {self.config.host}:{self.config.port}: {exc}"
            self._state = GatewaySourceState.ERROR

    def _handle_disconnect(self, error_msg: str) -> None:
        """Marks connection as disconnected."""
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
