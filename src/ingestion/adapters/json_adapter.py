"""JSON Telemetry Ingestion Adapter.

Parses JSON strings, bytes, and dictionary payloads into strongly-typed TelemetrySnapshot instances.
Supports standard canonical schema formats and flat JSON BMS payloads.
"""

import json
from typing import Any, Mapping, Optional, Union

from src.ingestion.base import AbstractIngestionAdapter, PacketMetadata
from src.ingestion.exceptions import MalformedPayloadError
from src.schemas.telemetry_schema import validate_telemetry_payload
from src.telemetry.snapshots import TelemetrySnapshot


class JSONTelemetryAdapter(AbstractIngestionAdapter):
    """Parses JSON-formatted battery telemetry payloads."""

    def __init__(self, adapter_name: str = "JSONTelemetryAdapter") -> None:
        super().__init__(adapter_name=adapter_name)

    def supports_format(self, format_identifier: str) -> bool:
        """Returns True if the format is JSON-compatible."""
        fmt = format_identifier.strip().upper()
        return fmt in ("JSON", "APPLICATION/JSON", "JSON_DICT", "JSON_STRING", "JSON_BYTES")

    def parse(
        self,
        raw_data: Union[str, bytes, Mapping[str, Any]],
        metadata: Optional[PacketMetadata] = None,
    ) -> TelemetrySnapshot:
        """Parses a JSON string, bytes, or dict into a TelemetrySnapshot.

        Raises:
            MalformedPayloadError: If JSON syntax is invalid or structure cannot be parsed.
        """
        data_dict: Mapping[str, Any]

        if isinstance(raw_data, (str, bytes)):
            try:
                data_dict = json.loads(raw_data)
            except Exception as exc:
                raise MalformedPayloadError(
                    f"Failed to decode JSON payload: {exc}",
                    source_id=metadata.source_id if metadata else None,
                    details={"raw_sample": str(raw_data)[:200]},
                ) from exc
        elif isinstance(raw_data, Mapping):
            data_dict = raw_data
        else:
            raise MalformedPayloadError(
                f"JSONTelemetryAdapter expects str, bytes, or Mapping, got {type(raw_data).__name__}.",
                source_id=metadata.source_id if metadata else None,
            )

        # Standardize flat field aliases if present
        payload = dict(data_dict)

        # If system_id or snapshot_id missing, fallback to metadata source_id
        if metadata is not None:
            if "system_id" not in payload or not payload["system_id"]:
                payload["system_id"] = metadata.source_id
            if "snapshot_id" not in payload or not payload["snapshot_id"]:
                payload["snapshot_id"] = f"{metadata.source_id}_{payload.get('timestamp_ns', metadata.received_at_ns)}"

        # Convert timestamp aliases to timestamp_ns if missing
        if "timestamp_ns" not in payload or payload["timestamp_ns"] is None:
            if "timestamp_s" in payload and payload["timestamp_s"] is not None:
                payload["timestamp_ns"] = int(float(payload["timestamp_s"]) * 1_000_000_000)
            elif "timestamp_ms" in payload and payload["timestamp_ms"] is not None:
                payload["timestamp_ns"] = int(float(payload["timestamp_ms"]) * 1_000_000)
            elif "timestamp" in payload and payload["timestamp"] is not None:
                # If numeric timestamp
                ts_val = float(payload["timestamp"])
                # If timestamp looks like epoch seconds (< 1e11), convert to ns
                if ts_val < 1e11:
                    payload["timestamp_ns"] = int(ts_val * 1_000_000_000)
                else:
                    payload["timestamp_ns"] = int(ts_val)
            elif metadata is not None:
                payload["timestamp_ns"] = metadata.received_at_ns

        # Map flat voltage/current/temp aliases if top-level pack_* fields are missing
        if "pack_voltage_v" not in payload:
            for alias in ("voltage_v", "voltage", "pack_voltage", "v_pack"):
                if alias in payload and payload[alias] is not None:
                    payload["pack_voltage_v"] = float(payload[alias])
                    break

        if "pack_current_a" not in payload:
            for alias in ("current_a", "current", "pack_current", "i_pack"):
                if alias in payload and payload[alias] is not None:
                    payload["pack_current_a"] = float(payload[alias])
                    break

        if "ambient_temperature_c" not in payload:
            for alias in ("ambient_temp_c", "temp_c", "temperature_c", "t_amb"):
                if alias in payload and payload[alias] is not None:
                    payload["ambient_temperature_c"] = float(payload[alias])
                    break

        try:
            return validate_telemetry_payload(payload)
        except Exception as exc:
            raise MalformedPayloadError(
                f"Validation failed during JSON telemetry parsing: {exc}",
                source_id=payload.get("system_id", metadata.source_id if metadata else None),
                details={"payload": payload},
            ) from exc
