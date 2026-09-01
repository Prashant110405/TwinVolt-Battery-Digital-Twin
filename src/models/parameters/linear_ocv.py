"""Default Analytical Linear/Interpolated OCV Model.

Provides a baseline analytical Open-Circuit Voltage model satisfying the OCVModel protocol.
"""

from src.models.base import OCVModel
from src.models.exceptions import InvalidModelParametersError
from src.models.math import assert_finite, clamp


class LinearOCVModel:
    """Linear parameterized Open-Circuit Voltage model:

    $V_{oc}(SOC, T) = V_{min} + SOC \\cdot (V_{max} - V_{min}) + (T - 25.0) \\cdot \\frac{\\partial V_{oc}}{\\partial T}$
    """

    def __init__(
        self,
        v_min_v: float = 3.0,
        v_max_v: float = 4.2,
        d_ocv_d_temp_v_per_k: float = 0.0,
    ) -> None:
        assert_finite(v_min_v, "v_min_v")
        assert_finite(v_max_v, "v_max_v")
        assert_finite(d_ocv_d_temp_v_per_k, "d_ocv_d_temp_v_per_k")

        if v_min_v <= 0.0 or v_max_v <= 0.0:
            raise InvalidModelParametersError("Voltages must be strictly positive.")
        if v_min_v >= v_max_v:
            raise InvalidModelParametersError(
                f"v_min_v ({v_min_v}V) must be less than v_max_v ({v_max_v}V)."
            )

        self._v_min = float(v_min_v)
        self._v_max = float(v_max_v)
        self._d_ocv_d_temp = float(d_ocv_d_temp_v_per_k)
        self._span = self._v_max - self._v_min

    @property
    def v_min_v(self) -> float:
        """Minimum OCV in Volts (at 0% SOC)."""
        return self._v_min

    @property
    def v_max_v(self) -> float:
        """Maximum OCV in Volts (at 100% SOC)."""
        return self._v_max

    def get_ocv(self, soc_fraction: float, temperature_c: float = 25.0) -> float:
        """Calculates open circuit voltage in Volts."""
        assert_finite(soc_fraction, "soc_fraction")
        assert_finite(temperature_c, "temperature_c")
        clamped_soc = clamp(soc_fraction, 0.0, 1.0)
        temp_correction = (temperature_c - 25.0) * self._d_ocv_d_temp
        return self._v_min + (clamped_soc * self._span) + temp_correction

    def get_docv_dsoc(self, soc_fraction: float, temperature_c: float = 25.0) -> float:
        """Calculates derivative dOCV/dSOC in V/fraction."""
        return self._span

    def get_docv_dtemp(self, soc_fraction: float, temperature_c: float = 25.0) -> float:
        """Calculates entropic derivative dOCV/dT in V/K."""
        return self._d_ocv_d_temp
