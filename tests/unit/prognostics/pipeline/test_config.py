"""Unit Tests for Level 6.7 Portfolio and Pipeline Configuration.

Validates:
- EOLPortfolio validation (rejection of empty criteria, duplicate IDs, invalid types)
- PrognosticPipelineConfig defaults and type checking
- Serialization of configuration containers
"""

import pytest

from src.prognostics.estimators.base import EstimatorConfig
from src.prognostics.pipeline.config import EOLPortfolio, PrognosticPipelineConfig
from src.prognostics.pipeline.types import LimitingResolutionStrategy
from src.prognostics.prediction import EOLDefinition
from src.prognostics.types import EOLCriterionType
from src.prognostics.uncertainty.engine import UncertaintyEngineConfig


def test_eol_portfolio_valid():
    crit1 = EOLDefinition(
        criterion_id="crit_soh_80",
        criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
        threshold_value=0.80,
        unit="ratio",
    )
    crit2 = EOLDefinition(
        criterion_id="crit_r0_200",
        criterion_type=EOLCriterionType.RESISTANCE_GROWTH_RATIO_THRESHOLD,
        threshold_value=2.0,
        unit="ratio",
    )

    portfolio = EOLPortfolio(
        portfolio_id="port_ev_pack",
        name="EV Pack Dual Degradation Portfolio",
        criteria=[crit1, crit2],
        description="Tracks capacity fade and internal impedance growth.",
    )

    assert portfolio.portfolio_id == "port_ev_pack"
    assert len(portfolio.criteria) == 2
    assert portfolio.criteria[0].criterion_id == "crit_soh_80"
    assert portfolio.criteria[1].criterion_id == "crit_r0_200"

    d = portfolio.to_dict()
    assert d["portfolio_id"] == "port_ev_pack"
    assert len(d["criteria"]) == 2


def test_eol_portfolio_rejects_empty():
    with pytest.raises(ValueError, match="at least one EOLDefinition"):
        EOLPortfolio(
            portfolio_id="port_empty",
            name="Empty Portfolio",
            criteria=[],
        )


def test_eol_portfolio_rejects_duplicates():
    crit1 = EOLDefinition(
        criterion_id="crit_soh_80",
        criterion_type=EOLCriterionType.CAPACITY_RETENTION_THRESHOLD,
        threshold_value=0.80,
        unit="ratio",
    )
    crit2 = EOLDefinition(
        criterion_id="crit_soh_80",  # Duplicate ID
        criterion_type=EOLCriterionType.ABSOLUTE_CAPACITY_THRESHOLD,
        threshold_value=2.0,
        unit="Ah",
    )

    with pytest.raises(ValueError, match="Duplicate criterion_id"):
        EOLPortfolio(
            portfolio_id="port_dup",
            name="Duplicate Portfolio",
            criteria=[crit1, crit2],
        )


def test_eol_portfolio_rejects_invalid_types():
    with pytest.raises(TypeError, match="Expected EOLDefinition"):
        EOLPortfolio(
            portfolio_id="port_inv",
            name="Invalid Portfolio",
            criteria=["not_an_eol_definition"],  # type: ignore[list-item]
        )


def test_pipeline_config_defaults_and_validation():
    config = PrognosticPipelineConfig()
    assert config.resolution_strategy == LimitingResolutionStrategy.SHORTEST_RUL
    assert config.extract_features is True
    assert config.allow_cross_domain_fallback_to_priority is False

    d = config.to_dict()
    assert d["resolution_strategy"] == "SHORTEST_RUL"
    assert d["extract_features"] is True

    # Invalid strategy
    with pytest.raises(TypeError, match="Expected LimitingResolutionStrategy"):
        PrognosticPipelineConfig(resolution_strategy="INVALID")  # type: ignore[arg-type]

    # Invalid estimator_config
    with pytest.raises(TypeError, match="Expected EstimatorConfig"):
        PrognosticPipelineConfig(estimator_config="invalid")  # type: ignore[arg-type]

    # Invalid uncertainty_config
    with pytest.raises(TypeError, match="Expected UncertaintyEngineConfig"):
        PrognosticPipelineConfig(uncertainty_config="invalid")  # type: ignore[arg-type]
