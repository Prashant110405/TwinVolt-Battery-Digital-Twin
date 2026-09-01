"""Enumerations for the Universal Battery Domain.

Defines strongly-typed enumerations for chemistries, form factors,
and system lifecycle states.
"""

from enum import Enum


class BatteryChemistry(str, Enum):
    """Electrochemical battery chemistry classifications.

    TwinVolt is chemistry-agnostic. These enums categorize known
    electrochemical systems without hardcoding their operational physics
    into the domain model.
    """

    NMC = "NMC"                  # Lithium Nickel Manganese Cobalt Oxide
    LFP = "LFP"                  # Lithium Iron Phosphate (LiFePO4)
    LCO = "LCO"                  # Lithium Cobalt Oxide
    NCA = "NCA"                  # Lithium Nickel Cobalt Aluminum Oxide
    LTO = "LTO"                  # Lithium Titanate Oxide
    SODIUM_ION = "SODIUM_ION"    # Sodium-ion electrochemical cells
    SOLID_STATE = "SOLID_STATE"  # Solid-state electrolyte cells
    NIMH = "NIMH"                # Nickel-Metal Hydride
    LEAD_ACID = "LEAD_ACID"      # Lead-Acid (Flooded, AGM, Gel)
    OTHER = "OTHER"              # Custom or experimental chemistry


class CellFormFactor(str, Enum):
    """Physical mechanical form factors for battery cells."""

    CYLINDRICAL = "CYLINDRICAL"  # e.g., 18650, 21700, 4680
    POUCH = "POUCH"              # Flat laminated pouch cells
    PRISMATIC = "PRISMATIC"      # Rigid rectangular canned cells
    COIN = "COIN"                # Button / coin cells
    OTHER = "OTHER"              # Custom / bespoke form factors


class BatteryOperationalState(str, Enum):
    """Real-time operational states of a battery pack or digital twin."""

    UNINITIALIZED = "UNINITIALIZED"
    STANDBY = "STANDBY"
    CHARGING = "CHARGING"
    DISCHARGING = "DISCHARGING"
    BALANCING = "BALANCING"
    FAULT = "FAULT"
    SHUTDOWN = "SHUTDOWN"
    DEGRADED = "DEGRADED"


class BatteryHealthState(str, Enum):
    """Macro health and degradation classification of a battery system."""

    HEALTHY = "HEALTHY"          # SOH > 90%
    AGED = "AGED"                # 80% <= SOH <= 90%
    DEGRADED = "DEGRADED"        # 70% <= SOH < 80%
    CRITICAL = "CRITICAL"        # SOH < 70% or severe impedance growth
    END_OF_LIFE = "END_OF_LIFE"  # Below operational safety threshold
