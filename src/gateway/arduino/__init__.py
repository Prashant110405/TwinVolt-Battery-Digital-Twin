"""Arduino Hardware Gateway Module.

Provides serial transport, frame parsing, port enumeration, and connection management
for physical microcontrollers and BMS hardware.
"""

from src.gateway.arduino.connection_manager import ArduinoConnectionManager
from src.gateway.arduino.frame_parser import ArduinoFrameParser
from src.gateway.arduino.models import (
    ArduinoConfig,
    HardwareConnectionState,
    HardwareGatewayStatus,
    HardwarePortInfo,
    ParsedHardwareRecord,
    SerialDataFormat,
)
from src.gateway.arduino.serial_transport import ArduinoSerialTransport, list_available_ports

__all__ = [
    "ArduinoConfig",
    "ArduinoConnectionManager",
    "ArduinoFrameParser",
    "ArduinoSerialTransport",
    "HardwareConnectionState",
    "HardwareGatewayStatus",
    "HardwarePortInfo",
    "ParsedHardwareRecord",
    "SerialDataFormat",
    "list_available_ports",
]
