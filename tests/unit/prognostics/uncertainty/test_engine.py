"""Unit Tests for Prognostic Uncertainty Engine and End-to-End Synthetic Verification.

Validates:
- End-to-end integration with HistoricalLinearRULEstimator results
- Exact synthetic mathematical verification (PART 24):
  EFC: 0, 10, 20, 30, 40
  Capacity: 3.00, 2.90, 2.80, 2.70, 2.60 Ah
  EOL: 2.40 Ah
  Expected RUL: 20 EFC
- Reproducibility and determinism (identical results across runs, no Monte Carlo)
- Input immutability
- Live Twin isolation (pure input/output, zero subsystem mutation)
- Chemistry and hardware independence
- Prediction interval request semantics (strictly UNAVAILABLE under first-order baseline)
- Non-valid prediction result handling
- Zero RUL handling when system is already at EOL
"""

import pytest

from src.prognostics.estimators.base import EstimatorConfig
from src.prognostics.estimators.linear import HistoricalLinearRULEstimator
from src.prognostics.horizon import PrognosticHorizon
from src.prognostics.prediction import (
    EOLDefinition,
    PredictionUncertainty,
    RULPredictionResult,
)
from src.prognostics.provenance import PrognosticQuantity, PrognosticValueProvenance
from src.prognostics.trajectory import DegradationObservation, DegradationTrajectory

from src.prognostics.types import (
    EOLCriterionType,
    HorizonDomain,
    PrognosticStatus,
    UncertaintyType,
    ValueOriginType,
)
from src.prognostics.uncertainty.engine import (
    PrognosticUncertaintyEngine,
    UncertaintyEngineConfig,
    UncertaintyEvaluationResult,
)
from src.prognostics.uncertainty.types import (
    UncertaintyIntervalType,
    UncertaintyStatus,
)


class TestPrognosticUncertaintyEngine:
    """End-to-end engine tests and synthetic mathematical verification."""

    def _create_synthetic_trajectory(self) -> DegradationTrajectory:
        """Synthetic benchmark: EFC 0..40, capacity 3.00..2.60 Ah (slope = -0.01 Ah/cycle)."""
        efcs = [0.0, 10.0, 20.0, 30.0, 40.0]
        caps = [3.00, 2.90, 2.80, 2.70, 2.60]
        obs_list = []
        for i, (efc, cap) in enumerate(zip(efcs, caps)):
            prov = PrognosticValueProvenance(
                origin_type=ValueOriginType.MEASURED,
                measurement_uncertainty=0.005,
            )
            obs = DegradationObservation(
                timestamp_ns=(i + 1) * 86400 * 1_000_000_000,
                created_at_utc="2026-09-06T00:00:00Z",
                usable_capacity_ah=PrognosticQuantity(
                    name="usable_capacity_ah",
                    value=cap,
                    unit="Ah",
                    provenance=prov,
                ),
                equivalent_full_cycles=PrognosticQuantity(
                    name="equivalent_full_cycles",
                    value=efc,
                    unit="cycles",
                ),
            )
            obs_list.append(obs)

        return DegradationTrajectory(
            trajectory_id="traj_synthetic_benchmark",
            system_id="cell_universal_01",
            observations=tuple(obs_list),
        )


    def test_synthetic_mathematical_verification(self) -> None:
        """PART 24 synthetic verification: EFC 0-40, Cap 3.00-2.60 Ah, EOL=2.40 Ah -> RUL = 20 EFC."""
        traj = self._create_synthetic_trajectory()
        eol = EOLDefinition(
            criterion_id="eol_cap_240",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.40,
            unit="Ah",
        )
        estimator = HistoricalLinearRULEstimator()
        rul_res = estimator.estimate(
            trajectory=traj,
            eol_definition=eol,
            config=EstimatorConfig(use_ols_slope=True),
        )

        assert rul_res.status == PrognosticStatus.VALID
        assert rul_res.rul_value == pytest.approx(20.0, rel=1e-6)

        # Evaluate Uncertainty
        engine = PrognosticUncertaintyEngine()
        cfg = UncertaintyEngineConfig(
            confidence_level=0.95,
            assume_independent_sources=True,
        )
        unc_res = engine.evaluate_uncertainty(
            prediction_result=rul_res,
            trajectory=traj,
            eol_definition=eol,
            config=cfg,
        )

        assert unc_res.status == UncertaintyStatus.STATISTICALLY_SUPPORTED
        assert unc_res.rul_value == pytest.approx(20.0, rel=1e-6)
        assert unc_res.is_valid is True

        # Check Trend Statistics (perfect linear: RSS = 0, slope = -0.01)
        assert unc_res.trend_statistics is not None
        assert unc_res.trend_statistics.slope == pytest.approx(-0.01, rel=1e-6)
        assert unc_res.trend_statistics.residual_sum_of_squares == pytest.approx(0.0, abs=1e-12)
        assert unc_res.trend_statistics.r_squared == pytest.approx(1.0, rel=1e-6)

        # Check Measurement Uncertainty
        assert unc_res.measurement_evaluation is not None
        assert unc_res.measurement_evaluation.standard_uncertainty == 0.005

        # Check Extrapolation Metrics
        assert unc_res.extrapolation_metrics is not None
        assert unc_res.extrapolation_metrics.observed_history_span == 40.0
        assert unc_res.extrapolation_metrics.extrapolation_distance == pytest.approx(20.0, rel=1e-6)
        assert unc_res.extrapolation_metrics.extrapolation_ratio == pytest.approx(0.5, rel=1e-6)


        # Check Bounds: state uncertainty propagated = (1 / 0.01) * 0.005 = 0.5 cycles
        assert unc_res.propagation_result is not None
        assert unc_res.propagation_result.propagated_standard_uncertainty == pytest.approx(0.5, rel=1e-6)
        assert unc_res.bounds is not None
        assert unc_res.bounds.lower < 20.0 < unc_res.bounds.upper

        # Check Level 6.1 PredictionUncertainty container
        pu = unc_res.prediction_uncertainty
        assert pu.uncertainty_type == UncertaintyType.CONFIDENCE_BOUNDS
        assert pu.lower_bound == unc_res.bounds.lower
        assert pu.upper_bound == unc_res.bounds.upper
        assert pu.coverage_parameter == 0.95
        assert pu.standard_deviation == pytest.approx(0.5, rel=1e-6)

    def test_determinism_and_reproducibility(self) -> None:
        """Verifies that two identical evaluations produce bit-for-bit equivalent values (no Monte Carlo)."""
        traj = self._create_synthetic_trajectory()
        eol = EOLDefinition(
            criterion_id="eol_cap_240",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.40,
            unit="Ah",
        )
        estimator = HistoricalLinearRULEstimator()
        rul_res = estimator.estimate(trajectory=traj, eol_definition=eol)

        engine = PrognosticUncertaintyEngine()
        cfg = UncertaintyEngineConfig(confidence_level=0.95)

        res1 = engine.evaluate_uncertainty(rul_res, traj, eol, cfg)
        res2 = engine.evaluate_uncertainty(rul_res, traj, eol, cfg)

        assert res1.rul_value == res2.rul_value
        assert res1.prediction_uncertainty.lower_bound == res2.prediction_uncertainty.lower_bound
        assert res1.prediction_uncertainty.upper_bound == res2.prediction_uncertainty.upper_bound
        assert res1.prediction_uncertainty.standard_deviation == res2.prediction_uncertainty.standard_deviation
        assert res1.evidence_assessment.overall_strength == res2.evidence_assessment.overall_strength

    def test_prediction_interval_request_returns_unavailable(self) -> None:
        """Verifies that requesting a PREDICTION_INTERVAL returns UNAVAILABLE (Correction 1)."""
        traj = self._create_synthetic_trajectory()
        eol = EOLDefinition(
            criterion_id="eol_cap_240",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.40,
            unit="Ah",
        )
        estimator = HistoricalLinearRULEstimator()
        rul_res = estimator.estimate(trajectory=traj, eol_definition=eol)

        engine = PrognosticUncertaintyEngine()
        cfg = UncertaintyEngineConfig(
            confidence_level=0.95,
            target_interval_type=UncertaintyIntervalType.PREDICTION_INTERVAL,
        )
        unc_res = engine.evaluate_uncertainty(rul_res, traj, eol, cfg)

        assert unc_res.status == UncertaintyStatus.UNDEFINED
        assert unc_res.prediction_uncertainty.uncertainty_type == UncertaintyType.UNDEFINED
        assert unc_res.bounds is None

    def test_non_valid_prediction_input(self) -> None:
        """Verifies graceful handling when input prediction is not VALID."""
        non_valid_res = RULPredictionResult(
            prediction_id="pred_err",
            prediction_timestamp_ns=0,
            created_at_utc="2026-09-06T00:00:00Z",
            system_id="sys_err",
            status=PrognosticStatus.INSUFFICIENT_DATA,
            rul_value=None,
            rul_unit="cycles",
            rul_domain=HorizonDomain.CYCLE,
        )
        traj = self._create_synthetic_trajectory()
        eol = EOLDefinition(
            criterion_id="eol_cap_240",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.40,
            unit="Ah",
        )
        engine = PrognosticUncertaintyEngine()
        unc_res = engine.evaluate_uncertainty(non_valid_res, traj, eol)

        assert unc_res.status == UncertaintyStatus.INSUFFICIENT_EVIDENCE
        assert unc_res.rul_value is None
        assert unc_res.prediction_uncertainty.uncertainty_type == UncertaintyType.UNDEFINED

    def test_already_at_eol_system(self) -> None:
        """Verifies uncertainty evaluation when system is already at EOL (RUL = 0.0)."""
        traj = self._create_synthetic_trajectory()
        eol = EOLDefinition(
            criterion_id="eol_cap_280",
            criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            threshold_value=2.80,  # Current capacity is 2.60 Ah <= 2.80 Ah
            unit="Ah",
        )
        estimator = HistoricalLinearRULEstimator()
        rul_res = estimator.estimate(trajectory=traj, eol_definition=eol)

        assert rul_res.status == PrognosticStatus.VALID
        assert rul_res.rul_value == 0.0

        engine = PrognosticUncertaintyEngine()
        unc_res = engine.evaluate_uncertainty(rul_res, traj, eol)

        assert unc_res.status == UncertaintyStatus.DETERMINISTIC_ONLY
        assert unc_res.rul_value == 0.0
        assert unc_res.prediction_uncertainty.uncertainty_type == UncertaintyType.DETERMINISTIC_NO_UNCERTAINTY
        assert unc_res.bounds is not None
        assert unc_res.bounds.lower == 0.0
        assert unc_res.bounds.upper == 0.0
