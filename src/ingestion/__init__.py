"""Telemetry Ingestion Subsystem.

Provides universal protocol adaptation, payload parsing, rate limiting,
monotonic timestamp validation, and pipeline coordination for battery telemetry.
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
from src.ingestion.base import (
    AbstractIngestionAdapter,
    IngestionAdapter,
    IngestionResult,
    IngestionStatus,
    PacketMetadata,
)
from src.ingestion.exceptions import (
    AdapterNotFoundError,
    FrameChecksumError,
    IngestionError,
    IngestionValidationError,
    MalformedPayloadError,
    RateLimitExceededError,
    TimestampMonotonicityError,
)
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.validation import (
    IngestionFilterConfig,
    RateLimiter,
    TimestampValidator,
)

__all__ = [
    "IngestionPipeline",
    "IngestionAdapter",
    "AbstractIngestionAdapter",
    "IngestionResult",
    "IngestionStatus",
    "PacketMetadata",
    "JSONTelemetryAdapter",
    "CSVTelemetryAdapter",
    "SyntheticTelemetryAdapter",
    "SyntheticTelemetryConfig",
    "SerialFrameTelemetryAdapter",
    "SerialFrameConfig",
    "compute_crc16_ccitt",
    "IngestionFilterConfig",
    "RateLimiter",
    "TimestampValidator",
    "IngestionError",
    "MalformedPayloadError",
    "IngestionValidationError",
    "RateLimitExceededError",
    "TimestampMonotonicityError",
    "AdapterNotFoundError",
    "FrameChecksumError",
]
