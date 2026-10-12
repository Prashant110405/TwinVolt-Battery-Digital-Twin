"""Evaluation Validity and Limitation Classifier for Battery Prognostics.

Audits prognostic results across data quality, history sufficiency, domain limits,
EOL validity, uncertainty availability, and evidence strength to classify decision usability
without collapsing multi-dimensional validity into opaque scalar penalties.
"""

from typing import Optional, Sequence

from src.prognostics.evaluation.types import (
    EOLAssessment,
    EOLState,
    EvaluationStatus,
    EvaluationValidity,
)
from src.prognostics.prediction import RULPredictionResult
from src.prognostics.types import PrognosticStatus
from src.prognostics.uncertainty.engine import UncertaintyEvaluationResult
from src.prognostics.uncertainty.evidence import EvidenceAssessment
from src.prognostics.uncertainty.types import EvidenceStrength, UncertaintyStatus


class EvaluationValidityEvaluator:
    """Pure, stateless evaluator for prognostic validity and limitation auditing."""

    @classmethod
    def evaluate_validity(
        cls,
        prediction: Optional[RULPredictionResult] = None,
        eol_assessment: Optional[EOLAssessment] = None,
        uncertainty: Optional[UncertaintyEvaluationResult] = None,
        evidence: Optional[EvidenceAssessment] = None,
    ) -> tuple[EvaluationStatus, EvaluationValidity]:
        """Evaluates overall EvaluationStatus and detailed EvaluationValidity."""
        limitations: list[str] = []
        notes: list[str] = []

        # 1. Inspect EOL Validity
        eol_valid = True
        if eol_assessment is not None:
            if eol_assessment.eol_state == EOLState.INVALID:
                eol_valid = False
                limitations.append(
                    f"EOL criterion is invalid or incompatible: {eol_assessment.diagnostic_message}"
                )
            elif eol_assessment.eol_state == EOLState.INDETERMINATE:
                limitations.append("Current system degradation value is indeterminate relative to EOL.")
            elif eol_assessment.eol_state == EOLState.ALREADY_REACHED:
                notes.append("System degradation currently satisfies or exceeds configured EOL boundary.")

        # 2. Inspect Prediction Status & Data Quality
        pred_status = prediction.status if prediction else PrognosticStatus.INSUFFICIENT_DATA
        pred_valid = prediction.is_valid if prediction else False

        data_quality_status = PrognosticStatus.VALID
        history_status = PrognosticStatus.VALID
        domain_status = PrognosticStatus.VALID

        if pred_status == PrognosticStatus.DATA_QUALITY_FAILED:
            data_quality_status = PrognosticStatus.DATA_QUALITY_FAILED
            limitations.append(
                f"Prediction failed data quality validation: {prediction.diagnostic_message if prediction else ''}"
            )
        elif pred_status == PrognosticStatus.INSUFFICIENT_HISTORY:
            history_status = PrognosticStatus.INSUFFICIENT_HISTORY
            limitations.append(
                f"Historical observation window insufficient for projection: {prediction.diagnostic_message if prediction else ''}"
            )
        elif pred_status == PrognosticStatus.INSUFFICIENT_DATA:
            data_quality_status = PrognosticStatus.INSUFFICIENT_DATA
            limitations.append("Required degradation or domain channels missing.")
        elif pred_status == PrognosticStatus.OUT_OF_DOMAIN:
            domain_status = PrognosticStatus.OUT_OF_DOMAIN
            limitations.append(
                f"Trajectory rate of change or operating conditions are out-of-domain: {prediction.diagnostic_message if prediction else ''}"
            )

        # 3. Inspect Uncertainty Availability
        unc_status = uncertainty.status if uncertainty else UncertaintyStatus.UNDEFINED
        if unc_status in (
            UncertaintyStatus.UNDEFINED,
            UncertaintyStatus.INSUFFICIENT_EVIDENCE,
            UncertaintyStatus.COMBINATION_UNAVAILABLE,
        ):
            limitations.append(
                f"Statistical uncertainty is limited or undefined ({unc_status.value})."
            )
        elif unc_status == UncertaintyStatus.DETERMINISTIC_ONLY:
            notes.append("Point estimate without quantified statistical dispersion.")

        # 4. Inspect Evidence Strength
        ev_strength = evidence.overall_strength if evidence else EvidenceStrength.INSUFFICIENT
        if ev_strength in (EvidenceStrength.INSUFFICIENT, EvidenceStrength.VERY_WEAK, EvidenceStrength.WEAK):
            limitations.append(f"Observational evidence strength is {ev_strength.value}.")
        else:
            notes.append(f"Observational evidence strength is {ev_strength.value}.")

        # 5. Resolve Top-Level EvaluationStatus
        # Priority order of blocking conditions:
        if not eol_valid:
            eval_status = EvaluationStatus.INVALID_EOL_CRITERION
        elif pred_status == PrognosticStatus.DATA_QUALITY_FAILED:
            eval_status = EvaluationStatus.DATA_QUALITY_FAILED
        elif pred_status == PrognosticStatus.INSUFFICIENT_DATA:
            eval_status = EvaluationStatus.INSUFFICIENT_DATA
        elif pred_status == PrognosticStatus.INSUFFICIENT_HISTORY:
            eval_status = EvaluationStatus.INSUFFICIENT_HISTORY
        elif pred_status == PrognosticStatus.OUT_OF_DOMAIN:
            eval_status = EvaluationStatus.OUT_OF_DOMAIN
        elif not pred_valid:
            eval_status = EvaluationStatus.INDETERMINATE
        else:
            # Prediction is VALID
            if limitations:
                eval_status = EvaluationStatus.VALID_WITH_LIMITATIONS
            else:
                eval_status = EvaluationStatus.VALID

        is_usable = eval_status in (EvaluationStatus.VALID, EvaluationStatus.VALID_WITH_LIMITATIONS)

        validity = EvaluationValidity(
            data_quality=data_quality_status,
            history_sufficiency=history_status,
            domain_validity=domain_status,
            eol_validity=eol_valid,
            prediction_validity=pred_valid,
            uncertainty_availability=unc_status,
            evidence_strength=ev_strength,
            limitations=tuple(limitations),
            diagnostic_notes=tuple(notes),
            is_usable_for_decision=is_usable,
        )

        return eval_status, validity
