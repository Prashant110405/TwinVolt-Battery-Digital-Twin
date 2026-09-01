"""Unit tests for Canonical Telemetry Enums."""

import unittest

from src.telemetry.enums import (
    CurrentFlowDirection,
    MeasurementProvenance,
    TelemetryQuality,
)


class TestTelemetryEnums(unittest.TestCase):
    """Unit tests for telemetry quality, provenance, and flow direction enums."""

    def test_telemetry_quality_states(self) -> None:
        """Verify all quality/validity states exist."""
        expected = {"VALID", "DEGRADED", "INVALID", "UNAVAILABLE", "STALE"}
        actual = {q.value for q in TelemetryQuality}
        self.assertEqual(expected, actual)

    def test_measurement_provenance(self) -> None:
        """Verify measured vs estimated vs synthetic vs derived provenance."""
        expected = {"MEASURED", "ESTIMATED", "SYNTHETIC", "DERIVED"}
        actual = {p.value for p in MeasurementProvenance}
        self.assertEqual(expected, actual)

    def test_current_flow_direction(self) -> None:
        """Verify macro flow directions."""
        expected = {"CHARGING", "DISCHARGING", "IDLE"}
        actual = {f.value for f in CurrentFlowDirection}
        self.assertEqual(expected, actual)


if __name__ == "__main__":
    unittest.main()
