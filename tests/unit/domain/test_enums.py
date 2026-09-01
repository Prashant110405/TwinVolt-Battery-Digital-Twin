"""Unit tests for Universal Battery Domain Enums."""

import unittest

from src.domain.battery.enums import (
    BatteryChemistry,
    BatteryHealthState,
    BatteryOperationalState,
    CellFormFactor,
)


class TestBatteryEnums(unittest.TestCase):
    """Tests covering domain enumeration definitions and string representations."""

    def test_battery_chemistry_members(self) -> None:
        """Verify all standard and custom chemistries are represented."""
        expected_chemistries = {
            "NMC", "LFP", "LCO", "NCA", "LTO", "SODIUM_ION",
            "SOLID_STATE", "NIMH", "LEAD_ACID", "OTHER"
        }
        actual_chemistries = {c.value for c in BatteryChemistry}
        self.assertEqual(expected_chemistries, actual_chemistries)
        self.assertEqual(BatteryChemistry.NMC.value, "NMC")
        self.assertEqual(BatteryChemistry.LFP.value, "LFP")

    def test_cell_form_factor_members(self) -> None:
        """Verify mechanical form factors."""
        expected_factors = {"CYLINDRICAL", "POUCH", "PRISMATIC", "COIN", "OTHER"}
        actual_factors = {f.value for f in CellFormFactor}
        self.assertEqual(expected_factors, actual_factors)

    def test_operational_states(self) -> None:
        """Verify all lifecycle operational states exist."""
        states = {s.value for s in BatteryOperationalState}
        self.assertIn("UNINITIALIZED", states)
        self.assertIn("CHARGING", states)
        self.assertIn("DISCHARGING", states)
        self.assertIn("BALANCING", states)
        self.assertIn("FAULT", states)

    def test_health_states(self) -> None:
        """Verify health degradation classifications."""
        health_states = {h.value for h in BatteryHealthState}
        self.assertIn("HEALTHY", health_states)
        self.assertIn("DEGRADED", health_states)
        self.assertIn("END_OF_LIFE", health_states)


if __name__ == "__main__":
    unittest.main()
