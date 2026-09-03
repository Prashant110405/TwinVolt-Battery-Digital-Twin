"""Mathematical & Algorithmic Validation of ZOH Discrete ARX RLS Parameter Identification.

NOTE: Synthetic tests validate mathematical and algorithmic correctness under known discrete-time
ODEs. They do NOT constitute physical battery accuracy validation against real hardware.
"""

import math
import random
import unittest
from typing import Any

from src.calibration.guard import ParameterSafetyGuard
from src.calibration.rls import RLSParameterIdentifier, UDCovarianceFactorizer
from src.calibration.types import ParameterStateClassification, RLSConfig
from src.telemetry.snapshots import TelemetrySnapshot


class MockModelOutput:
    """Mock model output containing simulated OCV and state for testing."""

    def __init__(self, soc_fraction: float = 0.5, open_circuit_voltage_v: float = 3.6) -> None:
        self.open_circuit_voltage_v = open_circuit_voltage_v
        self.state = type("MockState", (), {"soc_fraction": soc_fraction})()


class MockSyncOutput:
    """Mock TwinSyncOutput container."""

    def __init__(
        self,
        soc_fraction: float = 0.5,
        open_circuit_voltage_v: float = 3.6,
        voltage_residual_v: float = 0.0,
        dt_s: float = 1.0,
    ) -> None:
        self.model_output = MockModelOutput(soc_fraction, open_circuit_voltage_v)
        self.residuals = {"voltage_residual_v": voltage_residual_v}
        self.dt_s = dt_s


class TestRLSParameterIdentification(unittest.TestCase):
    """Test suite verifying discrete ZOH ARX equations, Bierman U-D factorization, and parameter recovery."""

    def test_zoh_algebraic_derivation(self) -> None:
        """Verifies exact algebraic inversion from continuous ECM to discrete ARX and back."""
        r0_true = 0.025
        r1_true = 0.015
        c1_true = 1000.0
        dt_s = 1.0

        tau_true = r1_true * c1_true  # 15.0 s
        alpha = math.exp(-dt_s / tau_true)

        # Discrete ARX coefficients:
        a1 = alpha
        b0 = r0_true
        b1 = r1_true * (1.0 - alpha) - (alpha * r0_true)

        # Recovery using ParameterSafetyGuard
        guard = ParameterSafetyGuard()
        res = guard.validate_and_recover(a1=a1, b0=b0, b1=b1, dt_s=dt_s)

        self.assertTrue(res.is_r0_valid)
        self.assertTrue(res.is_secondary_valid)
        self.assertAlmostEqual(res.r0_ohm, r0_true, places=8)
        self.assertAlmostEqual(res.r1_ohm, r1_true, places=8)
        self.assertAlmostEqual(res.c1_farad, c1_true, places=6)
        self.assertAlmostEqual(res.tau1_s, tau_true, places=6)

    def test_bierman_ud_factorization_properties(self) -> None:
        """Verifies that U-D factorization maintains positive diagonal factors and symmetry."""
        ud = UDCovarianceFactorizer(dim=3, initial_variance=100.0)

        # Initial checks
        diag = ud.get_diagonal_elements()
        self.assertEqual(diag, (100.0, 100.0, 100.0))
        self.assertEqual(ud.get_trace(), 300.0)

        # Perform 10 pseudo-random measurement updates
        random.seed(42)
        for _ in range(10):
            phi = [random.uniform(-1.0, 1.0), random.uniform(-5.0, 5.0), random.uniform(-5.0, 5.0)]
            k_gain, alpha_m = ud.update(phi=phi, lam=0.995)
            self.assertGreater(alpha_m, 0.0)
            self.assertEqual(len(k_gain), 3)

            # Assert all D elements remain strictly positive
            for d_val in ud.d:
                self.assertGreater(d_val, 0.0)

            # Assert reconstructed covariance matrix is symmetric
            cov = ud.get_covariance_matrix()
            self.assertAlmostEqual(cov[0][1], cov[1][0], places=7)
            self.assertAlmostEqual(cov[0][2], cov[2][0], places=7)
            self.assertAlmostEqual(cov[1][2], cov[2][1], places=7)

    def test_noise_free_synthetic_parameter_recovery(self) -> None:
        """MATHEMATICAL VALIDATION: RLS recovers known R0, R1, C1 under dynamic pulse current."""
        r0_true = 0.025
        r1_true = 0.015
        c1_true = 1000.0
        tau_true = r1_true * c1_true
        dt_s = 1.0
        v_oc = 3.6

        identifier = RLSParameterIdentifier(
            system_id="synth_twin",
            nominal_r0_ohm=0.030,  # Seed with slight initial mismatch
            nominal_r1_ohm=0.020,
            nominal_c1_farad=800.0,
            config=RLSConfig(forgetting_factor_lambda=0.995),
        )

        # Simulate 600 seconds of pulse current excitation
        v_p = 0.0
        i_prev = 0.0
        alpha = math.exp(-dt_s / tau_true)

        for step in range(600):
            # Dynamic pulse current sequence (+5A, -3A, +4A, -4A in blocks of 15-20s)
            t = step * dt_s
            cycle_pos = t % 60.0
            if cycle_pos < 15.0:
                i_k = 5.0
            elif cycle_pos < 30.0:
                i_k = -3.0
            elif cycle_pos < 45.0:
                i_k = 4.0
            else:
                i_k = -4.0

            # Exact ZOH simulation step: Vp[k] = alpha * Vp[k-1] + R1 * (1 - alpha) * I[k-1]
            v_p = alpha * v_p + r1_true * (1.0 - alpha) * i_prev
            v_term = v_oc - (i_k * r0_true) - v_p
            i_prev = i_k

            snap = TelemetrySnapshot(
                system_id="synth_twin",
                snapshot_id=f"snap_{step}",
                timestamp_ns=step * 1_000_000_000,
                pack_current_a=i_k,
                pack_voltage_v=v_term,
            )
            sync = MockSyncOutput(
                soc_fraction=0.6,
                open_circuit_voltage_v=v_oc,
                dt_s=dt_s,
            )

            param_set = identifier.update(snapshot=snap, sync_output=sync, dt_s=dt_s)

        # Assert convergence within target tolerance (<= 0.5% error)
        self.assertIsNotNone(param_set.r0_ohm)
        self.assertIsNotNone(param_set.r1_ohm)
        self.assertIsNotNone(param_set.c1_farad)

        r0_error_pct = abs(param_set.r0_ohm - r0_true) / r0_true * 100.0
        r1_error_pct = abs(param_set.r1_ohm - r1_true) / r1_true * 100.0
        c1_error_pct = abs(param_set.c1_farad - c1_true) / c1_true * 100.0

        self.assertLess(r0_error_pct, 0.5, f"R0 error {r0_error_pct:.3f}% exceeded 0.5%")
        self.assertLess(r1_error_pct, 0.5, f"R1 error {r1_error_pct:.3f}% exceeded 0.5%")
        self.assertLess(c1_error_pct, 0.5, f"C1 error {c1_error_pct:.3f}% exceeded 0.5%")

    def test_noisy_telemetry_recovery(self) -> None:
        """MATHEMATICAL VALIDATION: RLS converges to true R0 under 2 mV Gaussian measurement noise."""
        r0_true = 0.025
        r1_true = 0.015
        c1_true = 1000.0
        tau_true = r1_true * c1_true
        dt_s = 1.0
        v_oc = 3.6

        identifier = RLSParameterIdentifier(
            system_id="noisy_twin",
            nominal_r0_ohm=0.028,
            config=RLSConfig(forgetting_factor_lambda=0.998),
        )

        random.seed(12345)
        v_p = 0.0
        i_prev = 0.0
        alpha = math.exp(-dt_s / tau_true)

        for step in range(800):
            t = step * dt_s
            cycle_pos = t % 40.0
            i_k = 6.0 if cycle_pos < 20.0 else -6.0

            v_p = alpha * v_p + r1_true * (1.0 - alpha) * i_prev
            noise_v = random.gauss(0.0, 0.002)  # 2 mV RMS noise
            v_term = v_oc - (i_k * r0_true) - v_p + noise_v
            i_prev = i_k

            snap = TelemetrySnapshot(
                system_id="noisy_twin",
                snapshot_id=f"snap_{step}",
                timestamp_ns=step * 1_000_000_000,
                pack_current_a=i_k,
                pack_voltage_v=v_term,
            )
            sync = MockSyncOutput(soc_fraction=0.5, open_circuit_voltage_v=v_oc, dt_s=dt_s)
            param_set = identifier.update(snapshot=snap, sync_output=sync, dt_s=dt_s)

        # Assert R0 recovery within 2.0% under noisy telemetry
        r0_error_pct = abs(param_set.r0_ohm - r0_true) / r0_true * 100.0
        self.assertLess(r0_error_pct, 2.0, f"Noisy R0 error {r0_error_pct:.3f}% exceeded 2.0%")


if __name__ == "__main__":
    unittest.main()
