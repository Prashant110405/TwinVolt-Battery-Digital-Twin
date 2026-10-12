"""Prognostic Evaluation and Decision Orchestration Engine.

Orchestrates pure, immutable, and auditable prognostic evaluations combining:
- Trajectory and feature extraction (Level 6.2)
- Deterministic RUL prediction (Level 6.3)
- Analytical uncertainty & evidence auditing (Level 6.4)
- EOL boundary assessment (Level 6.5)
- Multi-dimensional validity and limitation analysis (Level 6.5)
"""

import datetime
import uuid
from typing import Any, Mapping, Optional, Sequence

from src.prognostics.estimators.base import EstimatorConfig
from src.prognostics.estimators.linear import HistoricalLinearRULEstimator
from src.prognostics.evaluation.eol import EOLEvaluator
from src.prognostics.evaluation.types import (
    EOLAssessment,
    EvaluationStatus,
    EvaluationValidity,
    PrognosticEvaluationResult,
)
from src.prognostics.evaluation.validity import EvaluationValidityEvaluator
from src.prognostics.features import DegradationFeatureSet, TrajectoryFeatureExtractor
from src.prognostics.horizon import PrognosticHorizon
from src.prognostics.prediction import EOLDefinition, RULPredictionResult
from src.prognostics.trajectory import DegradationTrajectory
from src.prognostics.uncertainty.engine import (
    PrognosticUncertaintyEngine,
    UncertaintyEngineConfig,
    UncertaintyEvaluationResult,
)


class PrognosticEvaluationEngine:
    """Stateless orchestrator for comprehensive battery prognostic evaluations.

    Strict Invariants:
    1. Pure and deterministic: Identical inputs produce equivalent evaluation results.
    2. Zero algorithm mutation: Consumes existing Level 6.3 estimators without altering mathematics.
    3. Isolated: Operates strictly on supplied immutable objects (zero live Twin mutation).
    4. Decoupled validity: Preserves valid deterministic RUL point estimates even when
       uncertainty is limited or unavailable.
    """

    def __init__(self) -> None:
        self._engine_id = "twinvolt_prognostic_evaluation_engine"
        self._version = "1.0.0"
        self._linear_estimator = HistoricalLinearRULEstimator()
        self._uncertainty_engine = PrognosticUncertaintyEngine()
        self._feature_extractor = TrajectoryFeatureExtractor()

    def evaluate(
        self,
        trajectory: DegradationTrajectory,
        eol_definition: EOLDefinition,
        horizon: Optional[PrognosticHorizon] = None,
        estimator_config: Optional[EstimatorConfig] = None,
        uncertainty_config: Optional[UncertaintyEngineConfig] = None,
        precomputed_prediction: Optional[RULPredictionResult] = None,
        extract_features: bool = False,
    ) -> PrognosticEvaluationResult:
        """Executes a structured prognostic evaluation over a degradation trajectory."""
        if not isinstance(trajectory, DegradationTrajectory):
            raise TypeError(f"Expected DegradationTrajectory, got {type(trajectory).__name__}.")
        if not isinstance(eol_definition, EOLDefinition):
            raise TypeError(f"Expected EOLDefinition, got {type(eol_definition).__name__}.")
        if precomputed_prediction is not None and not isinstance(precomputed_prediction, RULPredictionResult):
            raise TypeError(f"Expected RULPredictionResult, got {type(precomputed_prediction).__name__}.")

        eval_id = f"eval_{uuid.uuid4().hex[:8]}"
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
        ts_ns = trajectory.end_timestamp_ns if trajectory.end_timestamp_ns is not None else 0

        # 1. RUL Estimation (consume pre-computed result or evaluate via locked Level 6.3 linear baseline)
        if precomputed_prediction is not None:
            prediction = precomputed_prediction
        else:
            prediction = self._linear_estimator.estimate(
                trajectory=trajectory,
                eol_definition=eol_definition,
                horizon=horizon,
                config=estimator_config,
            )

        # 2. EOL Assessment
        last_domain_val = None
        if prediction.reproducibility_metadata and "last_observation_domain_value" in prediction.reproducibility_metadata:
            last_domain_val = float(prediction.reproducibility_metadata["last_observation_domain_value"])

        eol_assessment = EOLEvaluator.evaluate_from_trajectory(
            trajectory=trajectory,
            eol_definition=eol_definition,
            rul_value=prediction.rul_value,
            last_domain_value=last_domain_val,
        )

        # 3. Uncertainty & Evidence Evaluation (Level 6.4)
        uncertainty_result: Optional[UncertaintyEvaluationResult] = None
        if prediction.is_valid:
            uncertainty_result = self._uncertainty_engine.evaluate_uncertainty(
                prediction_result=prediction,
                trajectory=trajectory,
                eol_definition=eol_definition,
                config=uncertainty_config,
            )
        else:
            # For non-valid predictions, uncertainty engine produces standard undefined container
            uncertainty_result = self._uncertainty_engine.evaluate_uncertainty(
                prediction_result=prediction,
                trajectory=trajectory,
                eol_definition=eol_definition,
                config=uncertainty_config,
            )

        evidence_assessment = uncertainty_result.evidence_assessment if uncertainty_result else None

        # 4. Optional Feature Extraction (Level 6.2)
        feature_set: Optional[DegradationFeatureSet] = None
        if extract_features:
            feature_set = self._feature_extractor.extract_features(trajectory)

        # 5. Multi-Dimensional Validity Assessment
        eval_status, validity = EvaluationValidityEvaluator.evaluate_validity(
            prediction=prediction,
            eol_assessment=eol_assessment,
            uncertainty=uncertainty_result,
            evidence=evidence_assessment,
        )

        # 6. Aggregate Diagnostic Messages
        diag_list: list[str] = []
        if prediction.diagnostic_message:
            diag_list.append(f"Prediction: {prediction.diagnostic_message}")
        if eol_assessment.diagnostic_message:
            diag_list.append(f"EOL: {eol_assessment.diagnostic_message}")
        if uncertainty_result and uncertainty_result.diagnostic_message:
            diag_list.append(f"Uncertainty: {uncertainty_result.diagnostic_message}")
        if validity.limitations:
            diag_list.extend([f"Limitation: {lim}" for lim in validity.limitations])

        # 7. Assemble Immutability and Provenance Record
        meta = {
            "evaluation_engine": self._engine_id,
            "engine_version": self._version,
            "trajectory_id": trajectory.trajectory_id,
            "observation_count": len(trajectory.observations),
            "eol_criterion_id": eol_definition.criterion_id,
            "prediction_status": prediction.status.value,
            "is_usable_for_decision": validity.is_usable_for_decision,
        }

        return PrognosticEvaluationResult(
            evaluation_id=eval_id,
            system_id=trajectory.system_id,
            evaluation_timestamp_ns=ts_ns,
            created_at_utc=now_utc,
            evaluation_status=eval_status,
            prediction=prediction,
            eol_assessment=eol_assessment,
            uncertainty=uncertainty_result,
            evidence=evidence_assessment,
            validity=validity,
            feature_set=feature_set,
            diagnostics=tuple(diag_list),
            reproducibility_metadata=meta,
        )
