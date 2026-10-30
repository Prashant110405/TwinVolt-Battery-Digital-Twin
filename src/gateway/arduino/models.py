"""Data Models and Configuration for Arduino Serial Gateway.

Defines schemas for serial port settings, frame parsing options,
connection states, and parsed hardware telemetry records.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Mapping, Optional, Sequence
from pydantic import BaseModel, Field


class SerialDataFormat(str, Enum):
    """Supported data formats emitted by Arduino firmware."""
    AUTO = "AUTO"
    CSV = "CSV"
    JSON = "JSON"
    BMS_BINARY = "BMS_BINARY"


class HardwareConnectionState(str, Enum):
    """State machine for hardware serial connection."""
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    ERROR = "ERROR"


class ArduinoConfig(BaseModel):
    """Configuration for physical Arduino serial connection and telemetry parsing."""
    port: str = Field(..., description="Serial device path (e.g., 'COM3', '/dev/ttyUSB0', '/dev/ttyACM0').")
    baud_rate: int = Field(115200, ge=1200, le=2000000, description="Serial communication baud rate.")
    data_format: SerialDataFormat = Field(SerialDataFormat.AUTO, description="Expected frame format.")
    delimiter: bytes = Field(b"\n", description="Frame delimiter byte sequence.")
    auto_reconnect: bool = Field(True, description="Enable automatic reconnection on port loss.")
    reconnect_interval_s: float = Field(2.0, ge=0.5, le=30.0, description="Seconds between reconnect attempts.")
    read_timeout_s: float = Field(1.0, ge=0.1, le=10.0, description="Serial read timeout in seconds.")
    system_id: str = Field("twin_prototype_3s1p", description="Target digital twin system identifier.")
    voltage_column: str = Field("voltage_v", description="Field/column name for pack voltage in Volts.")
    current_column: str = Field("current_a", description="Field/column name for pack current in Amperes.")
    temp_column: str = Field("temperature_c", description="Field/column name for temperature in Celsius.")
    soc_column: Optional[str] = Field(None, description="Optional field name for state of charge (0..1 or 0..100%).")
    cell_prefix: str = Field("cell_v_", description="Prefix for individual cell voltage columns (e.g. cell_v_1).")


class ParsedHardwareRecord(BaseModel):
    """Normalized telemetry record decoded from raw hardware frame."""
    source_id: str
    source_mode: str = "LIVE_HARDWARE"
    sequence: int
    source_timestamp_ns: Optional[int] = None
    received_timestamp_ns: int
    voltage_v: float
    current_a: Optional[float] = None
    power_w: Optional[float] = None
    temperature_c: Optional[float] = None
    soc_fraction: Optional[float] = None
    cell_voltages_v: Sequence[float] = Field(default_factory=tuple)
    raw_payload: str
    is_valid: bool = True
    errors: Sequence[str] = Field(default_factory=tuple)
    declared_units: Mapping[str, str] = Field(default_factory=lambda: {
        "voltage": "V",
        "current": "A",
        "temperature": "°C",
        "power": "W",
    })


class HardwarePortInfo(BaseModel):
    """Information about an available system serial COM port."""
    device: str
    name: str
    description: str
    hwid: str
    manufacturer: Optional[str] = None
    is_arduino_candidate: bool = False
    is_bluetooth_link: bool = False


class HardwareGatewayStatus(BaseModel):
    """Real-time operational status and statistics for hardware gateway."""
    state: HardwareConnectionState
    port: Optional[str] = None
    baud_rate: Optional[int] = None
    data_format: SerialDataFormat = SerialDataFormat.AUTO
    system_id: Optional[str] = None
    frames_received: int = 0
    frames_parsed: int = 0
    parse_errors: int = 0
    transport_errors: int = 0
    sample_rate_hz: float = 0.0
    last_received_timestamp_ns: Optional[int] = None
    last_valid_reading: Optional[ParsedHardwareRecord] = None
    last_error: Optional[str] = None
    reconnect_attempts: int = 0
    is_stale: bool = False
