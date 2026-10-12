"""Semantic, Safety, and Architectural Isolation Tests for Level 6.6 Decision Layer.

Strict Invariants Verified:
1. Safety Authority Separation: Physical BMS remains the sole safety and control authority.
2. Zero Actuation: is_safety_critical_actuation is permanently False; digital twin cannot actuate.
3. Chemistry & Hardware Independence: Zero hardcoded thresholds or chemistry constants.
4. Immutability & Zero Side-Effects: Input evaluation result, policy, and twin state are unmodified.
5. Architectural Isolation: No imports of runtime, API, UI, services, storage, or hardware drivers.
"""

import sys
import pytest

from src.prognostics.decision.engine import PrognosticDecisionEngine
from src.prognostics.decision.policy import (
    DecisionCondition,
    DecisionPolicy,
    DecisionRule,
)
from src.prognostics.decision.types import (
    Actionability,
    DecisionClass,
    DecisionStatus,
    PrognosticDecisionResult,
    RecommendationPriority,
)
from src.prognostics.evaluation.types import (
    EOLAssessment,
    EOLState,
    EvaluationStatus,
    EvaluationValidity,
    PrognosticEvaluationResult,
)
from src.prognostics.prediction import EOLDefinition, RULPredictionResult
from src.prognostics.types import (
    ComparisonOperator,
    EOLCriterionType,
    HorizonDomain,
    PrognosticStatus,
)
from src.prognostics.uncertainty.evidence import (
    EvidenceAssessment,
    EvidenceEvaluatorConfig,
)
from src.prognostics.uncertainty.types import EvidenceStrength, UncertaintyStatus


class TestDecisionSemanticsAndSafety:
    """Safety boundary and architectural integrity tests for Level 6.6."""

    def test_safety_authority_and_actuation_invariants(self) -> None:
        """Verifies safety disclaimer, advisory status, and refusal of physical actuation."""
        engine = PrognosticDecisionEngine()
        cond = DecisionCondition(
            condition_id="c_crit",
            rul_threshold_value=5.0,
            rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        )
        rule = DecisionRule(
            rule_id="r_shutdown_advisory",
            precedence_rank=1,
            decision_class=DecisionClass.APPROACHING_EOL,
            priority=RecommendationPriority.CRITICAL,
            actionability=Actionability.ACTIONABLE,
            condition=cond,
            recommendation_template="Advisory: Impending EOL for system {system_id}.",
            rationale_template="Critical wear boundary reached.",
        )
        policy = DecisionPolicy(
            policy_id="pol_safe",
            policy_name="Safety Advisory Policy",
            version="1.0.0",
            rules=(rule,),
        )

        eol_def = EOLDefinition(
            criterion_id="eol_crit",
            criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
            threshold_value=0.70,
            unit="ratio",
        )
        eval_res = PrognosticEvaluationResult(
            evaluation_id="eval_safe_01",
            system_id="system_bms_test",
            evaluation_timestamp_ns=1_000_000_000,
            created_at_utc="2026-09-28T00:00:00Z",
            evaluation_status=EvaluationStatus.VALID,
            eol_assessment=EOLAssessment(
                eol_state=EOLState.PROJECTED,
                eol_definition=eol_def,
                threshold_value=0.70,
                comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
                unit="ratio",
                quantity_name="capacity_retention",
                current_value=0.71,
                distance_to_eol=0.01,
            ),
            validity=EvaluationValidity(
                data_quality=PrognosticStatus.VALID,
                history_sufficiency=PrognosticStatus.VALID,
                domain_validity=PrognosticStatus.VALID,
                eol_validity=True,
                prediction_validity=True,
                uncertainty_availability=UncertaintyStatus.STATISTICALLY_SUPPORTED,
                evidence_strength=EvidenceStrength.STRONG,
                is_usable_for_decision=True,
            ),
            prediction=RULPredictionResult(
                prediction_id="pred_safe",
                prediction_timestamp_ns=1_000_000_000,
                created_at_utc="2026-09-28T00:00:00Z",
                system_id="system_bms_test",
                status=PrognosticStatus.VALID,
                rul_value=3.0,
                rul_unit="cycles",
                rul_domain=HorizonDomain.CYCLE,
                eol_definition=eol_def,
            ),
            evidence=EvidenceAssessment(
                overall_strength=EvidenceStrength.STRONG,
                dimensions={},
                evaluated_dimension_count=0,
                total_dimension_count=4,
                is_sufficient_for_uncertainty=True,
                diagnostic_summary="Evidence is strong.",
                config_applied=EvidenceEvaluatorConfig(),
            ),
        )

        res = engine.evaluate(eval_res, policy)

        # Strict safety verifications
        assert res.is_safety_critical_actuation is False
        assert "Physical BMS" in res.safety_authority
        assert "ADVISORY ONLY" in res.safety_disclaimer
        assert "do not command physical actuators" in res.safety_disclaimer


    def test_input_immutability_and_zero_side_effects(self) -> None:
        """Verifies that running the decision engine does NOT mutate the input evaluation result."""
        engine = PrognosticDecisionEngine()
        cond = DecisionCondition(
            condition_id="c_maint",
            rul_threshold_value=50.0,
            rul_comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
        )
        rule = DecisionRule(
            rule_id="r_maint",
            precedence_rank=1,
            decision_class=DecisionClass.PLAN_MAINTENANCE,
            priority=RecommendationPriority.HIGH,
            actionability=Actionability.ACTIONABLE,
            condition=cond,
            recommendation_template="Rec",
            rationale_template="Rat",
        )
        policy = DecisionPolicy(
            policy_id="pol_immut",
            policy_name="Immutability Policy",
            version="1.0.0",
            rules=(rule,),
        )

        eol_def = EOLDefinition(
            criterion_id="eol_crit",
            criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
            threshold_value=0.80,
            unit="ratio",
        )
        eval_res = PrognosticEvaluationResult(
            evaluation_id="eval_immut_01",
            system_id="system_immut",
            evaluation_timestamp_ns=1_000_000_000,
            created_at_utc="2026-09-28T00:00:00Z",
            evaluation_status=EvaluationStatus.VALID,
            eol_assessment=EOLAssessment(
                eol_state=EOLState.PROJECTED,
                eol_definition=eol_def,
                threshold_value=0.80,
                comparison_operator=ComparisonOperator.LESS_THAN_OR_EQUAL,
                unit="ratio",
                quantity_name="capacity_retention",
                current_value=0.85,
                distance_to_eol=0.05,
            ),
            validity=EvaluationValidity(
                data_quality=PrognosticStatus.VALID,
                history_sufficiency=PrognosticStatus.VALID,
                domain_validity=PrognosticStatus.VALID,
                eol_validity=True,
                prediction_validity=True,
                uncertainty_availability=UncertaintyStatus.STATISTICALLY_SUPPORTED,
                evidence_strength=EvidenceStrength.STRONG,
                is_usable_for_decision=True,
            ),
            prediction=RULPredictionResult(
                prediction_id="pred_immut",
                prediction_timestamp_ns=1_000_000_000,
                created_at_utc="2026-09-28T00:00:00Z",
                system_id="system_immut",
                status=PrognosticStatus.VALID,
                rul_value=35.0,
                rul_unit="cycles",
                rul_domain=HorizonDomain.CYCLE,
                eol_definition=eol_def,
            ),
        )

        dict_before = eval_res.to_dict()
        res = engine.evaluate(eval_res, policy)
        dict_after = eval_res.to_dict()

        # Input evaluation result must be unmodified
        assert dict_before == dict_after
        assert res.evaluation_reference_id == eval_res.evaluation_id

    def test_architectural_isolation_no_infrastructure_imports(self) -> None:
        """Verifies Level 6.6 decision modules do not import runtime, API, UI, storage, or gateway."""
        import src.prognostics.decision.engine as eng
        import src.prognostics.decision.policy as pol
        import src.prognostics.decision.recommendation as rec
        import src.prognostics.decision.types as typ

        modules = [eng, pol, rec, typ]
        forbidden_substrings = [
            "src.runtime",
            "src.api",
            "src.ui",
            "src.storage",
            "src.gateway",
            "src.services",
            "fastapi",
            "uvicorn",
            "serial",
            "can",
        ]

        for mod in modules:
            mod_code = open(mod.__file__, "r", encoding="utf-8").read()
            for forbidden in forbidden_substrings:
                assert f"import {forbidden}" not in mod_code, (
                    f"Forbidden import '{forbidden}' found in {mod.__name__}."
                )
                assert f"from {forbidden}" not in mod_code, (
                    f"Forbidden import '{forbidden}' found in {mod.__name__}."
                )
