"""Base Contracts and Protocols for Telemetry Ingestion.

Defines packet metadata, ingestion result containers, and the universal IngestionAdapter protocol.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
import time
from typing import Any, Mapping, Optional, Protocol, Union, runtime_checkable

from src.telemetry.snapshots import TelemetrySnapshot


class IngestionStatus(str, Enum):
    """Execution status of an ingestion attempt."""

    SUCCESS = "SUCCESS"
    DEGRADED = "DEGRADED"
    REJECTED = "REJECTED"
    DROPPED = "DROPPED"


@dataclass(frozen=True)
class PacketMetadata:
    """Metadata detailing the origin, transport protocol, and timing of an incoming packet."""

    source_id: str
    transport_protocol: str = "UNKNOWN"
    received_at_ns: int = field(default_factory=lambda: time.time_ns())
    raw_size_bytes: int = 0
    content_type: str = "application/json"
    headers: Mapping[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes metadata to a dictionary."""
        return {
            "source_id": self.source_id,
            "transport_protocol": self.transport_protocol,
            "received_at_ns": self.received_at_ns,
            "raw_size_bytes": self.raw_size_bytes,
            "content_type": self.content_type,
            "headers": dict(self.headers),
        }


@dataclass(frozen=True)
class IngestionResult:
    """Standardized result container returned by the ingestion pipeline."""

    status: IngestionStatus
    snapshot: Optional[TelemetrySnapshot] = None
    metadata: Optional[PacketMetadata] = None
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    processing_latency_ms: float = 0.0

    @property
    def is_success(self) -> bool:
        """True if the telemetry payload was successfully ingested and parsed."""
        return self.status in (IngestionStatus.SUCCESS, IngestionStatus.DEGRADED) and self.snapshot is not None

    def to_dict(self) -> dict[str, Any]:
        """Serializes ingestion result to a dictionary."""
        return {
            "status": self.status.value,
            "is_success": self.is_success,
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
            "metadata": self.metadata.to_dict() if self.metadata else None,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "processing_latency_ms": self.processing_latency_ms,
        }


@runtime_checkable
class IngestionAdapter(Protocol):
    """Protocol for format-specific telemetry adapters."""

    @property
    def adapter_name(self) -> str:
        """Identifier for the adapter implementation."""
        ...

    def supports_format(self, format_identifier: str) -> bool:
        """Returns True if this adapter can process payloads in the specified format."""
        ...

    def parse(
        self,
        raw_data: Union[str, bytes, Mapping[str, Any]],
        metadata: Optional[PacketMetadata] = None,
    ) -> TelemetrySnapshot:
        """Parses raw input data into a validated domain TelemetrySnapshot."""
        ...


class AbstractIngestionAdapter(ABC, IngestionAdapter):
    """Base class for ingestion adapters providing shared validation and conversion utilities."""

    def __init__(self, adapter_name: str) -> None:
        self._name = adapter_name

    @property
    def adapter_name(self) -> str:
        """Adapter unique name."""
        return self._name

    @abstractmethod
    def supports_format(self, format_identifier: str) -> bool:
        """Checks if format is supported."""
        ...

    @abstractmethod
    def parse(
        self,
        raw_data: Union[str, bytes, Mapping[str, Any]],
        metadata: Optional[PacketMetadata] = None,
    ) -> TelemetrySnapshot:
        """Parses raw data into TelemetrySnapshot."""
        ...
