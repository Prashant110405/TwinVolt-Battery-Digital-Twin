"""SocketCAN and CAN Bus Telemetry Source.

Receives standard CAN 2.0B and CAN-FD broadcast frames from automotive or industrial
battery management systems without hard-coded vendor IDs or packet structures.
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


class CanConfig(BaseModel):
    """Declarative configuration for CAN telemetry source."""

    channel: str = Field("can0", description="CAN interface or virtual channel name.")
    interface: str = Field("socketcan", description="CAN driver interface backend.")
    bitrate: Optional[int] = Field(500000, description="CAN bus bitrate (bps).")
    receive_filters: Optional[list[dict[str, Any]]] = Field(
        None, description="Optional CAN arbitration ID receive acceptance filters."
    )
    format_identifier: str = Field("JSON", description="Format identifier hint.")
    auto_reconnect: bool = Field(True, description="Enable automatic reconnection on bus off.")
    reconnect_initial_delay_s: float = Field(0.5, ge=0.01)
    reconnect_max_delay_s: float = Field(5.0, ge=0.1)


class SocketCanSource(BaseTelemetrySource):
    """SocketCAN and CAN Bus Telemetry Source.

    Captures raw CAN messages preserving arbitration ID, DLC, timestamp, and payload bytes.
    Accepts pluggable message generators or mock queues for deterministic offline testing.
    """

    def __init__(
        self,
        source_id: str,
        config: CanConfig,
        bus_factory: Optional[Callable[[], Coroutine[Any, Any, Any]]] = None,
    ) -> None:
        super().__init__(source_id=source_id, transport_type="CAN")
        self.config = config
        self._bus_factory = bus_factory
        self._bus: Any = None
        self._running = False
        self._seq = 0
        self._reconnect_delay = self.config.reconnect_initial_delay_s
        self._inbound_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def start(self) -> None:
        """Initializes CAN bus listener."""
        self._running = True
        self._state = GatewaySourceState.INITIALIZING
        await self._connect()

    async def stop(self) -> None:
        """Stops CAN bus listener and closes interface."""
        self._running = False
        self._state = GatewaySourceState.STOPPED
        if self._bus is not None:
            try:
                if hasattr(self._bus, "shutdown"):
                    self._bus.shutdown()
            except Exception:
                pass
            self._bus = None

    def inject_mock_can_message(
        self,
        arbitration_id: int,
        data: bytes,
        is_extended_id: bool = False,
        is_fd: bool = False,
    ) -> None:
        """Utility for test suites to inject synthetic CAN frames directly."""
        self._inbound_queue.put_nowait({
            "arbitration_id": arbitration_id,
            "data": data,
            "is_extended_id": is_extended_id,
            "is_fd": is_fd,
            "timestamp_ns": time.time_ns(),
        })

    async def read_frame(self) -> Optional[RawTelemetryFrame]:
        """Reads the next CAN message frame."""
        if not self._running:
            return None

        while self._running:
            if self._state != GatewaySourceState.CONNECTED:
                if self.config.auto_reconnect:
                    await self._reconnect()
                else:
                    return None
                continue

            try:
                # 1. Check if mock queue has messages or read from bus
                if not self._inbound_queue.empty():
                    msg = await self._inbound_queue.get()
                elif self._bus is not None and hasattr(self._bus, "recv"):
                    loop = asyncio.get_running_loop()
                    raw_msg = await loop.run_in_executor(None, self._bus.recv, 0.5)
                    if raw_msg is None:
                        continue
                    msg = {
                        "arbitration_id": getattr(raw_msg, "arbitration_id", 0),
                        "data": bytes(getattr(raw_msg, "data", b"")),
                        "is_extended_id": getattr(raw_msg, "is_extended_id", False),
                        "is_fd": getattr(raw_msg, "is_fd", False),
                        "timestamp_ns": int(getattr(raw_msg, "timestamp", time.time()) * 1e9),
                    }
                else:
                    # Wait for message injection with timeout
                    try:
                        msg = await asyncio.wait_for(self._inbound_queue.get(), timeout=0.5)
                    except asyncio.TimeoutError:
                        continue

                self._frames_received += 1
                self._seq += 1
                self._last_received_at_ns = time.time_ns()

                frame_payload = {
                    "arbitration_id": msg["arbitration_id"],
                    "data_hex": msg["data"].hex(),
                    "dlc": len(msg["data"]),
                    "is_extended_id": msg.get("is_extended_id", False),
                    "is_fd": msg.get("is_fd", False),
                }

                return RawTelemetryFrame(
                    payload=frame_payload,
                    source_id=self._source_id,
                    transport_type=self._transport_type,
                    received_timestamp_ns=self._last_received_at_ns,
                    source_timestamp_ns=msg.get("timestamp_ns"),
                    sequence_number=self._seq,
                    device_id=self.config.channel,
                    format_identifier=self.config.format_identifier,
                    metadata={
                        "channel": self.config.channel,
                        "interface": self.config.interface,
                        "arbitration_id": hex(msg["arbitration_id"]),
                    },
                )

            except Exception as exc:
                self._transport_errors += 1
                self._last_error = f"CAN bus read error: {exc}"
                self._state = GatewaySourceState.DISCONNECTED

        return None

    async def _connect(self) -> None:
        """Connects to CAN bus via factory or establishes mock channel."""
        try:
            if self._bus_factory is not None:
                self._bus = await self._bus_factory()
            self._state = GatewaySourceState.CONNECTED
            self._reconnect_delay = self.config.reconnect_initial_delay_s
            self._last_error = None
        except Exception as exc:
            self._transport_errors += 1
            self._last_error = f"Failed to initialize CAN channel '{self.config.channel}': {exc}"
            self._state = GatewaySourceState.ERROR

    async def _reconnect(self) -> None:
        """Executes bounded exponential backoff reconnection."""
        self._state = GatewaySourceState.RECONNECTING
        self._reconnect_count += 1
        await asyncio.sleep(self._reconnect_delay)
        self._reconnect_delay = min(self._reconnect_delay * 1.5, self.config.reconnect_max_delay_s)
        await self._connect()
