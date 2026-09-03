"""Unit tests for ParameterValidationEvaluator, parameter covariance mapping, and multi-dimensional evidence tiers."""

import unittest

from src.calibration.types import IdentifiedParameterSet, ParameterStateClassification
from src.validation.parameter_validator import (
    ARX_PARAMETER_INDICES,
    ARX_PARAMETER_ORDER,
    ParameterValidationEvaluator,
    get_parameter_covariance,
)
from src.validation.types import ParameterEvidenceTier, ValidationConfig


class TestParameterValidationEvaluator(unittest.TestCase):
    """Test suite verifying multi-dimensional evidence tiers and explicit Level 5.2 parameter covariance mapping."""

    def _build_params(
        self,
        r0: float = 0.025,
        r1: float = 0.015,
        c1: float = 1000.0,
        tau1: float = 15.0,
        cov: float = 0.001,
        diag: tuple[float, float, float] = (0.01, 0.001, 0.02),
        gating: str = "ACTIVE",
    ) -> IdentifiedParameterSet:
        return IdentifiedParameterSet(
            timestamp_ns=1_000_000_000,
            system_id="twin_01",
            r0_ohm=r0,
            r1_ohm=r1,
            c1_farad=c1,
            tau1_s=tau1,
            r0_covariance=cov,
            coefficient_covariance_diagonal=diag,
            sample_count=50,
            classification=ParameterStateClassification.ONLINE_IDENTIFIED,
            gating_status=gating,
        )

    def test_parameter_covariance_mapping_against_level_5_2_order(self) -> None:
        """Verifies explicit parameter name mapping matches Level 5.2 RLS theta ordering [a1, b0, b1]."""
        self.assertEqual(ARX_PARAMETER_ORDER, ("a1", "b0", "b1"))
        self.assertEqual(ARX_PARAMETER_INDICES["a1"], 0)
        self.assertEqual(ARX_PARAMETER_INDICES["b0"], 1)
        self.assertEqual(ARX_PARAMETER_INDICES["r0"], 1)
        self.assertEqual(ARX_PARAMETER_INDICES["b1"], 2)

        # Covariance diagonal: P11 = 0.012, P22 = 0.0034, P33 = 0.056
        p = self._build_params(diag=(0.012, 0.0034, 0.056), cov=0.0034)

        cov_a1 = get_parameter_covariance(p, "a1")
        cov_b0 = get_parameter_covariance(p, "b0")
        cov_r0 = get_parameter_covariance(p, "r0")
        cov_b1 = get_parameter_covariance(p, "b1")
        cov_unknown = get_parameter_covariance(p, "non_existent_param")

        self.assertAlmostEqual(cov_a1, 0.012, places=6)
        self.assertAlmostEqual(cov_b0, 0.0034, places=6)
        self.assertAlmostEqual(cov_r0, 0.0034, places=6)
        self.assertAlmostEqual(cov_b1, 0.056, places=6)
        self.assertIsNone(cov_unknown)

    def test_strong_evidence_classification(self) -> None:
        """Valid parameters with low covariance, stable drift, and positive Delta_RMSE yield EVIDENCE_STRONG."""
        evaluator = ParameterValidationEvaluator()
        p0 = self._build_params(r0=0.025, cov=0.001)

        # First window baseline
        evaluator.evaluate(1000, "twin_01", p0, nominal_rmse_v=0.040, prospective_rmse_v=0.020, sample_count=50)

        # Second window with minimal drift and positive delta RMSE
        p1 = self._build_params(r0=0.0251, cov=0.001)
        res = evaluator.evaluate(2000, "twin_01", p1, nominal_rmse_v=0.040, prospective_rmse_v=0.020, sample_count=50)

        self.assertEqual(res.tier, ParameterEvidenceTier.EVIDENCE_STRONG)
        self.assertTrue(res.bounds_satisfied)
        self.assertTrue(res.excitation_sufficient)
        self.assertTrue(res.covariance_acceptable)
        self.assertIsNotNone(res.delta_rmse_v)
        self.assertGreater(res.delta_rmse_v, 0.0)

    def test_moderate_evidence_on_neutral_residual(self) -> None:
        """Valid parameters with acceptable covariance but neutral Delta_RMSE yield EVIDENCE_MODERATE."""
        evaluator = ParameterValidationEvaluator()
        p0 = self._build_params(r0=0.025, cov=0.001)

        res = evaluator.evaluate(1000, "twin_01", p0, nominal_rmse_v=0.020, prospective_rmse_v=0.025, sample_count=50)
        self.assertEqual(res.tier, ParameterEvidenceTier.EVIDENCE_MODERATE)

    def test_weak_evidence_on_insufficient_excitation(self) -> None:
        """Parameters identified during unexcited conditions yield EVIDENCE_WEAK."""
        evaluator = ParameterValidationEvaluator()
        p_gated = self._build_params(r0=0.025, cov=0.001, gating="INSUFFICIENT_CURRENT")

        res = evaluator.evaluate(1000, "twin_01", p_gated, nominal_rmse_v=0.030, prospective_rmse_v=0.020, sample_count=50)
        self.assertEqual(res.tier, ParameterEvidenceTier.EVIDENCE_WEAK)
        self.assertFalse(res.excitation_sufficient)

    def test_weak_evidence_on_parameter_drift(self) -> None:
        """Excessive parameter shift across consecutive windows (>5%) yields EVIDENCE_WEAK."""
        evaluator = ParameterValidationEvaluator(config=ValidationConfig(max_acceptable_drift_fraction=0.05))
        p0 = self._build_params(r0=0.020)
        evaluator.evaluate(1000, "twin_01", p0, nominal_rmse_v=0.030, prospective_rmse_v=0.020, sample_count=50)

        # Shift from 0.020 to 0.030 is a 50% drift
        p1 = self._build_params(r0=0.030)
        res = evaluator.evaluate(2000, "twin_01", p1, nominal_rmse_v=0.030, prospective_rmse_v=0.020, sample_count=50)

        self.assertEqual(res.tier, ParameterEvidenceTier.EVIDENCE_WEAK)
        self.assertIn("drift", res.diagnostics.get("evidence_reason", "").lower())

    def test_rejected_evidence_on_primary_or_secondary_boundary_violation(self) -> None:
        """Unphysical R0 or secondary parameters (R1, C1, tau1) yield EVIDENCE_REJECTED."""
        evaluator = ParameterValidationEvaluator()

        # Negative R0
        p_bad_r0 = self._build_params(r0=-0.05)
        res0 = evaluator.evaluate(1000, "twin_01", p_bad_r0)
        self.assertEqual(res0.tier, ParameterEvidenceTier.EVIDENCE_REJECTED)
        self.assertFalse(res0.bounds_satisfied)

        # Secondary R1 out of bounds (> 1.0 Ohm)
        p_bad_r1 = self._build_params(r1=2.5)
        res1 = evaluator.evaluate(1000, "twin_01", p_bad_r1)
        self.assertEqual(res1.tier, ParameterEvidenceTier.EVIDENCE_REJECTED)
        self.assertFalse(res1.bounds_satisfied)

        # Secondary C1 out of bounds (< 10 Farads)
        p_bad_c1 = self._build_params(c1=2.0)
        res2 = evaluator.evaluate(1000, "twin_01", p_bad_c1)
        self.assertEqual(res2.tier, ParameterEvidenceTier.EVIDENCE_REJECTED)
        self.assertFalse(res2.bounds_satisfied)


if __name__ == "__main__":
    unittest.main()
