"""Unit tests for CSV Telemetry Ingestion Adapter."""

import unittest

from src.ingestion.adapters.csv_adapter import CSVTelemetryAdapter
from src.ingestion.base import PacketMetadata
from src.ingestion.exceptions import MalformedPayloadError
from src.telemetry.snapshots import TelemetrySnapshot


class TestCSVTelemetryAdapter(unittest.TestCase):
    """Test suite verifying single-row and multi-row CSV parsing with dynamic cell mapping."""

    def setUp(self) -> None:
        self.adapter = CSVTelemetryAdapter()

    def test_supports_format(self) -> None:
        """Verify supported format strings."""
        self.assertTrue(self.adapter.supports_format("CSV"))
        self.assertTrue(self.adapter.supports_format("text/csv"))
        self.assertTrue(self.adapter.supports_format("TABULAR"))
        self.assertFalse(self.adapter.supports_format("JSON"))

    def test_parse_single_csv_row_string(self) -> None:
        """Parse single CSV row with header."""
        csv_text = "timestamp_s,voltage_v,current_a,temperature_c,soc_fraction\n10.5,48.1,5.2,26.0,0.88\n"
        meta = PacketMetadata(source_id="bess_unit_1")
        snapshot = self.adapter.parse(csv_text, metadata=meta)

        self.assertIsInstance(snapshot, TelemetrySnapshot)
        self.assertEqual(snapshot.system_id, "bess_unit_1")
        self.assertEqual(snapshot.timestamp_ns, 10_500_000_000)
        self.assertEqual(snapshot.pack_voltage_v, 48.1)
        self.assertEqual(snapshot.pack_current_a, 5.2)
        self.assertEqual(snapshot.ambient_temperature_c, 26.0)
        self.assertEqual(snapshot.soc_fraction, 0.88)

    def test_parse_dynamic_cell_voltages(self) -> None:
        """Parse CSV row containing dynamic cell_v_* columns."""
        csv_text = "timestamp_s,voltage_v,current_a,cell_v_0,cell_v_1,cell_v_2,cell_v_3\n1.0,14.8,2.0,3.70,3.71,3.69,3.70\n"
        snapshot = self.adapter.parse(csv_text)

        self.assertEqual(len(snapshot.cell_telemetries), 4)
        cell_dict = snapshot.get_all_cell_voltages()
        self.assertEqual(cell_dict["0"], 3.70)
        self.assertEqual(cell_dict["1"], 3.71)
        self.assertEqual(cell_dict["2"], 3.69)
        self.assertEqual(cell_dict["3"], 3.70)

    def test_parse_multiple_rows(self) -> None:
        """Parse multi-line CSV dataset into sequential snapshots."""
        csv_data = (
            "timestamp_s,voltage_v,current_a\n"
            "0.0,48.0,0.0\n"
            "1.0,47.5,10.0\n"
            "2.0,47.0,10.0\n"
        )
        snapshots = self.adapter.parse_multiple(csv_data)
        self.assertEqual(len(snapshots), 3)
        self.assertEqual(snapshots[0].timestamp_ns, 0)
        self.assertEqual(snapshots[1].timestamp_ns, 1_000_000_000)
        self.assertEqual(snapshots[2].timestamp_ns, 2_000_000_000)
        self.assertEqual(snapshots[1].pack_current_a, 10.0)

    def test_empty_csv_raises_malformed_payload_error(self) -> None:
        """Empty CSV content must raise MalformedPayloadError."""
        with self.assertRaises(MalformedPayloadError):
            self.adapter.parse("")


if __name__ == "__main__":
    unittest.main()
