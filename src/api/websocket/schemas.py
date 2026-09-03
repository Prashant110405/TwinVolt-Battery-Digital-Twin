"""Pydantic Transport Schemas for WebSocket Protocol Messages.

Defines strongly-typed JSON message structures for client-to-server commands
and server-to-client streaming telemetry and twin state updates.
"""

from typing import Any, Mapping, Optional, Union
from pydantic import BaseModel, Field


# ------------------------------------------------------------------------------
# Inbound Client Messages
# ------------------------------------------------------------------------------
class WSSubscribeMessage(BaseModel):
    """Client command to subscribe to a digital twin's real-time state stream."""

    type: str = Field("subscribe", description="Message type tag")
    system_id: str = Field(..., description="Target digital twin system identifier")


class WSUnsubscribeMessage(BaseModel):
    """Client command to unsubscribe from a digital twin stream."""

    type: str = Field("unsubscribe", description="Message type tag")
    system_id: str = Field(..., description="Target digital twin system identifier")


class WSPingMessage(BaseModel):
    """Client heartbeat ping message."""

    type: str = Field("ping", description="Message type tag")


class WSTelemetryIngestMessage(BaseModel):
    """Client command to ingest a telemetry observation for an active digital twin."""

    type: str = Field("telemetry_ingest", description="Message type tag")
    system_id: str = Field(..., description="Target digital twin system identifier")
    raw_data: Optional[Union[str, dict[str, Any]]] = Field(None, description="Raw CSV string or JSON dictionary")
    format_identifier: Optional[str] = Field("JSON", description="Format tag ('JSON', 'CSV', 'SERIAL_FRAME')")
    pack_voltage_v: Optional[float] = Field(None, gt=0.0)
    pack_current_a: Optional[float] = None
    pack_power_w: Optional[float] = None
    ambient_temperature_c: Optional[float] = Field(25.0)
    avg_cell_temperature_c: Optional[float] = None
    max_cell_temperature_c: Optional[float] = None
    soc_fraction: Optional[float] = Field(None, ge=0.0, le=1.0)
    timestamp_ns: Optional[int] = None
    sequence_number: Optional[int] = None
    headers: Optional[Mapping[str, str]] = None


# ------------------------------------------------------------------------------
# Outbound Server Messages
# ------------------------------------------------------------------------------
class WSConnectedMessage(BaseModel):
    """Server welcome message sent upon successful WebSocket connection."""

    type: str = "connected"
    client_id: str
    message: str = "Connected to TwinVolt WebSocket Streaming API"


class WSPongMessage(BaseModel):
    """Server heartbeat pong response."""

    type: str = "pong"


class WSTelemetryAckMessage(BaseModel):
    """Server acknowledgement for an ingested telemetry frame."""

    type: str = "telemetry_ack"
    system_id: str
    status: str = "ACK"
    stepped_twin: bool = False
    step_index: Optional[int] = None


class WSTwinStateMessage(BaseModel):
    """Real-time broadcast containing the latest synchronized digital twin state."""

    type: str = "twin_state"
    system_id: str
    step_index: int
    timestamp_ns: int
    dt_s: float
    terminal_voltage_v: float
    simulated_soc: float
    estimated_soc: Optional[float] = None
    temperature_c: float
    voltage_residual_v: Optional[float] = None
    temperature_residual_c: Optional[float] = None
    anomalies_count: int = 0
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class WSTwinEventMessage(BaseModel):
    """Real-time broadcast containing a domain/runtime event published by the twin."""

    type: str = "twin_event"
    system_id: str
    event_type: str
    event_id: str
    timestamp_ns: int
    payload: dict[str, Any] = Field(default_factory=dict)


class WSErrorMessage(BaseModel):
    """Server error response for malformed messages, missing twins, or service errors."""

    type: str = "error"
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
