"""Prognostic Uncertainty and Confidence Quantification Engine.

Orchestrates transparent, deterministic, and scientifically justified uncertainty
and evidence evaluation around Level 6.3 deterministic RUL predictions.

Strict Scientific Guarantees:
1. No fabricated uncertainty or confidence percentages.
2. No ML, Monte Carlo, bootstrap, or Bayesian approximations.
3. Strict separation of confidence intervals vs. prediction intervals.
4. Transparent multi-dimensional evidence auditing without hidden scores.
5. Operates solely on explicitly supplied immutable inputs (zero Live Twin mutation).
"""

from dataclasses import dataclass, field
import datetime
import math
from typing import Any, Mapping, Optional, Sequence, Tuple
import uuid

from src.prognostics.prediction import (
    EOLDefinition,
    PredictionUncertainty,
    RULPredictionResult,
)
from src.prognostics.trajectory import DegradationObservation, DegradationTrajectory
from src.prognostics.types import (
    EOLCriterionType,
    HorizonDomain,
    PrognosticStatus,
    UncertaintyType,
)
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
from src.prognostics.uncertainty.propagation import (
    RULPropagationResult,
    RULUncertaintyPropagator,
)
from src.prognostics.uncertainty.trajectory import (
    OLSTrendUncertaintyEvaluator,
    TrajectoryTrendStatistics,
)
from src.prognostics.uncertainty.types import (
    UncertaintyBound,
    UncertaintyComponent,
    UncertaintyIntervalType,
    UncertaintySourceCategory,
    UncertaintyStatus,
)


@dataclass(frozen=True)
class UncertaintyEngineConfig:
    """Configuration options governing uncertainty and confidence quantification."""

    confidence_level: Optional[float] = None  # e.g. 0.95 for 95% confidence bounds
    assume_independent_sources: bool = True
    target_interval_type: UncertaintyIntervalType = UncertaintyIntervalType.CONFIDENCE_INTERVAL
    evidence_config: Optional[EvidenceEvaluatorConfig] = None
    custom_parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.confidence_level is not None:
            if (
                not isinstance(self.confidence_level, (int, float))
                or math.isnan(self.confidence_level)
                or math.isinf(self.confidence_level)
                or self.confidence_level <= 0.0
                or self.confidence_level >= 1.0
            ):
                raise ValueError(f"confidence_level must be in (0, 1), got {self.confidence_level}.")
        if not isinstance(self.target_interval_type, UncertaintyIntervalType):
            raise TypeError(f"Expected UncertaintyIntervalType, got {type(self.target_interval_type).__name__}.")

    def to_dict(self) -> dict[str, Any]:
        """Serializes uncertainty engine configuration to dictionary."""
        return {
            "confidence_level": (
                round(float(self.confidence_level), 4) if self.confidence_level is not None else None
            ),
            "assume_independent_sources": self.assume_independent_sources,
            "target_interval_type": self.target_interval_type.value,
            "evidence_config": self.evidence_config.to_dict() if self.evidence_config else None,
            "custom_parameters": dict(self.custom_parameters),
        }


@dataclass(frozen=True)
class UncertaintyEvaluationResult:
    """Comprehensive, immutable prognostic uncertainty and evidence report."""

    evaluation_id: str
    prediction_id: str
    created_at_utc: str
    status: UncertaintyStatus
    prediction_uncertainty: PredictionUncertainty
    rul_value: Optional[float]
    rul_unit: str
    trend_statistics: Optional[TrajectoryTrendStatistics] = None
    measurement_evaluation: Optional[MeasurementUncertaintyEvaluation] = None
    extrapolation_metrics: Optional[ExtrapolationMetrics] = None
    propagation_result: Optional[RULPropagationResult] = None
    evidence_assessment: Optional[EvidenceAssessment] = None
    components: Sequence[UncertaintyComponent] = field(default_factory=tuple)
    bounds: Optional[UncertaintyBound] = None
    diagnostic_message: Optional[str] = None
    provenance_metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def is_valid(self) -> bool:
        """Returns True if the uncertainty evaluation produced a valid statistical result."""
        return self.status in (
            UncertaintyStatus.STATISTICALLY_SUPPORTED,
            UncertaintyStatus.ESTIMATED,
            UncertaintyStatus.DETERMINISTIC_ONLY,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serializes comprehensive uncertainty evaluation report to dictionary."""
        return {
            "evaluation_id": self.evaluation_id,
            "prediction_id": self.prediction_id,
            "created_at_utc": self.created_at_utc,
            "status": self.status.value,
            "is_valid": self.is_valid,
            "rul_value": round(float(self.rul_value), 6) if self.rul_value is not None else None,
            "rul_unit": self.rul_unit,
            "prediction_uncertainty": self.prediction_uncertainty.to_dict(),
            "trend_statistics": self.trend_statistics.to_dict() if self.trend_statistics else None,
            "measurement_evaluation": (
                self.measurement_evaluation.to_dict() if self.measurement_evaluation else None
            ),
            "extrapolation_metrics": (
                self.extrapolation_metrics.to_dict() if self.extrapolation_metrics else None
            ),
            "propagation_result": self.propagation_result.to_dict() if self.propagation_result else None,
            "evidence_assessment": self.evidence_assessment.to_dict() if self.evidence_assessment else None,
            "components": [c.to_dict() for c in self.components],
            "bounds": self.bounds.to_dict() if self.bounds else None,
            "diagnostic_message": self.diagnostic_message,
            "provenance_metadata": dict(self.provenance_metadata),
        }


class PrognosticUncertaintyEngine:
    """Orchestrator for transparent battery prognostic uncertainty evaluation."""

    def __init__(self) -> None:
        self._method_id = "twinvolt_prognostic_uncertainty_engine"
        self._version = "1.0.0"

    def evaluate_uncertainty(
        self,
        prediction_result: RULPredictionResult,
        trajectory: DegradationTrajectory,
        eol_definition: EOLDefinition,
        config: Optional[UncertaintyEngineConfig] = None,
    ) -> UncertaintyEvaluationResult:
        """Evaluates uncertainty, evidence dimensions, and bounds for an RUL prediction."""
        if not isinstance(prediction_result, RULPredictionResult):
            raise TypeError(f"Expected RULPredictionResult, got {type(prediction_result).__name__}.")
        if not isinstance(trajectory, DegradationTrajectory):
            raise TypeError(f"Expected DegradationTrajectory, got {type(trajectory).__name__}.")
        if not isinstance(eol_definition, EOLDefinition):
            raise TypeError(f"Expected EOLDefinition, got {type(eol_definition).__name__}.")
        if config is not None and not isinstance(config, UncertaintyEngineConfig):
            raise TypeError(f"Expected UncertaintyEngineConfig, got {type(config).__name__}.")

        cfg = config or UncertaintyEngineConfig()
        eval_id = f"unc_eval_{uuid.uuid4().hex[:8]}"
        now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Handle Non-VALID prediction input (e.g. INSUFFICIENT_DATA, OUT_OF_DOMAIN)
        if prediction_result.status != PrognosticStatus.VALID or prediction_result.rul_value is None:
            comp = UncertaintyComponent(
                source_category=UncertaintySourceCategory.UNKNOWN,
                status=UncertaintyStatus.INSUFFICIENT_EVIDENCE,
                unit=prediction_result.rul_unit,
                description=f"Source prediction status is {prediction_result.status.value}; uncertainty undefined.",
            )
            pu = PredictionUncertainty(
                uncertainty_type=UncertaintyType.UNDEFINED,
                unit=prediction_result.rul_unit,
                description=f"Uncertainty undefined for non-valid prediction ({prediction_result.status.value}).",
            )
            return UncertaintyEvaluationResult(
                evaluation_id=eval_id,
                prediction_id=prediction_result.prediction_id,
                created_at_utc=now_utc,
                status=UncertaintyStatus.INSUFFICIENT_EVIDENCE,
                prediction_uncertainty=pu,
                rul_value=None,
                rul_unit=prediction_result.rul_unit,
                components=(comp,),
                diagnostic_message=f"Source RUL prediction was not VALID ({prediction_result.status.value}).",
            )

        rul = prediction_result.rul_value
        unit_x = prediction_result.rul_unit
        domain = prediction_result.rul_domain

        # 1. Extract Quantity Field Name from EOL Definition
        field_name, unit_y = self._map_eol_quantity(eol_definition.criterion_type)

        # 2. Extract Aligned Trajectory Coordinate Pairs
        pairs, latest_obs = self._extract_domain_series(
            trajectory=trajectory,
            field_name=field_name,
            domain=domain,
            unit_x=unit_x,
            eol_definition=eol_definition,
        )

        # 3. Trajectory & Trend Statistics
        trend_stats = OLSTrendUncertaintyEvaluator.evaluate_pairs(
            pairs=pairs,
            unit_x=unit_x,
            unit_y=unit_y,
        )

        # 4. Measurement Uncertainty Evaluation
        measurement_eval: Optional[MeasurementUncertaintyEvaluation] = None
        if latest_obs is not None:
            q = latest_obs.get_quantity(field_name)
            if q is not None:
                measurement_eval = MeasurementUncertaintyEvaluator.evaluate_quantity(q)
            elif latest_obs.metadata and "provenance" in latest_obs.metadata:
                measurement_eval = MeasurementUncertaintyEvaluator.evaluate_provenance(
                    provenance=latest_obs.metadata["provenance"],
                    nominal_value=latest_obs.get_value(field_name),
                    unit=unit_y,
                    quantity_name=field_name,
                )


        if measurement_eval is None:
            # Default unavailable measurement evaluation
            meas_comp = UncertaintyComponent(
                source_category=UncertaintySourceCategory.MEASUREMENT,
                status=UncertaintyStatus.UNDEFINED,
                unit=unit_y,
                description=f"Measurement uncertainty not provided for field '{field_name}'.",
            )
            measurement_eval = MeasurementUncertaintyEvaluation(
                availability=MeasurementUncertaintyAvailability.UNAVAILABLE_MEASUREMENT_UNCERTAINTY,
                status=UncertaintyStatus.UNDEFINED,
                representation_type=UncertaintyRepresentationType.UNAVAILABLE,
                quantity_name=field_name,
                nominal_value=latest_obs.get_value(field_name) if latest_obs else None,
                unit=unit_y,
                component=meas_comp,
                diagnostic_message="No measurement uncertainty was supplied in quantity provenance.",
            )

        # 5. Extrapolation Metrics
        delta_x = pairs[-1][0] - pairs[0][0] if len(pairs) >= 2 else 0.0
        extrapolation_metrics = ExtrapolationEvaluator.evaluate(
            observed_history_span=delta_x,
            extrapolation_distance=rul,
            sample_count=len(pairs),
            slope_standard_error=trend_stats.slope_standard_error,
            residual_standard_error=trend_stats.residual_standard_error,
            domain_unit=unit_x,
        )

        # 6. Multi-Dimensional Evidence Assessment
        evidence_assessment = EvidenceEvaluator.evaluate(
            trajectory=trajectory,
            trend_stats=trend_stats,
            extrapolation_metrics=extrapolation_metrics,
            measurement_eval=measurement_eval,
            operating_context=prediction_result.operating_context,
            config=cfg.evidence_config,
        )

        # 7. RUL Uncertainty Propagation
        deg_rate: float = 0.0
        if prediction_result.reproducibility_metadata and "degradation_rate" in prediction_result.reproducibility_metadata:
            deg_rate = float(prediction_result.reproducibility_metadata["degradation_rate"])
        elif trend_stats.slope is not None and abs(trend_stats.slope) > 0.0:
            deg_rate = abs(trend_stats.slope)

        # If system was already at EOL (RUL=0)
        if rul == 0.0:
            pu = PredictionUncertainty(
                uncertainty_type=UncertaintyType.DETERMINISTIC_NO_UNCERTAINTY,
                lower_bound=0.0,
                upper_bound=0.0,
                standard_deviation=0.0,
                unit=unit_x,
                description="System is already at or beyond EOL boundary; uncertainty is zero.",
            )
            bound = UncertaintyBound(
                lower=0.0,
                upper=0.0,
                coverage_parameter=cfg.confidence_level,
                interval_type=UncertaintyIntervalType.CONFIDENCE_INTERVAL,
                is_truncated_at_zero=False,
                constraint_description="System at EOL.",
            )
            return UncertaintyEvaluationResult(
                evaluation_id=eval_id,
                prediction_id=prediction_result.prediction_id,
                created_at_utc=now_utc,
                status=UncertaintyStatus.DETERMINISTIC_ONLY,
                prediction_uncertainty=pu,
                rul_value=0.0,
                rul_unit=unit_x,
                trend_statistics=trend_stats,
                measurement_evaluation=measurement_eval,
                extrapolation_metrics=extrapolation_metrics,
                evidence_assessment=evidence_assessment,
                components=(extrapolation_metrics.component,) if extrapolation_metrics.component else (),
                bounds=bound,
                diagnostic_message="System currently at or beyond EOL threshold.",
            )

        # Handle Prediction Interval request: strictly report UNAVAILABLE as per Correction 1
        if cfg.target_interval_type == UncertaintyIntervalType.PREDICTION_INTERVAL:
            comp_pi = UncertaintyComponent(
                source_category=UncertaintySourceCategory.COMBINED,
                status=UncertaintyStatus.UNDEFINED,
                unit=unit_x,
                description="Prediction intervals for individual future realization crossing points require stochastic diffusion degradation models not supported by deterministic baseline.",
                assumptions=("Deterministic first-order baseline does not model stochastic realization diffusion.",),
            )
            pu = PredictionUncertainty(
                uncertainty_type=UncertaintyType.UNDEFINED,
                unit=unit_x,
                description="Prediction interval for future realization is unavailable under deterministic baseline.",
            )
            return UncertaintyEvaluationResult(
                evaluation_id=eval_id,
                prediction_id=prediction_result.prediction_id,
                created_at_utc=now_utc,
                status=UncertaintyStatus.UNDEFINED,
                prediction_uncertainty=pu,
                rul_value=rul,
                rul_unit=unit_x,
                trend_statistics=trend_stats,
                measurement_evaluation=measurement_eval,
                extrapolation_metrics=extrapolation_metrics,
                evidence_assessment=evidence_assessment,
                components=(comp_pi,),
                bounds=None,
                diagnostic_message="Prediction interval unavailable: stochastic first-passage models required.",
            )

        # Analytical Propagation for Confidence / Dispersion
        propagation_result = RULUncertaintyPropagator.propagate(
            rul_value=rul,
            degradation_rate=deg_rate,
            rate_uncertainty_component=trend_stats.slope_component,
            state_uncertainty_component=measurement_eval.component,
            assume_independent=cfg.assume_independent_sources,
            confidence_level=cfg.confidence_level,
            domain_unit=unit_x,
        )

        # 8. Assemble Level 6.1 PredictionUncertainty Object
        all_comps: list[UncertaintyComponent] = []
        if trend_stats.slope_component:
            all_comps.append(trend_stats.slope_component)
        if measurement_eval.component:
            all_comps.append(measurement_eval.component)
        if extrapolation_metrics.component:
            all_comps.append(extrapolation_metrics.component)
        if propagation_result.components:
            for c in propagation_result.components:
                if c not in all_comps:
                    all_comps.append(c)

        if propagation_result.bounds is not None:
            pu_type = UncertaintyType.CONFIDENCE_BOUNDS
            pu_lower = propagation_result.bounds.lower
            pu_upper = propagation_result.bounds.upper
            pu_cov = propagation_result.bounds.coverage_parameter
            pu_std = propagation_result.propagated_standard_uncertainty
            pu_desc = (
                f"Analytically propagated {pu_cov*100:.1f}% confidence bounds "
                f"[{pu_lower:.2f}, {pu_upper:.2f}] {unit_x}."
            )
        elif propagation_result.propagated_standard_uncertainty is not None:
            pu_type = UncertaintyType.STANDARD_DEVIATION
            pu_lower = None
            pu_upper = None
            pu_cov = None
            pu_std = propagation_result.propagated_standard_uncertainty
            pu_desc = f"Analytically propagated standard deviation (sigma = {pu_std:.4f} {unit_x})."
        elif propagation_result.status == UncertaintyStatus.DETERMINISTIC_ONLY:
            pu_type = UncertaintyType.DETERMINISTIC_NO_UNCERTAINTY
            pu_lower = None
            pu_upper = None
            pu_cov = None
            pu_std = None
            pu_desc = "Deterministic point estimate without quantified statistical dispersion."
        else:
            pu_type = UncertaintyType.UNDEFINED
            pu_lower = None
            pu_upper = None
            pu_cov = None
            pu_std = None
            pu_desc = "Uncertainty undefined or insufficient input data."

        pred_unc = PredictionUncertainty(
            uncertainty_type=pu_type,
            lower_bound=pu_lower,
            upper_bound=pu_upper,
            coverage_parameter=pu_cov,
            standard_deviation=pu_std,
            unit=unit_x,
            description=pu_desc,
        )

        return UncertaintyEvaluationResult(
            evaluation_id=eval_id,
            prediction_id=prediction_result.prediction_id,
            created_at_utc=now_utc,
            status=propagation_result.status,
            prediction_uncertainty=pred_unc,
            rul_value=rul,
            rul_unit=unit_x,
            trend_statistics=trend_stats,
            measurement_evaluation=measurement_eval,
            extrapolation_metrics=extrapolation_metrics,
            propagation_result=propagation_result,
            evidence_assessment=evidence_assessment,
            components=tuple(all_comps),
            bounds=propagation_result.bounds,
            diagnostic_message="Prognostic uncertainty and evidence evaluated successfully.",
            provenance_metadata={
                "engine_version": self._version,
                "confidence_level": cfg.confidence_level,
                "evidence_strength": evidence_assessment.overall_strength.value,
            },
        )

    def _map_eol_quantity(self, criterion_type: EOLCriterionType) -> Tuple[str, str]:
        """Maps EOLCriterionType to (quantity_field_name, unit_y)."""
        if criterion_type == EOLCriterionType.CAPACITY_RETENTION_THRESHOLD:
            return ("capacity_retention_fraction", "fraction")
        elif criterion_type == EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD:
            return ("usable_capacity_ah", "Ah")
        elif criterion_type == EOLCriterionType.RESISTANCE_GROWTH_RATIO_THRESHOLD:
            return ("resistance_growth_ratio", "ratio")
        elif criterion_type == EOLCriterionType.ABSOLUTE_RESISTANCE_THRESHOLD:
            return ("internal_resistance_r0_ohm", "ohm")
        return ("usable_capacity_ah", "Ah")

    def _extract_domain_series(
        self,
        trajectory: DegradationTrajectory,
        field_name: str,
        domain: HorizonDomain,
        unit_x: str,
        eol_definition: Optional[EOLDefinition] = None,
    ) -> Tuple[list[Tuple[float, float]], Optional[DegradationObservation]]:
        """Extracts aligned (x, y) coordinate series."""
        pairs: list[Tuple[float, float]] = []
        latest_obs: Optional[DegradationObservation] = None

        eol_baseline_r0: Optional[float] = None
        if eol_definition is not None and eol_definition.metadata:
            b_val = eol_definition.metadata.get("baseline_resistance_r0_ohm") or eol_definition.metadata.get("baseline_r0_ohm")
            if isinstance(b_val, (int, float)) and b_val > 0.0:
                eol_baseline_r0 = float(b_val)

        for obs in trajectory.observations:
            y_val: Optional[float] = None
            if field_name == "resistance_growth_ratio":
                r_ratio = obs.get_value("resistance_growth_ratio")
                if r_ratio is not None:
                    y_val = r_ratio
                else:
                    r0 = obs.get_value("internal_resistance_r0_ohm")
                    r0_base = eol_baseline_r0
                    if r0_base is None and obs.metadata:
                        obs_b = obs.metadata.get("baseline_resistance_r0_ohm") or obs.metadata.get("baseline_r0_ohm")
                        if isinstance(obs_b, (int, float)) and obs_b > 0.0:
                            r0_base = float(obs_b)
                    if r0 is not None and r0_base is not None and r0_base > 0.0:
                        y_val = r0 / r0_base
            else:
                y_val = obs.get_value(field_name)

            if y_val is None:
                continue

            x_val: Optional[float] = None
            if domain == HorizonDomain.CYCLE:
                x_val = obs.get_value("equivalent_full_cycles")
            elif domain == HorizonDomain.TIME:
                u = unit_x.lower()
                if u in ("seconds", "s", "sec"):
                    x_val = obs.timestamp_ns / 1_000_000_000.0
                elif u in ("hours", "h", "hr"):
                    x_val = obs.timestamp_ns / (3600.0 * 1_000_000_000.0)
                elif u in ("weeks", "w", "week"):
                    x_val = obs.timestamp_ns / (7.0 * 86400.0 * 1_000_000_000.0)
                elif u in ("years", "y", "year"):
                    x_val = obs.timestamp_ns / (365.25 * 86400.0 * 1_000_000_000.0)
                else:
                    x_val = obs.timestamp_ns / (86400.0 * 1_000_000_000.0)
            elif domain == HorizonDomain.AMPERE_HOUR_THROUGHPUT:
                x_val = obs.get_value("discharge_throughput_ah") or obs.get_value("charge_throughput_ah")
            elif domain == HorizonDomain.WATT_HOUR_THROUGHPUT:
                x_val = obs.get_value("total_energy_throughput_wh")

            if x_val is not None:
                pairs.append((float(x_val), float(y_val)))
                latest_obs = obs

        return pairs, latest_obs
