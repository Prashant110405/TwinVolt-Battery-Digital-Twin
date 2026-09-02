"""Binary Serial / BMS Frame Telemetry Ingestion Adapter.

Decodes and encodes compact binary telemetry frames produced by embedded BMS
microcontrollers (e.g. STM32, ESP32, TI BQ769x, ADI LTC681x) with CRC integrity checks.
"""

from dataclasses import dataclass
import struct
from typing import Any, Mapping, Optional, Union

from src.ingestion.base import AbstractIngestionAdapter, PacketMetadata
from src.ingestion.exceptions import FrameChecksumError, MalformedPayloadError
from src.schemas.telemetry_schema import validate_telemetry_payload
from src.telemetry.snapshots import TelemetrySnapshot


def compute_crc16_ccitt(data: bytes) -> int:
    """Computes CRC-16-CCITT (polynomial 0x1021, init 0xFFFF) over data bytes."""
    crc = 0xFFFF
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


@dataclass(frozen=True)
class SerialFrameConfig:
    """Configuration for binary BMS serial frame decoding."""

    magic_header: bytes = b"\xAA\x55"
    protocol_version: int = 1
    system_id_default: str = "bms_serial_system"


class SerialFrameTelemetryAdapter(AbstractIngestionAdapter):
    r"""Binary frame adapter for embedded BMS telemetry packets.

    Frame Structure:
    - [0:2]   Header (2 bytes): 0xAA 0x55
    - [2:3]   Version (1 byte): 0x01
    - [3:5]   Sequence Number (2 bytes uint16, Big-Endian)
    - [5:13]  Timestamp ms (8 bytes uint64, Big-Endian)
    - [13:15] Pack Voltage (2 bytes uint16 in 0.01 V)
    - [15:17] Pack Current (2 bytes int16 in 0.01 A)
    - [17:19] SOC (2 bytes uint16 in 0.01% [0..10000])
    - [19:20] Ambient Temp (1 byte int8 in °C)
    - [20:21] Max Cell Temp (1 byte int8 in °C)
    - [21:22] Cell Count N (1 byte uint8)
    - [22 : 22 + 2*N] Cell Voltages (N * 2 bytes uint16 in mV)
    - [22 + 2*N : 24 + 2*N] CRC-16 (2 bytes uint16)
    """

    def __init__(
        self,
        config: Optional[SerialFrameConfig] = None,
        adapter_name: str = "SerialFrameTelemetryAdapter",
    ) -> None:
        super().__init__(adapter_name=adapter_name)
        self._config = config or SerialFrameConfig()

    def supports_format(self, format_identifier: str) -> bool:
        """Returns True if the format is SERIAL, BINARY, or BMS_FRAME."""
        fmt = format_identifier.strip().upper()
        return fmt in ("SERIAL", "BINARY", "BMS_FRAME", "RAW_BYTES")

    def encode_frame(
        self,
        sequence: int,
        timestamp_ms: int,
        pack_voltage_v: float,
        pack_current_a: float,
        soc_fraction: float,
        ambient_temp_c: float,
        max_cell_temp_c: float,
        cell_voltages_v: list[float],
    ) -> bytes:
        """Encodes telemetry values into a binary BMS byte frame."""
        v_pack_c = int(round(pack_voltage_v * 100.0))
        i_pack_c = int(round(pack_current_a * 100.0))
        soc_bp = int(round(soc_fraction * 10000.0))
        t_amb_int = int(round(ambient_temp_c))
        t_max_int = int(round(max_cell_temp_c))
        n_cells = len(cell_voltages_v)

        header_and_body = struct.pack(
            ">2sBHQhhHbbB",
            self._config.magic_header,
            self._config.protocol_version,
            sequence & 0xFFFF,
            timestamp_ms,
            v_pack_c & 0xFFFF,
            i_pack_c,
            soc_bp & 0xFFFF,
            t_amb_int,
            t_max_int,
            n_cells & 0xFF,
        )

        cell_bytes = bytearray()
        for v in cell_voltages_v:
            v_mv = int(round(v * 1000.0))
            cell_bytes.extend(struct.pack(">H", v_mv & 0xFFFF))

        payload_to_crc = header_and_body + bytes(cell_bytes)
        crc = compute_crc16_ccitt(payload_to_crc)
        return payload_to_crc + struct.pack(">H", crc)

    def parse(
        self,
        raw_data: Union[str, bytes, Mapping[str, Any]],
        metadata: Optional[PacketMetadata] = None,
    ) -> TelemetrySnapshot:
        """Decodes binary frame bytes into a TelemetrySnapshot.

        Raises:
            MalformedPayloadError: If frame length or header is invalid.
            FrameChecksumError: If CRC-16 checksum verification fails.
        """
        if isinstance(raw_data, str):
            # Try hex-string decode
            try:
                frame_bytes = bytes.fromhex(raw_data.strip())
            except Exception as exc:
                raise MalformedPayloadError(
                    f"Failed to decode hex string frame: {exc}",
                    source_id=metadata.source_id if metadata else None,
                ) from exc
        elif isinstance(raw_data, (bytes, bytearray)):
            frame_bytes = bytes(raw_data)
        else:
            raise MalformedPayloadError(
                f"SerialFrameTelemetryAdapter expects bytes or hex str, got {type(raw_data).__name__}.",
                source_id=metadata.source_id if metadata else None,
            )

        min_len = 24  # 22 bytes header/fixed + 2 bytes CRC (0 cells)
        if len(frame_bytes) < min_len:
            raise MalformedPayloadError(
                f"Frame length {len(frame_bytes)} bytes is less than minimum {min_len} bytes.",
                source_id=metadata.source_id if metadata else None,
            )

        # 1. Validate CRC
        payload_data = frame_bytes[:-2]
        received_crc = struct.unpack(">H", frame_bytes[-2:])[0]
        expected_crc = compute_crc16_ccitt(payload_data)
        if received_crc != expected_crc:
            raise FrameChecksumError(
                f"CRC16 checksum mismatch: received 0x{received_crc:04X}, computed 0x{expected_crc:04X}.",
                source_id=metadata.source_id if metadata else None,
                details={"received_crc": received_crc, "expected_crc": expected_crc},
            )

        # 2. Unpack fixed fields
        try:
            magic, version, seq, ts_ms, v_pack_c, i_pack_c, soc_bp, t_amb, t_max, n_cells = struct.unpack(
                ">2sBHQhhHbbB",
                payload_data[:22],
            )
        except Exception as exc:
            raise MalformedPayloadError(
                f"Failed to unpack binary header: {exc}",
                source_id=metadata.source_id if metadata else None,
            ) from exc

        if magic != self._config.magic_header:
            raise MalformedPayloadError(
                f"Invalid magic header {magic!r}, expected {self._config.magic_header!r}.",
                source_id=metadata.source_id if metadata else None,
            )

        # 3. Unpack cell voltages
        expected_cell_bytes_len = n_cells * 2
        actual_cell_bytes = payload_data[22:]
        if len(actual_cell_bytes) != expected_cell_bytes_len:
            raise MalformedPayloadError(
                f"Expected {expected_cell_bytes_len} bytes for {n_cells} cells, got {len(actual_cell_bytes)} bytes.",
                source_id=metadata.source_id if metadata else None,
            )

        direct_cells = []
        for i in range(n_cells):
            v_mv = struct.unpack(">H", actual_cell_bytes[i * 2 : (i + 1) * 2])[0]
            direct_cells.append({
                "cell_id": f"cell_{i}",
                "voltage_v": round(v_mv / 1000.0, 4),
            })

        sys_id = metadata.source_id if metadata else self._config.system_id_default
        timestamp_ns = int(ts_ms * 1_000_000)

        payload_dict: dict[str, Any] = {
            "snapshot_id": f"{sys_id}_{timestamp_ns}",
            "system_id": sys_id,
            "timestamp_ns": timestamp_ns,
            "sequence_number": seq,
            "pack_voltage_v": round(v_pack_c / 100.0, 4),
            "pack_current_a": round(i_pack_c / 100.0, 4),
            "ambient_temperature_c": float(t_amb),
            "max_cell_temperature_c": float(t_max),
            "soc_fraction": round(soc_bp / 10000.0, 4),
            "direct_cells": direct_cells,
        }

        return validate_telemetry_payload(payload_dict)
