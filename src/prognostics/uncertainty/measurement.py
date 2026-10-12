"""Measurement Uncertainty Evaluation and Extraction for Battery Prognostics.

Extracts, standardizes, and evaluates measurement uncertainty strictly from explicitly
provided metrological provenance contracts. Never fabricates, infers, or estimates
sensor accuracy from hardware existence, chemistry assumptions, or generic datasheets.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Sequence

from src.prognostics.provenance import PrognosticQuantity, PrognosticValueProvenance
from src.prognostics.trajectory import DegradationObservation, DegradationTrajectory
from src.prognostics.uncertainty.types import (
    MeasurementUncertaintyAvailability,
    UncertaintyComponent,
    UncertaintyRepresentationType,
    UncertaintySourceCategory,
    UncertaintyStatus,
)


@dataclass(frozen=True)
class MeasurementUncertaintyEvaluation:
    """Immutable result of evaluating measurement uncertainty from a quantity or trajectory."""

    availability: MeasurementUncertaintyAvailability
    status: UncertaintyStatus
    representation_type: UncertaintyRepresentationType
    quantity_name: str
    nominal_value: Optional[float]
    unit: str
    standard_uncertainty: Optional[float] = None
    relative_uncertainty: Optional[float] = None
    expanded_uncertainty: Optional[float] = None
    coverage_factor: Optional[float] = None
    degrees_of_freedom: Optional[int] = None
    component: Optional[UncertaintyComponent] = None
    diagnostic_message: Optional[str] = None
    provenance_metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes measurement uncertainty evaluation to dictionary."""
        return {
            "availability": self.availability.value,
            "status": self.status.value,
            "representation_type": self.representation_type.value,
            "quantity_name": self.quantity_name,
            "nominal_value": round(float(self.nominal_value), 6) if self.nominal_value is not None else None,
            "unit": self.unit,
            "standard_uncertainty": (
                round(float(self.standard_uncertainty), 8)
                if self.standard_uncertainty is not None
                else None
            ),
            "relative_uncertainty": (
                round(float(self.relative_uncertainty), 6)
                if self.relative_uncertainty is not None
                else None
            ),
            "expanded_uncertainty": (
                round(float(self.expanded_uncertainty), 8)
                if self.expanded_uncertainty is not None
                else None
            ),
            "coverage_factor": (
                round(float(self.coverage_factor), 4) if self.coverage_factor is not None else None
            ),
            "degrees_of_freedom": self.degrees_of_freedom,
            "component": self.component.to_dict() if self.component else None,
            "diagnostic_message": self.diagnostic_message,
            "provenance_metadata": dict(self.provenance_metadata),
        }


class MeasurementUncertaintyEvaluator:
    """Deterministic evaluator for metrological measurement uncertainty.

    Strict Invariants:
    1. Operates solely on explicitly supplied PrognosticQuantity or PrognosticValueProvenance.
    2. Never assumes generic sensor accuracy, default tolerance, or chemistry-specific precision.
    3. If provenance does not contain explicit measurement uncertainty, returns UNAVAILABLE.
    """

    @classmethod
    def evaluate_quantity(
        cls,
        quantity: PrognosticQuantity,
    ) -> MeasurementUncertaintyEvaluation:
        """Evaluates measurement uncertainty from a single PrognosticQuantity container."""
        if not isinstance(quantity, PrognosticQuantity):
            raise TypeError(f"Expected PrognosticQuantity, got {type(quantity).__name__}.")

        q_name = quantity.name or "unnamed_quantity"
        val = quantity.value
        unit = quantity.unit

        if quantity.provenance is None:
            comp = UncertaintyComponent(
                source_category=UncertaintySourceCategory.MEASUREMENT,
                status=UncertaintyStatus.UNDEFINED,
                unit=unit,
                description=f"Measurement uncertainty not provided for quantity '{q_name}' (no provenance record).",
                assumptions=("No measurement uncertainty was supplied in quantity provenance.",),
            )
            return MeasurementUncertaintyEvaluation(
                availability=MeasurementUncertaintyAvailability.UNAVAILABLE_MEASUREMENT_UNCERTAINTY,
                status=UncertaintyStatus.UNDEFINED,
                representation_type=UncertaintyRepresentationType.UNAVAILABLE,
                quantity_name=q_name,
                nominal_value=val,
                unit=unit,
                component=comp,
                diagnostic_message="Quantity contains no evidentiary provenance record.",
            )

        return cls.evaluate_provenance(
            provenance=quantity.provenance,
            nominal_value=val,
            unit=unit,
            quantity_name=q_name,
        )

    @classmethod
    def evaluate_provenance(
        cls,
        provenance: PrognosticValueProvenance,
        nominal_value: Optional[float] = None,
        unit: str = "",
        quantity_name: str = "unnamed_quantity",
    ) -> MeasurementUncertaintyEvaluation:
        """Evaluates measurement uncertainty from an explicit PrognosticValueProvenance record."""
        if not isinstance(provenance, PrognosticValueProvenance):
            raise TypeError(f"Expected PrognosticValueProvenance, got {type(provenance).__name__}.")

        raw_u = provenance.measurement_uncertainty
        meta = provenance.metadata or {}

        if raw_u is None and "relative_uncertainty_fraction" not in meta and "uncertainty_absolute" not in meta:
            comp = UncertaintyComponent(
                source_category=UncertaintySourceCategory.MEASUREMENT,
                status=UncertaintyStatus.UNDEFINED,
                unit=unit,
                description=f"Measurement uncertainty not provided for quantity '{quantity_name}'.",
                assumptions=("No quantitative uncertainty field present in value provenance.",),
                metadata=meta,
            )
            return MeasurementUncertaintyEvaluation(
                availability=MeasurementUncertaintyAvailability.UNAVAILABLE_MEASUREMENT_UNCERTAINTY,
                status=UncertaintyStatus.UNDEFINED,
                representation_type=UncertaintyRepresentationType.UNAVAILABLE,
                quantity_name=quantity_name,
                nominal_value=nominal_value,
                unit=unit,
                component=comp,
                diagnostic_message="No measurement uncertainty specified in provenance record.",
                provenance_metadata=meta,
            )

        # Resolve provided uncertainty quantities
        std_u: Optional[float] = None
        rel_u: Optional[float] = None
        exp_u: Optional[float] = None
        cov_factor: Optional[float] = None
        df: Optional[int] = None
        rep_type = UncertaintyRepresentationType.STANDARD_UNCERTAINTY

        if raw_u is not None:
            std_u = float(raw_u)
            if nominal_value is not None and abs(nominal_value) > 1e-15:
                rel_u = std_u / abs(nominal_value)
            rep_type = UncertaintyRepresentationType.STANDARD_UNCERTAINTY

        # Check explicit metadata fields if supplied
        if "relative_uncertainty_fraction" in meta:
            r_val = meta["relative_uncertainty_fraction"]
            if isinstance(r_val, (int, float)) and not math.isnan(r_val) and not math.isinf(r_val) and r_val >= 0.0:
                rel_u = float(r_val)
                if std_u is None and nominal_value is not None:
                    std_u = rel_u * abs(nominal_value)
                    rep_type = UncertaintyRepresentationType.RELATIVE_FRACTION

        if "coverage_factor" in meta or "k_factor" in meta:
            k_val = meta.get("coverage_factor") or meta.get("k_factor")
            if isinstance(k_val, (int, float)) and not math.isnan(k_val) and not math.isinf(k_val) and k_val > 0.0:
                cov_factor = float(k_val)
                if std_u is not None:
                    exp_u = std_u * cov_factor
                    rep_type = UncertaintyRepresentationType.EXPANDED_UNCERTAINTY

        if "degrees_of_freedom" in meta:
            df_val = meta["degrees_of_freedom"]
            if isinstance(df_val, int) and df_val >= 0:
                df = df_val

        status = UncertaintyStatus.STATISTICALLY_SUPPORTED if df is not None else UncertaintyStatus.ESTIMATED

        assumptions = [
            f"Measurement uncertainty extracted directly from value provenance (origin={provenance.origin_type.value}).",
        ]
        if provenance.quality_rating:
            assumptions.append(f"Provenance quality rating: {provenance.quality_rating}")

        comp = UncertaintyComponent(
            source_category=UncertaintySourceCategory.MEASUREMENT,
            status=status,
            standard_uncertainty=std_u,
            relative_uncertainty=rel_u,
            expanded_uncertainty=exp_u,
            coverage_factor=cov_factor,
            degrees_of_freedom=df,
            unit=unit,
            description=f"Measurement uncertainty for quantity '{quantity_name}' from origin '{provenance.origin_type.value}'.",
            assumptions=tuple(assumptions),
            metadata=meta,
        )

        return MeasurementUncertaintyEvaluation(
            availability=MeasurementUncertaintyAvailability.PROVIDED_MEASUREMENT_UNCERTAINTY,
            status=status,
            representation_type=rep_type,
            quantity_name=quantity_name,
            nominal_value=nominal_value,
            unit=unit,
            standard_uncertainty=std_u,
            relative_uncertainty=rel_u,
            expanded_uncertainty=exp_u,
            coverage_factor=cov_factor,
            degrees_of_freedom=df,
            component=comp,
            diagnostic_message=f"Measurement uncertainty successfully resolved from {provenance.origin_type.value} provenance.",
            provenance_metadata=meta,
        )

    @classmethod
    def evaluate_trajectory_observations(
        cls,
        trajectory: DegradationTrajectory,
        field_name: str,
    ) -> Sequence[MeasurementUncertaintyEvaluation]:
        """Evaluates measurement uncertainty for each observation in a trajectory.

        Important Metrological Note:
        Preserves individual observation evaluations. Does NOT assume temporal independence
        or combine uncertainties across samples without explicit covariance/correlation models.
        """
        if not isinstance(trajectory, DegradationTrajectory):
            raise TypeError(f"Expected DegradationTrajectory, got {type(trajectory).__name__}.")

        evaluations: list[MeasurementUncertaintyEvaluation] = []
        for obs in trajectory.observations:
            q = obs.get_quantity(field_name)
            if q is not None:
                ev = cls.evaluate_quantity(q)
            else:
                val = obs.get_value(field_name)
                # Check quantity-level provenance if available in observation metadata
                prov: Optional[PrognosticValueProvenance] = None
                if obs.metadata and "provenance" in obs.metadata:
                    raw_p = obs.metadata["provenance"]
                    if isinstance(raw_p, PrognosticValueProvenance):
                        prov = raw_p

                if prov is not None:
                    ev = cls.evaluate_provenance(
                        provenance=prov,
                        nominal_value=val,
                        quantity_name=field_name,
                    )
                else:
                    # No explicit quantity provenance attached
                    comp = UncertaintyComponent(
                        source_category=UncertaintySourceCategory.MEASUREMENT,
                        status=UncertaintyStatus.UNDEFINED,
                        description=f"No measurement uncertainty attached to observation for field '{field_name}'.",
                    )
                    ev = MeasurementUncertaintyEvaluation(
                        availability=MeasurementUncertaintyAvailability.UNAVAILABLE_MEASUREMENT_UNCERTAINTY,
                        status=UncertaintyStatus.UNDEFINED,
                        representation_type=UncertaintyRepresentationType.UNAVAILABLE,
                        quantity_name=field_name,
                        nominal_value=val,
                        unit="",
                        component=comp,
                        diagnostic_message="Observation lacks explicit measurement provenance record.",
                    )
            evaluations.append(ev)

        return tuple(evaluations)

