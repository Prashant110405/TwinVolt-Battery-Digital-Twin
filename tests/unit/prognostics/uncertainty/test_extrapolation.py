"""Unit Tests for Extrapolation Metrics and Evidence Evaluation.

Validates:
- Extrapolation distance, observed span, and extrapolation ratio calculations
- Zero extrapolation behavior when already at EOL boundary
- Infinite ratio handling when historical span is zero
- Preservation of extrapolation metrics without arbitrary multiplier equations
"""

import math
import pytest

from src.prognostics.uncertainty.extrapolation import (
    ExtrapolationEvaluator,
    ExtrapolationMetrics,
)
from src.prognostics.uncertainty.types import (
    UncertaintySourceCategory,
    UncertaintyStatus,
)


class TestExtrapolationEvaluator:
    """Extrapolation evaluation tests."""

    def test_standard_extrapolation(self) -> None:
        """Verifies standard extrapolation distance and ratio."""
        metrics = ExtrapolationEvaluator.evaluate(
            observed_history_span=100.0,
            extrapolation_distance=50.0,
            sample_count=20,
            slope_standard_error=0.0001,
            residual_standard_error=0.005,
            domain_unit="cycles",
        )
        assert metrics.observed_history_span == 100.0
        assert metrics.extrapolation_distance == 50.0
        assert metrics.extrapolation_ratio == pytest.approx(0.5, rel=1e-6)
        assert metrics.is_extrapolating is True
        assert metrics.component is not None
        assert metrics.component.source_category == UncertaintySourceCategory.EXTRAPOLATION
        assert metrics.component.status == UncertaintyStatus.ESTIMATED

    def test_zero_extrapolation_at_eol(self) -> None:
        """Verifies zero extrapolation when at EOL."""
        metrics = ExtrapolationEvaluator.evaluate(
            observed_history_span=80.0,
            extrapolation_distance=0.0,
            sample_count=15,
            domain_unit="cycles",
        )
        assert metrics.extrapolation_distance == 0.0
        assert metrics.extrapolation_ratio == 0.0
        assert metrics.is_extrapolating is False
        assert metrics.component is not None
        assert metrics.component.status == UncertaintyStatus.DETERMINISTIC_ONLY

    def test_zero_history_span_infinite_ratio(self) -> None:
        """Verifies infinite extrapolation ratio when history span is zero."""
        metrics = ExtrapolationEvaluator.evaluate(
            observed_history_span=0.0,
            extrapolation_distance=50.0,
            sample_count=1,
            domain_unit="cycles",
        )
        assert math.isinf(metrics.extrapolation_ratio)
        assert metrics.component is not None
        assert metrics.component.status == UncertaintyStatus.INSUFFICIENT_EVIDENCE
