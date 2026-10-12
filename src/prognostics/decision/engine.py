"""Prognostic Decision and Recommendation Orchestration Engine.

Orchestrates pure, deterministic, and auditable prognostic decision synthesis:
1. Validates DecisionPolicy structure and domain compatibility.
2. Inspects Level 6.5 multi-dimensional validity gating.
3. Evaluates declarative decision conditions against authoritative evaluation results.
4. Deterministically resolves multi-rule matches via explicit precedence ranking.
5. Synthesizes primary operational recommendations while preserving structured secondary advisories.
6. Enforces strict safety authority separation (BMS remains control authority).
"""

from typing import Any, Mapping, Optional, Sequence

from src.prognostics.decision.policy import DecisionPolicy, DecisionRule
from src.prognostics.decision.recommendation import RecommendationSynthesizer
from src.prognostics.decision.types import (
    Actionability,
    DecisionClass,
    DecisionStatus,
    PrognosticDecisionResult,
    RecommendationPriority,
    SecondaryAdvisory,
)
from src.prognostics.evaluation.types import (
    EvaluationStatus,
    PrognosticEvaluationResult,
)
from src.prognostics.uncertainty.types import EvidenceStrength, UncertaintyStatus


class PrognosticDecisionEngine:
    """Stateless orchestrator for prognostic decision and recommendation synthesis.

    Strict Invariants:
    1. Pure & Deterministic: Identical inputs produce byte-for-byte identical decision records.
    2. Zero Algorithm Re-computation: Never recalculates RUL, uncertainty, or degradation rates.
    3. Safety Authority Separation: Never commands physical actuators; all outputs remain advisory.
    4. Gated Validity: Prevents corrupted data quality from triggering physical maintenance rules.
    5. Preserved Secondary Advisories: Preserves independent failure modes and limitations.
    """

    def __init__(
        self,
        engine_id: str = "twinvolt_prognostic_decision_engine",
        version: str = "1.0.0",
    ) -> None:
        self._engine_id = engine_id
        self._version = version

    def evaluate(
        self,
        evaluation: PrognosticEvaluationResult,
        policy: DecisionPolicy,
        decision_id: Optional[str] = None,
        decision_timestamp_ns: Optional[int] = None,
        created_at_utc: Optional[str] = None,
    ) -> PrognosticDecisionResult:
        """Executes deterministic decision synthesis against an authoritative evaluation result."""
        # 1. Type verification
        if not isinstance(evaluation, PrognosticEvaluationResult):
            raise TypeError(f"Expected PrognosticEvaluationResult, got {type(evaluation).__name__}.")
        if not isinstance(policy, DecisionPolicy):
            raise TypeError(f"Expected DecisionPolicy, got {type(policy).__name__}.")

        # 2. Validate policy invariants
        policy.validate()

        # 3. Establish deterministic IDs and timestamps
        dec_id = decision_id if decision_id is not None else f"dec_{evaluation.evaluation_id}"
        ts_ns = (
            decision_timestamp_ns
            if decision_timestamp_ns is not None
            else evaluation.evaluation_timestamp_ns
        )
        utc_str = created_at_utc if created_at_utc is not None else evaluation.created_at_utc

        # 4. Check domain compatibility
        if policy.target_domain is not None and evaluation.prediction is not None:
            if evaluation.prediction.is_valid and evaluation.prediction.rul_domain != policy.target_domain:
                # Incompatible domain between policy and valid evaluation prediction
                diag_msg = (
                    f"Evaluation prediction domain '{evaluation.prediction.rul_domain.value}' is "
                    f"incompatible with policy target_domain '{policy.target_domain.value}'."
                )
                return PrognosticDecisionResult(
                    decision_id=dec_id,
                    system_id=evaluation.system_id,
                    decision_timestamp_ns=ts_ns,
                    created_at_utc=utc_str,
                    status=DecisionStatus.INCOMPATIBLE_EVALUATION,
                    primary_decision_class=DecisionClass.INDETERMINATE_STATE,
                    primary_recommendation=f"Cannot evaluate decision: {diag_msg}",
                    primary_priority=RecommendationPriority.MEDIUM,
                    primary_actionability=Actionability.NON_ACTIONABLE,
                    primary_rationale=diag_msg,
                    policy_id=policy.policy_id,
                    policy_version=policy.version,
                    evaluation_reference_id=evaluation.evaluation_id,
                    validity_limitations=tuple(evaluation.validity.limitations) + (diag_msg,),
                    reproducibility_metadata={
                        "engine_id": self._engine_id,
                        "engine_version": self._version,
                        "domain_mismatch": True,
                    },
                )

        # 5. Evaluate all policy rules
        matched_rules: list[tuple[DecisionRule, list[str]]] = []
        for rule in policy.rules:
            is_match, reasons = rule.condition.matches(evaluation)
            if is_match:
                matched_rules.append((rule, reasons))

        # 6. Sort matched rules by precedence_rank ascending (strictly deterministic)
        matched_rules.sort(key=lambda item: item[0].precedence_rank)

        # Collect validity limitations and diagnostic notes
        limitations_list = list(evaluation.validity.limitations)
        if evaluation.validity.diagnostic_notes:
            limitations_list.extend(evaluation.validity.diagnostic_notes)

        # 7. Precedence Resolution & Output Assembly
        if matched_rules:
            # At least one configured rule matched
            primary_rule, primary_reasons = matched_rules[0]
            rec_text, rat_text = RecommendationSynthesizer.synthesize_primary(
                primary_rule, evaluation, primary_reasons
            )

            # Synthesize secondary advisories from remaining matched rules
            sec_advisories: list[SecondaryAdvisory] = []
            for sec_rule, sec_reasons in matched_rules[1:]:
                sec_adv = RecommendationSynthesizer.synthesize_secondary(
                    sec_rule, evaluation, sec_reasons
                )
                sec_advisories.append(sec_adv)

            matched_ids = tuple(r[0].rule_id for r in matched_rules)
            all_triggering_conditions = tuple(
                f"{r[0].rule_id}: {'; '.join(r[1])}" for r in matched_rules
            )

            meta: dict[str, Any] = {
                "engine_id": self._engine_id,
                "engine_version": self._version,
                "matched_rule_count": len(matched_rules),
                "primary_rule_rank": primary_rule.precedence_rank,
                "evaluation_status": evaluation.evaluation_status.value,
                "eol_state": evaluation.eol_assessment.eol_state.value,
            }
            if evaluation.prediction and evaluation.prediction.rul_value is not None:
                meta["rul_value"] = round(float(evaluation.prediction.rul_value), 6)
                meta["rul_unit"] = evaluation.prediction.rul_unit
                meta["rul_domain"] = evaluation.prediction.rul_domain.value

            return PrognosticDecisionResult(
                decision_id=dec_id,
                system_id=evaluation.system_id,
                decision_timestamp_ns=ts_ns,
                created_at_utc=utc_str,
                status=DecisionStatus.EVALUATED,
                primary_decision_class=primary_rule.decision_class,
                primary_recommendation=rec_text,
                primary_priority=primary_rule.priority,
                primary_actionability=primary_rule.actionability,
                primary_rationale=rat_text,
                policy_id=policy.policy_id,
                policy_version=policy.version,
                primary_rule_id=primary_rule.rule_id,
                matched_rule_ids=matched_ids,
                triggering_conditions=all_triggering_conditions,
                secondary_advisories=tuple(sec_advisories),
                validity_limitations=tuple(limitations_list),
                evaluation_reference_id=evaluation.evaluation_id,
                reproducibility_metadata=meta,
            )

        # 8. No rule matched: Check validity gating vs default policy fallback
        if not evaluation.validity.is_usable_for_decision:
            # Fatal validity failure with no specific policy handler
            eval_stat = evaluation.evaluation_status
            if eval_stat == EvaluationStatus.DATA_QUALITY_FAILED:
                dec_class = DecisionClass.DATA_QUALITY_ACTION_REQUIRED
                priority = RecommendationPriority.CRITICAL
                actionability = Actionability.INVESTIGATION_REQUIRED
                rec_text = "Telemetry data failed integrity validation. Investigate sensor stream before scheduling maintenance."
                rat_text = f"Evaluation failed data quality checks: {'; '.join(evaluation.validity.limitations)}"
            elif eval_stat == EvaluationStatus.OUT_OF_DOMAIN:
                dec_class = DecisionClass.OUT_OF_DOMAIN
                priority = RecommendationPriority.HIGH
                actionability = Actionability.INVESTIGATION_REQUIRED
                rec_text = "Operating profile or rate of degradation is out of valid prognostic domain. Recalibrate operational model."
                rat_text = f"Operating state out of domain: {'; '.join(evaluation.validity.limitations)}"
            elif eval_stat in (EvaluationStatus.INSUFFICIENT_DATA, EvaluationStatus.INVALID_EOL_CRITERION):
                dec_class = DecisionClass.DATA_QUALITY_ACTION_REQUIRED
                priority = RecommendationPriority.HIGH
                actionability = Actionability.INVESTIGATION_REQUIRED
                rec_text = "Prognostic evaluation blocked by missing data channels or invalid EOL criterion."
                rat_text = f"Blocked by validity failure ({eval_stat.value}): {'; '.join(evaluation.validity.limitations)}"
            elif eval_stat == EvaluationStatus.INSUFFICIENT_HISTORY:
                dec_class = DecisionClass.INSUFFICIENT_EVIDENCE
                priority = RecommendationPriority.MEDIUM
                actionability = Actionability.ADVISORY_ONLY
                rec_text = "Historical observation window too short for actionable prognostic decision."
                rat_text = f"Insufficient history: {'; '.join(evaluation.validity.limitations)}"
            else:
                dec_class = DecisionClass.INDETERMINATE_STATE
                priority = RecommendationPriority.MEDIUM
                actionability = Actionability.NON_ACTIONABLE
                rec_text = "Prognostic state is indeterminate. Maintain standard operational monitoring."
                rat_text = f"Indeterminate prognostic state ({eval_stat.value})."

            return PrognosticDecisionResult(
                decision_id=dec_id,
                system_id=evaluation.system_id,
                decision_timestamp_ns=ts_ns,
                created_at_utc=utc_str,
                status=DecisionStatus.BLOCKED_BY_VALIDITY,
                primary_decision_class=dec_class,
                primary_recommendation=rec_text,
                primary_priority=priority,
                primary_actionability=actionability,
                primary_rationale=rat_text,
                policy_id=policy.policy_id,
                policy_version=policy.version,
                primary_rule_id=None,
                matched_rule_ids=(),
                triggering_conditions=(),
                secondary_advisories=(),
                validity_limitations=tuple(limitations_list),
                evaluation_reference_id=evaluation.evaluation_id,
                reproducibility_metadata={
                    "engine_id": self._engine_id,
                    "engine_version": self._version,
                    "blocked_by_validity": True,
                    "evaluation_status": eval_stat.value,
                },
            )

        # 9. Usable evaluation, but no specific rule matched: Apply policy default rule
        def_rec = RecommendationSynthesizer.format_template(
            policy.default_recommendation, evaluation
        )
        def_rat = RecommendationSynthesizer.format_template(
            policy.default_rationale, evaluation
        )

        return PrognosticDecisionResult(
            decision_id=dec_id,
            system_id=evaluation.system_id,
            decision_timestamp_ns=ts_ns,
            created_at_utc=utc_str,
            status=DecisionStatus.DEFAULT_RULE_APPLIED,
            primary_decision_class=policy.default_decision_class,
            primary_recommendation=def_rec,
            primary_priority=policy.default_priority,
            primary_actionability=policy.default_actionability,
            primary_rationale=def_rat,
            policy_id=policy.policy_id,
            policy_version=policy.version,
            primary_rule_id=None,
            matched_rule_ids=(),
            triggering_conditions=(),
            secondary_advisories=(),
            validity_limitations=tuple(limitations_list),
            evaluation_reference_id=evaluation.evaluation_id,
            reproducibility_metadata={
                "engine_id": self._engine_id,
                "engine_version": self._version,
                "default_rule_applied": True,
                "evaluation_status": evaluation.evaluation_status.value,
                "eol_state": evaluation.eol_assessment.eol_state.value,
            },
        )
