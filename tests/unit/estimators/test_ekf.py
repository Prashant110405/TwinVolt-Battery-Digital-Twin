"""Unit tests for Extended Kalman Filter (EKF) State of Charge (SOC) Estimator."""

import math
import random
import unittest

from src.estimators.base import EstimationInput, StateEstimator
from src.estimators.ekf import ExtendedKalmanFilter
from src.estimators.exceptions import EstimatorConvergenceError, InvalidEstimatorInputError
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.ecm.parameters import GenericECMParameters, RCBranchParameters
from src.models.exceptions import InvalidModelParametersError
from src.models.parameters.chemistry_defaults import (
    get_chemistry_default_ocv_model,
    get_chemistry_default_parameters,
)
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.parameters.ocv_curve import OCVCurve
from src.models.types import ModelInput, ModelMetadata


class TestExtendedKalmanFilter(unittest.TestCase):
    """Test suite verifying EKF convergence, covariance stability, RC estimation, and invariants."""

    def setUp(self) -> None:
        """Create reference ECM parameters and EKF instances."""
        self.params_1rc = GenericECMParameters(
            nominal_capacity_ah=2.5,
            nominal_voltage_v=3.7,
            series_resistance_r0_ohm=0.025,
            rc_branches=(
                RCBranchParameters(resistance_r_ohm=0.015, capacitance_c_farad=1500.0),
            ),
        )
        self.ocv_nmc = OCVCurve(
            soc_points=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
            ocv_points_v=(3.0, 3.6, 3.75, 3.9, 4.08, 4.2),
            interpolation_method="PCHIP",
        )
        self.ekf = ExtendedKalmanFilter(
            estimator_id="ekf_nmc_1rc",
            parameters=self.params_1rc,
            ocv_model=self.ocv_nmc,
            process_noise_soc=1e-7,
            process_noise_rc=1e-6,
            measurement_noise_voltage_v2=1e-4,
            initial_covariance_soc=0.04,
        )

    # --------------------------------------------------------------------------
    # 1. Protocol & Basic Initialization
    # --------------------------------------------------------------------------
    def test_state_estimator_protocol_compliance(self) -> None:
        """Verify EKF adheres to the StateEstimator protocol."""
        self.assertIsInstance(self.ekf, StateEstimator)
        self.assertEqual(self.ekf.estimator_id, "ekf_nmc_1rc")
        self.assertEqual(self.ekf.state_dimension, 2)  # 1 (SOC) + 1 (V_RC1)

    # --------------------------------------------------------------------------
    # 2. Convergence from Large Initial Error
    # --------------------------------------------------------------------------
    def test_soc_convergence_from_initial_error(self) -> None:
        """EKF initialized at SOC=0.50 must converge to true SOC=0.80 when driven by true cell voltage."""
        # 1. True battery simulation model
        true_model = GenericECMModel(
            metadata=ModelMetadata(model_id="true_cell", name="True Cell", paradigm="ECM_1RC"),
            parameters=self.params_1rc,
            ocv_model=self.ocv_nmc,
        )
        true_model.initialize(soc_init=0.80, temperature_c=25.0)

        # 2. Initialize EKF with intentional 30% error (SOC=0.50)
        self.ekf.initialize(initial_soc=0.50, temperature_c=25.0)

        # 3. Run dynamic current pulse cycle (2.0 A discharge, 0 A rest pulses)
        random.seed(42)
        for step_idx in range(120):
            current = 2.0 if (step_idx % 20 < 10) else 0.0
            dt = 1.0

            # Step true model
            sim_out = true_model.step(ModelInput(current_a=current, dt_s=dt, ambient_temperature_c=25.0))
            v_meas = sim_out.terminal_voltage_v

            # Step EKF estimator
            est_inp = EstimationInput(current_a=current, voltage_v=v_meas, temperature_c=25.0, dt_s=dt)
            est_out = self.ekf.step(est_inp)

        # 4. Check convergence: estimated SOC must closely track true model SOC
        true_soc = true_model.state.soc_fraction
        est_soc = self.ekf.state.soc_fraction
        self.assertAlmostEqual(est_soc, true_soc, delta=0.02)
        # Covariance must have reduced significantly
        self.assertLess(self.ekf.state.soc_variance, 0.005)

    # --------------------------------------------------------------------------
    # 3. 2-RC Dual Polarization and LFP Chemistry Compatibility
    # --------------------------------------------------------------------------
    def test_ekf_with_2rc_dual_polarization(self) -> None:
        """Verify EKF works seamlessly with 2-RC Dual Polarization parameter models."""
        params_2rc = get_chemistry_default_parameters("NMC")
        ocv_nmc = get_chemistry_default_ocv_model("NMC")

        sim_model = GenericECMModel(
            metadata=ModelMetadata(model_id="sim_2rc", name="2RC Sim", paradigm="ECM_2RC"),
            parameters=params_2rc,
            ocv_model=ocv_nmc,
        )
        sim_model.initialize(soc_init=0.90, temperature_c=25.0)

        ekf_2rc = ExtendedKalmanFilter(
            estimator_id="ekf_2rc",
            parameters=params_2rc,
            ocv_model=ocv_nmc,
        )
        self.assertEqual(ekf_2rc.state_dimension, 3)  # 1 SOC + 2 RC branches

        ekf_2rc.initialize(initial_soc=0.90, temperature_c=25.0)

        for _ in range(10):
            sim_out = sim_model.step(ModelInput(current_a=1.5, dt_s=1.0, ambient_temperature_c=25.0))
            out = ekf_2rc.step(EstimationInput(current_a=1.5, voltage_v=sim_out.terminal_voltage_v, dt_s=1.0))

        self.assertAlmostEqual(out.state.soc_fraction, sim_model.state.soc_fraction, delta=0.01)
        self.assertEqual(len(out.state.polarization_voltages_v), 2)

    def test_ekf_with_lfp_chemistry(self) -> None:
        """Verify EKF stability on flat plateau LFP chemistry."""
        params_lfp = get_chemistry_default_parameters("LFP")
        ocv_lfp = get_chemistry_default_ocv_model("LFP")

        sim_model = GenericECMModel(
            metadata=ModelMetadata(model_id="sim_lfp", name="LFP Sim", paradigm="ECM_2RC"),
            parameters=params_lfp,
            ocv_model=ocv_lfp,
        )
        sim_model.initialize(soc_init=0.50, temperature_c=25.0)

        ekf_lfp = ExtendedKalmanFilter(
            estimator_id="ekf_lfp",
            parameters=params_lfp,
            ocv_model=ocv_lfp,
        )
        ekf_lfp.initialize(initial_soc=0.50, temperature_c=25.0)

        # Step through flat plateau
        for _ in range(50):
            sim_out = sim_model.step(ModelInput(current_a=1.0, dt_s=1.0, ambient_temperature_c=25.0))
            out = ekf_lfp.step(EstimationInput(current_a=1.0, voltage_v=sim_out.terminal_voltage_v, dt_s=1.0))

        self.assertAlmostEqual(out.state.soc_fraction, sim_model.state.soc_fraction, delta=0.02)
        self.assertGreater(out.state.soc_variance, 0.0)

    # --------------------------------------------------------------------------
    # 4. Covariance Symmetry and Joseph Form Stability
    # --------------------------------------------------------------------------
    def test_covariance_symmetry_and_positive_definiteness(self) -> None:
        """Covariance matrix must remain strictly symmetric and positive diagonal across long simulation."""
        self.ekf.initialize(initial_soc=0.75)
        for i in range(200):
            self.ekf.step(EstimationInput(current_a=0.5, voltage_v=3.85, dt_s=1.0))

        P = self.ekf.covariance_matrix
        dim = self.ekf.state_dimension
        for i in range(dim):
            self.assertGreater(P[i][i], 0.0, f"Diagonal element P[{i}][{i}] must be strictly positive.")
            for j in range(dim):
                self.assertAlmostEqual(
                    P[i][j],
                    P[j][i],
                    places=7,
                    msg=f"Covariance asymmetry at ({i}, {j}).",
                )

    # --------------------------------------------------------------------------
    # 5. Invariants & Error Handling
    # --------------------------------------------------------------------------
    def test_invalid_construction_parameters_raise(self) -> None:
        """Invalid noise or parameter specifications must raise InvalidModelParametersError."""
        with self.assertRaises(InvalidModelParametersError):
            ExtendedKalmanFilter(
                estimator_id="bad",
                parameters="not_parameters_object",  # type: ignore
            )

        with self.assertRaises(InvalidModelParametersError):
            ExtendedKalmanFilter(
                estimator_id="bad",
                parameters=self.params_1rc,
                measurement_noise_voltage_v2=-1.0,
            )

        with self.assertRaises(InvalidModelParametersError):
            ExtendedKalmanFilter(
                estimator_id="bad",
                parameters=self.params_1rc,
                process_noise_soc=-0.1,
            )

    def test_invalid_step_inputs_raise(self) -> None:
        """Non-positive voltage or time step must raise InvalidEstimatorInputError."""
        with self.assertRaises(InvalidEstimatorInputError):
            self.ekf.step(EstimationInput(current_a=1.0, voltage_v=-3.0, dt_s=1.0))

        with self.assertRaises(InvalidEstimatorInputError):
            self.ekf.step(EstimationInput(current_a=1.0, voltage_v=3.7, dt_s=0.0))


if __name__ == "__main__":
    unittest.main()
