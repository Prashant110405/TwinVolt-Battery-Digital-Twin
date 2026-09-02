"""Unit tests for Standard Chemistry Reference Catalogs and Defaults."""

import unittest

from src.domain.battery.enums import BatteryChemistry
from src.models.base import BatteryModel, OCVModel
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.exceptions import InvalidModelParametersError
from src.models.parameters.chemistry_defaults import (
    ChemistryProfile,
    get_chemistry_default_ocv_model,
    get_chemistry_default_parameters,
    get_chemistry_default_temperature_scaling,
    get_chemistry_profile,
    list_supported_default_chemistries,
)
from src.models.parameters.ocv_curve import OCVCurve
from src.models.parameters.temperature_scaling import TemperatureScaling
from src.models.types import ModelInput, ModelMetadata


class TestChemistryDefaults(unittest.TestCase):
    """Test suite verifying built-in literature reference parameter sets and OCV models."""

    def test_list_supported_default_chemistries(self) -> None:
        """Verify list of supported chemistries contains core battery technologies."""
        supported = list_supported_default_chemistries()
        self.assertIn(BatteryChemistry.NMC, supported)
        self.assertIn(BatteryChemistry.LFP, supported)
        self.assertIn(BatteryChemistry.LTO, supported)
        self.assertIn(BatteryChemistry.SODIUM_ION, supported)
        self.assertIn(BatteryChemistry.LEAD_ACID, supported)

    def test_reference_default_provenance_flag(self) -> None:
        """All built-in profiles must be explicitly flagged with is_reference_default=True."""
        for chem in list_supported_default_chemistries():
            profile = get_chemistry_profile(chem)
            self.assertTrue(profile.is_reference_default, f"{chem.value} must be tagged as reference default.")
            self.assertTrue(len(profile.source_description) > 0)

    def test_chemistry_profile_retrieval_and_properties(self) -> None:
        """Verify profile nominal properties and OCV limits across chemistries."""
        # NMC
        nmc = get_chemistry_profile("NMC")
        self.assertEqual(nmc.nominal_voltage_v, 3.7)
        self.assertAlmostEqual(nmc.create_ocv_model().v_min_v, 3.0, places=2)
        self.assertAlmostEqual(nmc.create_ocv_model().v_max_v, 4.2, places=2)

        # LFP
        lfp = get_chemistry_profile(BatteryChemistry.LFP)
        self.assertEqual(lfp.nominal_voltage_v, 3.2)
        self.assertAlmostEqual(lfp.create_ocv_model().v_min_v, 2.5, places=2)
        self.assertAlmostEqual(lfp.create_ocv_model().v_max_v, 3.65, places=2)

        # LTO
        lto = get_chemistry_profile("LTO")
        self.assertEqual(lto.nominal_voltage_v, 2.3)
        self.assertAlmostEqual(lto.create_ocv_model().v_min_v, 1.5, places=2)
        self.assertAlmostEqual(lto.create_ocv_model().v_max_v, 2.8, places=2)

        # Sodium-Ion
        na = get_chemistry_profile("SODIUM_ION")
        self.assertEqual(na.nominal_voltage_v, 3.0)

        # Lead-Acid
        pb = get_chemistry_profile("LEAD_ACID")
        self.assertEqual(pb.nominal_voltage_v, 2.0)

    def test_chemistry_default_helpers(self) -> None:
        """Verify helper functions for parameters, OCV model, and temperature scaling."""
        params_nmc = get_chemistry_default_parameters("NMC", nominal_capacity_ah=3.0)
        self.assertEqual(params_nmc.nominal_capacity_ah, 3.0)
        self.assertEqual(params_nmc.nominal_voltage_v, 3.7)

        ocv_lfp = get_chemistry_default_ocv_model("LFP")
        self.assertIsInstance(ocv_lfp, OCVModel)
        self.assertIsInstance(ocv_lfp, OCVCurve)

        scaling_lto = get_chemistry_default_temperature_scaling("LTO")
        self.assertIsInstance(scaling_lto, TemperatureScaling)
        self.assertEqual(scaling_lto.activation_energy_j_per_mol, 18000.0)

    def test_simulation_execution_across_all_supported_chemistries(self) -> None:
        """Instantiate and simulate GenericECMModel with default parameters across all chemistries."""
        chemistries = [
            BatteryChemistry.NMC,
            BatteryChemistry.LFP,
            BatteryChemistry.LTO,
            BatteryChemistry.SODIUM_ION,
            BatteryChemistry.LEAD_ACID,
        ]

        for chem in chemistries:
            meta = ModelMetadata(
                model_id=f"default_{chem.value.lower()}",
                name=f"Default {chem.value} Model",
                paradigm="ECM_DEFAULT",
            )
            params = get_chemistry_default_parameters(chem)
            ocv = get_chemistry_default_ocv_model(chem)

            model = GenericECMModel(
                metadata=meta,
                parameters=params,
                ocv_model=ocv,
            )
            self.assertIsInstance(model, BatteryModel)

            # Initialize and step
            model.initialize(soc_init=0.8, temperature_c=25.0)
            inp = ModelInput(current_a=1.0, dt_s=1.0, ambient_temperature_c=25.0)
            out = model.step(inp)

            self.assertGreater(out.terminal_voltage_v, 1.0)
            self.assertLess(out.state.soc_fraction, 0.8)
            self.assertGreaterEqual(out.heat_generation_w, 0.0)

    def test_unsupported_chemistry_raises(self) -> None:
        """Unknown or unmapped chemistry must raise InvalidModelParametersError."""
        with self.assertRaises(InvalidModelParametersError):
            get_chemistry_profile("DILITHIUM_CRYSTAL_CHEMISTRY")

        with self.assertRaises(InvalidModelParametersError):
            get_chemistry_default_parameters("UNKNOWN_CHEM")


if __name__ == "__main__":
    unittest.main()
