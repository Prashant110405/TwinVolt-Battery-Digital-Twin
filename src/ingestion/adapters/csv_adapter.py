"""CSV / Tabular Telemetry Ingestion Adapter.

Parses CSV strings, single log lines, and tabular time-series data streams
into strongly-typed TelemetrySnapshot instances with configurable column mappings.
"""

import csv
import io
from typing import Any, Mapping, Optional, Sequence, Union

from src.ingestion.base import AbstractIngestionAdapter, PacketMetadata
from src.ingestion.exceptions import MalformedPayloadError
from src.schemas.telemetry_schema import validate_telemetry_payload
from src.telemetry.snapshots import TelemetrySnapshot


class CSVTelemetryAdapter(AbstractIngestionAdapter):
    """Parses delimited tabular CSV telemetry data."""

    def __init__(
        self,
        adapter_name: str = "CSVTelemetryAdapter",
        delimiter: str = ",",
        timestamp_col: str = "timestamp_s",
        voltage_col: str = "voltage_v",
        current_col: str = "current_a",
        temp_col: str = "temperature_c",
        soc_col: str = "soc_fraction",
        system_id_col: Optional[str] = "system_id",
        cell_prefix: str = "cell_v_",
    ) -> None:
        super().__init__(adapter_name=adapter_name)
        self._delimiter = delimiter
        self._timestamp_col = timestamp_col
        self._voltage_col = voltage_col
        self._current_col = current_col
        self._temp_col = temp_col
        self._soc_col = soc_col
        self._system_id_col = system_id_col
        self._cell_prefix = cell_prefix

    def supports_format(self, format_identifier: str) -> bool:
        """Returns True if the format is CSV-compatible."""
        fmt = format_identifier.strip().upper()
        return fmt in ("CSV", "TEXT/CSV", "TABULAR", "TSV")

    def parse(
        self,
        raw_data: Union[str, bytes, Mapping[str, Any]],
        metadata: Optional[PacketMetadata] = None,
    ) -> TelemetrySnapshot:
        """Parses a single CSV line or row dictionary into a TelemetrySnapshot."""
        if isinstance(raw_data, Mapping):
            row_dict = {str(k).strip(): v for k, v in raw_data.items()}
        elif isinstance(raw_data, (str, bytes)):
            text = raw_data.decode("utf-8") if isinstance(raw_data, bytes) else raw_data
            reader = csv.DictReader(io.StringIO(text.strip()), delimiter=self._delimiter)
            try:
                row_dict = next(reader)
            except StopIteration as exc:
                raise MalformedPayloadError(
                    "CSV data is empty or missing data rows.",
                    source_id=metadata.source_id if metadata else None,
                ) from exc
            except Exception as exc:
                raise MalformedPayloadError(
                    f"Failed to parse CSV row: {exc}",
                    source_id=metadata.source_id if metadata else None,
                ) from exc
        else:
            raise MalformedPayloadError(
                f"CSVTelemetryAdapter expects str, bytes, or Mapping, got {type(raw_data).__name__}.",
                source_id=metadata.source_id if metadata else None,
            )

        return self._row_to_snapshot(row_dict, metadata)

    def parse_multiple(
        self,
        raw_csv_text: Union[str, bytes],
        metadata: Optional[PacketMetadata] = None,
    ) -> list[TelemetrySnapshot]:
        """Parses multi-line CSV text with a header into a list of TelemetrySnapshot instances."""
        text = raw_csv_text.decode("utf-8") if isinstance(raw_csv_text, bytes) else raw_csv_text
        reader = csv.DictReader(io.StringIO(text.strip()), delimiter=self._delimiter)
        snapshots = []
        for line_idx, row in enumerate(reader):
            try:
                snap = self._row_to_snapshot(row, metadata, sequence_number=line_idx)
                snapshots.append(snap)
            except Exception as exc:
                raise MalformedPayloadError(
                    f"Error parsing CSV line {line_idx + 1}: {exc}",
                    source_id=metadata.source_id if metadata else None,
                    details={"row": row, "line_number": line_idx + 1},
                ) from exc
        return snapshots

    def _row_to_snapshot(
        self,
        row: dict[str, Any],
        metadata: Optional[PacketMetadata],
        sequence_number: Optional[int] = None,
    ) -> TelemetrySnapshot:
        """Converts a dictionary row into a TelemetrySnapshot."""
        sys_id = row.get(self._system_id_col or "") or (metadata.source_id if metadata else "battery_system_1")

        # Resolve timestamp
        timestamp_ns: int
        if self._timestamp_col in row and row[self._timestamp_col] != "":
            raw_ts = float(row[self._timestamp_col])
            # If timestamp in seconds (< 1e11), convert to ns
            if raw_ts < 1e11:
                timestamp_ns = int(raw_ts * 1_000_000_000)
            else:
                timestamp_ns = int(raw_ts)
        elif "timestamp_ns" in row and row["timestamp_ns"] != "":
            timestamp_ns = int(float(row["timestamp_ns"]))
        elif metadata is not None:
            timestamp_ns = metadata.received_at_ns
        else:
            timestamp_ns = 0

        # Build payload dictionary
        payload: dict[str, Any] = {
            "snapshot_id": f"{sys_id}_{timestamp_ns}",
            "system_id": str(sys_id).strip(),
            "timestamp_ns": timestamp_ns,
        }
        if sequence_number is not None:
            payload["sequence_number"] = sequence_number

        # Map electrical & thermal fields
        if self._voltage_col in row and row[self._voltage_col] not in ("", None):
            payload["pack_voltage_v"] = float(row[self._voltage_col])
        if self._current_col in row and row[self._current_col] not in ("", None):
            payload["pack_current_a"] = float(row[self._current_col])
        if self._temp_col in row and row[self._temp_col] not in ("", None):
            payload["ambient_temperature_c"] = float(row[self._temp_col])
        if self._soc_col in row and row[self._soc_col] not in ("", None):
            payload["soc_fraction"] = float(row[self._soc_col])

        # Extract discrete cell voltages matching cell_prefix (e.g. cell_v_0, cell_v_1)
        direct_cells = []
        for col_name, val in row.items():
            if col_name.startswith(self._cell_prefix) and val not in ("", None):
                cell_id = col_name[len(self._cell_prefix) :]
                direct_cells.append({
                    "cell_id": cell_id,
                    "voltage_v": float(val),
                })
        if direct_cells:
            payload["direct_cells"] = direct_cells

        try:
            return validate_telemetry_payload(payload)
        except Exception as exc:
            raise MalformedPayloadError(
                f"Validation failed during CSV row parsing: {exc}",
                source_id=sys_id,
                details={"row": row, "payload": payload},
            ) from exc
