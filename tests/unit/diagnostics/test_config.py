"""Unit tests for DiagnosticThresholdConfig validation and serialization."""

import math
import unittest

from src.diagnostics.config import DiagnosticThresholdConfig


class TestDiagnosticThresholdConfig(unittest.TestCase):
    """Test suite verifying DiagnosticThresholdConfig bounds, validation rules, and serialization."""

    def test_default_construction(self) -> None:
        """Default configuration instantiates with valid engineering criteria and serializes cleanly."""
        cfg = DiagnosticThresholdConfig()
        self.assertEqual(cfg.rest_current_threshold_a, 0.1)
        self.assertEqual(cfg.rest_min_duration_s, 10.0)
        self.assertEqual(cfg.persistence_debounce_steps, 5)
        self.assertEqual(cfg.recovery_hysteresis_steps, 10)

        data = cfg.to_dict()
        self.assertIsInstance(data, dict)
        self.assertEqual(data["voltage_warning_residual_v"], 0.030)
        self.assertEqual(data["voltage_critical_residual_v"], 0.080)

    def test_valid_custom_overrides(self) -> None:
        """Configuration accepts valid custom engineering criteria."""
        cfg = DiagnosticThresholdConfig(
            rest_current_threshold_a=0.2,
            rest_min_duration_s=15.0,
            voltage_warning_residual_v=0.040,
            voltage_critical_residual_v=0.100,
            apparent_r0_growth_fraction=0.20,
        )
        self.assertEqual(cfg.rest_current_threshold_a, 0.2)
        self.assertEqual(cfg.voltage_warning_residual_v, 0.040)
        self.assertEqual(cfg.voltage_critical_residual_v, 0.100)

    def test_negative_duration_rejection(self) -> None:
        """Non-positive durations raise ValueError."""
        with self.assertRaises(ValueError):
            DiagnosticThresholdConfig(rest_min_duration_s=-5.0)

        with self.assertRaises(ValueError):
            DiagnosticThresholdConfig(data_gap_threshold_s=0.0)

    def test_negative_thresholds_rejection(self) -> None:
        """Non-positive current and voltage thresholds raise ValueError."""
        with self.assertRaises(ValueError):
            DiagnosticThresholdConfig(rest_current_threshold_a=-0.1)

        with self.assertRaises(ValueError):
            DiagnosticThresholdConfig(voltage_warning_residual_v=0.0)

    def test_fraction_bounds_validation(self) -> None:
        """Fractional thresholds must lie strictly within [0.0, 1.0]."""
        with self.assertRaises(ValueError):
            DiagnosticThresholdConfig(apparent_r0_growth_fraction=1.5)

        with self.assertRaises(ValueError):
            DiagnosticThresholdConfig(min_evidence_coverage_fraction=-0.1)

    def test_step_count_validation(self) -> None:
        """Persistence and hysteresis step counts must be integers >= 1."""
        with self.assertRaises(ValueError):
            DiagnosticThresholdConfig(persistence_debounce_steps=0)

        with self.assertRaises(ValueError):
            DiagnosticThresholdConfig(recovery_hysteresis_steps=-1)

    def test_nan_and_inf_rejection(self) -> None:
        """NaN and Inf float values are rejected."""
        with self.assertRaises(ValueError):
            DiagnosticThresholdConfig(voltage_warning_residual_v=float("nan"))

        with self.assertRaises(ValueError):
            DiagnosticThresholdConfig(thermal_rate_threshold_c_per_s=float("inf"))

    def test_critical_ordering_relative_to_warning(self) -> None:
        """Critical threshold cannot be configured lower than corresponding warning threshold."""
        with self.assertRaises(ValueError):
            DiagnosticThresholdConfig(
                voltage_warning_residual_v=0.050,
                voltage_critical_residual_v=0.030,  # Critical < Warning is invalid
            )

        with self.assertRaises(ValueError):
            DiagnosticThresholdConfig(
                thermal_rate_threshold_c_per_s=0.10,
                thermal_critical_rate_c_per_s=0.05,  # Critical < Warning is invalid
            )


if __name__ == "__main__":
    unittest.main()
