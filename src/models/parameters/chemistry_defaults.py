"""Universal Battery Chemistry Reference Parameters and OCV Catalogs.

Provides standardized, chemistry-specific baseline parameter sets, non-linear OCV curves,
and temperature scaling for all major electrochemical battery families.

NOTE: All default parameter catalogs in this module are standard literature/reference baselines
intended for initialization, uncalibrated modeling, and baseline simulation.
They are explicitly tagged with `is_reference_default = True` to distinguish them from
measured, experimental, or field-calibrated parameter sets.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Union

from src.domain.battery.enums import BatteryChemistry
from src.models.ecm.parameters import GenericECMParameters, RCBranchParameters
from src.models.exceptions import InvalidModelParametersError
from src.models.parameters.ocv_curve import OCVCurve
from src.models.parameters.temperature_scaling import TemperatureScaling


@dataclass(frozen=True)
class ChemistryProfile:
    """Comprehensive reference profile for a battery electrochemical chemistry."""

    chemistry: BatteryChemistry
    is_reference_default: bool = True
    source_description: str = "Standard literature reference baseline"
    nominal_capacity_ah: float = 2.2
    nominal_voltage_v: float = 3.7
    cell_mass_kg: float = 0.045
    specific_heat_capacity_j_per_kg_k: float = 1000.0
    convective_heat_transfer_w_per_k: float = 1.0
    series_resistance_r0_ohm: float = 0.025
    r1_ohm: float = 0.015
    c1_farad: float = 1200.0
    r2_ohm: Optional[float] = None
    c2_farad: Optional[float] = None
    entropic_coefficient_v_per_k: float = 0.00015
    temperature_scaling: TemperatureScaling = field(default_factory=TemperatureScaling)
    ocv_soc_grid: tuple[float, ...] = ()
    ocv_voltage_grid: tuple[float, ...] = ()

    def create_ocv_model(self, interpolation_method: str = "PCHIP") -> OCVCurve:
        """Instantiates an OCVCurve based on this chemistry profile."""
        return OCVCurve(
            soc_points=self.ocv_soc_grid,
            ocv_points_v=self.ocv_voltage_grid,
            d_ocv_d_temp_v_per_k=self.entropic_coefficient_v_per_k,
            interpolation_method=interpolation_method,
            name=f"ReferenceOCV_{self.chemistry.value}",
        )

    def create_ecm_parameters(
        self,
        nominal_capacity_ah: Optional[float] = None,
        cell_mass_kg: Optional[float] = None,
    ) -> GenericECMParameters:
        """Constructs a GenericECMParameters container configured for this chemistry."""
        cap = nominal_capacity_ah if nominal_capacity_ah is not None else self.nominal_capacity_ah
        mass = cell_mass_kg if cell_mass_kg is not None else self.cell_mass_kg

        branches = [
            RCBranchParameters(resistance_r_ohm=self.r1_ohm, capacitance_c_farad=self.c1_farad)
        ]
        if self.r2_ohm is not None and self.c2_farad is not None:
            branches.append(
                RCBranchParameters(resistance_r_ohm=self.r2_ohm, capacitance_c_farad=self.c2_farad)
            )

        return GenericECMParameters(
            nominal_capacity_ah=cap,
            nominal_voltage_v=self.nominal_voltage_v,
            cell_mass_kg=mass,
            specific_heat_capacity_j_per_kg_k=self.specific_heat_capacity_j_per_kg_k,
            convective_heat_transfer_w_per_k=self.convective_heat_transfer_w_per_k,
            series_resistance_r0_ohm=self.series_resistance_r0_ohm,
            rc_branches=tuple(branches),
            entropic_coefficient_v_per_k=self.entropic_coefficient_v_per_k,
        )


# ==============================================================================
# Canonical Chemistry Catalogs (Standard Literature Reference Baselines)
# ==============================================================================

# 1. NMC (Lithium Nickel Manganese Cobalt Oxide - High energy density, progressive voltage slope)
_NMC_SOC_GRID = (0.00, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 1.00)
_NMC_OCV_GRID = (3.00, 3.35, 3.48, 3.60, 3.68, 3.74, 3.82, 3.90, 4.00, 4.08, 4.15, 4.18, 4.20)

_NMC_PROFILE = ChemistryProfile(
    chemistry=BatteryChemistry.NMC,
    is_reference_default=True,
    source_description="Literature reference baseline for NMC (e.g. LG Chem / Panasonic 21700)",
    nominal_capacity_ah=2.5,
    nominal_voltage_v=3.7,
    cell_mass_kg=0.048,
    series_resistance_r0_ohm=0.025,
    r1_ohm=0.015,
    c1_farad=1500.0,
    r2_ohm=0.010,
    c2_farad=4500.0,
    entropic_coefficient_v_per_k=0.00018,
    temperature_scaling=TemperatureScaling(
        activation_energy_j_per_mol=25000.0,
        low_temp_resistance_multiplier=1.8,
        capacity_derating_fraction_per_k=0.006,
    ),
    ocv_soc_grid=_NMC_SOC_GRID,
    ocv_voltage_grid=_NMC_OCV_GRID,
)


# 2. LFP (Lithium Iron Phosphate - Long cycle life, distinct flat 3.28V - 3.32V plateau across 20%-80% SOC)
_LFP_SOC_GRID = (0.00, 0.05, 0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.95, 1.00)
_LFP_OCV_GRID = (2.50, 3.05, 3.18, 3.24, 3.28, 3.29, 3.295, 3.30, 3.305, 3.31, 3.32, 3.34, 3.38, 3.45, 3.65)

_LFP_PROFILE = ChemistryProfile(
    chemistry=BatteryChemistry.LFP,
    is_reference_default=True,
    source_description="Literature reference baseline for LiFePO4 (e.g. A123 26650 / CATL prismatic)",
    nominal_capacity_ah=2.3,
    nominal_voltage_v=3.2,
    cell_mass_kg=0.070,
    series_resistance_r0_ohm=0.020,
    r1_ohm=0.012,
    c1_farad=2000.0,
    r2_ohm=0.008,
    c2_farad=6000.0,
    entropic_coefficient_v_per_k=0.00008,
    temperature_scaling=TemperatureScaling(
        activation_energy_j_per_mol=30000.0,
        low_temp_resistance_multiplier=2.5,
        capacity_derating_fraction_per_k=0.009,
    ),
    ocv_soc_grid=_LFP_SOC_GRID,
    ocv_voltage_grid=_LFP_OCV_GRID,
)


# 3. LTO (Lithium Titanate Oxide - High rate, extreme low-temperature capability, 2.3V nominal)
_LTO_SOC_GRID = (0.00, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 1.00)
_LTO_OCV_GRID = (1.50, 2.05, 2.18, 2.26, 2.28, 2.29, 2.30, 2.31, 2.33, 2.36, 2.45, 2.58, 2.80)

_LTO_PROFILE = ChemistryProfile(
    chemistry=BatteryChemistry.LTO,
    is_reference_default=True,
    source_description="Literature reference baseline for LTO (e.g. Toshiba SCiB)",
    nominal_capacity_ah=2.9,
    nominal_voltage_v=2.3,
    cell_mass_kg=0.080,
    series_resistance_r0_ohm=0.010,
    r1_ohm=0.006,
    c1_farad=3500.0,
    entropic_coefficient_v_per_k=0.00010,
    temperature_scaling=TemperatureScaling(
        activation_energy_j_per_mol=18000.0,
        low_temp_resistance_multiplier=1.3,
        capacity_derating_fraction_per_k=0.003,
    ),
    ocv_soc_grid=_LTO_SOC_GRID,
    ocv_voltage_grid=_LTO_OCV_GRID,
)


# 4. SODIUM_ION (Sodium-Ion - Emerging low-cost, 3.0V nominal, broad sloping OCV curve)
_SODIUM_SOC_GRID = (0.00, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 1.00)
_SODIUM_OCV_GRID = (1.50, 2.30, 2.55, 2.78, 2.92, 3.02, 3.12, 3.24, 3.38, 3.55, 3.75, 3.88, 4.00)

_SODIUM_PROFILE = ChemistryProfile(
    chemistry=BatteryChemistry.SODIUM_ION,
    is_reference_default=True,
    source_description="Literature reference baseline for Sodium-Ion (Hard Carbon / Prussian White)",
    nominal_capacity_ah=1.5,
    nominal_voltage_v=3.0,
    cell_mass_kg=0.040,
    series_resistance_r0_ohm=0.035,
    r1_ohm=0.020,
    c1_farad=1000.0,
    entropic_coefficient_v_per_k=0.00012,
    temperature_scaling=TemperatureScaling(
        activation_energy_j_per_mol=28000.0,
        low_temp_resistance_multiplier=1.9,
        capacity_derating_fraction_per_k=0.007,
    ),
    ocv_soc_grid=_SODIUM_SOC_GRID,
    ocv_voltage_grid=_SODIUM_OCV_GRID,
)


# 5. LEAD_ACID (Lead-Acid - 2.0V/cell nominal, flooded/AGM characteristics)
_LEAD_SOC_GRID = (0.00, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00)
_LEAD_OCV_GRID = (1.75, 1.88, 1.94, 1.98, 2.01, 2.04, 2.07, 2.09, 2.11, 2.13, 2.15)

_LEAD_PROFILE = ChemistryProfile(
    chemistry=BatteryChemistry.LEAD_ACID,
    is_reference_default=True,
    source_description="Literature reference baseline for Lead-Acid (2.0V per single cell)",
    nominal_capacity_ah=50.0,
    nominal_voltage_v=2.0,
    cell_mass_kg=1.80,
    series_resistance_r0_ohm=0.008,
    r1_ohm=0.005,
    c1_farad=8000.0,
    entropic_coefficient_v_per_k=0.00020,
    temperature_scaling=TemperatureScaling(
        activation_energy_j_per_mol=35000.0,
        low_temp_resistance_multiplier=2.2,
        capacity_derating_fraction_per_k=0.010,
    ),
    ocv_soc_grid=_LEAD_SOC_GRID,
    ocv_voltage_grid=_LEAD_OCV_GRID,
)


# Registry of default chemistry catalogs
_CHEMISTRY_REGISTRY: dict[BatteryChemistry, ChemistryProfile] = {
    BatteryChemistry.NMC: _NMC_PROFILE,
    BatteryChemistry.LFP: _LFP_PROFILE,
    BatteryChemistry.LTO: _LTO_PROFILE,
    BatteryChemistry.SODIUM_ION: _SODIUM_PROFILE,
    BatteryChemistry.LEAD_ACID: _LEAD_PROFILE,
    # Chemistry mappings for variants
    BatteryChemistry.LCO: _NMC_PROFILE,
    BatteryChemistry.NCA: _NMC_PROFILE,
}


def _normalize_chemistry(chemistry: Union[BatteryChemistry, str]) -> BatteryChemistry:
    """Normalizes chemistry string or enum to BatteryChemistry."""
    if isinstance(chemistry, BatteryChemistry):
        return chemistry
    try:
        return BatteryChemistry(chemistry.upper().strip())
    except ValueError:
        raise InvalidModelParametersError(
            f"Unsupported battery chemistry '{chemistry}'. Supported: {[c.value for c in BatteryChemistry]}."
        )


def get_chemistry_profile(chemistry: Union[BatteryChemistry, str]) -> ChemistryProfile:
    """Retrieves the standard literature reference profile for a battery chemistry.

    Args:
        chemistry: BatteryChemistry enum or valid string identifier (e.g. 'NMC', 'LFP', 'LTO').

    Returns:
        ChemistryProfile containing default physical and OCV parameters.
    """
    chem_enum = _normalize_chemistry(chemistry)
    if chem_enum not in _CHEMISTRY_REGISTRY:
        raise InvalidModelParametersError(
            f"No default reference profile registered for chemistry '{chem_enum.value}'. "
            f"Available default profiles: {[c.value for c in _CHEMISTRY_REGISTRY.keys()]}."
        )
    return _CHEMISTRY_REGISTRY[chem_enum]


def get_chemistry_default_parameters(
    chemistry: Union[BatteryChemistry, str],
    nominal_capacity_ah: Optional[float] = None,
    cell_mass_kg: Optional[float] = None,
) -> GenericECMParameters:
    """Convenience helper returning standard GenericECMParameters for a battery chemistry."""
    profile = get_chemistry_profile(chemistry)
    return profile.create_ecm_parameters(
        nominal_capacity_ah=nominal_capacity_ah,
        cell_mass_kg=cell_mass_kg,
    )


def get_chemistry_default_ocv_model(
    chemistry: Union[BatteryChemistry, str],
    interpolation_method: str = "PCHIP",
) -> OCVCurve:
    """Convenience helper returning a calibrated non-linear OCVCurve model for a battery chemistry."""
    profile = get_chemistry_profile(chemistry)
    return profile.create_ocv_model(interpolation_method=interpolation_method)


def get_chemistry_default_temperature_scaling(
    chemistry: Union[BatteryChemistry, str],
) -> TemperatureScaling:
    """Convenience helper returning default TemperatureScaling for a battery chemistry."""
    profile = get_chemistry_profile(chemistry)
    return profile.temperature_scaling


def list_supported_default_chemistries() -> list[BatteryChemistry]:
    """Returns a list of all chemistries with built-in reference baseline catalogs."""
    return sorted(list(_CHEMISTRY_REGISTRY.keys()), key=lambda c: c.value)
