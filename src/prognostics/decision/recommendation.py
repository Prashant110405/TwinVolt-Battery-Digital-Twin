"""Recommendation Representation and Deterministic Template Synthesizer.

Provides pure, deterministic formatting and synthesis of primary recommendations,
rationales, and secondary advisories without accessing live runtime or hardware state.
"""

from dataclasses import dataclass
from typing import Any, Optional, Sequence

from src.prognostics.decision.policy import DecisionRule
from src.prognostics.decision.types import (
    Actionability,
    DecisionClass,
    RecommendationPriority,
    SecondaryAdvisory,
)
from src.prognostics.evaluation.types import PrognosticEvaluationResult
from src.prognostics.uncertainty.types import EvidenceStrength, UncertaintyStatus


@dataclass(frozen=True)
class DecisionRecommendation:
    """Immutable synthesized recommendation payload."""

    decision_class: DecisionClass
    recommendation_text: str
    priority: RecommendationPriority
    actionability: Actionability
    rationale: str
    rule_id: Optional[str] = None
    matched_condition_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Serializes recommendation payload to dictionary."""
        return {
            "decision_class": self.decision_class.value,
            "recommendation_text": self.recommendation_text,
            "priority": self.priority.value,
            "actionability": self.actionability.value,
            "rationale": self.rationale,
            "rule_id": self.rule_id,
            "matched_condition_id": self.matched_condition_id,
        }


class RecommendationSynthesizer:
    """Pure, stateless synthesizer for deterministic recommendation and rationale generation."""

    @classmethod
    def _build_format_context(
        cls,
        evaluation: PrognosticEvaluationResult,
        rule: Optional[DecisionRule] = None,
        matched_reasons: Optional[Sequence[str]] = None,
    ) -> dict[str, Any]:
        """Extracts standard formatting context variables from evaluation result."""
        rul_val_str = (
            f"{evaluation.prediction.rul_value:.2f}"
            if evaluation.prediction and evaluation.prediction.rul_value is not None
            else "N/A"
        )
        rul_unit_str = evaluation.prediction.rul_unit if evaluation.prediction else ""
        rul_domain_str = (
            evaluation.prediction.rul_domain.value if evaluation.prediction else "N/A"
        )
        eol_state_str = evaluation.eol_assessment.eol_state.value
        eval_status_str = evaluation.evaluation_status.value
        unc_status_str = (
            evaluation.uncertainty.status.value
            if evaluation.uncertainty
            else UncertaintyStatus.UNDEFINED.value
        )
        ev_strength_str = (
            evaluation.evidence.overall_strength.value
            if evaluation.evidence
            else EvidenceStrength.INSUFFICIENT.value
        )
        reasons_summary = "; ".join(matched_reasons) if matched_reasons else "Condition satisfied."

        ctx = {
            "system_id": evaluation.system_id,
            "rul_value": rul_val_str,
            "rul_unit": rul_unit_str,
            "rul_domain": rul_domain_str,
            "eol_state": eol_state_str,
            "evaluation_status": eval_status_str,
            "uncertainty_status": unc_status_str,
            "evidence_strength": ev_strength_str,
            "matched_reasons": reasons_summary,
            "rule_id": rule.rule_id if rule else "",
            "rule_name": rule.rule_name if rule else "",
        }
        return ctx

    @classmethod
    def format_template(
        cls,
        template: str,
        evaluation: PrognosticEvaluationResult,
        rule: Optional[DecisionRule] = None,
        matched_reasons: Optional[Sequence[str]] = None,
    ) -> str:
        """Deterministically formats a string template using evaluation context."""
        ctx = cls._build_format_context(evaluation, rule, matched_reasons)
        try:
            return template.format(**ctx)
        except (KeyError, ValueError, IndexError):
            # Fallback to safe substitution if template contains non-standard placeholder
            formatted = template
            for k, v in ctx.items():
                formatted = formatted.replace(f"{{{k}}}", str(v))
            return formatted

    @classmethod
    def synthesize_primary(
        cls,
        rule: DecisionRule,
        evaluation: PrognosticEvaluationResult,
        matched_reasons: Sequence[str],
    ) -> tuple[str, str]:
        """Synthesizes deterministic primary recommendation and rationale texts."""
        rec_text = cls.format_template(
            rule.recommendation_template, evaluation, rule, matched_reasons
        )
        rat_text = cls.format_template(
            rule.rationale_template, evaluation, rule, matched_reasons
        )
        return rec_text, rat_text

    @classmethod
    def synthesize_secondary(
        cls,
        rule: DecisionRule,
        evaluation: PrognosticEvaluationResult,
        matched_reasons: Sequence[str],
    ) -> SecondaryAdvisory:
        """Synthesizes a structured secondary advisory from a matched non-primary rule."""
        summary_text = cls.format_template(
            rule.recommendation_template, evaluation, rule, matched_reasons
        )
        rationale_text = cls.format_template(
            rule.rationale_template, evaluation, rule, matched_reasons
        )

        return SecondaryAdvisory(
            advisory_id=f"adv_{rule.rule_id}",
            decision_class=rule.decision_class,
            priority=rule.priority,
            actionability=rule.actionability,
            summary=summary_text,
            rationale=rationale_text,
            matched_condition_id=rule.condition.condition_id,
            category="MATCHED_RULE_ADVISORY",
            source=f"POLICY_RULE:{rule.rule_id}",
            metadata={"precedence_rank": rule.precedence_rank},
        )
