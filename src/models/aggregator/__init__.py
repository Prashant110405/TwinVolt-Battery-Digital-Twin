"""Multi-Cell and Battery Pack Aggregation Subsystem.

Provides aggregated pack simulation, series-parallel current distribution,
cell-to-cell dispersion tracking, thermal hotspot detection, and passive balancing models.
"""

from src.models.aggregator.balancing_model import (
    PassiveBalancingConfig,
    PassiveBalancingModel,
)
from src.models.aggregator.pack_model import (
    BatteryPackModel,
    PackModelOutput,
)

__all__ = [
    "BatteryPackModel",
    "PackModelOutput",
    "PassiveBalancingModel",
    "PassiveBalancingConfig",
]
