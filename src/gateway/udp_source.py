"""Asynchronous UDP Datagram Telemetry Source.

Receives connectionless, datagram-oriented telemetry packets from remote battery packs,
wireless IoT sensors, or edge streaming gateways.
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


class UdpConfig(BaseModel):
    """Declarative configuration for UDP socket telemetry source."""

    host: str = Field("0.0.0.0", description="Local binding host IP.")
    port: int = Field(9001, ge=1, le=65535, description="Local binding UDP port.")
    max_datagram_size: int = Field(65535, ge=128, le=65535, description="Maximum datagram buffer size.")
    format_identifier: str = Field("JSON", description="Format identifier hint ('JSON', 'CSV').")


class _UdpProtocol(asyncio.DatagramProtocol):
    """Asyncio datagram protocol forwarding received packets to an in-memory queue."""

    def __init__(self, queue: asyncio.Queue[tuple[bytes, tuple[str, int]]]) -> None:
        self.queue = queue
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore
        self.transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.queue.put_nowait((data, addr))

    def error_received(self, exc: Exception) -> None:
        pass


class UdpSocketSource(BaseTelemetrySource):
    """Asynchronous UDP Datagram Source."""

    def __init__(self, source_id: str, config: UdpConfig) -> None:
        super().__init__(source_id=source_id, transport_type="UDP")
        self.config = config
        self._queue: asyncio.Queue[tuple[bytes, tuple[str, int]]] = asyncio.Queue()
        self._transport: Optional[asyncio.DatagramTransport] = None
        self._protocol: Optional[_UdpProtocol] = None
        self._running = False
        self._seq = 0

    async def start(self) -> None:
        """Binds UDP socket and starts listening for datagrams."""
        self._running = True
        self._state = GatewaySourceState.INITIALIZING
        try:
            loop = asyncio.get_running_loop()
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: _UdpProtocol(self._queue),
                local_addr=(self.config.host, self.config.port),
            )
            self._transport = transport
            self._protocol = protocol
            self._state = GatewaySourceState.CONNECTED
            self._last_error = None
        except Exception as exc:
            self._transport_errors += 1
            self._last_error = f"Failed to bind UDP port {self.config.host}:{self.config.port}: {exc}"
            self._state = GatewaySourceState.ERROR

    async def stop(self) -> None:
        """Closes UDP datagram transport."""
        self._running = False
        self._state = GatewaySourceState.STOPPED
        if self._transport is not None:
            self._transport.close()
            self._transport = None
            self._protocol = None

    async def read_frame(self) -> Optional[RawTelemetryFrame]:
        """Reads the next datagram from the queue."""
        if not self._running:
            return None

        while self._running:
            if self._state != GatewaySourceState.CONNECTED:
                return None

            try:
                data, addr = await asyncio.wait_for(self._queue.get(), timeout=0.5)
                self._frames_received += 1
                self._seq += 1
                self._last_received_at_ns = time.time_ns()

                cleaned = data.rstrip(b"\r\n")
                payload = cleaned.decode("utf-8", errors="replace")

                return RawTelemetryFrame(
                    payload=payload,
                    source_id=self._source_id,
                    transport_type=self._transport_type,
                    received_timestamp_ns=self._last_received_at_ns,
                    sequence_number=self._seq,
                    device_id=f"{addr[0]}:{addr[1]}",
                    format_identifier=self.config.format_identifier,
                    metadata={"sender_ip": addr[0], "sender_port": addr[1]},
                )
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                self._parse_errors += 1
                self._last_error = f"UDP datagram read error: {exc}"

        return None
