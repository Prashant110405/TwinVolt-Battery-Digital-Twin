"""Robust Frame Parser for Arduino Serial Telemetry Streams.

Parses CSV, JSON lines, and binary BMS frames from serial hardware into
strongly-typed, validated ParsedHardwareRecord instances.
Rejects non-finite values (NaN, Inf), bootloader logs, and malformed lines.
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
import struct
import time
from typing import Any, Mapping, Optional, Sequence

from src.gateway.arduino.models import ArduinoConfig, ParsedHardwareRecord, SerialDataFormat


# Common bootloader or log message signatures to ignore cleanly
BOOT_LOG_SIGNATURES = (
    re.compile(r"^(?:boot|init|ready|setup|starting|twinvolt|arduino|reset|version)\b", re.IGNORECASE),
    re.compile(r"^(?:bms\s+online|wifi|connected|calibrating)\b", re.IGNORECASE),
)


def _safe_float(val: Any) -> Optional[float]:
    """Safely converts value to float, strictly rejecting None, bool, NaN, and Inf."""
    if val is None or isinstance(val, bool):
        return None
    try:
        f = float(val)
        return f if math.isfinite(f) else None
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> Optional[int]:
    """Safely converts value to int."""
    if val is None or isinstance(val, bool):
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


class ArduinoFrameParser:
    """Decodes, validates, and standardizes raw serial payloads from Arduino devices."""

    def __init__(self, config: ArduinoConfig) -> None:
        self.config = config
        self._seq_counter = 0

    def parse_line(
        self,
        raw_payload: str,
        received_timestamp_ns: Optional[int] = None,
    ) -> ParsedHardwareRecord:
        """Parses a single line or payload from the serial stream."""
        self._seq_counter += 1
        t_recv = received_timestamp_ns or time.time_ns()
        cleaned = raw_payload.strip()

        # 1. Filter empty lines
        if not cleaned:
            return ParsedHardwareRecord(
                source_id=self.config.system_id,
                sequence=self._seq_counter,
                received_timestamp_ns=t_recv,
                voltage_v=0.0,
                raw_payload=raw_payload,
                is_valid=False,
                errors=("Empty line received from serial stream.",),
            )

        # 2. Check for bootloader / informational logs
        for pattern in BOOT_LOG_SIGNATURES:
            if pattern.search(cleaned):
                return ParsedHardwareRecord(
                    source_id=self.config.system_id,
                    sequence=self._seq_counter,
                    received_timestamp_ns=t_recv,
                    voltage_v=0.0,
                    raw_payload=raw_payload,
                    is_valid=False,
                    errors=(f"Informational / boot log skipped: '{cleaned[:40]}'",),
                )

        # 3. Format dispatch
        fmt = self.config.data_format
        if fmt == SerialDataFormat.AUTO:
            if cleaned.startswith("{") and cleaned.endswith("}"):
                return self._parse_json(cleaned, t_recv)
            else:
                return self._parse_csv(cleaned, t_recv)
        elif fmt == SerialDataFormat.JSON:
            return self._parse_json(cleaned, t_recv)
        elif fmt == SerialDataFormat.CSV:
            return self._parse_csv(cleaned, t_recv)
        elif fmt == SerialDataFormat.BMS_BINARY:
            return self._parse_binary_hex_or_raw(cleaned, t_recv)
        else:
            return self._parse_csv(cleaned, t_recv)

    def _parse_json(self, line: str, t_recv: int) -> ParsedHardwareRecord:
        """Parses JSON-encoded telemetry frame."""
        try:
            data = json.loads(line)
        except Exception as exc:
            return ParsedHardwareRecord(
                source_id=self.config.system_id,
                sequence=self._seq_counter,
                received_timestamp_ns=t_recv,
                voltage_v=0.0,
                raw_payload=line,
                is_valid=False,
                errors=(f"JSON parse error: {exc}",),
            )

        if not isinstance(data, dict):
            return ParsedHardwareRecord(
                source_id=self.config.system_id,
                sequence=self._seq_counter,
                received_timestamp_ns=t_recv,
                voltage_v=0.0,
                raw_payload=line,
                is_valid=False,
                errors=("JSON payload must be a key-value object.",),
            )

        # Look up voltage with aliases
        v_keys = (self.config.voltage_column, "v", "voltage", "voltage_V", "pack_v")
        raw_v = None
        for k in v_keys:
            if k in data:
                raw_v = data[k]
                break

        voltage_v = _safe_float(raw_v)
        if voltage_v is None or voltage_v <= 0.0:
            return ParsedHardwareRecord(
                source_id=self.config.system_id,
                sequence=self._seq_counter,
                received_timestamp_ns=t_recv,
                voltage_v=0.0,
                raw_payload=line,
                is_valid=False,
                errors=(f"Missing or non-positive voltage reading: got '{raw_v}'.",),
            )

        # Look up current with aliases
        i_keys = (self.config.current_column, "i", "current", "current_A", "current_a", "pack_i")
        raw_i = None
        for k in i_keys:
            if k in data:
                raw_i = data[k]
                break
        current_a = _safe_float(raw_i)

        # Look up temperature with aliases
        t_keys = (self.config.temp_column, "temp", "temperature", "temp_c", "temperature_C", "temperature_c")
        raw_t = None
        for k in t_keys:
            if k in data:
                raw_t = data[k]
                break
        temperature_c = _safe_float(raw_t)

        # Look up SoC with aliases
        soc_keys = ("soc", "soc_fraction", "state_of_charge", "soc_pct", "soc_percent")
        if self.config.soc_column:
            soc_keys = (self.config.soc_column,) + soc_keys
        raw_soc = None
        for k in soc_keys:
            if k in data:
                raw_soc = data[k]
                break
        soc_val = _safe_float(raw_soc)
        soc_fraction = None
        if soc_val is not None:
            if 0.0 <= soc_val <= 1.0:
                soc_fraction = soc_val
            elif 1.0 < soc_val <= 100.0:
                soc_fraction = soc_val / 100.0

        # Look up timestamp
        ts_keys = ("timestamp_ms", "timestamp_s", "timestamp", "time_ms", "millis")
        raw_ts = None
        for k in ts_keys:
            if k in data:
                raw_ts = data[k]
                break
        source_ts_ns = None
        numeric_ts = _safe_float(raw_ts)
        if numeric_ts is not None and numeric_ts > 0.0:
            if numeric_ts > 1e16:
                source_ts_ns = int(numeric_ts)
            elif numeric_ts > 1e11:
                source_ts_ns = int(numeric_ts * 1_000_000)
            elif numeric_ts > 1e8:
                source_ts_ns = int(numeric_ts * 1_000_000_000)
            else:
                # Local Arduino millis() counter
                source_ts_ns = int(numeric_ts * 1_000_000)

        # Cell voltages (array or cell_v_1, cell_v_2, etc.)
        cell_voltages: list[float] = []
        if "cells" in data and isinstance(data["cells"], list):
            for cv in data["cells"]:
                cf = _safe_float(cv)
                if cf is not None and cf > 0.0:
                    cell_voltages.append(cf)
        else:
            for k, val in sorted(data.items()):
                if k.lower().startswith(self.config.cell_prefix.lower()) or k.lower().startswith("c_"):
                    cf = _safe_float(val)
                    if cf is not None and cf > 0.0:
                        cell_voltages.append(cf)

        # Calculate power: P = V × I only if both are valid numbers
        power_w = (voltage_v * current_a) if current_a is not None else None

        return ParsedHardwareRecord(
            source_id=self.config.system_id,
            sequence=self._seq_counter,
            source_timestamp_ns=source_ts_ns,
            received_timestamp_ns=t_recv,
            voltage_v=voltage_v,
            current_a=current_a,
            power_w=power_w,
            temperature_c=temperature_c,
            soc_fraction=soc_fraction,
            cell_voltages_v=tuple(cell_voltages),
            raw_payload=line,
            is_valid=True,
        )

    def _parse_csv(self, line: str, t_recv: int) -> ParsedHardwareRecord:
        """Parses CSV-encoded telemetry frame."""
        try:
            reader = csv.reader(io.StringIO(line))
            tokens = next(reader)
        except Exception as exc:
            return ParsedHardwareRecord(
                source_id=self.config.system_id,
                sequence=self._seq_counter,
                received_timestamp_ns=t_recv,
                voltage_v=0.0,
                raw_payload=line,
                is_valid=False,
                errors=(f"CSV tokenization error: {exc}",),
            )

        tokens = [t.strip() for t in tokens if t.strip()]
        if not tokens:
            return ParsedHardwareRecord(
                source_id=self.config.system_id,
                sequence=self._seq_counter,
                received_timestamp_ns=t_recv,
                voltage_v=0.0,
                raw_payload=line,
                is_valid=False,
                errors=("CSV line contained no data tokens.",),
            )

        # Check if line is a header row (e.g. "voltage,current,temperature")
        if any(tok.lower() in ("voltage", "v", "voltage_v", "current", "temp") for tok in tokens):
            return ParsedHardwareRecord(
                source_id=self.config.system_id,
                sequence=self._seq_counter,
                received_timestamp_ns=t_recv,
                voltage_v=0.0,
                raw_payload=line,
                is_valid=False,
                errors=("Header line detected and skipped.",),
            )

        # Key-value pair format: "V=3.7,I=1.2,T=25.0"
        if any("=" in tok or ":" in tok for tok in tokens):
            kv_dict: dict[str, str] = {}
            for tok in tokens:
                sep = "=" if "=" in tok else ":"
                parts = tok.split(sep, 1)
                if len(parts) == 2:
                    kv_dict[parts[0].strip().lower()] = parts[1].strip()
            return self._parse_json(json.dumps(kv_dict), t_recv)

        # Positional CSV mapping
        # Supported conventions:
        # 1 token:  [voltage]
        # 2 tokens: [voltage, current] OR [timestamp, voltage]
        # 3 tokens: [timestamp, voltage, current] OR [voltage, current, temp]
        # 4 tokens: [timestamp, voltage, current, temp]
        # >4 tokens: [timestamp, voltage, current, temp, cell_1, cell_2, ...]
        floats = [_safe_float(t) for t in tokens]
        if any(f is None for f in floats):
            return ParsedHardwareRecord(
                source_id=self.config.system_id,
                sequence=self._seq_counter,
                received_timestamp_ns=t_recv,
                voltage_v=0.0,
                raw_payload=line,
                is_valid=False,
                errors=(f"Non-numeric tokens in CSV row: {tokens}",),
            )

        numeric_vals = [f for f in floats if f is not None]
        source_ts_ns: Optional[int] = None
        voltage_v: float = 0.0
        current_a: Optional[float] = None
        temperature_c: Optional[float] = None
        cells: list[float] = []

        n = len(numeric_vals)
        if n == 1:
            voltage_v = numeric_vals[0]
        elif n == 2:
            # If first is large integer/float (millis), it is timestamp
            if numeric_vals[0] > 1000.0 and numeric_vals[1] < 100.0:
                source_ts_ns = int(numeric_vals[0] * 1_000_000)
                voltage_v = numeric_vals[1]
            else:
                voltage_v = numeric_vals[0]
                current_a = numeric_vals[1]
        elif n == 3:
            # Check if first is timestamp millis
            if numeric_vals[0] > 1000.0 and numeric_vals[1] < 100.0:
                source_ts_ns = int(numeric_vals[0] * 1_000_000)
                voltage_v = numeric_vals[1]
                current_a = numeric_vals[2]
            else:
                voltage_v = numeric_vals[0]
                current_a = numeric_vals[1]
                temperature_c = numeric_vals[2]
        elif n >= 4:
            source_ts_ns = int(numeric_vals[0] * 1_000_000)
            voltage_v = numeric_vals[1]
            current_a = numeric_vals[2]
            temperature_c = numeric_vals[3]
            if n > 4:
                cells = [cv for cv in numeric_vals[4:] if cv > 0.0]

        if voltage_v <= 0.0:
            return ParsedHardwareRecord(
                source_id=self.config.system_id,
                sequence=self._seq_counter,
                received_timestamp_ns=t_recv,
                voltage_v=0.0,
                raw_payload=line,
                is_valid=False,
                errors=(f"Invalid voltage reading in CSV row: {voltage_v} V",),
            )

        power_w = (voltage_v * current_a) if current_a is not None else None

        return ParsedHardwareRecord(
            source_id=self.config.system_id,
            sequence=self._seq_counter,
            source_timestamp_ns=source_ts_ns,
            received_timestamp_ns=t_recv,
            voltage_v=voltage_v,
            current_a=current_a,
            power_w=power_w,
            temperature_c=temperature_c,
            cell_voltages_v=tuple(cells),
            raw_payload=line,
            is_valid=True,
        )

    def _parse_binary_hex_or_raw(self, line: str, t_recv: int) -> ParsedHardwareRecord:
        """Parses hex-encoded or binary BMS frame."""
        try:
            raw_bytes = bytes.fromhex(line.replace(" ", "").replace("0x", ""))
        except Exception:
            raw_bytes = line.encode("latin1")

        if len(raw_bytes) < 22 or raw_bytes[:2] != b"\xAA\x55":
            return ParsedHardwareRecord(
                source_id=self.config.system_id,
                sequence=self._seq_counter,
                received_timestamp_ns=t_recv,
                voltage_v=0.0,
                raw_payload=line,
                is_valid=False,
                errors=("Invalid binary BMS frame magic or length.",),
            )

        try:
            seq, ts_ms, v_centivolts, i_centiamps, soc_centipct, temp_amb = struct.unpack_from(
                ">HIHhHb", raw_bytes, 3
            )
            v = v_centivolts / 100.0
            i = i_centiamps / 100.0
            soc = soc_centipct / 10000.0
            temp = float(temp_amb)
            return ParsedHardwareRecord(
                source_id=self.config.system_id,
                sequence=seq,
                source_timestamp_ns=int(ts_ms * 1_000_000),
                received_timestamp_ns=t_recv,
                voltage_v=v,
                current_a=i,
                power_w=v * i,
                temperature_c=temp,
                soc_fraction=soc,
                raw_payload=line,
                is_valid=True,
            )
        except Exception as exc:
            return ParsedHardwareRecord(
                source_id=self.config.system_id,
                sequence=self._seq_counter,
                received_timestamp_ns=t_recv,
                voltage_v=0.0,
                raw_payload=line,
                is_valid=False,
                errors=(f"Binary frame unpack error: {exc}",),
            )
