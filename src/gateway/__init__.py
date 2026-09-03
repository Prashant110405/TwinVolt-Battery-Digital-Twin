"""Edge Telemetry Gateway and External Communication Daemon Layer."""

from src.gateway.base import (
    BaseTelemetrySource,
    GatewayConfig,
    GatewayOverflowPolicy,
    GatewaySourceState,
    GatewaySourceStatus,
    RawTelemetryFrame,
)
from src.gateway.can_source import CanConfig, SocketCanSource
from src.gateway.manager import GatewayDaemonManager
from src.gateway.serial_source import SerialConfig, SerialUartSource
from src.gateway.tcp_source import TcpConfig, TcpSocketSource
from src.gateway.udp_source import UdpConfig, UdpSocketSource

__all__ = [
    # Core Base Contracts
    "BaseTelemetrySource",
    "RawTelemetryFrame",
    "GatewaySourceState",
    "GatewaySourceStatus",
    "GatewayOverflowPolicy",
    "GatewayConfig",
    # Gateway Manager
    "GatewayDaemonManager",
    # Serial UART
    "SerialConfig",
    "SerialUartSource",
    # SocketCAN
    "CanConfig",
    "SocketCanSource",
    # TCP / UDP
    "TcpConfig",
    "TcpSocketSource",
    "UdpConfig",
    "UdpSocketSource",
]
