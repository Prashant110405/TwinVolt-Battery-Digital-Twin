"""Unit tests for Arduino Frame Parser.

Verifies CSV, JSON lines, bootloader skipping, non-finite number rejection (NaN, Inf),
multi-cell extraction, and power calculation invariants.
"""

import math
import unittest
from src.gateway.arduino.frame_parser import ArduinoFrameParser
from src.gateway.arduino.models import ArduinoConfig, SerialDataFormat


class TestArduinoFrameParser(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ArduinoConfig(
            port="COM3",
            baud_rate=115200,
            data_format=SerialDataFormat.AUTO,
            system_id="test_twin_01",
        )
        self.parser = ArduinoFrameParser(config=self.config)

    def test_json_lines_parsing_with_standard_keys(self) -> None:
        """Parses JSON line with voltage, current, temperature, and timestamp."""
        payload = '{"millis": 12500, "voltage_v": 3.725, "current_a": 1.5, "temperature_c": 26.5}'
        record = self.parser.parse_line(payload)

        self.assertTrue(record.is_valid)
        self.assertEqual(record.source_id, "test_twin_01")
        self.assertAlmostEqual(record.voltage_v, 3.725, places=3)
        self.assertAlmostEqual(record.current_a, 1.5, places=3)
        self.assertAlmostEqual(record.power_w, 3.725 * 1.5, places=3)
        self.assertAlmostEqual(record.temperature_c, 26.5, places=1)
        self.assertEqual(record.source_timestamp_ns, 12500 * 1_000_000)

    def test_json_lines_multi_cell_parsing(self) -> None:
        """Parses cell-level voltages from JSON object."""
        payload = '{"voltage": 11.1, "current": 2.0, "cell_v_1": 3.7, "cell_v_2": 3.69, "cell_v_3": 3.71}'
        record = self.parser.parse_line(payload)

        self.assertTrue(record.is_valid)
        self.assertEqual(len(record.cell_voltages_v), 3)
        self.assertAlmostEqual(record.cell_voltages_v[0], 3.7, places=2)
        self.assertAlmostEqual(record.cell_voltages_v[1], 3.69, places=2)
        self.assertAlmostEqual(record.cell_voltages_v[2], 3.71, places=2)

    def test_rejection_of_nan_and_infinity(self) -> None:
        """Rejects non-finite numbers (NaN, Inf) and marks record invalid."""
        payload_nan = '{"voltage_v": "NaN", "current_a": 1.0}'
        record1 = self.parser.parse_line(payload_nan)
        self.assertFalse(record1.is_valid)

        payload_inf = '{"voltage_v": "Infinity", "current_a": 1.0}'
        record2 = self.parser.parse_line(payload_inf)
        self.assertFalse(record2.is_valid)

    def test_csv_positional_parsing(self) -> None:
        """Parses positional CSV telemetry line."""
        line = "5000, 3.68, 1.25, 25.4"
        record = self.parser.parse_line(line)

        self.assertTrue(record.is_valid)
        self.assertAlmostEqual(record.voltage_v, 3.68, places=2)
        self.assertAlmostEqual(record.current_a, 1.25, places=2)
        self.assertAlmostEqual(record.power_w, 3.68 * 1.25, places=3)
        self.assertAlmostEqual(record.temperature_c, 25.4, places=1)
        self.assertEqual(record.source_timestamp_ns, 5000 * 1_000_000)

    def test_csv_header_skipped_cleanly(self) -> None:
        """Recognizes CSV column header row and skips without error."""
        header = "timestamp_ms,voltage_v,current_a,temperature_c"
        record = self.parser.parse_line(header)
        self.assertFalse(record.is_valid)
        self.assertIn("Header line detected", record.errors[0])

    def test_bootloader_logs_skipped_without_crashing(self) -> None:
        """Recognizes informational boot / init messages and skips them."""
        boot_msg = "TwinVolt Hardware Telemetry Bridge v1.0 Initialized"
        record = self.parser.parse_line(boot_msg)
        self.assertFalse(record.is_valid)
        self.assertIn("boot log skipped", record.errors[0])

    def test_power_not_computed_without_current(self) -> None:
        """Power is None when current measurement is absent."""
        payload = '{"voltage_v": 3.72}'
        record = self.parser.parse_line(payload)
        self.assertTrue(record.is_valid)
        self.assertIsNone(record.current_a)
        self.assertIsNone(record.power_w)

    def test_negative_voltage_rejected(self) -> None:
        """Rejects unphysical non-positive voltages."""
        payload = '{"voltage_v": -3.7, "current_a": 1.0}'
        record = self.parser.parse_line(payload)
        self.assertFalse(record.is_valid)


if __name__ == "__main__":
    unittest.main()
