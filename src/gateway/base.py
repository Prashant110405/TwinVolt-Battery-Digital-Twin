"""Core Abstractions and Contracts for Edge Telemetry Gateway.

Defines the base source protocols, immutable transport frames, source lifecycle states,
and configuration models for external communication daemons.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Mapping, Optional, Union
from pydantic import BaseModel, Field


class GatewaySourceState(str, Enum):
    """Lifecycle connection state of an edge telemetry transport source."""

    INITIALIZING = "INITIALIZING"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"
    STOPPED = "STOPPED"


class GatewayOverflowPolicy(str, Enum):
    """Buffer overflow backpressure policy when the gateway ingestion queue is full."""

    DROP_OLDEST = "DROP_OLDEST"
    DROP_NEWEST = "DROP_NEWEST"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class RawTelemetryFrame:
    """Immutable transport-level raw observation frame preserving provenance and timing.

    Attributes:
        payload: Raw binary buffer, ASCII text line, or parsed dictionary.
        source_id: Target system or source identifier.
        transport_type: Identifier of the physical/network transport (e.g., 'SERIAL', 'CAN', 'TCP', 'UDP').
        received_timestamp_ns: Locally measured system timestamp at frame reception.
        source_timestamp_ns: Timestamp from hardware header/packet payload if available.
        sequence_number: Frame/packet sequence number if provided by hardware.
        device_id: Physical hardware port or bus device identifier.
        format_identifier: Hint for downstream parsing (e.g., 'CSV', 'JSON', 'SERIAL_FRAME').
        metadata: Transport-specific framing metadata (baud rate, CAN ID, socket address).
    """

    payload: Union[bytes, str, dict[str, Any]]
    source_id: str
    transport_type: str
    received_timestamp_ns: int = field(default_factory=lambda: time.time_ns())
    source_timestamp_ns: Optional[int] = None
    sequence_number: Optional[int] = None
    device_id: Optional[str] = None
    format_identifier: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_id or not self.source_id.strip():
            raise ValueError("source_id cannot be empty.")
        if not self.transport_type or not self.transport_type.strip():
            raise ValueError("transport_type cannot be empty.")
        if self.received_timestamp_ns < 0:
            raise ValueError("received_timestamp_ns cannot be negative.")


@dataclass(frozen=True)
class GatewaySourceStatus:
    """Operational health metrics and connection telemetry for a gateway source."""

    source_id: str
    transport_type: str
    state: GatewaySourceState
    is_connected: bool
    frames_received: int
    frames_dropped: int
    parse_errors: int
    transport_errors: int
    reconnect_count: int
    last_received_at_ns: Optional[int] = None
    last_error: Optional[str] = None
    queue_depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serializes status to a JSON-compatible dictionary."""
        return {
            "source_id": self.source_id,
            "transport_type": self.transport_type,
            "state": self.state.value,
            "is_connected": self.is_connected,
            "frames_received": self.frames_received,
            "frames_dropped": self.frames_dropped,
            "parse_errors": self.parse_errors,
            "transport_errors": self.transport_errors,
            "reconnect_count": self.reconnect_count,
            "last_received_at_ns": self.last_received_at_ns,
            "last_error": self.last_error,
            "queue_depth": self.queue_depth,
        }


class GatewayConfig(BaseModel):
    """Declarative configuration for GatewayDaemonManager."""

    max_queue_size: int = Field(1000, ge=1, description="Maximum bounded buffer queue capacity.")
    overflow_policy: GatewayOverflowPolicy = Field(
        GatewayOverflowPolicy.DROP_OLDEST,
        description="Backpressure policy on buffer saturation.",
    )
    worker_concurrency: int = Field(1, ge=1, le=16, description="Parallel ingestion consumer worker count.")


class BaseTelemetrySource(ABC):
    """Abstract base class for all physical and network telemetry sources."""

    def __init__(self, source_id: str, transport_type: str) -> None:
        if not source_id or not source_id.strip():
            raise ValueError("source_id cannot be empty.")
        self._source_id = source_id
        self._transport_type = transport_type
        self._state = GatewaySourceState.INITIALIZING
        self._frames_received = 0
        self._frames_dropped = 0
        self._parse_errors = 0
        self._transport_errors = 0
        self._reconnect_count = 0
        self._last_received_at_ns: Optional[int] = None
        self._last_error: Optional[str] = None

    @property
    def source_id(self) -> str:
        """Source system identifier."""
        return self._source_id

    @property
    def transport_type(self) -> str:
        """Physical/network transport identifier."""
        return self._transport_type

    @property
    def state(self) -> GatewaySourceState:
        """Current lifecycle connection state."""
        return self._state

    @abstractmethod
    async def start(self) -> None:
        """Initializes transport resources and establishes continuous listening loop."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully closes transport resources and releases connections."""
        pass

    @abstractmethod
    async def read_frame(self) -> Optional[RawTelemetryFrame]:
        """Asynchronously retrieves the next available raw telemetry frame from the source."""
        pass

    def get_status(self) -> GatewaySourceStatus:
        """Returns the current operational status and frame statistics."""
        return GatewaySourceStatus(
            source_id=self._source_id,
            transport_type=self._transport_type,
            state=self._state,
            is_connected=(self._state == GatewaySourceState.CONNECTED),
            frames_received=self._frames_received,
            frames_dropped=self._frames_dropped,
            parse_errors=self._parse_errors,
            transport_errors=self._transport_errors,
            reconnect_count=self._reconnect_count,
            last_received_at_ns=self._last_received_at_ns,
            last_error=self._last_error,
        )
