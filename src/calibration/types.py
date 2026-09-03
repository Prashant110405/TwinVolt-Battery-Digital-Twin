"""Data types, configuration specifications, and immutable containers for Online Parameter Identification.

Defines strongly-typed representations for RLS configuration, parameter provenance tiers,
and immutable identified parameter snapshots.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Any, Mapping, Optional


class ParameterStateClassification(str, Enum):
    """Classification of battery model parameter origin and validation tier."""

    CONFIGURED_NOMINAL = "CONFIGURED_NOMINAL"           # Provided by static profile/YAML
    ONLINE_IDENTIFIED = "ONLINE_IDENTIFIED"             # Estimated online via streaming RLS
    VALIDATED_LAB_REFERENCE = "VALIDATED_LAB_REFERENCE" # Certified by physical laboratory characterization (HPPC/EIS)


@dataclass(frozen=True)
class RLSConfig:
    """Configuration options governing Recursive Least Squares (RLS) parameter identification."""

    # RLS core parameters
    forgetting_factor_lambda: float = 0.995             # Exponential forgetting factor in [0.98, 1.0]
    initial_covariance_diagonal: float = 100.0          # Initial diagonal variance P0
    min_covariance_trace: float = 1.0e-5                # Trace lower bound to prevent estimator "sleep"
    max_covariance_trace: float = 1.0e5                 # Trace upper bound to prevent windup
    gap_covariance_inflation_factor: float = 1.5        # Factor to inflate covariance after telemetry gap

    # Excitation & Observability gating thresholds
    min_current_a: float = 0.1                          # Minimum current magnitude for R0 observation [A]
    min_current_step_a: float = 0.2                     # Minimum current step |dI| for dynamic observation [A]
    min_current_variance: float = 0.01                  # Minimum windowed current variance Var(I) [A^2]
    excitation_window_size: int = 10                    # Window sample count for variance calculation
    min_soc: float = 0.10                               # Lower bound for non-cliff SOC regime
    max_soc: float = 0.90                               # Upper bound for non-cliff SOC regime
    max_dt_s: float = 5.0                               # Maximum allowable step interval before gap reset [s]
    max_voltage_residual_v: float = 0.15                # Outlier innovation threshold [V]

    # Physical parameter bounds
    r0_min_ohm: float = 0.0001                          # Minimum plausible series resistance [Ohm]
    r0_max_ohm: float = 1.0                             # Maximum plausible series resistance [Ohm]
    r1_min_ohm: float = 0.0001                          # Minimum plausible polarization resistance [Ohm]
    r1_max_ohm: float = 1.0                             # Maximum plausible polarization resistance [Ohm]
    c1_min_farad: float = 1.0                           # Minimum plausible polarization capacitance [F]
    c1_max_farad: float = 100000.0                      # Maximum plausible polarization capacitance [F]
    tau1_min_s: float = 0.05                            # Minimum polarization time constant [s]
    tau1_max_s: float = 300.0                           # Maximum polarization time constant [s]

    def __post_init__(self) -> None:
        if not (0.98 <= self.forgetting_factor_lambda <= 1.0):
            raise ValueError(
                f"forgetting_factor_lambda must be in [0.98, 1.0], got {self.forgetting_factor_lambda}."
            )
        if self.initial_covariance_diagonal <= 0.0:
            raise ValueError("initial_covariance_diagonal must be strictly positive.")
        if self.min_current_a <= 0.0:
            raise ValueError("min_current_a must be strictly positive.")
        if self.min_soc < 0.0 or self.max_soc > 1.0 or self.min_soc >= self.max_soc:
            raise ValueError("Invalid SOC gating range [min_soc, max_soc].")
        if self.r0_min_ohm <= 0.0 or self.r0_min_ohm >= self.r0_max_ohm:
            raise ValueError("Invalid R0 parameter bounds.")


@dataclass(frozen=True)
class IdentifiedParameterSet:
    """Snapshot of online identified battery model parameters and statistical covariance.

    Distinguishes high-confidence primary parameters (R0) from conditionally identified
    secondary parameters (R1, C1, tau1).
    """

    timestamp_ns: int
    system_id: str
    r0_ohm: float
    r1_ohm: Optional[float]
    c1_farad: Optional[float]
    tau1_s: Optional[float]
    r0_covariance: float
    coefficient_covariance_diagonal: tuple[float, ...]
    sample_count: int
    classification: ParameterStateClassification = ParameterStateClassification.ONLINE_IDENTIFIED
    gating_status: str = "ACTIVE"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serializes identified parameter set to dictionary for REST and WebSocket transport."""
        return {
            "timestamp_ns": self.timestamp_ns,
            "system_id": self.system_id,
            "r0_ohm": round(self.r0_ohm, 6),
            "r1_ohm": round(self.r1_ohm, 6) if self.r1_ohm is not None else None,
            "c1_farad": round(self.c1_farad, 4) if self.c1_farad is not None else None,
            "tau1_s": round(self.tau1_s, 4) if self.tau1_s is not None else None,
            "r0_covariance": float(self.r0_covariance),
            "coefficient_covariance_diagonal": [float(c) for c in self.coefficient_covariance_diagonal],
            "sample_count": self.sample_count,
            "classification": self.classification.value,
            "gating_status": self.gating_status,
            "metadata": dict(self.metadata),
        }
