"""Unit tests for Model Configuration Schemas."""

import unittest

from src.schemas.exceptions import (
    ConfigurationValidationError,
    InvalidModelConfigurationError,
    SchemaVersionMismatchError,
)
from src.schemas.model_profile import (
    ECMParametersSchema,
    ModelConfigurationSchema,
    SamplingConfigSchema,
)


class TestModelProfileSchema(unittest.TestCase):
    """Unit tests for declarative battery model configuration schemas."""

    def test_valid_ecm_2rc_model_configuration(self) -> None:
        """Create a valid ECM 2-RC model configuration."""
        sampling = SamplingConfigSchema(simulation_step_ms=100, solver_type="explicit_rk4")
        params = ECMParametersSchema(
            series_resistance_r0_mohm=25.0,
            rc1_resistance_r1_mohm=15.0,
            rc1_capacitance_c1_f=1200.0,
            rc2_resistance_r2_mohm=10.0,
            rc2_capacitance_c2_f=4500.0,
            thermal_mass_j_per_k=45.0,
            convective_heat_transfer_w_per_k=1.2,
        )
        model_cfg = ModelConfigurationSchema(
            model_id="ecm_2rc_nmc_standard",
            paradigm="ECM_2RC",
            description="Standard 2-RC model for NMC cells",
            sampling=sampling,
            parameters=params,
            custom_parameters={"coulombic_efficiency": 0.995},
        )
        self.assertEqual(model_cfg.model_id, "ecm_2rc_nmc_standard")
        self.assertEqual(model_cfg.paradigm, "ECM_2RC")
        self.assertEqual(model_cfg.parameters.series_resistance_r0_mohm, 25.0)

    def test_model_to_dict_serialization(self) -> None:
        """Verify model serialization to dictionary."""
        model_cfg = ModelConfigurationSchema(
            model_id="ecm_1rc_fast",
            paradigm="ECM_1RC",
        )
        data = model_cfg.to_dict()
        self.assertEqual(data["schema_version"], "1.0")
        self.assertEqual(data["model_configuration"]["model_id"], "ecm_1rc_fast")
        self.assertEqual(data["model_configuration"]["paradigm"], "ECM_1RC")

    def test_invalid_paradigm_raises(self) -> None:
        """Unknown or unvetted model paradigm must fail."""
        with self.assertRaises(InvalidModelConfigurationError):
            ModelConfigurationSchema(
                model_id="invalid_model",
                paradigm="QUANTUM_TELEPORTATION_MODEL",
            )

    def test_unsupported_schema_version_raises(self) -> None:
        """Unsupported schema version must fail."""
        with self.assertRaises(SchemaVersionMismatchError):
            ModelConfigurationSchema(
                schema_version="3.0",
                model_id="model_v3",
                paradigm="ECM_1RC",
            )

    def test_invalid_parameters_raise(self) -> None:
        """Negative resistance or invalid time step must fail."""
        with self.assertRaises(ConfigurationValidationError):
            ECMParametersSchema(series_resistance_r0_mohm=-5.0)

        with self.assertRaises(ConfigurationValidationError):
            SamplingConfigSchema(simulation_step_ms=0)


if __name__ == "__main__":
    unittest.main()
