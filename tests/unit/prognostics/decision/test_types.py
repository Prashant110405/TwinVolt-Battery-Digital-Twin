"""Unit Tests for Level 6.6 Decision Types, Enums, and Value Objects.

Validates:
- DecisionStatus, DecisionClass, RecommendationPriority, Actionability enums
- SecondaryAdvisory immutability, validation, and serialization
- PrognosticDecisionResult immutability, safety invariants, and serialization
"""

from dataclasses import FrozenInstanceError
import pytest

from src.prognostics.decision.types import (
    Actionability,
    DecisionClass,
    DecisionStatus,
    PrognosticDecisionResult,
    RecommendationPriority,
    SecondaryAdvisory,
)


class TestDecisionTypes:
    """Contract and immutability tests for Level 6.6 domain types."""

    def test_decision_status_enum_distinctness(self) -> None:
        """Verifies DecisionStatus members are unique and string-valued."""
        statuses = {
            DecisionStatus.EVALUATED,
            DecisionStatus.DEFAULT_RULE_APPLIED,
            DecisionStatus.BLOCKED_BY_VALIDITY,
            DecisionStatus.INCOMPATIBLE_EVALUATION,
            DecisionStatus.INVALID_POLICY,
            DecisionStatus.NO_MATCH,
            DecisionStatus.INDETERMINATE,
        }
        assert len(statuses) == 7
        assert DecisionStatus.EVALUATED.value == "EVALUATED"
        assert DecisionStatus.BLOCKED_BY_VALIDITY.value == "BLOCKED_BY_VALIDITY"

    def test_decision_class_enum_distinctness(self) -> None:
        """Verifies DecisionClass members are unique and string-valued."""
        classes = {
            DecisionClass.CONTINUE_MONITORING,
            DecisionClass.INCREASE_MONITORING,
            DecisionClass.SCHEDULE_INSPECTION,
            DecisionClass.PLAN_MAINTENANCE,
            DecisionClass.APPROACHING_EOL,
            DecisionClass.EOL_REACHED,
            DecisionClass.INSUFFICIENT_EVIDENCE,
            DecisionClass.DATA_QUALITY_ACTION_REQUIRED,
            DecisionClass.OUT_OF_DOMAIN,
            DecisionClass.INDETERMINATE_STATE,
            DecisionClass.NO_ACTION,
            DecisionClass.CUSTOM,
        }
        assert len(classes) == 12

    def test_recommendation_priority_enum_distinctness(self) -> None:
        """Verifies RecommendationPriority members are distinct."""
        priorities = {
            RecommendationPriority.CRITICAL,
            RecommendationPriority.HIGH,
            RecommendationPriority.MEDIUM,
            RecommendationPriority.LOW,
            RecommendationPriority.INFORMATIONAL,
        }
        assert len(priorities) == 5

    def test_actionability_enum_distinctness(self) -> None:
        """Verifies Actionability members are distinct."""
        actionabilities = {
            Actionability.ACTIONABLE,
            Actionability.ADVISORY_ONLY,
            Actionability.INVESTIGATION_REQUIRED,
            Actionability.NON_ACTIONABLE,
            Actionability.MAINTENANCE_RECOMMENDATION,
            Actionability.DATA_QUALITY_ACTION,
            Actionability.INFORMATIONAL,
        }
        assert len(actionabilities) == 7

    def test_secondary_advisory_instantiation_and_serialization(self) -> None:
        """Verifies SecondaryAdvisory properties and dictionary serialization."""
        adv = SecondaryAdvisory(
            advisory_id="adv_inspect_01",
            decision_class=DecisionClass.SCHEDULE_INSPECTION,
            priority=RecommendationPriority.MEDIUM,
            actionability=Actionability.ADVISORY_ONLY,
            summary="Schedule cell balancing inspection.",
            rationale="Minor dispersion noted in degradation trajectory.",
            matched_condition_id="cond_dispersion",
            metadata={"source": "unit_test"},
        )
        assert adv.advisory_id == "adv_inspect_01"
        assert adv.decision_class == DecisionClass.SCHEDULE_INSPECTION
        assert adv.priority == RecommendationPriority.MEDIUM
        assert adv.actionability == Actionability.ADVISORY_ONLY

        d = adv.to_dict()
        assert d["advisory_id"] == "adv_inspect_01"
        assert d["decision_class"] == "SCHEDULE_INSPECTION"
        assert d["priority"] == "MEDIUM"
        assert d["actionability"] == "ADVISORY_ONLY"
        assert d["matched_condition_id"] == "cond_dispersion"

        # Immutability
        with pytest.raises(FrozenInstanceError):
            adv.summary = "Modified"  # type: ignore

    def test_secondary_advisory_invalid_inputs(self) -> None:
        """Verifies type enforcement on SecondaryAdvisory."""
        with pytest.raises(ValueError):
            SecondaryAdvisory(
                advisory_id="",
                decision_class=DecisionClass.SCHEDULE_INSPECTION,
                priority=RecommendationPriority.MEDIUM,
                actionability=Actionability.ADVISORY_ONLY,
                summary="Valid",
                rationale="Valid",
            )
        with pytest.raises(TypeError):
            SecondaryAdvisory(
                advisory_id="adv_01",
                decision_class="INVALID_CLASS",  # type: ignore
                priority=RecommendationPriority.MEDIUM,
                actionability=Actionability.ADVISORY_ONLY,
                summary="Valid",
                rationale="Valid",
            )

    def test_prognostic_decision_result_instantiation_and_serialization(self) -> None:
        """Verifies PrognosticDecisionResult properties, properties, and dictionary serialization."""
        sec_adv = SecondaryAdvisory(
            advisory_id="adv_sec_01",
            decision_class=DecisionClass.INCREASE_MONITORING,
            priority=RecommendationPriority.LOW,
            actionability=Actionability.ADVISORY_ONLY,
            summary="Increase monitoring polling.",
            rationale="Moderate extrapolation distance.",
        )
        result = PrognosticDecisionResult(
            decision_id="dec_test_001",
            system_id="cell_pack_1",
            decision_timestamp_ns=1_700_000_000_000,
            created_at_utc="2026-09-28T00:00:00Z",
            status=DecisionStatus.EVALUATED,
            primary_decision_class=DecisionClass.PLAN_MAINTENANCE,
            primary_recommendation="Schedule battery pack overhaul within 50 cycles.",
            primary_priority=RecommendationPriority.HIGH,
            primary_actionability=Actionability.ACTIONABLE,
            primary_rationale="RUL (45.00 cycles) <= 50.00 cycles threshold.",
            policy_id="pol_ev_fleet_v1",
            policy_version="1.0.0",
            primary_rule_id="rule_maint_50",
            matched_rule_ids=("rule_maint_50", "rule_monitor_inc"),
            triggering_conditions=("rule_maint_50: RUL <= 50.00",),
            secondary_advisories=(sec_adv,),
            validity_limitations=("Statistical uncertainty is limited.",),
            evaluation_reference_id="eval_001",
            reproducibility_metadata={"engine": "twinvolt_engine"},
        )

        assert result.decision_id == "dec_test_001"
        assert result.status == DecisionStatus.EVALUATED
        assert result.primary_decision_class == DecisionClass.PLAN_MAINTENANCE
        assert result.is_actionable is True
        assert result.is_safety_critical_actuation is False
        assert "BMS" in result.safety_authority

        d = result.to_dict()
        assert d["decision_id"] == "dec_test_001"
        assert d["status"] == "EVALUATED"
        assert d["primary_decision_class"] == "PLAN_MAINTENANCE"
        assert d["is_actionable"] is True
        assert d["is_safety_critical_actuation"] is False
        assert len(d["secondary_advisories"]) == 1
        assert d["secondary_advisories"][0]["advisory_id"] == "adv_sec_01"

        # Immutability
        with pytest.raises(FrozenInstanceError):
            result.primary_recommendation = "Changed"  # type: ignore

    def test_prognostic_decision_result_safety_actuation_invariant(self) -> None:
        """Verifies that is_safety_critical_actuation cannot be set to True."""
        with pytest.raises(ValueError, match="is_safety_critical_actuation must be False"):
            PrognosticDecisionResult(
                decision_id="dec_test_002",
                system_id="cell_pack_1",
                decision_timestamp_ns=1_000_000_000,
                created_at_utc="2026-09-28T00:00:00Z",
                status=DecisionStatus.EVALUATED,
                primary_decision_class=DecisionClass.PLAN_MAINTENANCE,
                primary_recommendation="Valid",
                primary_priority=RecommendationPriority.HIGH,
                primary_actionability=Actionability.ACTIONABLE,
                primary_rationale="Valid",
                policy_id="pol_01",
                policy_version="1.0.0",
                is_safety_critical_actuation=True,  # type: ignore
            )

    def test_prognostic_decision_result_invalid_fields(self) -> None:
        """Verifies type and non-empty checks on PrognosticDecisionResult fields."""
        base_kwargs = {
            "decision_id": "dec_01",
            "system_id": "sys_01",
            "decision_timestamp_ns": 1_000,
            "created_at_utc": "2026-09-28T00:00:00Z",
            "status": DecisionStatus.EVALUATED,
            "primary_decision_class": DecisionClass.PLAN_MAINTENANCE,
            "primary_recommendation": "Rec",
            "primary_priority": RecommendationPriority.HIGH,
            "primary_actionability": Actionability.ACTIONABLE,
            "primary_rationale": "Rat",
            "policy_id": "pol_01",
            "policy_version": "1.0.0",
        }

        # Empty decision_id
        with pytest.raises(ValueError):
            PrognosticDecisionResult(**{**base_kwargs, "decision_id": ""})

        # Negative timestamp
        with pytest.raises(ValueError):
            PrognosticDecisionResult(**{**base_kwargs, "decision_timestamp_ns": -1})

        # Invalid status type
        with pytest.raises(TypeError):
            PrognosticDecisionResult(**{**base_kwargs, "status": "INVALID"})  # type: ignore

        # Invalid priority type
        with pytest.raises(TypeError):
            PrognosticDecisionResult(**{**base_kwargs, "primary_priority": "CRITICAL"})  # type: ignore

