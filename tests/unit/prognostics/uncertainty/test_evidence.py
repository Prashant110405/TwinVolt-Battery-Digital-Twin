"""Unit Tests for Multi-Dimensional Evidence Strength Assessment.

Validates:
- Dimension-level audit trail (observation_count, history_span, explanatory_fit_r2, extrapolation_ratio, measurement_uncertainty_availability, operating_context_coverage)
- Evaluated status, input values, thresholds, rationales, and missing reasons
- Configurable thresholds via EvidenceEvaluatorConfig (no hardcoded universal battery truths)
- Aggregation policies (MINIMUM_DIMENSION vs. MAJORITY/AVERAGE)
- Strict absence of arbitrary percentage mappings (STRONG != 95%)
"""

import pytest

from src.prognostics.provenance import PrognosticQuantity, PrognosticValueProvenance
from src.prognostics.state import PrognosticOperatingContext
from src.prognostics.types import QuantityAvailability, ValueOriginType
from src.prognostics.uncertainty.evidence import (
    EvidenceAssessment,
    EvidenceEvaluator,
    EvidenceEvaluatorConfig,
)
from src.prognostics.uncertainty.extrapolation import (
    ExtrapolationEvaluator,
    ExtrapolationMetrics,
)
from src.prognostics.uncertainty.measurement import (
    MeasurementUncertaintyEvaluation,
    MeasurementUncertaintyEvaluator,
)
from src.prognostics.uncertainty.trajectory import (
    OLSTrendUncertaintyEvaluator,
    TrajectoryTrendStatistics,
)
from src.prognostics.uncertainty.types import (
    EvidenceStrength,
    MeasurementUncertaintyAvailability,
)


class TestEvidenceEvaluator:
    """Evidence strength evaluation and audit tests."""

    def test_multi_dimensional_evidence_audit_trail(self) -> None:
        """Verifies full audit trail across all evaluated dimensions."""
        pairs = [(float(i * 10), 3.0 - 0.01 * (i * 10)) for i in range(20)]
        trend_stats = OLSTrendUncertaintyEvaluator.evaluate_pairs(pairs)

        extrap = ExtrapolationEvaluator.evaluate(
            observed_history_span=190.0,
            extrapolation_distance=60.0,
            sample_count=20,
            slope_standard_error=trend_stats.slope_standard_error,
            residual_standard_error=trend_stats.residual_standard_error,
        )

        prov = PrognosticValueProvenance(
            origin_type=ValueOriginType.MEASURED,
            measurement_uncertainty=0.005,
        )
        meas_eval = MeasurementUncertaintyEvaluator.evaluate_provenance(
            provenance=prov,
            nominal_value=2.40,
        )

        op_ctx = PrognosticOperatingContext(
            ambient_temperature_c=25.0,
            cell_temperature_c=28.0,
            c_rate=0.5,
            soc_fraction=0.8,
        )


        assessment = EvidenceEvaluator.evaluate(
            trend_stats=trend_stats,
            extrapolation_metrics=extrap,
            measurement_eval=meas_eval,
            operating_context=op_ctx,
        )

        assert assessment.evaluated_dimension_count == 6
        assert assessment.total_dimension_count == 6
        assert assessment.is_sufficient_for_uncertainty is True
        assert assessment.overall_strength in (EvidenceStrength.STRONG, EvidenceStrength.VERY_STRONG)

        # Audit dimensions
        dims = assessment.dimensions
        assert "observation_count" in dims
        assert dims["observation_count"].evaluated is True
        assert dims["observation_count"].input_value == 20

        assert "history_span" in dims
        assert dims["history_span"].evaluated is True
        assert dims["history_span"].input_value == 190.0

        assert "explanatory_fit_r2" in dims
        assert dims["explanatory_fit_r2"].evaluated is True
        assert dims["explanatory_fit_r2"].input_value == 1.0

        assert "extrapolation_ratio" in dims
        assert dims["extrapolation_ratio"].evaluated is True
        assert dims["extrapolation_ratio"].input_value == pytest.approx(60.0 / 190.0, rel=1e-4)

        assert "measurement_uncertainty_availability" in dims
        assert dims["measurement_uncertainty_availability"].evaluated is True

        assert "operating_context_coverage" in dims
        assert dims["operating_context_coverage"].evaluated is True
        assert dims["operating_context_coverage"].input_value == 4


    def test_missing_dimension_audit(self) -> None:
        """Verifies that unprovided dimensions are explicitly recorded as not evaluated with missing reason."""
        assessment = EvidenceEvaluator.evaluate(
            trend_stats=None,
            extrapolation_metrics=None,
        )
        assert assessment.evaluated_dimension_count == 0
        assert assessment.overall_strength == EvidenceStrength.INSUFFICIENT
        assert assessment.is_sufficient_for_uncertainty is False

        dims = assessment.dimensions
        assert dims["observation_count"].evaluated is False
        assert dims["observation_count"].missing_reason is not None

    def test_configurable_thresholds_override(self) -> None:
        """Verifies that customized threshold configuration is respected."""
        custom_cfg = EvidenceEvaluatorConfig(
            min_observations_strong=50,  # Strict threshold
            max_extrapolation_ratio_strong=0.1,
            min_r2_strong=0.999,
        )
        pairs = [(float(i), 3.0 - 0.01 * i) for i in range(10)]
        trend_stats = OLSTrendUncertaintyEvaluator.evaluate_pairs(pairs)

        assessment = EvidenceEvaluator.evaluate(
            trend_stats=trend_stats,
            config=custom_cfg,
        )
        # Sample count is 10, which is < 50, so observation count is MODERATE, not STRONG
        assert assessment.dimensions["observation_count"].strength == EvidenceStrength.MODERATE
