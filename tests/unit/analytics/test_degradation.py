"""Unit tests for Semi-Empirical Degradation Modeling."""

import unittest
from src.analytics.degradation import (
    ArrheniusSEIEmpiricalDegradationModel,
    DegradationParameters,
)
from src.analytics.types import StressAccumulatorState


class TestDegradationModel(unittest.TestCase):
    """Test suite verifying Arrhenius SEI empirical capacity fade and resistance growth models."""

    def test_zero_stress_produces_zero_fade(self) -> None:
        """Initial state with 0 elapsed time and 0 EFC produces zero capacity fade."""
        model = ArrheniusSEIEmpiricalDegradationModel()
        stress = StressAccumulatorState(total_elapsed_time_s=0.0, equivalent_full_cycles=0.0)

        deg = model.evaluate(stress=stress, temperature_c=25.0)
        self.assertEqual(deg.calendar_capacity_fade_fraction, 0.0)
        self.assertEqual(deg.cycling_capacity_fade_fraction, 0.0)
        self.assertEqual(deg.total_capacity_fade_fraction, 0.0)
        self.assertEqual(deg.resistance_growth_fraction, 0.0)

    def test_calendar_aging_time_scaling(self) -> None:
        """Calendar aging follows square-root of time SEI growth law."""
        params = DegradationParameters(
            calendar_ref_rate_per_day=0.01,
            calendar_time_exponent=0.5,
            cycling_ref_rate_per_efc=0.0,
        )
        model = ArrheniusSEIEmpiricalDegradationModel(params)

        # 1 day elapsed
        st_1day = StressAccumulatorState(total_elapsed_time_s=86400.0, equivalent_full_cycles=0.0)
        deg_1day = model.evaluate(st_1day, temperature_c=25.0)
        self.assertAlmostEqual(deg_1day.calendar_capacity_fade_fraction, 0.01, places=5)

        # 4 days elapsed -> sqrt(4) = 2x fade of 1 day = 0.02
        st_4days = StressAccumulatorState(total_elapsed_time_s=4 * 86400.0, equivalent_full_cycles=0.0)
        deg_4days = model.evaluate(st_4days, temperature_c=25.0)
        self.assertAlmostEqual(deg_4days.calendar_capacity_fade_fraction, 0.02, places=5)

    def test_cycling_aging_efc_scaling(self) -> None:
        """Cycling aging scales linearly with Equivalent Full Cycles."""
        params = DegradationParameters(
            calendar_ref_rate_per_day=0.0,
            cycling_ref_rate_per_efc=0.0002,
        )
        model = ArrheniusSEIEmpiricalDegradationModel(params)

        # 100 EFC -> 100 * 0.0002 = 0.02 (2% capacity loss)
        st_100efc = StressAccumulatorState(total_elapsed_time_s=0.0, equivalent_full_cycles=100.0)
        deg_100 = model.evaluate(st_100efc, temperature_c=25.0)
        self.assertAlmostEqual(deg_100.cycling_capacity_fade_fraction, 0.02, places=5)
        self.assertAlmostEqual(deg_100.total_capacity_fade_fraction, 0.02, places=5)

        # 500 EFC -> 500 * 0.0002 = 0.10 (10% capacity loss)
        st_500efc = StressAccumulatorState(total_elapsed_time_s=0.0, equivalent_full_cycles=500.0)
        deg_500 = model.evaluate(st_500efc, temperature_c=25.0)
        self.assertAlmostEqual(deg_500.cycling_capacity_fade_fraction, 0.10, places=5)

    def test_arrhenius_temperature_acceleration(self) -> None:
        """Higher temperatures accelerate degradation through the Arrhenius factor."""
        model = ArrheniusSEIEmpiricalDegradationModel()
        st = StressAccumulatorState(total_elapsed_time_s=10 * 86400.0, equivalent_full_cycles=50.0)

        deg_25c = model.evaluate(st, temperature_c=25.0)
        deg_45c = model.evaluate(st, temperature_c=45.0)

        self.assertGreater(deg_45c.total_capacity_fade_fraction, deg_25c.total_capacity_fade_fraction)

    def test_resistance_growth_accumulation(self) -> None:
        """Internal resistance growth accumulates from calendar and cycling stress."""
        params = DegradationParameters(
            resistance_growth_calendar_per_day=0.001,
            resistance_growth_rate_per_efc=0.002,
        )
        model = ArrheniusSEIEmpiricalDegradationModel(params)

        # 10 days + 50 EFC -> (10 * 0.001) + (50 * 0.002) = 0.01 + 0.10 = 0.11 (+11% R0 growth)
        st = StressAccumulatorState(total_elapsed_time_s=10 * 86400.0, equivalent_full_cycles=50.0)
        deg = model.evaluate(st)
        self.assertAlmostEqual(deg.resistance_growth_fraction, 0.11, places=5)

    def test_capacity_fade_clamping(self) -> None:
        """Extreme accumulated stress clamps total capacity fade to [0.0, 1.0]."""
        model = ArrheniusSEIEmpiricalDegradationModel()
        st_huge = StressAccumulatorState(total_elapsed_time_s=10000 * 86400.0, equivalent_full_cycles=100000.0)
        deg = model.evaluate(st_huge)
        self.assertLessEqual(deg.total_capacity_fade_fraction, 1.0)
        self.assertGreaterEqual(deg.total_capacity_fade_fraction, 0.0)

    def test_invalid_parameters_rejected(self) -> None:
        """DegradationParameters validates positive ranges and exponents."""
        with self.assertRaises(ValueError):
            DegradationParameters(calendar_ref_rate_per_day=-0.01)

        with self.assertRaises(ValueError):
            DegradationParameters(calendar_time_exponent=0.0)

        with self.assertRaises(ValueError):
            DegradationParameters(calendar_time_exponent=1.5)

        with self.assertRaises(ValueError):
            DegradationParameters(eol_resistance_growth_limit=-1.0)


if __name__ == "__main__":
    unittest.main()
