"""Configuration and Portfolio Containers for Prognostic Pipeline Orchestration.

Defines immutable, strongly-typed configuration models and multi-mechanism EOL portfolios.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Sequence

from src.prognostics.estimators.base import EstimatorConfig
from src.prognostics.pipeline.types import LimitingResolutionStrategy
from src.prognostics.prediction import EOLDefinition
from src.prognostics.uncertainty.engine import UncertaintyEngineConfig


@dataclass(frozen=True)
class EOLPortfolio:
    """Immutable portfolio of multi-mechanism End-of-Life degradation criteria.

    Enforces strictly unique criterion IDs and non-empty criteria sequences.
    """

    portfolio_id: str
    name: str
    criteria: Sequence[EOLDefinition]
    description: Optional[str] = None
    version: str = "1.0.0"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.portfolio_id or not isinstance(self.portfolio_id, str):
            raise ValueError("portfolio_id must be a non-empty string.")
        if not self.name or not isinstance(self.name, str):
            raise ValueError("name must be a non-empty string.")
        if not self.version or not isinstance(self.version, str):
            raise ValueError("version must be a non-empty string.")

        if not self.criteria:
            raise ValueError("EOLPortfolio must contain at least one EOLDefinition.")

        crit_ids: set[str] = set()
        for c in self.criteria:
            if not isinstance(c, EOLDefinition):
                raise TypeError(f"Expected EOLDefinition in criteria, got {type(c).__name__}.")
            if c.criterion_id in crit_ids:
                raise ValueError(
                    f"Duplicate criterion_id '{c.criterion_id}' in portfolio '{self.portfolio_id}'."
                )
            crit_ids.add(c.criterion_id)
        object.__setattr__(self, "criteria", tuple(self.criteria))

    def to_dict(self) -> dict[str, Any]:
        """Serializes EOL portfolio to dictionary."""
        return {
            "portfolio_id": self.portfolio_id,
            "name": self.name,
            "criteria": [c.to_dict() for c in self.criteria],
            "description": self.description,
            "version": self.version,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class PrognosticPipelineConfig:
    """Immutable configuration options governing multi-criterion prognostic assessment."""

    resolution_strategy: LimitingResolutionStrategy = LimitingResolutionStrategy.SHORTEST_RUL
    extract_features: bool = True
    estimator_config: Optional[EstimatorConfig] = None
    uncertainty_config: Optional[UncertaintyEngineConfig] = None
    allow_cross_domain_fallback_to_priority: bool = False
    custom_parameters: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.resolution_strategy, LimitingResolutionStrategy):
            raise TypeError(
                f"Expected LimitingResolutionStrategy, got {type(self.resolution_strategy).__name__}."
            )
        if self.estimator_config is not None and not isinstance(self.estimator_config, EstimatorConfig):
            raise TypeError(
                f"Expected EstimatorConfig, got {type(self.estimator_config).__name__}."
            )
        if self.uncertainty_config is not None and not isinstance(
            self.uncertainty_config, UncertaintyEngineConfig
        ):
            raise TypeError(
                f"Expected UncertaintyEngineConfig, got {type(self.uncertainty_config).__name__}."
            )

    def to_dict(self) -> dict[str, Any]:
        """Serializes pipeline configuration to dictionary."""
        return {
            "resolution_strategy": self.resolution_strategy.value,
            "extract_features": self.extract_features,
            "estimator_config": self.estimator_config.to_dict() if self.estimator_config else None,
            "uncertainty_config": (
                self.uncertainty_config.to_dict() if self.uncertainty_config else None
            ),
            "allow_cross_domain_fallback_to_priority": self.allow_cross_domain_fallback_to_priority,
            "custom_parameters": dict(self.custom_parameters),
        }
