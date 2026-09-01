"""Domain Entities for the Universal Battery Domain.

Defines rich domain entities (Cell, Module, Pack, System) representing
physical and structural battery assemblies with strict invariant enforcement.
"""

from dataclasses import dataclass, field
from typing import Sequence, Tuple

from src.domain.battery.enums import (
    BatteryHealthState,
    BatteryOperationalState,
)
from src.domain.battery.validation import validate_battery_identifier
from src.domain.battery.value_objects import (
    BatteryIdentification,
    CellConfiguration,
    ModuleConfiguration,
    PackConfiguration,
)
from src.domain.exceptions import (
    DomainInvariantViolationError,
    InvalidModuleConfigurationError,
    InvalidPackConfigurationError,
)


@dataclass(frozen=True)
class BatteryCell:
    """Fundamental electrochemical cell entity with structural indexing."""

    cell_index: int
    config: CellConfiguration

    def __post_init__(self) -> None:
        if self.cell_index < 0:
            raise DomainInvariantViolationError(
                f"cell_index must be a non-negative integer, got {self.cell_index}.",
                details={"cell_index": self.cell_index},
            )

    @property
    def cell_id(self) -> str:
        """Returns the unique configuration ID of the cell."""
        return self.config.cell_id

    @property
    def nominal_voltage_v(self) -> float:
        """Returns the nominal voltage of the cell in Volts."""
        return self.config.nominal_voltage_v

    @property
    def nominal_capacity_ah(self) -> float:
        """Returns the nominal capacity of the cell in Ampere-hours."""
        return self.config.nominal_capacity_ah


@dataclass(frozen=True)
class BatteryModule:
    """Intermediate module entity containing a structured array of cells."""

    module_index: int
    config: ModuleConfiguration
    cells: Tuple[BatteryCell, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.module_index < 0:
            raise InvalidModuleConfigurationError(
                f"module_index must be non-negative, got {self.module_index}.",
                details={"module_index": self.module_index},
            )
        if self.cells:
            expected_cells = self.config.topology.total_cells
            if len(self.cells) != expected_cells:
                raise InvalidModuleConfigurationError(
                    f"Module {self.config.module_id} declared {expected_cells} cells, "
                    f"but contains {len(self.cells)} cell instances.",
                    details={
                        "module_id": self.config.module_id,
                        "expected_cells": expected_cells,
                        "actual_cells": len(self.cells),
                    },
                )

    @classmethod
    def create_with_cells(
        cls,
        module_index: int,
        config: ModuleConfiguration,
    ) -> "BatteryModule":
        """Factory method constructing a module with populated cell entities."""
        cells = tuple(
            BatteryCell(cell_index=i, config=config.cell_config)
            for i in range(config.topology.total_cells)
        )
        return cls(module_index=module_index, config=config, cells=cells)

    @property
    def total_cells(self) -> int:
        """Total number of cells in this module."""
        return self.config.topology.total_cells

    @property
    def module_id(self) -> str:
        """Module identifier string."""
        return self.config.module_id


@dataclass(frozen=True)
class BatteryPack:
    """Top-level physical battery pack entity with structural hierarchy."""

    identification: BatteryIdentification
    configuration: PackConfiguration
    modules: Tuple[BatteryModule, ...]

    def __post_init__(self) -> None:
        if not self.modules:
            raise InvalidPackConfigurationError(
                "Battery pack must contain at least one module.",
                details={"pack_id": self.configuration.pack_id},
            )
        total_cells_in_modules = sum(m.total_cells for m in self.modules)
        expected_cells = self.configuration.topology.total_cells
        if total_cells_in_modules != expected_cells:
            raise InvalidPackConfigurationError(
                f"Pack topology declares {expected_cells} total cells, but sum of "
                f"module cells is {total_cells_in_modules}.",
                details={
                    "pack_id": self.configuration.pack_id,
                    "declared_cells": expected_cells,
                    "module_cell_sum": total_cells_in_modules,
                },
            )

    @classmethod
    def create_monolithic_pack(
        cls,
        identification: BatteryIdentification,
        configuration: PackConfiguration,
        cell_config: CellConfiguration,
    ) -> "BatteryPack":
        """Creates a pack containing a single unified module with all cells populated."""
        module_config = ModuleConfiguration(
            module_id=f"{configuration.pack_id}_mod0",
            topology=configuration.topology,
            cell_config=cell_config,
            nominal_voltage_v=configuration.electrical_ratings.nominal_voltage_v,
            nominal_capacity_ah=configuration.electrical_ratings.nominal_capacity_ah,
        )
        single_module = BatteryModule.create_with_cells(module_index=0, config=module_config)
        return cls(
            identification=identification,
            configuration=configuration,
            modules=(single_module,),
        )

    @property
    def pack_id(self) -> str:
        """Unique pack identifier."""
        return self.configuration.pack_id

    @property
    def total_cell_count(self) -> int:
        """Total number of individual cells across all modules in the pack."""
        return self.configuration.topology.total_cells

    @property
    def total_module_count(self) -> int:
        """Total number of modules in the pack."""
        return len(self.modules)

    @property
    def series_count(self) -> int:
        """Total series string count."""
        return self.configuration.topology.series_count

    @property
    def parallel_count(self) -> int:
        """Total parallel string count."""
        return self.configuration.topology.parallel_count

    @property
    def nominal_voltage_v(self) -> float:
        """Pack nominal voltage in Volts."""
        return self.configuration.electrical_ratings.nominal_voltage_v

    @property
    def nominal_capacity_ah(self) -> float:
        """Pack nominal capacity in Ampere-hours."""
        return self.configuration.electrical_ratings.nominal_capacity_ah

    @property
    def nominal_energy_wh(self) -> float:
        """Pack nominal energy capacity in Watt-hours."""
        return self.configuration.electrical_ratings.nominal_energy_wh

    def get_module(self, index: int) -> BatteryModule:
        """Retrieves a module by its zero-based index."""
        if not (0 <= index < len(self.modules)):
            raise DomainInvariantViolationError(
                f"Module index {index} out of range [0, {len(self.modules) - 1}].",
                details={"index": index, "pack_id": self.pack_id},
            )
        return self.modules[index]


@dataclass(frozen=True)
class BatterySystem:
    """Aggregate domain root representing an integrated multi-pack energy storage system."""

    system_id: str
    system_name: str
    packs: Tuple[BatteryPack, ...]
    operational_state: BatteryOperationalState = BatteryOperationalState.UNINITIALIZED
    health_state: BatteryHealthState = BatteryHealthState.HEALTHY

    def __post_init__(self) -> None:
        validate_battery_identifier(self.system_id, "system_id")
        if not isinstance(self.system_name, str) or not self.system_name.strip():
            raise DomainInvariantViolationError(
                "system_name must be a non-empty string.",
                details={"system_id": self.system_id},
            )
        if not self.packs:
            raise DomainInvariantViolationError(
                "BatterySystem must contain at least one BatteryPack.",
                details={"system_id": self.system_id},
            )

    @property
    def total_pack_count(self) -> int:
        """Total number of packs in the system."""
        return len(self.packs)

    @property
    def total_cell_count(self) -> int:
        """Total count of cells across all constituent packs."""
        return sum(p.total_cell_count for p in self.packs)

    @property
    def total_nominal_energy_wh(self) -> float:
        """Total aggregated nominal energy capacity in Watt-hours."""
        return sum(p.nominal_energy_wh for p in self.packs)

    def get_pack(self, index: int) -> BatteryPack:
        """Retrieves a pack by its zero-based index."""
        if not (0 <= index < len(self.packs)):
            raise DomainInvariantViolationError(
                f"Pack index {index} out of range [0, {len(self.packs) - 1}].",
                details={"index": index, "system_id": self.system_id},
            )
        return self.packs[index]
