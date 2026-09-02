"""Unit tests for Non-Linear OCV Curve Interpolation and Derivatives."""

import math
import unittest

from src.models.base import OCVModel
from src.models.exceptions import (
    InvalidModelParametersError,
    InvalidModelStateError,
    NumericalInstabilityError,
)
from src.models.parameters.ocv_curve import OCVCurve


class TestOCVCurve(unittest.TestCase):
    """Test suite verifying OCVCurve interpolation, derivatives, plateau handling, and invariants."""

    def setUp(self) -> None:
        """Create reference NMC and LFP OCV curves."""
        self.soc_nmc = (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 1.0)
        self.ocv_nmc = (3.0, 3.48, 3.68, 3.82, 4.00, 4.15, 4.20)
        self.curve_nmc_pchip = OCVCurve(
            soc_points=self.soc_nmc,
            ocv_points_v=self.ocv_nmc,
            d_ocv_d_temp_v_per_k=0.0002,
            interpolation_method="PCHIP",
            name="NMC_PCHIP",
        )
        self.curve_nmc_linear = OCVCurve(
            soc_points=self.soc_nmc,
            ocv_points_v=self.ocv_nmc,
            d_ocv_d_temp_v_per_k=0.0002,
            interpolation_method="LINEAR",
            name="NMC_LINEAR",
        )

        # Flat plateau LFP
        self.soc_lfp = (0.0, 0.1, 0.2, 0.4, 0.6, 0.8, 0.9, 1.0)
        self.ocv_lfp = (2.5, 3.18, 3.28, 3.29, 3.30, 3.32, 3.40, 3.65)
        self.curve_lfp = OCVCurve(
            soc_points=self.soc_lfp,
            ocv_points_v=self.ocv_lfp,
            d_ocv_d_temp_v_per_k=0.00008,
            interpolation_method="PCHIP",
            name="LFP_PCHIP",
        )

    # --------------------------------------------------------------------------
    # 1. Protocol & Boundary Value Tests
    # --------------------------------------------------------------------------
    def test_ocv_model_protocol_compliance(self) -> None:
        """Verify OCVCurve adheres to the OCVModel Protocol."""
        self.assertIsInstance(self.curve_nmc_pchip, OCVModel)
        self.assertIsInstance(self.curve_nmc_linear, OCVModel)
        self.assertIsInstance(self.curve_lfp, OCVModel)

    def test_exact_grid_point_interpolation(self) -> None:
        """Interpolated OCV at tabulated points must exactly match specified grid values."""
        for s, v in zip(self.soc_nmc, self.ocv_nmc):
            v_interp = self.curve_nmc_pchip.get_ocv(s, temperature_c=25.0)
            self.assertAlmostEqual(v_interp, v, places=6)

            v_lin = self.curve_nmc_linear.get_ocv(s, temperature_c=25.0)
            self.assertAlmostEqual(v_lin, v, places=6)

    def test_endpoint_properties(self) -> None:
        """Verify v_min_v and v_max_v properties."""
        self.assertAlmostEqual(self.curve_nmc_pchip.v_min_v, 3.0, places=4)
        self.assertAlmostEqual(self.curve_nmc_pchip.v_max_v, 4.2, places=4)
        self.assertAlmostEqual(self.curve_lfp.v_min_v, 2.5, places=4)
        self.assertAlmostEqual(self.curve_lfp.v_max_v, 3.65, places=4)

    # --------------------------------------------------------------------------
    # 2. Monotonicity & Flat Plateau Handling
    # --------------------------------------------------------------------------
    def test_shape_preserving_monotonicity(self) -> None:
        """PCHIP spline must remain strictly monotonic across dense evaluation grid without Runge oscillations."""
        dense_soc = [i / 1000.0 for i in range(1001)]
        voltages = [self.curve_nmc_pchip.get_ocv(s, 25.0) for s in dense_soc]

        for i in range(len(voltages) - 1):
            self.assertLessEqual(
                voltages[i],
                voltages[i + 1],
                f"Monotonicity violation at SOC={dense_soc[i]}: {voltages[i]} > {voltages[i+1]}",
            )

    def test_lfp_flat_plateau_stability(self) -> None:
        """LFP curve over 20%-80% plateau must produce smooth, bounded voltage and non-negative derivative."""
        plateau_socs = [0.25, 0.35, 0.45, 0.55, 0.65, 0.75]
        for s in plateau_socs:
            v = self.curve_lfp.get_ocv(s, 25.0)
            # Voltage must stay within plateau range [3.28, 3.32]
            self.assertGreaterEqual(v, 3.28)
            self.assertLessEqual(v, 3.32)

            # Derivative dOCV/dSOC must be small and non-negative
            docv_dsoc = self.curve_lfp.get_docv_dsoc(s, 25.0)
            self.assertGreaterEqual(docv_dsoc, 0.0)
            self.assertLess(docv_dsoc, 0.5, "Plateau derivative should be flat.")

    # --------------------------------------------------------------------------
    # 3. Derivatives dOCV/dSOC and dOCV/dT
    # --------------------------------------------------------------------------
    def test_analytical_derivative_matches_finite_difference(self) -> None:
        """Analytical dOCV/dSOC must closely match numerical finite difference."""
        test_socs = [0.15, 0.35, 0.65, 0.85]
        eps = 1e-5
        for s in test_socs:
            docv_dsoc_analytic = self.curve_nmc_pchip.get_docv_dsoc(s, 25.0)
            v_plus = self.curve_nmc_pchip.get_ocv(s + eps, 25.0)
            v_minus = self.curve_nmc_pchip.get_ocv(s - eps, 25.0)
            docv_dsoc_fd = (v_plus - v_minus) / (2.0 * eps)
            self.assertAlmostEqual(docv_dsoc_analytic, docv_dsoc_fd, delta=0.01)

    def test_temperature_dependence_and_tabular_entropic_coefficient(self) -> None:
        """Test constant and SOC-dependent entropic coefficients dOCV/dT."""
        # Constant dOCV/dT
        v_25c = self.curve_nmc_pchip.get_ocv(0.5, temperature_c=25.0)
        v_45c = self.curve_nmc_pchip.get_ocv(0.5, temperature_c=45.0)
        # Delta = 20 K * 0.0002 V/K = 0.004 V
        self.assertAlmostEqual(v_45c - v_25c, 0.004, places=5)
        self.assertEqual(self.curve_nmc_pchip.get_docv_dtemp(0.5, 25.0), 0.0002)

        # Tabular dOCV/dT
        table_dtemp = (0.0001, 0.00015, 0.0002, 0.00025, 0.0003, 0.00035, 0.0004)
        curve_table = OCVCurve(
            soc_points=self.soc_nmc,
            ocv_points_v=self.ocv_nmc,
            d_ocv_d_temp_v_per_k=table_dtemp,
        )
        self.assertAlmostEqual(curve_table.get_docv_dtemp(0.0, 25.0), 0.0001, places=5)
        self.assertAlmostEqual(curve_table.get_docv_dtemp(1.0, 25.0), 0.0004, places=5)
        self.assertAlmostEqual(curve_table.get_docv_dtemp(0.5, 25.0), 0.00025, places=5)

    # --------------------------------------------------------------------------
    # 4. Out-of-Bounds Clamping & Invariant Defense
    # --------------------------------------------------------------------------
    def test_out_of_bounds_soc_clamping(self) -> None:
        """SOC outside [0.0, 1.0] is safely clamped to boundaries."""
        v_zero = self.curve_nmc_pchip.get_ocv(0.0, 25.0)
        v_subzero = self.curve_nmc_pchip.get_ocv(-0.2, 25.0)
        self.assertEqual(v_zero, v_subzero)

        v_full = self.curve_nmc_pchip.get_ocv(1.0, 25.0)
        v_overfull = self.curve_nmc_pchip.get_ocv(1.2, 25.0)
        self.assertEqual(v_full, v_overfull)

    def test_invalid_parameter_validation(self) -> None:
        """Test rejection of malformed or non-physical OCV parameters."""
        # Less than 2 points
        with self.assertRaises(InvalidModelParametersError):
            OCVCurve(soc_points=[0.5], ocv_points_v=[3.7])

        # Mismatched length
        with self.assertRaises(InvalidModelParametersError):
            OCVCurve(soc_points=[0.0, 0.5, 1.0], ocv_points_v=[3.0, 4.2])

        # Non-increasing SOC grid
        with self.assertRaises(InvalidModelParametersError):
            OCVCurve(soc_points=[0.0, 0.5, 0.4, 1.0], ocv_points_v=[3.0, 3.5, 3.8, 4.2])

        # SOC does not span [0.0, 1.0]
        with self.assertRaises(InvalidModelParametersError):
            OCVCurve(soc_points=[0.2, 0.5, 1.0], ocv_points_v=[3.0, 3.5, 4.2])
        with self.assertRaises(InvalidModelParametersError):
            OCVCurve(soc_points=[0.0, 0.5, 0.8], ocv_points_v=[3.0, 3.5, 4.2])

        # Non-positive OCV
        with self.assertRaises(InvalidModelParametersError):
            OCVCurve(soc_points=[0.0, 1.0], ocv_points_v=[-0.1, 4.2])

        # Monotonicity violation
        with self.assertRaises(InvalidModelParametersError):
            OCVCurve(
                soc_points=[0.0, 0.5, 1.0],
                ocv_points_v=[3.0, 2.8, 4.2],
                enforce_monotonicity=True,
            )

        # Monotonicity violation allowed when flag disabled
        curve_non_mono = OCVCurve(
            soc_points=[0.0, 0.5, 1.0],
            ocv_points_v=[3.0, 2.8, 4.2],
            enforce_monotonicity=False,
        )
        self.assertFalse(curve_non_mono.is_monotonic)

        # Unsupported interpolation method
        with self.assertRaises(InvalidModelParametersError):
            OCVCurve(
                soc_points=[0.0, 1.0],
                ocv_points_v=[3.0, 4.2],
                interpolation_method="FOURIER_NEURAL_OPERATOR",
            )

    def test_temperature_invariants(self) -> None:
        """Temperature <= -273.15 C must be rejected."""
        with self.assertRaises(InvalidModelStateError):
            self.curve_nmc_pchip.get_ocv(0.5, temperature_c=-273.15)

        with self.assertRaises(InvalidModelStateError):
            self.curve_nmc_pchip.get_docv_dsoc(0.5, temperature_c=-274.0)

    def test_nan_and_inf_rejection(self) -> None:
        """NaN or Inf inputs must raise NumericalInstabilityError."""
        with self.assertRaises(NumericalInstabilityError):
            self.curve_nmc_pchip.get_ocv(float("nan"), 25.0)

        with self.assertRaises(NumericalInstabilityError):
            self.curve_nmc_pchip.get_ocv(0.5, float("inf"))

    # --------------------------------------------------------------------------
    # 5. Serialization & Determinism
    # --------------------------------------------------------------------------
    def test_serialization_roundtrip(self) -> None:
        """Verify to_dict and from_dict produce identical OCV curves."""
        d = self.curve_nmc_pchip.to_dict()
        reconstructed = OCVCurve.from_dict(d)

        self.assertEqual(reconstructed.name, self.curve_nmc_pchip.name)
        self.assertEqual(reconstructed.soc_points, self.curve_nmc_pchip.soc_points)
        self.assertEqual(reconstructed.ocv_points_v, self.curve_nmc_pchip.ocv_points_v)
        self.assertEqual(
            reconstructed.get_ocv(0.45, 30.0),
            self.curve_nmc_pchip.get_ocv(0.45, 30.0),
        )

    def test_deterministic_evaluations(self) -> None:
        """Multiple evaluations with identical arguments must return bitwise equal floats."""
        v1 = self.curve_nmc_pchip.get_ocv(0.3333333333333333, 28.123456789)
        v2 = self.curve_nmc_pchip.get_ocv(0.3333333333333333, 28.123456789)
        self.assertEqual(v1, v2)


if __name__ == "__main__":
    unittest.main()
