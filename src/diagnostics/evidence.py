"""Evidence evaluation, scoring, and coverage calculations for Battery Diagnostics.

Defines rules, match intensities, coverage metrics, and the formal mathematical scoring engine
for empirical diagnostic evidence.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Callable, Mapping, Optional, Sequence

from src.diagnostics.config import DiagnosticThresholdConfig
from src.diagnostics.types import (
    DiagnosticCategory,
    DiagnosticEvidenceItem,
    EvidenceEvaluationStatus,
    OperatingContext,
)
from src.validation.types import SignalProvenance


@dataclass(frozen=True)
class EvidenceScoreResult:
    """Deterministic result of evaluating an evidence set against a hypothesis rule catalog."""

    evidence_score: float                            # Normalized empirical score [0.0, 1.0]
    confidence_level: str                            # "STRONG", "MODERATE", "WEAK", "REJECTED", "INSUFFICIENT_DATA", "NO_EVIDENCE"
    required_signal_coverage: float                  # Fraction of required signals with usable evidence [0.0, 1.0]
    optional_signal_coverage: float                  # Fraction of optional signals with usable evidence [0.0, 1.0]
    supporting_evidence: tuple[DiagnosticEvidenceItem, ...] = field(default_factory=tuple)
    contraindicating_evidence: tuple[DiagnosticEvidenceItem, ...] = field(default_factory=tuple)
    neutral_evidence: tuple[DiagnosticEvidenceItem, ...] = field(default_factory=tuple)
    unavailable_evidence: tuple[DiagnosticEvidenceItem, ...] = field(default_factory=tuple)
    unknown_evidence: tuple[DiagnosticEvidenceItem, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_score, (int, float)) or math.isnan(self.evidence_score) or math.isinf(self.evidence_score):
            raise ValueError(f"evidence_score must be a finite float, got {self.evidence_score}.")
        if not (0.0 <= self.evidence_score <= 1.0):
            raise ValueError(f"evidence_score must be in range [0.0, 1.0], got {self.evidence_score}.")
        if not (0.0 <= self.required_signal_coverage <= 1.0):
            raise ValueError(f"required_signal_coverage must be in range [0.0, 1.0], got {self.required_signal_coverage}.")
        if not (0.0 <= self.optional_signal_coverage <= 1.0):
            raise ValueError(f"optional_signal_coverage must be in range [0.0, 1.0], got {self.optional_signal_coverage}.")


class EvidenceScoringEngine:
    """Calculates deterministic empirical evidence scores, signal coverage, and confidence levels.

    Mathematical Scoring Formulation:
        MaxPossibleSupportingWeight = sum(rule.weight for rule in configured_supporting_rules)
        W_sup = sum(item.weight * match_intensity for item in supporting_items)
        V_contra = sum(item.weight * match_intensity for item in contraindicating_items)

        EvidenceScore = 0.0 if (W_sup == 0 or MaxPossibleSupportingWeight == 0) else
                        clamp((W_sup - V_contra) / MaxPossibleSupportingWeight, 0.0, 1.0)
    """

    @staticmethod
    def evaluate_evidence(
        evidence_items: Sequence[DiagnosticEvidenceItem],
        required_signals: Sequence[str],
        optional_signals: Sequence[str],
        total_possible_supporting_weight: float,
        config: Optional[DiagnosticThresholdConfig] = None,
    ) -> EvidenceScoreResult:
        """Evaluates an evidence collection and computes deterministic scores and coverage.

        Args:
            evidence_items: Sequence of evaluated DiagnosticEvidenceItem instances.
            required_signals: Canonical signal names required for evaluability.
            optional_signals: Canonical optional signal names.
            total_possible_supporting_weight: Sum of positive rule weights configured for the hypothesis.
            config: Optional threshold configuration for evidence coverage gates.

        Returns:
            EvidenceScoreResult containing scores, coverage fractions, and categorized evidence tuples.
        """
        cfg = config or DiagnosticThresholdConfig()

        if math.isnan(total_possible_supporting_weight) or math.isinf(total_possible_supporting_weight) or total_possible_supporting_weight < 0.0:
            raise ValueError(f"total_possible_supporting_weight must be a finite non-negative float, got {total_possible_supporting_weight}.")

        # 1. Deduplicate evidence by canonical signal_name (retaining the latest entry)
        deduped_map: dict[str, DiagnosticEvidenceItem] = {}
        for item in evidence_items:
            if not isinstance(item, DiagnosticEvidenceItem):
                raise TypeError(f"Expected DiagnosticEvidenceItem, got {type(item).__name__}.")
            deduped_map[item.signal_name] = item

        req_set = set(required_signals)
        opt_set = set(optional_signals)
        relevant_signals = req_set.union(opt_set)

        # Categorize items
        supporting: list[DiagnosticEvidenceItem] = []
        contraindicating: list[DiagnosticEvidenceItem] = []
        neutral: list[DiagnosticEvidenceItem] = []
        unavailable: list[DiagnosticEvidenceItem] = []
        unknown: list[DiagnosticEvidenceItem] = []

        usable_signals: set[str] = set()

        for sig_name, item in deduped_map.items():
            if relevant_signals and sig_name not in relevant_signals:
                continue

            if item.status == EvidenceEvaluationStatus.SUPPORTING:
                supporting.append(item)
                usable_signals.add(sig_name)
            elif item.status == EvidenceEvaluationStatus.CONTRAINDICATING:
                contraindicating.append(item)
                usable_signals.add(sig_name)
            elif item.status == EvidenceEvaluationStatus.NO_EVIDENCE:
                neutral.append(item)
                usable_signals.add(sig_name)
            elif item.status == EvidenceEvaluationStatus.UNAVAILABLE:
                unavailable.append(item)
            elif item.status == EvidenceEvaluationStatus.UNKNOWN:
                unknown.append(item)

        # 2. Coverage Calculations
        req_set = set(required_signals)
        opt_set = set(optional_signals)

        if len(req_set) > 0:
            usable_req_count = len(req_set.intersection(usable_signals))
            req_coverage = usable_req_count / len(req_set)
        else:
            req_coverage = 1.0

        if len(opt_set) > 0:
            usable_opt_count = len(opt_set.intersection(usable_signals))
            opt_coverage = usable_opt_count / len(opt_set)
        else:
            opt_coverage = 1.0

        # 3. Mathematical Evidence Scoring
        # Match intensity is implicitly encoded in item.weight (pre-scaled by rule) or weight is rule weight.
        # Following architecture contract: W_sup = sum(item.weight) for supporting items
        w_sup = sum(item.weight for item in supporting)
        v_contra = sum(item.weight for item in contraindicating)

        if total_possible_supporting_weight == 0.0 or w_sup == 0.0:
            evidence_score = 0.0
        else:
            raw_score = (w_sup - v_contra) / total_possible_supporting_weight
            evidence_score = max(0.0, min(1.0, raw_score))

        # 4. Confidence Tier Determination
        if req_coverage < 1.0:
            confidence_level = "INSUFFICIENT_DATA"
            evidence_score = 0.0
        elif w_sup == 0.0 and v_contra > 0.0:
            confidence_level = "REJECTED"
        elif w_sup == 0.0 and v_contra == 0.0:
            confidence_level = "NO_EVIDENCE"
        elif evidence_score >= 0.75 and v_contra == 0.0:
            if opt_coverage >= cfg.min_evidence_coverage_fraction or len(opt_set) == 0:
                confidence_level = "STRONG"
            else:
                confidence_level = "STRONG" if req_coverage == 1.0 and len(supporting) >= len(req_set) else "MODERATE"
        elif evidence_score >= 0.50:
            confidence_level = "MODERATE"
        elif evidence_score >= 0.20:
            confidence_level = "WEAK"
        else:
            confidence_level = "REJECTED"

        return EvidenceScoreResult(
            evidence_score=evidence_score,
            confidence_level=confidence_level,
            required_signal_coverage=req_coverage,
            optional_signal_coverage=opt_coverage,
            supporting_evidence=tuple(supporting),
            contraindicating_evidence=tuple(contraindicating),
            neutral_evidence=tuple(neutral),
            unavailable_evidence=tuple(unavailable),
            unknown_evidence=tuple(unknown),
        )
