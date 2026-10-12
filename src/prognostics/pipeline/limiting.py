"""Limiting Degradation Mechanism Resolver for Multi-Criterion Prognostic Assessment.

Enforces:
1. Explicit LimitingResolutionStrategy (never hidden universal 'minimum RUL').
2. Cross-domain comparison protection (preserves individual evaluations and returns INCOMPATIBLE_DOMAINS if HorizonDomains differ).
3. Independent evaluation integrity (no synthetic joint uncertainty).
4. Deterministic tie-breaking by criterion identity.
5. Numerical margin tracking only when mathematically and domain-compatible.
"""

from typing import Optional, Sequence

from src.prognostics.decision.types import DecisionClass, RecommendationPriority
from src.prognostics.evaluation.types import EOLState, EvaluationStatus
from src.prognostics.pipeline.types import (
    CriterionPrognosticEvaluation,
    LimitingMechanismAssessment,
    LimitingResolutionStatus,
    LimitingResolutionStrategy,
)
from src.prognostics.types import HorizonDomain


# Operational priority rankings for deterministic sorting
_PRIORITY_RANK: dict[RecommendationPriority, int] = {
    RecommendationPriority.CRITICAL: 5,
    RecommendationPriority.HIGH: 4,
    RecommendationPriority.MEDIUM: 3,
    RecommendationPriority.LOW: 2,
    RecommendationPriority.INFORMATIONAL: 1,
}

_DECISION_CLASS_RANK: dict[DecisionClass, int] = {
    DecisionClass.EOL_REACHED: 10,
    DecisionClass.APPROACHING_EOL: 9,
    DecisionClass.PLAN_MAINTENANCE: 8,
    DecisionClass.DATA_QUALITY_ACTION_REQUIRED: 7,
    DecisionClass.SCHEDULE_INSPECTION: 6,
    DecisionClass.INCREASE_MONITORING: 5,
    DecisionClass.OUT_OF_DOMAIN: 4,
    DecisionClass.INSUFFICIENT_EVIDENCE: 3,
    DecisionClass.CONTINUE_MONITORING: 2,
    DecisionClass.NO_ACTION: 1,
    DecisionClass.INDETERMINATE_STATE: 0,
    DecisionClass.CUSTOM: 0,
}


class LimitingMechanismResolver:
    """Deterministic, pure resolver for identifying the limiting degradation failure mode."""

    @classmethod
    def resolve(
        cls,
        criteria_evaluations: Sequence[CriterionPrognosticEvaluation],
        strategy: LimitingResolutionStrategy = LimitingResolutionStrategy.SHORTEST_RUL,
        allow_cross_domain_fallback_to_priority: bool = False,
    ) -> LimitingMechanismAssessment:
        """Resolves the limiting degradation mechanism from multi-criterion evaluations.

        Parameters
        ----------
        criteria_evaluations:
            Evaluations for each EOL criterion in the portfolio.
        strategy:
            Explicit limiting resolution strategy to apply.
        allow_cross_domain_fallback_to_priority:
            If True, falls back to HIGHEST_DECISION_PRIORITY when SHORTEST_RUL cannot be
            computed due to incompatible horizon domains. Default is False.

        Returns
        -------
        LimitingMechanismAssessment
            The resolved limiting mechanism assessment with status, candidate info, and margin.
        """
        if not criteria_evaluations:
            return LimitingMechanismAssessment(
                status=LimitingResolutionStatus.ALL_CRITERIA_UNAVAILABLE,
                resolution_strategy=strategy,
                rationale="Empty criteria evaluations sequence provided.",
            )

        # Filter to valid or evaluatable candidates
        valid_candidates = [
            c
            for c in criteria_evaluations
            if c.evaluation_result.evaluation_status
            in (EvaluationStatus.VALID, EvaluationStatus.VALID_WITH_LIMITATIONS)
            or c.evaluation_result.eol_assessment.eol_state
            in (EOLState.ALREADY_REACHED, EOLState.PROJECTED, EOLState.NOT_REACHED)
        ]

        if not valid_candidates:
            # Check if any candidate has an evaluated decision even with limitations
            valid_candidates = [
                c
                for c in criteria_evaluations
                if c.decision_result.primary_decision_class != DecisionClass.INDETERMINATE_STATE
            ]

        if not valid_candidates:
            return LimitingMechanismAssessment(
                status=LimitingResolutionStatus.ALL_CRITERIA_UNAVAILABLE,
                resolution_strategy=strategy,
                rationale="No criteria yielded a valid or actionable prognostic evaluation.",
            )

        if strategy == LimitingResolutionStrategy.SHORTEST_RUL:
            return cls._resolve_shortest_rul(
                valid_candidates,
                allow_cross_domain_fallback=allow_cross_domain_fallback_to_priority,
            )
        elif strategy == LimitingResolutionStrategy.HIGHEST_DECISION_PRIORITY:
            return cls._resolve_highest_decision_priority(valid_candidates)
        elif strategy == LimitingResolutionStrategy.NEAREST_EOL_DISTANCE:
            return cls._resolve_nearest_eol_distance(valid_candidates)
        elif strategy == LimitingResolutionStrategy.EXPLICIT_POLICY_ORDER:
            return cls._resolve_explicit_policy_order(valid_candidates)
        else:
            raise ValueError(f"Unsupported LimitingResolutionStrategy: {strategy}")

    @classmethod
    def _resolve_shortest_rul(
        cls,
        candidates: Sequence[CriterionPrognosticEvaluation],
        allow_cross_domain_fallback: bool,
    ) -> LimitingMechanismAssessment:
        """Resolves limiting mechanism by shortest numeric RUL within comparable domains."""
        # Candidates with finite RUL value
        rul_candidates = [
            c
            for c in candidates
            if c.evaluation_result.prediction is not None
            and c.evaluation_result.prediction.rul_value is not None
        ]

        if not rul_candidates:
            if allow_cross_domain_fallback:
                return cls._resolve_highest_decision_priority(
                    candidates,
                    fallback_note=" (Fell back from SHORTEST_RUL due to unavailable RUL values)",
                )
            return LimitingMechanismAssessment(
                status=LimitingResolutionStatus.ALL_CRITERIA_UNAVAILABLE,
                resolution_strategy=LimitingResolutionStrategy.SHORTEST_RUL,
                rationale="No criteria provided a finite RUL prediction value.",
            )

        # Check HorizonDomains for comparability
        domains: set[HorizonDomain] = {
            c.evaluation_result.prediction.rul_domain  # type: ignore[union-attr]
            for c in rul_candidates
        }
        if len(domains) > 1:
            if allow_cross_domain_fallback:
                return cls._resolve_highest_decision_priority(
                    candidates,
                    fallback_note=f" (Fell back from SHORTEST_RUL due to cross-domain incompatibility: {', '.join(d.value for d in domains)})",
                )
            return LimitingMechanismAssessment(
                status=LimitingResolutionStatus.INCOMPATIBLE_DOMAINS,
                resolution_strategy=LimitingResolutionStrategy.SHORTEST_RUL,
                rationale=(
                    f"Incompatible horizon domains ({', '.join(d.value for d in domains)}) "
                    "prevent direct numerical RUL comparison without conversion context."
                ),
            )

        # Check units for comparability
        units: set[str] = {
            c.evaluation_result.prediction.rul_unit  # type: ignore[union-attr]
            for c in rul_candidates
        }
        if len(units) > 1:
            if allow_cross_domain_fallback:
                return cls._resolve_highest_decision_priority(
                    candidates,
                    fallback_note=f" (Fell back from SHORTEST_RUL due to unit incompatibility: {', '.join(units)})",
                )
            return LimitingMechanismAssessment(
                status=LimitingResolutionStatus.INCOMPATIBLE_UNITS,
                resolution_strategy=LimitingResolutionStrategy.SHORTEST_RUL,
                rationale=(
                    f"Incompatible horizon units ({', '.join(units)}) "
                    "prevent direct numerical RUL comparison."
                ),
            )

        # Deterministic sort by (rul_value, criterion_id)
        sorted_candidates = sorted(
            rul_candidates,
            key=lambda c: (
                float(c.evaluation_result.prediction.rul_value),  # type: ignore[union-attr,arg-type]
                c.criterion_id,
            ),
        )

        limiting = sorted_candidates[0]
        limiting_pred = limiting.evaluation_result.prediction
        limiting_rul = limiting_pred.rul_value if limiting_pred else None
        limiting_unit = limiting_pred.rul_unit if limiting_pred else None
        limiting_domain = limiting_pred.rul_domain if limiting_pred else None
        secondary_id: Optional[str] = None
        margin: Optional[float] = None

        if len(sorted_candidates) > 1:
            secondary = sorted_candidates[1]
            secondary_id = secondary.criterion_id
            sec_pred = secondary.evaluation_result.prediction
            sec_rul = sec_pred.rul_value if sec_pred else None
            if sec_rul is not None and limiting_rul is not None:
                margin = max(0.0, float(sec_rul) - float(limiting_rul))

        return LimitingMechanismAssessment(
            status=LimitingResolutionStatus.RESOLVED,
            resolution_strategy=LimitingResolutionStrategy.SHORTEST_RUL,
            limiting_criterion_id=limiting.criterion_id,
            limiting_criterion_type=limiting.eol_definition.criterion_type,
            limiting_rul_value=limiting_rul,
            limiting_rul_unit=limiting_unit,
            limiting_rul_domain=limiting_domain,
            limiting_decision_class=limiting.decision_result.primary_decision_class,
            limiting_priority=limiting.decision_result.primary_priority,
            margin_to_secondary_rul=margin,
            secondary_criterion_id=secondary_id,
            rationale=(
                f"Resolved limiting mechanism as '{limiting.criterion_id}' with shortest RUL of "
                f"{limiting_rul} {limiting_unit}."
            ),
        )

    @classmethod
    def _resolve_highest_decision_priority(
        cls,
        candidates: Sequence[CriterionPrognosticEvaluation],
        fallback_note: str = "",
    ) -> LimitingMechanismAssessment:
        """Resolves limiting mechanism by highest recommendation priority / decision class."""
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (
                -_PRIORITY_RANK.get(c.decision_result.primary_priority, 0),
                -_DECISION_CLASS_RANK.get(c.decision_result.primary_decision_class, 0),
                c.criterion_id,
            ),
        )

        limiting = sorted_candidates[0]
        secondary_id: Optional[str] = None
        margin: Optional[float] = None

        lim_pred = limiting.evaluation_result.prediction
        lim_rul = lim_pred.rul_value if lim_pred else None
        lim_unit = lim_pred.rul_unit if lim_pred else None
        lim_domain = lim_pred.rul_domain if lim_pred else None

        if len(sorted_candidates) > 1:
            secondary = sorted_candidates[1]
            secondary_id = secondary.criterion_id
            sec_pred = secondary.evaluation_result.prediction
            sec_rul = sec_pred.rul_value if sec_pred else None
            sec_unit = sec_pred.rul_unit if sec_pred else None
            sec_domain = sec_pred.rul_domain if sec_pred else None

            # Calculate margin only if same domain, same unit, and both have finite RUL
            if (
                lim_rul is not None
                and sec_rul is not None
                and lim_domain is not None
                and lim_domain == sec_domain
                and lim_unit == sec_unit
            ):
                margin = max(0.0, float(sec_rul) - float(lim_rul))

        return LimitingMechanismAssessment(
            status=LimitingResolutionStatus.RESOLVED,
            resolution_strategy=LimitingResolutionStrategy.HIGHEST_DECISION_PRIORITY,
            limiting_criterion_id=limiting.criterion_id,
            limiting_criterion_type=limiting.eol_definition.criterion_type,
            limiting_rul_value=lim_rul,
            limiting_rul_unit=lim_unit,
            limiting_rul_domain=lim_domain,
            limiting_decision_class=limiting.decision_result.primary_decision_class,
            limiting_priority=limiting.decision_result.primary_priority,
            margin_to_secondary_rul=margin,
            secondary_criterion_id=secondary_id,
            rationale=(
                f"Resolved limiting mechanism as '{limiting.criterion_id}' with highest operational priority "
                f"{limiting.decision_result.primary_priority.value} ({limiting.decision_result.primary_decision_class.value}){fallback_note}."
            ),
        )

    @classmethod
    def _resolve_nearest_eol_distance(
        cls,
        candidates: Sequence[CriterionPrognosticEvaluation],
    ) -> LimitingMechanismAssessment:
        """Resolves limiting mechanism by smallest current distance to EOL threshold."""
        dist_candidates = [
            c
            for c in candidates
            if c.evaluation_result.eol_assessment.distance_to_eol is not None
        ]

        if not dist_candidates:
            return cls._resolve_highest_decision_priority(
                candidates,
                fallback_note=" (Fell back from NEAREST_EOL_DISTANCE due to unavailable distance values)",
            )

        # Check unit comparability across distance candidates
        units = {c.evaluation_result.eol_assessment.unit for c in dist_candidates}
        if len(units) > 1:
            # Different physical units for distance to EOL (e.g. Ohm vs Ah vs ratio)
            return cls._resolve_highest_decision_priority(
                candidates,
                fallback_note=f" (Fell back from NEAREST_EOL_DISTANCE due to incomparable units: {', '.join(units)})",
            )

        sorted_candidates = sorted(
            dist_candidates,
            key=lambda c: (
                float(c.evaluation_result.eol_assessment.distance_to_eol),  # type: ignore[arg-type]
                c.criterion_id,
            ),
        )

        limiting = sorted_candidates[0]
        secondary_id: Optional[str] = None
        margin: Optional[float] = None

        lim_pred = limiting.evaluation_result.prediction
        lim_rul = lim_pred.rul_value if lim_pred else None
        lim_unit = lim_pred.rul_unit if lim_pred else None
        lim_domain = lim_pred.rul_domain if lim_pred else None

        if len(sorted_candidates) > 1:
            secondary = sorted_candidates[1]
            secondary_id = secondary.criterion_id
            lim_dist = limiting.evaluation_result.eol_assessment.distance_to_eol
            sec_dist = secondary.evaluation_result.eol_assessment.distance_to_eol
            if lim_dist is not None and sec_dist is not None:
                margin = max(0.0, float(sec_dist) - float(lim_dist))

        return LimitingMechanismAssessment(
            status=LimitingResolutionStatus.RESOLVED,
            resolution_strategy=LimitingResolutionStrategy.NEAREST_EOL_DISTANCE,
            limiting_criterion_id=limiting.criterion_id,
            limiting_criterion_type=limiting.eol_definition.criterion_type,
            limiting_rul_value=lim_rul,
            limiting_rul_unit=lim_unit,
            limiting_rul_domain=lim_domain,
            limiting_decision_class=limiting.decision_result.primary_decision_class,
            limiting_priority=limiting.decision_result.primary_priority,
            margin_to_secondary_rul=margin,
            secondary_criterion_id=secondary_id,
            rationale=(
                f"Resolved limiting mechanism as '{limiting.criterion_id}' with nearest distance to EOL boundary "
                f"({limiting.evaluation_result.eol_assessment.distance_to_eol} {limiting.evaluation_result.eol_assessment.unit})."
            ),
        )

    @classmethod
    def _resolve_explicit_policy_order(
        cls,
        candidates: Sequence[CriterionPrognosticEvaluation],
    ) -> LimitingMechanismAssessment:
        """Resolves limiting mechanism by first valid criterion according to portfolio definition order."""
        limiting = candidates[0]
        secondary_id: Optional[str] = None
        margin: Optional[float] = None

        lim_pred = limiting.evaluation_result.prediction
        lim_rul = lim_pred.rul_value if lim_pred else None
        lim_unit = lim_pred.rul_unit if lim_pred else None
        lim_domain = lim_pred.rul_domain if lim_pred else None

        if len(candidates) > 1:
            secondary = candidates[1]
            secondary_id = secondary.criterion_id
            sec_pred = secondary.evaluation_result.prediction
            sec_rul = sec_pred.rul_value if sec_pred else None
            sec_unit = sec_pred.rul_unit if sec_pred else None
            sec_domain = sec_pred.rul_domain if sec_pred else None

            if (
                lim_rul is not None
                and sec_rul is not None
                and lim_domain is not None
                and lim_domain == sec_domain
                and lim_unit == sec_unit
            ):
                margin = max(0.0, float(sec_rul) - float(lim_rul))

        return LimitingMechanismAssessment(
            status=LimitingResolutionStatus.RESOLVED,
            resolution_strategy=LimitingResolutionStrategy.EXPLICIT_POLICY_ORDER,
            limiting_criterion_id=limiting.criterion_id,
            limiting_criterion_type=limiting.eol_definition.criterion_type,
            limiting_rul_value=lim_rul,
            limiting_rul_unit=lim_unit,
            limiting_rul_domain=lim_domain,
            limiting_decision_class=limiting.decision_result.primary_decision_class,
            limiting_priority=limiting.decision_result.primary_priority,
            margin_to_secondary_rul=margin,
            secondary_criterion_id=secondary_id,
            rationale=f"Resolved limiting mechanism as '{limiting.criterion_id}' by explicit portfolio policy order.",
        )
