"""Unit tests for Mathematical Core Data Types and State Space Vectors."""

import unittest

from src.models.exceptions import (
    InvalidModelInputError,
    InvalidModelParametersError,
    InvalidModelStateError,
)
from src.models.types import (
    ModelInput,
    ModelMetadata,
    ModelOutput,
    ModelParameters,
    ModelState,
)


class TestModelTypes(unittest.TestCase):
    """Test suite verifying state vector, input, output, and parameter types."""

    # --------------------------------------------------------------------------
    # 1. ModelMetadata Tests
    # --------------------------------------------------------------------------
    def test_valid_model_metadata(self) -> None:
        """Create valid ModelMetadata."""
        meta = ModelMetadata(
            model_id="ecm_thevenin_1rc",
            name="Thevenin 1-RC Battery Model",
            paradigm="ECM_1RC",
            version="1.0.0",
        )
        self.assertEqual(meta.model_id, "ecm_thevenin_1rc")
        self.assertEqual(meta.paradigm, "ECM_1RC")
        d = meta.to_dict()
        self.assertEqual(d["model_id"], "ecm_thevenin_1rc")

    def test_invalid_model_metadata_raises(self) -> None:
        """Empty model_id or paradigm must fail."""
        with self.assertRaises(InvalidModelParametersError):
            ModelMetadata(model_id="", name="Test", paradigm="ECM_1RC")
        with self.assertRaises(InvalidModelParametersError):
            ModelMetadata(model_id="id1", name="Test", paradigm="")

    # --------------------------------------------------------------------------
    # 2. ModelState Tests
    # --------------------------------------------------------------------------
    def test_valid_model_state(self) -> None:
        """Create valid ModelState and verify immutability & with_updates."""
        state = ModelState(
            soc_fraction=0.85,
            soh_fraction=0.98,
            temperature_c=28.5,
            surface_temperature_c=27.2,
            polarization_voltages_v=(0.015, 0.005),
            hysteresis_voltage_v=0.002,
            timestamp_ns=1700000000000000000,
        )
        self.assertEqual(state.soc_fraction, 0.85)
        self.assertEqual(len(state.polarization_voltages_v), 2)

        # with_updates
        updated = state.with_updates(soc_fraction=0.84, temperature_c=29.0)
        self.assertEqual(updated.soc_fraction, 0.84)
        self.assertEqual(updated.temperature_c, 29.0)
        self.assertEqual(updated.soh_fraction, 0.98)

        # to_dict
        d = state.to_dict()
        self.assertEqual(d["soc_fraction"], 0.85)
        self.assertEqual(d["polarization_voltages_v"], [0.015, 0.005])

    def test_invalid_model_state_raises(self) -> None:
        """Out of bounds SOC, SOH, temperature, or non-finite values must fail."""
        # SOC > 1.0
        with self.assertRaises(InvalidModelStateError):
            ModelState(soc_fraction=1.05)

        # SOC < 0.0
        with self.assertRaises(InvalidModelStateError):
            ModelState(soc_fraction=-0.01)

        # SOH > 1.0
        with self.assertRaises(InvalidModelStateError):
            ModelState(soc_fraction=0.5, soh_fraction=1.2)

        # Temp <= -273.15 C
        with self.assertRaises(InvalidModelStateError):
            ModelState(soc_fraction=0.5, temperature_c=-273.16)

        # NaN / Inf
        with self.assertRaises(InvalidModelStateError):
            ModelState(soc_fraction=float("nan"))

    # --------------------------------------------------------------------------
    # 3. ModelInput Tests
    # --------------------------------------------------------------------------
    def test_valid_model_input(self) -> None:
        """Create valid ModelInput and test serialization."""
        inp = ModelInput(
            current_a=2.5,
            dt_s=0.1,
            ambient_temperature_c=25.0,
            coolant_temperature_c=20.0,
            coolant_flow_rate_m3_per_s=0.001,
            timestamp_ns=1700000000000000000,
        )
        self.assertEqual(inp.current_a, 2.5)
        self.assertEqual(inp.dt_s, 0.1)
        d = inp.to_dict()
        self.assertEqual(d["current_a"], 2.5)

    def test_invalid_model_input_raises(self) -> None:
        """Non-positive dt or invalid temperature must fail."""
        # dt <= 0
        with self.assertRaises(InvalidModelInputError):
            ModelInput(current_a=1.0, dt_s=0.0)
        with self.assertRaises(InvalidModelInputError):
            ModelInput(current_a=1.0, dt_s=-0.1)

        # Ambient temp <= -273.15
        with self.assertRaises(InvalidModelInputError):
            ModelInput(current_a=1.0, dt_s=1.0, ambient_temperature_c=-274.0)

    # --------------------------------------------------------------------------
    # 4. ModelOutput Tests
    # --------------------------------------------------------------------------
    def test_valid_model_output(self) -> None:
        """Create valid ModelOutput."""
        state = ModelState(soc_fraction=0.8)
        out = ModelOutput(
            terminal_voltage_v=3.85,
            open_circuit_voltage_v=3.90,
            state=state,
            heat_generation_w=0.45,
            internal_resistance_mohm=25.0,
        )
        self.assertEqual(out.terminal_voltage_v, 3.85)
        self.assertEqual(out.open_circuit_voltage_v, 3.90)
        d = out.to_dict()
        self.assertEqual(d["terminal_voltage_v"], 3.85)

    # --------------------------------------------------------------------------
    # 5. ModelParameters Tests
    # --------------------------------------------------------------------------
    def test_valid_model_parameters(self) -> None:
        """Create valid ModelParameters and test thermal mass computation."""
        params = ModelParameters(
            nominal_capacity_ah=2.2,
            nominal_voltage_v=3.7,
            cell_mass_kg=0.045,
            specific_heat_capacity_j_per_kg_k=1000.0,
            convective_heat_transfer_w_per_k=1.2,
        )
        self.assertEqual(params.nominal_capacity_ah, 2.2)
        self.assertAlmostEqual(params.thermal_mass_j_per_k, 45.0, places=3)
        d = params.to_dict()
        self.assertEqual(d["thermal_mass_j_per_k"], 45.0)

    def test_invalid_model_parameters_raises(self) -> None:
        """Zero/negative capacity or mass must fail."""
        with self.assertRaises(InvalidModelParametersError):
            ModelParameters(nominal_capacity_ah=0.0, nominal_voltage_v=3.7)
        with self.assertRaises(InvalidModelParametersError):
            ModelParameters(nominal_capacity_ah=2.2, nominal_voltage_v=0.0)


if __name__ == "__main__":
    unittest.main()
