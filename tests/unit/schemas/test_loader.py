"""Unit tests for Safe Battery & Model Profile Loaders."""

from pathlib import Path
import unittest

from src.schemas.exceptions import ConfigurationValidationError
from src.schemas.loader import (
    BatteryProfileLoader,
    ModelConfigurationLoader,
)


class TestProfileLoaders(unittest.TestCase):
    """Unit tests covering YAML/JSON file loaders and domain entity materialization."""

    def setUp(self) -> None:
        """Locate reference profile directories."""
        self.project_root = Path(__file__).resolve().parent.parent.parent.parent
        self.battery_config_dir = self.project_root / "config" / "battery_profiles"
        self.model_config_dir = self.project_root / "config" / "model_profiles"

    # --------------------------------------------------------------------------
    # 1. Reference Battery Profile YAML File Loading Tests
    # --------------------------------------------------------------------------
    def test_load_all_reference_battery_profiles(self) -> None:
        """Load and validate all 5 standard reference battery profiles from disk."""
        reference_files = [
            ("batt_nmc_18650_1s1p.yaml", "NMC", 1, 1),
            ("batt_nmc_3s1p_prototype.yaml", "NMC", 3, 1),
            ("batt_lfp_16s1p_bess.yaml", "LFP", 16, 1),
            ("batt_nmc_96s2p_ev.yaml", "NMC", 96, 2),
            ("batt_lto_10s1p_robot.yaml", "LTO", 10, 1),
        ]

        for filename, expected_chem, expected_s, expected_p in reference_files:
            file_path = self.battery_config_dir / filename
            with self.subTest(file=filename):
                self.assertTrue(file_path.is_file(), f"Profile file missing: {file_path}")
                schema = BatteryProfileLoader.load_from_file(file_path)
                self.assertEqual(schema.chemistry, expected_chem)
                self.assertEqual(schema.topology.series_count, expected_s)
                self.assertEqual(schema.topology.parallel_count, expected_p)

    def test_create_domain_pack_from_reference_files(self) -> None:
        """End-to-end materialization from YAML profile files directly to BatteryPack domain objects."""
        # 1S1P Single Cell Testbench
        p_1s = BatteryProfileLoader.create_domain_pack_from_file(
            self.battery_config_dir / "batt_nmc_18650_1s1p.yaml"
        )
        self.assertEqual(p_1s.total_cell_count, 1)
        self.assertEqual(p_1s.nominal_voltage_v, 3.7)

        # 3S1P Prototype Validation Bench
        p_3s = BatteryProfileLoader.create_domain_pack_from_file(
            self.battery_config_dir / "batt_nmc_3s1p_prototype.yaml"
        )
        self.assertEqual(p_3s.total_cell_count, 3)
        self.assertEqual(p_3s.nominal_voltage_v, 11.1)

        # 16S1P 48V Stationary BESS
        p_16s = BatteryProfileLoader.create_domain_pack_from_file(
            self.battery_config_dir / "batt_lfp_16s1p_bess.yaml"
        )
        self.assertEqual(p_16s.total_cell_count, 16)
        self.assertEqual(p_16s.nominal_voltage_v, 51.2)

        # 96S2P 400V EV Pack
        p_96s = BatteryProfileLoader.create_domain_pack_from_file(
            self.battery_config_dir / "batt_nmc_96s2p_ev.yaml"
        )
        self.assertEqual(p_96s.total_cell_count, 192)
        self.assertEqual(p_96s.nominal_voltage_v, 355.2)

        # 10S1P LTO Robotics Pack
        p_lto = BatteryProfileLoader.create_domain_pack_from_file(
            self.battery_config_dir / "batt_lto_10s1p_robot.yaml"
        )
        self.assertEqual(p_lto.total_cell_count, 10)
        self.assertEqual(p_lto.nominal_voltage_v, 23.0)

    # --------------------------------------------------------------------------
    # 2. Reference Model Profile Loading Tests
    # --------------------------------------------------------------------------
    def test_load_all_reference_model_profiles(self) -> None:
        """Load and validate standard ECM model configurations from disk."""
        model_files = [
            ("ecm_2rc_nmc_standard.yaml", "ECM_2RC"),
            ("ecm_1rc_lfp_fast.yaml", "ECM_1RC"),
        ]

        for filename, expected_paradigm in model_files:
            file_path = self.model_config_dir / filename
            with self.subTest(file=filename):
                self.assertTrue(file_path.is_file(), f"Model file missing: {file_path}")
                model_schema = ModelConfigurationLoader.load_from_file(file_path)
                self.assertEqual(model_schema.paradigm, expected_paradigm)

    # --------------------------------------------------------------------------
    # 3. Loader Error Handling Tests
    # --------------------------------------------------------------------------
    def test_file_not_found_raises(self) -> None:
        """Loading a non-existent file must raise ConfigurationValidationError."""
        with self.assertRaises(ConfigurationValidationError):
            BatteryProfileLoader.load_from_file("non_existent_profile.yaml")

    def test_malformed_yaml_raises(self) -> None:
        """Malformed YAML syntax must raise ConfigurationValidationError."""
        malformed_yaml = "schema_version: '1.0'\n  invalid_indentation:\n [unclosed array"
        with self.assertRaises(ConfigurationValidationError):
            BatteryProfileLoader.load_from_yaml(malformed_yaml)

    def test_malformed_json_raises(self) -> None:
        """Malformed JSON syntax must raise ConfigurationValidationError."""
        malformed_json = "{'bad_json': true,}"
        with self.assertRaises(ConfigurationValidationError):
            BatteryProfileLoader.load_from_json(malformed_json)


if __name__ == "__main__":
    unittest.main()
