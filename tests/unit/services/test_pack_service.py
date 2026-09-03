"""Unit tests for PackManagementService."""

import unittest

from src.domain.battery.entities import BatteryPack
from src.domain.battery.enums import BatteryChemistry, CellFormFactor
from src.domain.battery.value_objects import (
    BatteryIdentification,
    BatteryTopology,
    CellConfiguration,
    ElectricalRatings,
    PackConfiguration,
    ThermalLimits,
)
from src.services.exceptions import DuplicateEntityError, PackNotFoundError
from src.services.pack_service import PackManagementService


class TestPackManagementService(unittest.TestCase):
    """Test suite verifying battery pack registration, profile loading, and registry queries."""

    def setUp(self) -> None:
        self.service = PackManagementService()

        # Helper test pack
        self.ident = BatteryIdentification(
            identifier="pack_alpha",
            display_name="TwinVolt LFP 1S Pack",
        )
        self.cell_cfg = CellConfiguration(
            cell_id="cell_lfp_2500",
            chemistry=BatteryChemistry.LFP,
            form_factor=CellFormFactor.CYLINDRICAL,
            nominal_voltage_v=3.2,
            min_voltage_v=2.5,
            max_voltage_v=3.65,
            nominal_capacity_ah=2.5,
        )
        self.ratings = ElectricalRatings(
            nominal_voltage_v=3.2,
            min_voltage_v=2.5,
            max_voltage_v=3.65,
            nominal_capacity_ah=2.5,
            nominal_energy_wh=8.0,
            max_continuous_charge_current_a=2.5,
            max_continuous_discharge_current_a=5.0,
            peak_charge_current_a=5.0,
            peak_discharge_current_a=10.0,
        )
        self.thermal = ThermalLimits(
            min_charge_temp_c=0.0,
            max_charge_temp_c=45.0,
            min_discharge_temp_c=-20.0,
            max_discharge_temp_c=60.0,
            warning_temp_c=60.0,
            critical_temp_c=80.0,
        )
        self.pack_cfg = PackConfiguration(
            pack_id="pack_alpha",
            topology=BatteryTopology(series_count=1, parallel_count=1),
            electrical_ratings=self.ratings,
            thermal_limits=self.thermal,
        )
        self.pack = BatteryPack.create_monolithic_pack(
            identification=self.ident,
            configuration=self.pack_cfg,
            cell_config=self.cell_cfg,
        )

    def test_register_and_get_pack(self) -> None:
        """Registering a BatteryPack allows retrieval by identifier."""
        registered = self.service.register_pack(self.pack)
        self.assertEqual(registered.pack_id, "pack_alpha")
        self.assertEqual(self.service.count, 1)
        self.assertTrue(self.service.exists("pack_alpha"))

        retrieved = self.service.get_pack("pack_alpha")
        self.assertEqual(retrieved.pack_id, "pack_alpha")
        self.assertEqual(retrieved.total_cell_count, 1)

    def test_duplicate_registration_raises_unless_overwrite(self) -> None:
        """Registering duplicate pack_id raises DuplicateEntityError unless overwrite is True."""
        self.service.register_pack(self.pack)

        with self.assertRaises(DuplicateEntityError):
            self.service.register_pack(self.pack)

        # Allowed with overwrite=True
        updated_pack = self.service.register_pack(self.pack, overwrite=True)
        self.assertEqual(updated_pack.pack_id, "pack_alpha")
        self.assertEqual(self.service.count, 1)

    def test_get_nonexistent_pack_raises_not_found(self) -> None:
        """Retrieving unregistered pack raises PackNotFoundError."""
        with self.assertRaises(PackNotFoundError):
            self.service.get_pack("nonexistent_pack")

    def test_create_pack_from_dict_profile(self) -> None:
        """Loading a dictionary profile materializes and registers a valid BatteryPack."""
        profile_dict = {
            "schema_version": "1.0",
            "profile_id": "profile_lfp_test",
            "display_name": "LFP Test Profile",
            "chemistry": "LFP",
            "topology": {"series_count": 4, "parallel_count": 2},
            "cell_profile": {
                "cell_id": "cell_lfp",
                "chemistry": "LFP",
                "form_factor": "CYLINDRICAL",
                "nominal_voltage_v": 3.2,
                "min_voltage_v": 2.5,
                "max_voltage_v": 3.65,
                "nominal_capacity_ah": 2.5,
            },
            "ratings": {
                "nominal_pack_voltage_v": 12.8,
                "nominal_cell_voltage_v": 3.2,
                "nominal_capacity_ah": 5.0,
                "nominal_energy_wh": 64.0,
            },
            "voltage_limits": {
                "cell_min_cutoff_v": 2.5,
                "cell_max_cutoff_v": 3.65,
                "pack_min_cutoff_v": 10.0,
                "pack_max_cutoff_v": 14.6,
            },
            "current_limits": {
                "max_continuous_charge_a": 5.0,
                "max_continuous_discharge_a": 10.0,
                "peak_pulse_discharge_a": 20.0,
            },
            "thermal_limits": {
                "min_charge_temp_c": 0.0,
                "max_charge_temp_c": 45.0,
                "min_discharge_temp_c": -20.0,
                "max_discharge_temp_c": 60.0,
                "thermal_warning_temp_c": 60.0,
                "critical_thermal_runaway_temp_c": 80.0,
            },
        }

        pack = self.service.create_pack_from_profile(profile_dict)
        self.assertEqual(pack.pack_id, "profile_lfp_test")
        self.assertEqual(pack.series_count, 4)
        self.assertEqual(pack.parallel_count, 2)
        self.assertEqual(pack.total_cell_count, 8)
        self.assertTrue(self.service.exists("profile_lfp_test"))

    def test_list_delete_and_clear_packs(self) -> None:
        """Listing, deleting, and clearing packs operates correctly."""
        self.service.register_pack(self.pack)
        packs = self.service.list_packs()
        self.assertEqual(len(packs), 1)
        self.assertEqual(packs[0].pack_id, "pack_alpha")

        # Delete
        self.assertTrue(self.service.delete_pack("pack_alpha"))
        self.assertFalse(self.service.delete_pack("pack_alpha"))
        self.assertEqual(self.service.count, 0)

        # Clear
        self.service.register_pack(self.pack)
        self.assertEqual(self.service.count, 1)
        self.service.clear()
        self.assertEqual(self.service.count, 0)


if __name__ == "__main__":
    unittest.main()
