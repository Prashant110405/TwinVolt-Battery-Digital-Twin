"""Telemetry Ingestion Adapters.

Provides format-specific parsers for JSON, CSV, Synthetic, and Binary Serial BMS frames.
"""

from src.ingestion.adapters.csv_adapter import CSVTelemetryAdapter
from src.ingestion.adapters.json_adapter import JSONTelemetryAdapter
from src.ingestion.adapters.serial_frame_adapter import (
    SerialFrameConfig,
    SerialFrameTelemetryAdapter,
    compute_crc16_ccitt,
)
from src.ingestion.adapters.synthetic_adapter import (
    SyntheticTelemetryAdapter,
    SyntheticTelemetryConfig,
)

__all__ = [
    "JSONTelemetryAdapter",
    "CSVTelemetryAdapter",
    "SyntheticTelemetryAdapter",
    "SyntheticTelemetryConfig",
    "SerialFrameTelemetryAdapter",
    "SerialFrameConfig",
    "compute_crc16_ccitt",
]
