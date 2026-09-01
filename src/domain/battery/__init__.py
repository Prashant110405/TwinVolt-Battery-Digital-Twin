"""Universal Battery Domain Module.

Provides entities, value objects, enums, and validation functions
for generic, multi-chemistry, multi-topology battery representations.
"""

from src.domain.battery.entities import (
    BatteryCell,
    BatteryModule,
    BatteryPack,
    BatterySystem,
)
from src.domain.battery.enums import (
    BatteryChemistry,
    BatteryHealthState,
    BatteryOperationalState,
    CellFormFactor,
)
from src.domain.battery.value_objects import (
    BatteryCapacity,
    BatteryIdentification,
    BatteryTopology,
    CellConfiguration,
    ElectricalRatings,
    ModuleConfiguration,
    OperatingLimits,
    PackConfiguration,
    ThermalLimits,
)

__all__ = [
    "BatteryChemistry",
    "CellFormFactor",
    "BatteryOperationalState",
    "BatteryHealthState",
    "BatteryIdentification",
    "BatteryTopology",
    "BatteryCapacity",
    "ElectricalRatings",
    "ThermalLimits",
    "CellConfiguration",
    "ModuleConfiguration",
    "PackConfiguration",
    "OperatingLimits",
    "BatteryCell",
    "BatteryModule",
    "BatteryPack",
    "BatterySystem",
]
