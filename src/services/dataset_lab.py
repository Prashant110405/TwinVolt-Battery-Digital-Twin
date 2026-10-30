"""Ephemeral, bounded dataset parsing and profiling for Dataset Lab.

Uploaded files are parsed in memory and are never written to a user-controlled path.
The service intentionally does not ingest rows into live telemetry or run battery models.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import statistics
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional


ALLOWED_FORMATS = {"csv", "json"}
MAX_ROWS = 100_000
MAX_COLUMNS = 200
MAX_CELLS = 500_000
MAX_PREVIEW = 100
MAX_SERIES = 2_000
TTL_SECONDS = 60 * 60
QUANTITIES = {"timestamp", "voltage", "current", "temperature", "soc", "soh", "cell_voltage"}
UNIT_FACTORS = {
    "voltage": {"V": 1.0, "mV": 0.001},
    "current": {"A": 1.0, "mA": 0.001},
    "temperature": {"°C": 1.0, "C": 1.0, "°F": (5.0 / 9.0)},
    "soc": {"%": 0.01, "fraction": 1.0},
    "soh": {"%": 0.01, "fraction": 1.0},
    "cell_voltage": {"V": 1.0, "mV": 0.001},
}
UNIT_ALIASES = {
    "v": "V", "volt": "V", "volts": "V", "mv": "mV", "millivolt": "mV",
    "a": "A", "amp": "A", "amps": "A", "ampere": "A", "ma": "mA",
    "c": "°C", "°c": "°C", "degc": "°C", "celsius": "°C", "°f": "°F", "fahrenheit": "°F",
    "%": "%", "percent": "%", "fraction": "fraction", "ns": "ns", "ms": "ms", "s": "s",
}
TIMESTAMP_FACTORS = {"ns": 1.0, "ms": 1_000_000.0, "s": 1_000_000_000.0}


class DatasetError(ValueError):
    """An upload or dataset query is invalid."""


def _number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return None
        try:
            result = float(cleaned)
        except ValueError:
            return None
    else:
        return None
    return result if math.isfinite(result) else None


def _timestamp_ns(value: Any, unit: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    numeric = _number(value)
    if numeric is not None:
        if unit not in TIMESTAMP_FACTORS:
            return None
        nanoseconds = numeric * TIMESTAMP_FACTORS[unit]
        if not math.isfinite(nanoseconds) or abs(nanoseconds) > 8.64e21:
            return None
        return int(nanoseconds)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                return None
            return int(parsed.timestamp() * 1_000_000_000)
        except (ValueError, OverflowError, OSError):
            return None
    return None


def parse_dataset(filename: str, content: bytes) -> dict[str, Any]:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_FORMATS:
        if ext == "xlsx":
            raise DatasetError("XLSX is unavailable: this installation has no XLSX parser (openpyxl). Upload CSV or JSON.")
        if ext == "xls":
            raise DatasetError("XLS is unsupported. Upload CSV or JSON.")
        if ext == "parquet":
            raise DatasetError("Parquet is unavailable: this installation has no Parquet parser (pyarrow). Upload CSV or JSON.")
        raise DatasetError("Unsupported format. Supported formats in this installation: CSV and JSON.")
    if not content:
        raise DatasetError("The uploaded file is empty.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise DatasetError("Could not decode the file as UTF-8. Re-export it as UTF-8 CSV or JSON.") from exc

    warnings: list[str] = []
    if ext == "csv":
        try:
            raw_reader = csv.reader(io.StringIO(text, newline=""), strict=True)
            try:
                columns = next(raw_reader)
            except StopIteration:
                columns = []
            if not columns or any(not name or not name.strip() for name in columns):
                raise DatasetError("CSV must have non-empty column headers.")
            if len(columns) > MAX_COLUMNS or len(set(columns)) != len(columns):
                raise DatasetError(f"CSV must have at most {MAX_COLUMNS} unique columns.")
            rows = []
            for row in raw_reader:
                if len(rows) >= MAX_ROWS:
                    raise DatasetError(f"Dataset exceeds the {MAX_ROWS:,}-row processing limit.")
                if (len(rows) + 1) * len(columns) > MAX_CELLS:
                    raise DatasetError(f"Dataset exceeds the {MAX_CELLS:,}-cell processing limit.")
                if not row:
                    rows.append({col: None for col in columns})
                else:
                    row_dict = {}
                    for i, col in enumerate(columns):
                        row_dict[col] = row[i] if i < len(row) else None
                    if len(row) > len(columns):
                        warnings.append("Some CSV rows contain more fields than the header; extra fields were ignored.")
                    rows.append(row_dict)
        except csv.Error as exc:
            raise DatasetError(f"Malformed CSV: {exc}") from exc
    else:
        try:
            parsed = json.loads(text, parse_constant=lambda value: value)
        except json.JSONDecodeError as exc:
            raise DatasetError(f"Malformed JSON at line {exc.lineno}, column {exc.colno}.") from exc
        if isinstance(parsed, dict):
            rows = parsed.get("data")
            if rows is None:
                rows = parsed.get("rows")
            if isinstance(parsed.get("metadata"), dict):
                warnings.append("Top-level metadata was retained as context only; no unit or source assumptions were applied.")
        else:
            rows = parsed
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise DatasetError("JSON must contain an array of row objects, or an object with a 'data'/'rows' array.")
        if not rows:
            raise DatasetError("The dataset contains no data rows.")
        if len(rows) > MAX_ROWS:
            raise DatasetError(f"Dataset exceeds the {MAX_ROWS:,}-row processing limit.")
        columns = list(dict.fromkeys(key for row in rows for key in row.keys()))
        if not columns or len(columns) > MAX_COLUMNS or any(not isinstance(name, str) for name in columns):
            raise DatasetError(f"JSON must contain 1–{MAX_COLUMNS} named columns.")
        if len(rows) * len(columns) > MAX_CELLS:
            raise DatasetError(f"Dataset exceeds the {MAX_CELLS:,}-cell processing limit.")
        rows = [{column: row.get(column) for column in columns} for row in rows]

    if not rows:
        raise DatasetError("The dataset contains headers but no data rows.")
    if not columns:
        raise DatasetError("No columns were found.")
    return {"columns": list(columns), "rows": rows, "warnings": list(dict.fromkeys(warnings))}


def _column_profile(columns: list[str], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for column in columns:
        values = [row.get(column) for row in rows]
        missing = sum(value is None or (isinstance(value, str) and not value.strip()) for value in values)
        parsed = [_number(value) for value in values]
        finite = [value for value in parsed if value is not None]
        non_finite_tokens = {"nan", "inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}
        non_finite = sum(
            (isinstance(value, (float, int)) and not isinstance(value, bool) and not math.isfinite(float(value)))
            or (isinstance(value, str) and value.strip().lower() in non_finite_tokens)
            for value in values
        )
        has_numeric_evidence = bool(finite or non_finite)
        invalid_numeric = sum(
            has_numeric_evidence and isinstance(value, str) and value.strip()
            and value.strip().lower() not in non_finite_tokens and _number(value) is None
            for value in values
        )
        if has_numeric_evidence and invalid_numeric:
            inferred = "mixed_numeric_text"
        elif has_numeric_evidence:
            inferred = "numeric"
        elif all(isinstance(value, bool) or value is None for value in values):
            inferred = "boolean"
        elif any(_timestamp_ns(value, None) is not None for value in values if isinstance(value, str)):
            inferred = "timestamp_candidate"
        else:
            inferred = "text"
        normalized = column.lower()
        suggestion = next((key for key, tokens in {
            "timestamp": ("timestamp", "time", "date"), "voltage": ("voltage", "volt", " v"),
            "current": ("current", "amp", " amp"), "temperature": ("temperature", "temp"),
            "soc": ("soc", "state_of_charge"), "soh": ("soh", "state_of_health"),
        }.items() if any(token in normalized for token in tokens)), None)
        unit_match = re.search(r"\(([^)]+)\)|\[([^]]+)\]", column)
        unit_hint = (unit_match.group(1) or unit_match.group(2)) if unit_match else None
        result.append({"name": column, "inferred_type": inferred, "missing_count": missing,
                       "invalid_numeric_count": int(invalid_numeric), "non_finite_count": int(non_finite),
                       "numeric_min": min(finite) if finite else None, "numeric_max": max(finite) if finite else None,
                       "candidate_mapping": suggestion, "candidate_unit": unit_hint})
    return result


def _profile(entry: dict[str, Any]) -> dict[str, Any]:
    rows, columns = entry["rows"], entry["columns"]
    seen = set()
    duplicate_rows = 0
    for row in rows:
        marker = json.dumps(row, sort_keys=True, default=str, allow_nan=True)
        if marker in seen:
            duplicate_rows += 1
        else:
            seen.add(marker)
    mapping = entry["mappings"]
    timestamp_column = mapping.get("timestamp", {}).get("column")
    timestamp_unit = mapping.get("timestamp", {}).get("unit")
    timestamps = [_timestamp_ns(row.get(timestamp_column), timestamp_unit) for row in rows] if timestamp_column else []
    valid_timestamps = [value for value in timestamps if value is not None]
    duplicate_times = len(valid_timestamps) - len(set(valid_timestamps))
    monotonic = all(a <= b for a, b in zip(valid_timestamps, valid_timestamps[1:]))
    intervals_s = [(b - a) / 1e9 for a, b in zip(valid_timestamps, valid_timestamps[1:]) if b > a]
    return {
        "row_count": len(rows), "column_count": len(columns), "columns": _column_profile(columns, rows),
        "duplicate_row_count": duplicate_rows,
        "timestamp": {"column": timestamp_column, "available": bool(timestamp_column and valid_timestamps),
                      "valid_count": len(valid_timestamps), "missing_or_invalid_count": len(rows) - len(valid_timestamps) if timestamp_column else len(rows),
                      "monotonic_non_decreasing": monotonic if valid_timestamps else None,
                      "duplicate_count": duplicate_times,
                      "sampling_interval_seconds": {"count": len(intervals_s), "min": min(intervals_s) if intervals_s else None,
                          "median": statistics.median(intervals_s) if intervals_s else None,
                          "max": max(intervals_s) if intervals_s else None}},
        "mappings": mapping,
        "parser_warnings": entry["warnings"],
    }


class DatasetLabStore:
    """Bounded in-memory dataset registry with expiry and safe generated IDs."""
    def __init__(self, ttl_seconds: int = TTL_SECONDS) -> None:
        self._items: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._ttl = ttl_seconds

    def _purge(self) -> None:
        cutoff = time.monotonic() - self._ttl
        for dataset_id in [key for key, value in self._items.items() if value["created_monotonic"] < cutoff]:
            del self._items[dataset_id]

    def add(self, filename: str, content: bytes) -> dict[str, Any]:
        parsed = parse_dataset(filename, content)
        dataset_id = f"ds_{uuid.uuid4().hex}"
        now = datetime.now(timezone.utc).isoformat()
        entry = {**parsed, "dataset_id": dataset_id, "filename": filename[:255], "created_at": now,
                 "created_monotonic": time.monotonic(), "size_bytes": len(content), "mappings": {}}
        with self._lock:
            self._purge()
            if len(self._items) >= 10 or sum(value["size_bytes"] for value in self._items.values()) + len(content) > 100 * 1024 * 1024:
                raise DatasetError("Temporary dataset session capacity is full. Delete an upload and try again.")
            self._items[dataset_id] = entry
        return self.get(dataset_id)

    def _get_entry(self, dataset_id: str) -> dict[str, Any]:
        with self._lock:
            self._purge()
            if not re.fullmatch(r"ds_[0-9a-f]{32}", dataset_id) or dataset_id not in self._items:
                raise KeyError(dataset_id)
            return self._items[dataset_id]

    def get(self, dataset_id: str) -> dict[str, Any]:
        entry = self._get_entry(dataset_id)
        return {"dataset_id": entry["dataset_id"], "filename": entry["filename"], "created_at": entry["created_at"],
                "size_bytes": entry["size_bytes"], "row_count": len(entry["rows"]), "column_count": len(entry["columns"]),
                "profile": _profile(entry)}

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            self._purge()
            ids = list(self._items)
        return [self.get(key) for key in ids]

    def preview(self, dataset_id: str, offset: int, limit: int) -> dict[str, Any]:
        entry = self._get_entry(dataset_id)
        return {"columns": entry["columns"], "offset": offset, "limit": limit, "total_rows": len(entry["rows"]),
                "rows": entry["rows"][offset:offset + limit]}

    def map_columns(self, dataset_id: str, mappings: dict[str, dict[str, Optional[str]]]) -> dict[str, Any]:
        entry = self._get_entry(dataset_id)
        validated = {}
        for quantity, value in mappings.items():
            if quantity not in QUANTITIES and not (quantity.startswith("series:") and len(quantity) <= 100):
                raise DatasetError(f"Unsupported mapping quantity '{quantity}'.")
            column, unit = value.get("column"), value.get("unit")
            if column is None:
                continue
            if column not in entry["columns"]:
                raise DatasetError(f"Mapped column '{column}' does not exist in this dataset.")
            if quantity.startswith("series:") and not any(_number(row.get(column)) is not None for row in entry["rows"]):
                raise DatasetError(f"Custom series '{column}' has no finite numeric values.")
            if quantity in UNIT_FACTORS:
                normalized = UNIT_ALIASES.get((unit or "").strip().lower(), UNIT_ALIASES.get((unit or "").strip(), unit))
                if normalized not in UNIT_FACTORS[quantity]:
                    raise DatasetError(f"Unit '{unit}' is unsupported or missing for {quantity}; select an explicit compatible unit.")
                unit = normalized
            elif quantity == "timestamp":
                if unit not in {None, "ns", "ms", "s"}:
                    raise DatasetError("Numeric timestamp unit must be ns, ms, or s; ISO timestamps do not need a unit.")
            elif unit:
                unit = str(unit)[:32]
            validated[quantity] = {"column": column, "unit": unit}
        entry["mappings"] = validated
        return self.get(dataset_id)

    def series(self, dataset_id: str, columns: list[str], limit: int) -> dict[str, Any]:
        entry = self._get_entry(dataset_id)
        mapping = entry["mappings"]
        mapped_cols = {item["column"] for item in mapping.values() if item.get("column")}
        for column in columns:
            if column not in entry["columns"] and column != "calculated_power_w":
                raise DatasetError(f"Unknown series column '{column}'.")
            if column not in mapped_cols and column != "calculated_power_w":
                raise DatasetError(f"Column '{column}' must be explicitly mapped before it can be charted.")
        by_column = {item["column"]: (key, item) for key, item in mapping.items() if item.get("column")}
        voltage = mapping.get("voltage", {})
        current = mapping.get("current", {})
        if "calculated_power_w" in columns:
            if not voltage.get("column") or not current.get("column"):
                raise DatasetError("Calculated power requires explicitly mapped voltage and current columns.")
        rows = entry["rows"]
        stride = max(1, math.ceil(len(rows) / limit))
        indices = list(range(0, len(rows), stride))
        if indices[-1] != len(rows) - 1:
            indices.append(len(rows) - 1)
        time_map = mapping.get("timestamp")
        all_timestamps = [_timestamp_ns(row.get(time_map["column"]), time_map.get("unit")) for row in rows] if time_map else []
        valid_timestamps = [stamp for stamp in all_timestamps if stamp is not None]
        points = []
        previous_idx = -1
        for idx in indices:
            row = rows[idx]
            x = _timestamp_ns(row.get(time_map["column"]), time_map.get("unit")) if time_map else None
            gap_before = []
            for column in columns:
                if column == "calculated_power_w":
                    has_gap = any(
                        _number(rows[omitted].get(voltage["column"])) is None
                        or _number(rows[omitted].get(current["column"])) is None
                        for omitted in range(previous_idx + 1, idx)
                    )
                else:
                    has_gap = any(_number(rows[omitted].get(column)) is None for omitted in range(previous_idx + 1, idx))
                if has_gap:
                    gap_before.append(column)
            point: dict[str, Any] = {"row_index": idx, "gap_before": gap_before}
            if x is not None:
                point["timestamp_ns"] = x
            for column in columns:
                if column == "calculated_power_w":
                    v = _number(row.get(voltage["column"]))
                    i = _number(row.get(current["column"]))
                    v_unit, i_unit = voltage.get("unit"), current.get("unit")
                    point[column] = (v * UNIT_FACTORS["voltage"][v_unit] * i * UNIT_FACTORS["current"][i_unit]
                                     if v is not None and i is not None else None)
                    continue
                quantity, item = by_column[column]
                number = _number(row.get(column))
                if number is not None and quantity in UNIT_FACTORS:
                    if quantity == "temperature" and item["unit"] == "°F":
                        number = (number - 32.0) * 5.0 / 9.0
                    else:
                        number *= UNIT_FACTORS[quantity][item["unit"]]
                    if quantity in {"soc", "soh"}:
                        number *= 100.0
                point[column] = number
            points.append(point)
            previous_idx = idx
        return {"points": points, "raw_row_count": len(rows), "rendered_point_count": len(points), "stride": stride,
                "downsampling": "Deterministic row stride with final row retained; source rows are unchanged.",
                "x_axis": "timestamp_ns" if time_map else "row_index",
                "x_min_ns": min(valid_timestamps) if valid_timestamps else None,
                "x_max_ns": max(valid_timestamps) if valid_timestamps else None,
                "derived": {"calculated_power_w": {"label": "Calculated power", "formula": "P = V × I", "sign_convention": "Dataset current-sign convention is unknown; sign is preserved, no direction inferred."}} if "calculated_power_w" in columns else {}}

    def delete(self, dataset_id: str) -> None:
        entry = self._get_entry(dataset_id)
        with self._lock:
            self._items.pop(entry["dataset_id"], None)
