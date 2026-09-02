"""Unit tests for TwinVolt Event Models and Typed Domain Events."""

from dataclasses import FrozenInstanceError
import unittest

from src.estimators.base import EstimationState
from src.events.base import TwinEvent
from src.events.exceptions import InvalidEventError
from src.events.types import (
    BatteryAnomalyDetectedEvent,
    StateEstimatedEvent,
    TelemetryPersistedEvent,
    TelemetryReceivedEvent,
    ThermalAlertEvent,
    TwinSynchronizedEvent,
)
from src.models.types import ModelState
from src.storage.base import TwinStateRecord
from src.telemetry.snapshots import TelemetrySnapshot


class TestEventTypes(unittest.TestCase):
    """Test suite verifying event immutability, validation, and domain event properties."""

    def test_base_event_creation_and_immutability(self) -> None:
        """Verify TwinEvent creation and immutability."""
        evt = TwinEvent(
            event_type="test.event",
            source_id="test_source",
            payload={"key": "value"},
        )
        self.assertEqual(evt.event_type, "test.event")
        self.assertEqual(evt.source_id, "test_source")
        self.assertEqual(evt.payload["key"], "value")

        with self.assertRaises(FrozenInstanceError):
            evt.event_type = "modified"  # type: ignore

    def test_invalid_event_raises(self) -> None:
        """Empty event_type or negative timestamp must raise InvalidEventError."""
        with self.assertRaises(InvalidEventError):
            TwinEvent(event_type="")

        with self.assertRaises(InvalidEventError):
            TwinEvent(event_type="valid.type", timestamp_ns=-1)

    def test_telemetry_received_event_properties(self) -> None:
        """Verify TelemetryReceivedEvent wraps TelemetrySnapshot."""
        snap = TelemetrySnapshot(
            snapshot_id="snap_1",
            system_id="pack_alpha",
            timestamp_ns=1000,
            pack_voltage_v=48.2,
            pack_current_a=10.0,
        )
        evt = TelemetryReceivedEvent(snapshot=snap)
        self.assertEqual(evt.event_type, "telemetry.received")
        self.assertEqual(evt.system_id, "pack_alpha")
        self.assertEqual(evt.pack_voltage_v, 48.2)
        self.assertEqual(evt.pack_current_a, 10.0)

    def test_state_estimated_event_properties(self) -> None:
        """Verify StateEstimatedEvent wraps EstimationState."""
        est = EstimationState(soc_fraction=0.85, soh_fraction=0.98)
        evt = StateEstimatedEvent(source_id="ekf_01", estimation_state=est)
        self.assertEqual(evt.event_type, "state.estimated")
        self.assertEqual(evt.soc_fraction, 0.85)
        self.assertEqual(evt.soh_fraction, 0.98)

    def test_twin_synchronized_event_properties(self) -> None:
        """Verify TwinSynchronizedEvent wraps TwinStateRecord with residuals."""
        rec = TwinStateRecord(
            record_id="rec_1",
            system_id="twin_1",
            timestamp_ns=2000,
            model_state=ModelState(soc_fraction=0.85, temperature_c=25.0),
            residuals={"voltage_residual_v": 0.012, "temp_residual_c": 0.5},
        )
        evt = TwinSynchronizedEvent(twin_record=rec)
        self.assertEqual(evt.event_type, "twin.synchronized")
        self.assertAlmostEqual(evt.voltage_residual_v, 0.012)
        self.assertAlmostEqual(evt.temp_residual_c, 0.5)

    def test_thermal_and_anomaly_alerts(self) -> None:
        """Verify ThermalAlertEvent and BatteryAnomalyDetectedEvent."""
        thermal_evt = ThermalAlertEvent(
            system_id="pack_1",
            temperature_c=65.2,
            threshold_c=60.0,
            severity="CRITICAL",
        )
        self.assertEqual(thermal_evt.severity, "CRITICAL")
        self.assertEqual(thermal_evt.temperature_c, 65.2)

        anomaly_evt = BatteryAnomalyDetectedEvent(
            system_id="pack_1",
            anomaly_type="IMPEDANCE_GROWTH",
            observed_value=0.08,
            expected_value=0.03,
            residual=0.05,
            severity="WARNING",
        )
        self.assertEqual(anomaly_evt.anomaly_type, "IMPEDANCE_GROWTH")
        self.assertEqual(anomaly_evt.residual, 0.05)


if __name__ == "__main__":
    unittest.main()
