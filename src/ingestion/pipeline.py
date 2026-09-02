"""Telemetry Ingestion Pipeline Orchestrator.

Coordinates adapter selection, payload parsing, rate limiting, and timestamp
monotonicity validation into a robust ingestion pipeline.
"""

import time
from typing import Any, Mapping, Optional, Sequence, Union

from src.ingestion.adapters.csv_adapter import CSVTelemetryAdapter
from src.ingestion.adapters.json_adapter import JSONTelemetryAdapter
from src.ingestion.adapters.serial_frame_adapter import SerialFrameTelemetryAdapter
from src.ingestion.adapters.synthetic_adapter import SyntheticTelemetryAdapter
from src.ingestion.base import (
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
from src.ingestion.validation import (
    IngestionFilterConfig,
    RateLimiter,
    TimestampValidator,
)
from src.telemetry.snapshots import TelemetrySnapshot


class IngestionPipeline:
    """Universal Telemetry Ingestion Pipeline.

    Validates, adapts, rate-limits, and parses raw incoming battery telemetry payloads
    from heterogeneous protocols into canonical domain TelemetrySnapshot objects.
    """

    def __init__(
        self,
        adapters: Optional[Sequence[IngestionAdapter]] = None,
        filter_config: Optional[IngestionFilterConfig] = None,
    ) -> None:
        self._filter_config = filter_config or IngestionFilterConfig()
        self._rate_limiter = RateLimiter(
            max_samples_per_second=self._filter_config.max_samples_per_second,
        )
        self._timestamp_validator = TimestampValidator(config=self._filter_config)

        if adapters is not None:
            self._adapters = list(adapters)
        else:
            # Default standard suite of adapters
            self._adapters = [
                JSONTelemetryAdapter(),
                CSVTelemetryAdapter(),
                SerialFrameTelemetryAdapter(),
                SyntheticTelemetryAdapter(),
            ]

    @property
    def registered_adapters(self) -> tuple[IngestionAdapter, ...]:
        """Tuple of registered adapter instances."""
        return tuple(self._adapters)

    def register_adapter(self, adapter: IngestionAdapter) -> None:
        """Registers a new ingestion adapter at the front of the adapter chain."""
        self._adapters.insert(0, adapter)

    def ingest(
        self,
        raw_data: Union[str, bytes, Mapping[str, Any]],
        format_identifier: Optional[str] = None,
        source_id: Optional[str] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> IngestionResult:
        """Processes a raw incoming telemetry payload through the ingestion pipeline.

        Returns:
            IngestionResult containing the parsed snapshot, status, and latency.
        """
        t_start_ns = time.perf_counter_ns()
        t_recv_ns = time.time_ns()

        # 1. Construct PacketMetadata
        raw_bytes_len = 0
        if isinstance(raw_data, (bytes, bytearray)):
            raw_bytes_len = len(raw_data)
        elif isinstance(raw_data, str):
            raw_bytes_len = len(raw_data.encode("utf-8"))

        sys_source = source_id or self._extract_source_id(raw_data) or "unknown_source"
        metadata = PacketMetadata(
            source_id=sys_source,
            transport_protocol=format_identifier or "AUTO_DETECTED",
            received_at_ns=t_recv_ns,
            raw_size_bytes=raw_bytes_len,
            headers=headers or {},
        )

        try:
            # 2. Rate Limiting Check
            self._rate_limiter.check_and_record(sys_source, t_recv_ns)

            # 3. Select Adapter
            adapter = self._resolve_adapter(raw_data, format_identifier)

            # 4. Parse Raw Payload into Domain TelemetrySnapshot
            snapshot = adapter.parse(raw_data, metadata=metadata)

            # 5. Monotonicity and Clock Drift Validation
            self._timestamp_validator.validate(
                system_id=snapshot.system_id,
                timestamp_ns=snapshot.timestamp_ns,
                received_at_ns=t_recv_ns,
            )

            latency_ms = (time.perf_counter_ns() - t_start_ns) / 1_000_000.0
            return IngestionResult(
                status=IngestionStatus.SUCCESS,
                snapshot=snapshot,
                metadata=metadata,
                processing_latency_ms=latency_ms,
            )

        except RateLimitExceededError as exc:
            latency_ms = (time.perf_counter_ns() - t_start_ns) / 1_000_000.0
            return IngestionResult(
                status=IngestionStatus.DROPPED,
                snapshot=None,
                metadata=metadata,
                errors=(str(exc),),
                processing_latency_ms=latency_ms,
            )

        except (
            TimestampMonotonicityError,
            MalformedPayloadError,
            IngestionValidationError,
            AdapterNotFoundError,
            FrameChecksumError,
        ) as exc:
            latency_ms = (time.perf_counter_ns() - t_start_ns) / 1_000_000.0
            return IngestionResult(
                status=IngestionStatus.REJECTED,
                snapshot=None,
                metadata=metadata,
                errors=(str(exc),),
                processing_latency_ms=latency_ms,
            )

        except Exception as exc:
            latency_ms = (time.perf_counter_ns() - t_start_ns) / 1_000_000.0
            return IngestionResult(
                status=IngestionStatus.REJECTED,
                snapshot=None,
                metadata=metadata,
                errors=(f"Unexpected ingestion error: {exc}",),
                processing_latency_ms=latency_ms,
            )

    def _resolve_adapter(
        self,
        raw_data: Union[str, bytes, Mapping[str, Any]],
        format_identifier: Optional[str],
    ) -> IngestionAdapter:
        """Finds the first registered adapter that supports the format or payload."""
        if format_identifier is not None:
            for adapter in self._adapters:
                if adapter.supports_format(format_identifier):
                    return adapter
            raise AdapterNotFoundError(
                f"No registered adapter supports format '{format_identifier}'.",
            )

        # Auto-detection heuristic
        if isinstance(raw_data, (bytes, bytearray)):
            if raw_data.startswith(b"\xAA\x55"):
                for adapter in self._adapters:
                    if isinstance(adapter, SerialFrameTelemetryAdapter):
                        return adapter
            # Try JSON decode
            try:
                raw_data.decode("utf-8")
                for adapter in self._adapters:
                    if isinstance(adapter, JSONTelemetryAdapter):
                        return adapter
            except UnicodeDecodeError:
                pass

        if isinstance(raw_data, Mapping):
            for adapter in self._adapters:
                if isinstance(adapter, JSONTelemetryAdapter):
                    return adapter

        if isinstance(raw_data, str):
            stripped = raw_data.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                for adapter in self._adapters:
                    if isinstance(adapter, JSONTelemetryAdapter):
                        return adapter
            if "," in stripped or "\n" in stripped:
                for adapter in self._adapters:
                    if isinstance(adapter, CSVTelemetryAdapter):
                        return adapter

        # Fallback to first adapter
        if self._adapters:
            return self._adapters[0]

        raise AdapterNotFoundError("No ingestion adapters registered in pipeline.")

    def _extract_source_id(self, raw_data: Union[str, bytes, Mapping[str, Any]]) -> Optional[str]:
        """Attempts a lightweight extraction of system_id or source_id from raw payload."""
        if isinstance(raw_data, Mapping):
            return raw_data.get("system_id") or raw_data.get("source_id")
        return None

    def reset_trackers(self, system_id: Optional[str] = None) -> None:
        """Resets rate limit and timestamp monotonicity state."""
        self._rate_limiter.reset(system_id)
        self._timestamp_validator.reset(system_id)
