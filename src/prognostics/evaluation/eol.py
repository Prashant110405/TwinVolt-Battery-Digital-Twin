"""End-of-Life (EOL) Assessment and Boundary Crossing Evaluation.

Evaluates current and projected degradation states relative to configured EOL criteria.
Enforces metrological unit compatibility, mathematical operator semantics, and exact
crossing determination without chemistry-specific assumptions or threshold fabrication.
"""

import math
from typing import Any, Mapping, Optional, Tuple

from src.prognostics.evaluation.types import EOLAssessment, EOLState
from src.prognostics.prediction import EOLDefinition
from src.prognostics.provenance import PrognosticQuantity
from src.prognostics.trajectory import DegradationObservation, DegradationTrajectory
from src.prognostics.types import (
    ComparisonOperator,
    EOLCriterionType,
)


class EOLEvaluator:
    """Pure, stateless evaluator for End-of-Life degradation boundaries."""

    @classmethod
    def evaluate(
        cls,
        eol_definition: EOLDefinition,
        current_quantity: Optional[PrognosticQuantity] = None,
        current_value: Optional[float] = None,
        projected_crossing_domain_value: Optional[float] = None,
        current_domain_value: Optional[float] = None,
        rul_value: Optional[float] = None,
        quantity_name: Optional[str] = None,
        unit: Optional[str] = None,
    ) -> EOLAssessment:
        """Evaluates system state relative to an explicit EOLDefinition."""
        if not isinstance(eol_definition, EOLDefinition):
            raise TypeError(f"Expected EOLDefinition, got {type(eol_definition).__name__}.")

        # 1. Resolve quantity name and unit
        q_name = quantity_name or (current_quantity.name if current_quantity else "unspecified_quantity")
        u = unit or (current_quantity.unit if current_quantity else eol_definition.unit)

        # 2. Check for invalid or non-finite threshold value in EOL definition
        thresh = eol_definition.threshold_value
        if math.isnan(thresh) or math.isinf(thresh):
            return EOLAssessment(
                eol_state=EOLState.INVALID,
                eol_definition=eol_definition,
                threshold_value=thresh,
                comparison_operator=eol_definition.comparison_operator,
                unit=u,
                quantity_name=q_name,
                is_reached=False,
                diagnostic_message="EOL threshold value is non-finite (NaN or Inf).",
            )
        if eol_definition.criterion_type in (
            EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
            EOLCriterionType.ABSOLUTE_RESISTANCE_THRESHOLD,
            EOLCriterionType.RESISTANCE_GROWTH_RATIO_THRESHOLD,
            EOLCriterionType.PEAK_POWER_THRESHOLD,
        ) and thresh <= 0.0:
            return EOLAssessment(
                eol_state=EOLState.INVALID,
                eol_definition=eol_definition,
                threshold_value=thresh,
                comparison_operator=eol_definition.comparison_operator,
                unit=u,
                quantity_name=q_name,
                is_reached=False,
                diagnostic_message=f"EOL threshold value must be strictly positive for {eol_definition.criterion_type.value}, got {thresh}.",
            )
        if eol_definition.criterion_type == EOLCriterionType.CAPACITY_RETENTION_THRESHOLD and (thresh <= 0.0 or thresh > 1.5):
            return EOLAssessment(
                eol_state=EOLState.INVALID,
                eol_definition=eol_definition,
                threshold_value=thresh,
                comparison_operator=eol_definition.comparison_operator,
                unit=u,
                quantity_name=q_name,
                is_reached=False,
                diagnostic_message=f"EOL threshold value for CAPACITY_RETENTION_THRESHOLD must be in (0, 1.5], got {thresh}.",
            )

        # 3. Resolve Current Scalar Value
        val: Optional[float] = None
        if current_quantity is not None:
            if not current_quantity.is_available or current_quantity.value is None:
                val = None
            else:
                val = current_quantity.value
        elif current_value is not None:
            val = float(current_value)

        # 4. Check for missing or indeterminate current value
        if val is None:
            return EOLAssessment(
                eol_state=EOLState.INDETERMINATE,
                eol_definition=eol_definition,
                threshold_value=thresh,
                comparison_operator=eol_definition.comparison_operator,
                unit=u,
                quantity_name=q_name,
                current_value=None,
                distance_to_eol=None,
                is_reached=False,
                diagnostic_message="Current degradation value is unavailable or unmeasured.",
            )

        # 5. Check for non-finite current value
        if math.isnan(val) or math.isinf(val):
            return EOLAssessment(
                eol_state=EOLState.INVALID,
                eol_definition=eol_definition,
                threshold_value=thresh,
                comparison_operator=eol_definition.comparison_operator,
                unit=u,
                quantity_name=q_name,
                current_value=val,
                distance_to_eol=None,
                is_reached=False,
                diagnostic_message="Current degradation value is non-finite (NaN or Inf).",
            )

        # 6. Validate Criterion Compatibility
        compatibility_error = cls._validate_criterion_compatibility(
            criterion_type=eol_definition.criterion_type,
            quantity_name=q_name,
            quantity_unit=u,
            definition_unit=eol_definition.unit,
        )
        if compatibility_error is not None:
            return EOLAssessment(
                eol_state=EOLState.INVALID,
                eol_definition=eol_definition,
                threshold_value=thresh,
                comparison_operator=eol_definition.comparison_operator,
                unit=u,
                quantity_name=q_name,
                current_value=val,
                distance_to_eol=abs(val - thresh),
                is_reached=False,
                diagnostic_message=compatibility_error,
            )

        # 7. Evaluate Relational Comparison
        is_reached = cls._evaluate_operator(
            val=val,
            threshold=thresh,
            op=eol_definition.comparison_operator,
        )
        dist_to_eol = abs(val - thresh)

        # 8. Resolve Projected Crossing Point
        proj_crossing = projected_crossing_domain_value
        if proj_crossing is None and current_domain_value is not None and rul_value is not None:
            proj_crossing = current_domain_value + rul_value

        if is_reached:
            state = EOLState.ALREADY_REACHED
            diag = (
                f"Degradation state ({val:.4f} {u}) currently satisfies EOL threshold "
                f"({eol_definition.comparison_operator.value} {thresh:.4f} {eol_definition.unit})."
            )
        else:
            if proj_crossing is not None:
                state = EOLState.PROJECTED
                diag = (
                    f"Degradation state ({val:.4f} {u}) is before EOL; projected crossing at "
                    f"domain value {proj_crossing:.2f}."
                )
            else:
                state = EOLState.NOT_REACHED
                diag = (
                    f"Degradation state ({val:.4f} {u}) is strictly before EOL threshold "
                    f"({thresh:.4f} {eol_definition.unit})."
                )

        return EOLAssessment(
            eol_state=state,
            eol_definition=eol_definition,
            threshold_value=thresh,
            comparison_operator=eol_definition.comparison_operator,
            unit=u,
            quantity_name=q_name,
            current_value=val,
            distance_to_eol=dist_to_eol,
            projected_crossing_domain_value=proj_crossing,
            is_reached=is_reached,
            diagnostic_message=diag,
            metadata={
                "criterion_type": eol_definition.criterion_type.value,
                "criterion_id": eol_definition.criterion_id,
            },
        )

    @classmethod
    def evaluate_from_trajectory(
        cls,
        trajectory: DegradationTrajectory,
        eol_definition: EOLDefinition,
        rul_value: Optional[float] = None,
        last_domain_value: Optional[float] = None,
    ) -> EOLAssessment:
        """Evaluates EOL assessment from the latest observation in a DegradationTrajectory."""
        if not isinstance(trajectory, DegradationTrajectory):
            raise TypeError(f"Expected DegradationTrajectory, got {type(trajectory).__name__}.")
        if not isinstance(eol_definition, EOLDefinition):
            raise TypeError(f"Expected EOLDefinition, got {type(eol_definition).__name__}.")

        field_name = cls._map_eol_field_name(eol_definition.criterion_type)
        if not trajectory.observations:
            return EOLAssessment(
                eol_state=EOLState.INDETERMINATE,
                eol_definition=eol_definition,
                threshold_value=eol_definition.threshold_value,
                comparison_operator=eol_definition.comparison_operator,
                unit=eol_definition.unit,
                quantity_name=field_name,
                is_reached=False,
                diagnostic_message="Degradation trajectory is empty.",
            )

        latest_obs = trajectory.observations[-1]
        q = latest_obs.get_quantity(field_name)

        # For resistance growth ratio, check computed ratio from baseline if available
        if field_name == "resistance_growth_ratio" and (q is None or not q.is_available):
            r0_q = latest_obs.get_quantity("internal_resistance_r0_ohm")
            base_r0: Optional[float] = None
            if eol_definition.metadata:
                b_val = eol_definition.metadata.get("baseline_resistance_r0_ohm") or eol_definition.metadata.get("baseline_r0_ohm")
                if isinstance(b_val, (int, float)) and b_val > 0.0:
                    base_r0 = float(b_val)
            if base_r0 is None and latest_obs.metadata:
                obs_b = latest_obs.metadata.get("baseline_resistance_r0_ohm") or latest_obs.metadata.get("baseline_r0_ohm")
                if isinstance(obs_b, (int, float)) and obs_b > 0.0:
                    base_r0 = float(obs_b)

            if r0_q is not None and r0_q.is_available and r0_q.value is not None and base_r0 is not None:
                q = PrognosticQuantity(
                    name="resistance_growth_ratio",
                    value=r0_q.value / base_r0,
                    unit="ratio",
                )

        return cls.evaluate(
            eol_definition=eol_definition,
            current_quantity=q,
            current_domain_value=last_domain_value,
            rul_value=rul_value,
            quantity_name=field_name,
            unit=eol_definition.unit,
        )

    @staticmethod
    def _evaluate_operator(val: float, threshold: float, op: ComparisonOperator) -> bool:
        """Evaluates mathematical relational comparison operator."""
        if op == ComparisonOperator.LESS_THAN_OR_EQUAL:
            return val <= threshold
        elif op == ComparisonOperator.GREATER_THAN_OR_EQUAL:
            return val >= threshold
        elif op == ComparisonOperator.LESS_THAN:
            return val < threshold
        elif op == ComparisonOperator.GREATER_THAN:
            return val > threshold
        elif op == ComparisonOperator.EQUALS:
            return math.isclose(val, threshold, rel_tol=1e-9, abs_tol=1e-12)
        return False

    @staticmethod
    def _map_eol_field_name(criterion_type: EOLCriterionType) -> str:
        """Maps an EOLCriterionType to its canonical trajectory observation field name."""
        if criterion_type == EOLCriterionType.CAPACITY_RETENTION_THRESHOLD:
            return "capacity_retention_fraction"
        elif criterion_type == EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD:
            return "usable_capacity_ah"
        elif criterion_type == EOLCriterionType.RESISTANCE_GROWTH_RATIO_THRESHOLD:
            return "resistance_growth_ratio"
        elif criterion_type == EOLCriterionType.ABSOLUTE_RESISTANCE_THRESHOLD:
            return "internal_resistance_r0_ohm"
        return "usable_capacity_ah"

    @classmethod
    def _validate_criterion_compatibility(
        cls,
        criterion_type: EOLCriterionType,
        quantity_name: str,
        quantity_unit: str,
        definition_unit: str,
    ) -> Optional[str]:
        """Validates that criterion type, quantity name, and unit are physically compatible."""
        # Check Unit Incompatibility (e.g. Ah vs Ohm, cycles vs Ah)
        incompatible_pairs = [
            ({"ah", "ampere-hours"}, {"ohm", "ohms", "\u03a9"}),
            ({"cycles", "efc"}, {"ah", "ampere-hours"}),
            ({"fraction", "%", "percent", "ratio"}, {"ah", "ohm"}),
        ]
        u1 = quantity_unit.lower().strip()
        u2 = definition_unit.lower().strip()

        for group_a, group_b in incompatible_pairs:
            if (u1 in group_a and u2 in group_b) or (u1 in group_b and u2 in group_a):
                return f"Incompatible units: quantity unit '{quantity_unit}' conflicts with EOL definition unit '{definition_unit}'."

        return None
