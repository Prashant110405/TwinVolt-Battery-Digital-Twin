"""Unit tests for Binary Serial / BMS Frame Ingestion Adapter."""

import unittest

from src.ingestion.adapters.serial_frame_adapter import (
    SerialFrameConfig,
    SerialFrameTelemetryAdapter,
    compute_crc16_ccitt,
)
from src.ingestion.base import PacketMetadata
from src.ingestion.exceptions import FrameChecksumError, MalformedPayloadError
from src.telemetry.snapshots import TelemetrySnapshot


class TestSerialFrameTelemetryAdapter(unittest.TestCase):
    """Test suite verifying binary frame encoding, decoding, CRC validation, and error handling."""

    def setUp(self) -> None:
        self.adapter = SerialFrameTelemetryAdapter()

    def test_supports_format(self) -> None:
        """Verify supported format strings."""
        self.assertTrue(self.adapter.supports_format("SERIAL"))
        self.assertTrue(self.adapter.supports_format("BINARY"))
        self.assertTrue(self.adapter.supports_format("bms_frame"))
        self.assertFalse(self.adapter.supports_format("JSON"))

    def test_encode_and_decode_roundtrip(self) -> None:
        """Encode telemetry values into binary frame and decode back into TelemetrySnapshot."""
        frame_bytes = self.adapter.encode_frame(
            sequence=42,
            timestamp_ms=1700000000123,
            pack_voltage_v=51.84,
            pack_current_a=-15.50,  # Charging current
            soc_fraction=0.9250,
            ambient_temp_c=25.0,
            max_cell_temp_c=29.0,
            cell_voltages_v=[3.701, 3.705, 3.700, 3.704],
        )

        meta = PacketMetadata(source_id="embedded_bms_node")
        snapshot = self.adapter.parse(frame_bytes, metadata=meta)

        self.assertIsInstance(snapshot, TelemetrySnapshot)
        self.assertEqual(snapshot.system_id, "embedded_bms_node")
        self.assertEqual(snapshot.sequence_number, 42)
        self.assertEqual(snapshot.timestamp_ns, 1700000000123 * 1_000_000)
        self.assertAlmostEqual(snapshot.pack_voltage_v, 51.84, places=2)
        self.assertAlmostEqual(snapshot.pack_current_a, -15.50, places=2)
        self.assertAlmostEqual(snapshot.soc_fraction, 0.925, places=3)
        self.assertEqual(snapshot.ambient_temperature_c, 25.0)
        self.assertEqual(snapshot.max_cell_temperature_c, 29.0)
        self.assertEqual(len(snapshot.cell_telemetries), 4)
        self.assertAlmostEqual(snapshot.cell_telemetries[1].voltage_v, 3.705, places=3)

    def test_corrupted_crc_raises_frame_checksum_error(self) -> None:
        """Altering a byte in the payload without updating CRC must trigger FrameChecksumError."""
        frame_bytes = bytearray(
            self.adapter.encode_frame(
                sequence=1,
                timestamp_ms=1000,
                pack_voltage_v=3.7,
                pack_current_a=1.0,
                soc_fraction=0.5,
                ambient_temp_c=25.0,
                max_cell_temp_c=25.0,
                cell_voltages_v=[3.7],
            )
        )
        # Corrupt one payload byte
        frame_bytes[10] ^= 0xFF

        with self.assertRaises(FrameChecksumError):
            self.adapter.parse(bytes(frame_bytes))

    def test_truncated_frame_raises_malformed_payload_error(self) -> None:
        """Frame shorter than minimum length must raise MalformedPayloadError."""
        with self.assertRaises(MalformedPayloadError):
            self.adapter.parse(b"\xAA\x55\x01\x00")


if __name__ == "__main__":
    unittest.main()
