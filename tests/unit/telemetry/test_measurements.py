"""Unit tests for Canonical Telemetry Measurement Value Objects."""

from dataclasses import FrozenInstanceError
import unittest

from src.domain.exceptions import InvalidBatteryIdentifierError
from src.telemetry.enums import (
    MeasurementProvenance,
    TelemetryQuality,
)
from src.telemetry.exceptions import InvalidTelemetryValueError
from src.telemetry.measurements import (
    CellTelemetry,
    MeasurementValue,
    ModuleTelemetry,
    TemperatureSensorTelemetry,
)


class TestTelemetryMeasurements(unittest.TestCase):
    """Unit tests for individual measurement containers and module aggregations."""

    # --------------------------------------------------------------------------
    # 1. MeasurementValue Tests
    # --------------------------------------------------------------------------
    def test_measurement_value_creation_and_properties(self) -> None:
        """Create valid MeasurementValue with explicit SI unit and metadata."""
        mv = MeasurementValue(
            value=3.715,
            unit="V",
            quality=TelemetryQuality.VALID,
            provenance=MeasurementProvenance.MEASURED,
            timestamp_ns=1700000000000000000,
            metadata={"sensor_channel": "ADC_CH0"},
        )
        self.assertEqual(mv.value, 3.715)
        self.assertEqual(mv.unit, "V")
        self.assertTrue(mv.is_valid)
        self.assertTrue(mv.is_available)

    def test_measurement_value_quality_flags(self) -> None:
        """Verify degraded, invalid, and unavailable states."""
        mv_degraded = MeasurementValue(value=3.7, unit="V", quality=TelemetryQuality.DEGRADED)
        self.assertTrue(mv_degraded.is_valid)

        mv_invalid = MeasurementValue(value=0.0, unit="V", quality=TelemetryQuality.INVALID)
        self.assertFalse(mv_invalid.is_valid)

        mv_unavail = MeasurementValue(value=0.0, unit="V", quality=TelemetryQuality.UNAVAILABLE)
        self.assertFalse(mv_unavail.is_available)

    def test_measurement_value_immutability(self) -> None:
        """Assert frozen dataclass prevents modification."""
        mv = MeasurementValue(value=3.7, unit="V")
        with self.assertRaises(FrozenInstanceError):
            mv.value = 4.0  # type: ignore[misc]

    # --------------------------------------------------------------------------
    # 2. CellTelemetry Tests
    # --------------------------------------------------------------------------
    def test_cell_telemetry_full_and_partial(self) -> None:
        """Verify full measurements and partial measurements without zero-coercion."""
        # Full cell telemetry
        c_full = CellTelemetry(
            cell_id="cell_01",
            voltage_v=3.72,
            temperature_c=26.5,
            internal_resistance_mohm=22.5,
            soc_fraction=0.75,
            quality=TelemetryQuality.VALID,
        )
        self.assertEqual(c_full.cell_id, "cell_01")
        self.assertEqual(c_full.voltage_v, 3.72)
        self.assertEqual(c_full.temperature_c, 26.5)
        self.assertTrue(c_full.has_voltage)
        self.assertTrue(c_full.has_temperature)

        # Partial cell telemetry (only voltage provided)
        c_partial = CellTelemetry(cell_id="cell_02", voltage_v=3.68)
        self.assertEqual(c_partial.voltage_v, 3.68)
        # CRITICAL: Assert missing temperature and SOC are strictly None, NOT 0.0!
        self.assertIsNone(c_partial.temperature_c)
        self.assertIsNone(c_partial.soc_fraction)
        self.assertIsNone(c_partial.internal_resistance_mohm)
        self.assertTrue(c_partial.has_voltage)
        self.assertFalse(c_partial.has_temperature)

    def test_cell_telemetry_invalid_raises(self) -> None:
        """Negative voltage or invalid SOC fraction must fail."""
        with self.assertRaises(InvalidTelemetryValueError):
            CellTelemetry(cell_id="c1", voltage_v=-0.5)

        with self.assertRaises(InvalidTelemetryValueError):
            CellTelemetry(cell_id="c1", soc_fraction=1.5)

        with self.assertRaises(InvalidBatteryIdentifierError):
            CellTelemetry(cell_id="")

    # --------------------------------------------------------------------------
    # 3. TemperatureSensorTelemetry Tests
    # --------------------------------------------------------------------------
    def test_temperature_sensor_telemetry(self) -> None:
        """Create discrete temperature sensor readings."""
        sensor1 = TemperatureSensorTelemetry(sensor_id="temp_inlet", temperature_c=22.4)
        sensor2 = TemperatureSensorTelemetry(
            sensor_id="temp_outlet",
            temperature_c=28.1,
            provenance=MeasurementProvenance.MEASURED,
        )
        self.assertEqual(sensor1.sensor_id, "temp_inlet")
        self.assertEqual(sensor1.temperature_c, 22.4)
        self.assertEqual(sensor2.temperature_c, 28.1)

    # --------------------------------------------------------------------------
    # 4. ModuleTelemetry Tests
    # --------------------------------------------------------------------------
    def test_module_telemetry_with_nested_cells(self) -> None:
        """Create module telemetry containing multiple cells and discrete temp sensors."""
        cells = (
            CellTelemetry(cell_id="c1", voltage_v=3.70),
            CellTelemetry(cell_id="c2", voltage_v=3.71),
            CellTelemetry(cell_id="c3", voltage_v=3.69),
        )
        temp_sensors = (
            TemperatureSensorTelemetry(sensor_id="t_mod1_a", temperature_c=25.0),
            TemperatureSensorTelemetry(sensor_id="t_mod1_b", temperature_c=25.8),
        )
        module = ModuleTelemetry(
            module_id="mod_01",
            voltage_v=11.10,
            temperature_c=25.4,
            cell_telemetries=cells,
            temperature_sensors=temp_sensors,
        )
        self.assertEqual(module.module_id, "mod_01")
        self.assertEqual(module.cell_count, 3)
        self.assertEqual(module.cell_voltages, (3.70, 3.71, 3.69))
        self.assertEqual(module.get_cell("c2"), cells[1])
        self.assertIsNone(module.get_cell("c99"))


if __name__ == "__main__":
    unittest.main()
