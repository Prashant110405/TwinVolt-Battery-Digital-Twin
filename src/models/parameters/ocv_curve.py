"""Non-Linear Open-Circuit Voltage (OCV) vs State-of-Charge (SOC) Curve Engine.

Provides high-fidelity, shape-preserving, monotonic OCV-SOC interpolation,
analytical derivatives (dOCV/dSOC, dOCV/dT), and flat plateau handling for all battery chemistries.
"""

from bisect import bisect_right
import math
from typing import Any, Mapping, Optional, Sequence, Union

from src.models.base import OCVModel
from src.models.exceptions import InvalidModelParametersError, InvalidModelStateError
from src.models.math import assert_finite, clamp
from src.models.types import ABSOLUTE_ZERO_CELSIUS


def _compute_pchip_derivatives(
    x: Sequence[float],
    y: Sequence[float],
) -> list[float]:
    """Computes shape-preserving Piecewise Cubic Hermite Interpolating Polynomial (PCHIP) derivatives.

    Guarantees monotonicity preservation and prevents unphysical overshoot/undershoot oscillations.
    """
    n = len(x)
    h = [x[i + 1] - x[i] for i in range(n - 1)]
    delta = [(y[i + 1] - y[i]) / h[i] for i in range(n - 1)]
    d = [0.0] * n

    # Endpoints
    if n == 2:
        d[0] = delta[0]
        d[1] = delta[0]
        return d

    # Standard PCHIP endpoint slopes with shape preservation
    d0 = ((2.0 * h[0] + h[1]) * delta[0] - h[0] * delta[1]) / (h[0] + h[1])
    if d0 * delta[0] <= 0.0:
        d[0] = 0.0
    elif (delta[0] * delta[1] < 0.0) and (abs(d0) > abs(3.0 * delta[0])):
        d[0] = 3.0 * delta[0]
    else:
        d[0] = d0

    dn = ((2.0 * h[-1] + h[-2]) * delta[-1] - h[-1] * delta[-2]) / (h[-1] + h[-2])
    if dn * delta[-1] <= 0.0:
        d[-1] = 0.0
    elif (delta[-1] * delta[-2] < 0.0) and (abs(dn) > abs(3.0 * delta[-1])):
        d[-1] = 3.0 * delta[-1]
    else:
        d[-1] = dn

    # Interior points (Brodlie-Butland weighted harmonic mean)
    for i in range(1, n - 1):
        if delta[i - 1] * delta[i] <= 0.0:
            d[i] = 0.0
        else:
            w1 = 2.0 * h[i] + h[i - 1]
            w2 = h[i] + 2.0 * h[i - 1]
            d[i] = (w1 + w2) / ((w1 / delta[i - 1]) + (w2 / delta[i]))

    return d


class OCVCurve:
    r"""Universal Non-Linear Open-Circuit Voltage Model satisfying the OCVModel protocol.

    Supports:
    - Tabulated SOC vs OCV points with piece-wise linear or shape-preserving PCHIP spline interpolation.
    - Flat voltage plateau regions (crucial for LFP and LTO chemistries).
    - Monotonicity defense: verifies that OCV does not exhibit unphysical local extrema.
    - Entropic thermal coefficient support: constant or SOC-dependent $dOCV/dT(SOC)$ in V/K.
    - Continuous analytical derivative $dOCV/dSOC$.
    """

    def __init__(
        self,
        soc_points: Sequence[float],
        ocv_points_v: Sequence[float],
        d_ocv_d_temp_v_per_k: Union[float, Sequence[float]] = 0.0,
        interpolation_method: str = "PCHIP",
        enforce_monotonicity: bool = True,
        name: str = "CustomOCVCurve",
    ) -> None:
        if len(soc_points) < 2:
            raise InvalidModelParametersError("soc_points must contain at least 2 coordinate points.")
        if len(soc_points) != len(ocv_points_v):
            raise InvalidModelParametersError(
                f"Length mismatch: soc_points ({len(soc_points)}) != ocv_points_v ({len(ocv_points_v)})."
            )

        # Validate finiteness and sorting of SOC points
        for idx, s in enumerate(soc_points):
            assert_finite(s, f"soc_points[{idx}]")
        for idx, v in enumerate(ocv_points_v):
            assert_finite(v, f"ocv_points_v[{idx}]")
            if v <= 0.0:
                raise InvalidModelParametersError(
                    f"OCV values must be strictly positive, got {v}V at index {idx}."
                )

        # Check strictly increasing SOC
        for i in range(len(soc_points) - 1):
            if soc_points[i + 1] <= soc_points[i]:
                raise InvalidModelParametersError(
                    f"soc_points must be strictly monotonically increasing. "
                    f"soc[{i}]={soc_points[i]} >= soc[{i+1}]={soc_points[i+1]}."
                )

        # Ensure range covers [0.0, 1.0]
        if soc_points[0] > 0.0 or soc_points[-1] < 1.0:
            raise InvalidModelParametersError(
                f"soc_points must span from <= 0.0 to >= 1.0. Got range [{soc_points[0]}, {soc_points[-1]}]."
            )

        # Check non-decreasing monotonicity of OCV
        is_monotonic = True
        for i in range(len(ocv_points_v) - 1):
            if ocv_points_v[i + 1] < ocv_points_v[i]:
                is_monotonic = False
                break

        if enforce_monotonicity and not is_monotonic:
            raise InvalidModelParametersError(
                "ocv_points_v violates monotonicity requirement (OCV cannot decrease as SOC increases)."
            )

        method_normalized = interpolation_method.upper().strip()
        if method_normalized not in {"PCHIP", "LINEAR"}:
            raise InvalidModelParametersError(
                f"Unsupported interpolation_method '{interpolation_method}'. Supported: ['PCHIP', 'LINEAR']."
            )

        self._soc = tuple(float(s) for s in soc_points)
        self._ocv = tuple(float(v) for v in ocv_points_v)
        self._method = method_normalized
        self._is_monotonic = is_monotonic
        self._name = name

        # Handle entropic coefficient (constant float or array)
        if isinstance(d_ocv_d_temp_v_per_k, (int, float)):
            assert_finite(d_ocv_d_temp_v_per_k, "d_ocv_d_temp_v_per_k")
            self._d_ocv_d_temp = float(d_ocv_d_temp_v_per_k)
            self._d_ocv_d_temp_table: Optional[tuple[float, ...]] = None
        else:
            if len(d_ocv_d_temp_v_per_k) != len(soc_points):
                raise InvalidModelParametersError(
                    f"d_ocv_d_temp_v_per_k table length ({len(d_ocv_d_temp_v_per_k)}) must match soc_points ({len(soc_points)})."
                )
            for idx, dt in enumerate(d_ocv_d_temp_v_per_k):
                assert_finite(dt, f"d_ocv_d_temp_v_per_k[{idx}]")
            self._d_ocv_d_temp_table = tuple(float(dt) for dt in d_ocv_d_temp_v_per_k)
            self._d_ocv_d_temp = 0.0

        # Precompute PCHIP derivatives if using cubic Hermite interpolation
        if self._method == "PCHIP":
            self._d = tuple(_compute_pchip_derivatives(self._soc, self._ocv))
        else:
            self._d = ()

    @property
    def name(self) -> str:
        """Descriptive identifier of the OCV curve."""
        return self._name

    @property
    def soc_points(self) -> tuple[float, ...]:
        """Configured State-of-Charge reference grid."""
        return self._soc

    @property
    def ocv_points_v(self) -> tuple[float, ...]:
        """Configured Open-Circuit Voltage points in Volts."""
        return self._ocv

    @property
    def interpolation_method(self) -> str:
        """Active interpolation method ('PCHIP' or 'LINEAR')."""
        return self._method

    @property
    def is_monotonic(self) -> bool:
        """Whether the curve is monotonically non-decreasing."""
        return self._is_monotonic

    @property
    def v_min_v(self) -> float:
        """Open-circuit voltage at 0% SOC and 25°C."""
        return self.get_ocv(0.0, 25.0)

    @property
    def v_max_v(self) -> float:
        """Open-circuit voltage at 100% SOC and 25°C."""
        return self.get_ocv(1.0, 25.0)

    # --------------------------------------------------------------------------
    # OCVModel Protocol Implementation
    # --------------------------------------------------------------------------
    def get_ocv(self, soc_fraction: float, temperature_c: float = 25.0) -> float:
        """Calculates Open-Circuit Voltage in Volts for a given SOC and temperature.

        Args:
            soc_fraction: State of Charge in range [0.0, 1.0].
            temperature_c: Cell core temperature in degrees Celsius (> -273.15°C).

        Returns:
            Open-circuit voltage $V_{oc}(SOC, T)$ in Volts.
        """
        assert_finite(soc_fraction, "soc_fraction")
        assert_finite(temperature_c, "temperature_c")
        if temperature_c <= ABSOLUTE_ZERO_CELSIUS:
            raise InvalidModelStateError(f"temperature_c below absolute zero: {temperature_c}°C.")

        soc = clamp(soc_fraction, self._soc[0], self._soc[-1])

        # Find interval
        idx = bisect_right(self._soc, soc) - 1
        if idx < 0:
            idx = 0
        elif idx >= len(self._soc) - 1:
            idx = len(self._soc) - 2

        x0, x1 = self._soc[idx], self._soc[idx + 1]
        y0, y1 = self._ocv[idx], self._ocv[idx + 1]
        h = x1 - x0

        if self._method == "LINEAR" or h <= 0.0:
            t = (soc - x0) / h if h > 0 else 0.0
            v_ref = y0 + t * (y1 - y0)
        else:
            # PCHIP Hermite evaluation
            d0, d1 = self._d[idx], self._d[idx + 1]
            t = (soc - x0) / h
            t2 = t * t
            t3 = t2 * t
            h00 = 2.0 * t3 - 3.0 * t2 + 1.0
            h10 = t3 - 2.0 * t2 + t
            h01 = -2.0 * t3 + 3.0 * t2
            h11 = t3 - t2
            v_ref = h00 * y0 + h10 * h * d0 + h01 * y1 + h11 * h * d1

        # Temperature correction
        docv_dtemp = self.get_docv_dtemp(soc, temperature_c)
        v_oc = v_ref + (temperature_c - 25.0) * docv_dtemp
        assert_finite(v_oc, "open_circuit_voltage_v")
        return v_oc

    def get_docv_dsoc(self, soc_fraction: float, temperature_c: float = 25.0) -> float:
        """Calculates analytical derivative $dOCV/dSOC$ in V/fraction.

        Essential for Extended Kalman Filter (EKF) linearizations and sensitivity analysis.
        """
        assert_finite(soc_fraction, "soc_fraction")
        assert_finite(temperature_c, "temperature_c")
        if temperature_c <= ABSOLUTE_ZERO_CELSIUS:
            raise InvalidModelStateError(f"temperature_c below absolute zero: {temperature_c}°C.")

        soc = clamp(soc_fraction, self._soc[0], self._soc[-1])

        idx = bisect_right(self._soc, soc) - 1
        if idx < 0:
            idx = 0
        elif idx >= len(self._soc) - 1:
            idx = len(self._soc) - 2

        x0, x1 = self._soc[idx], self._soc[idx + 1]
        y0, y1 = self._ocv[idx], self._ocv[idx + 1]
        h = x1 - x0

        if self._method == "LINEAR" or h <= 0.0:
            return (y1 - y0) / h if h > 0 else 0.0

        # PCHIP analytical derivative
        d0, d1 = self._d[idx], self._d[idx + 1]
        t = (soc - x0) / h
        t2 = t * t
        dh00 = 6.0 * t2 - 6.0 * t
        dh10 = 3.0 * t2 - 4.0 * t + 1.0
        dh01 = -6.0 * t2 + 6.0 * t
        dh11 = 3.0 * t2 - 2.0 * t

        docv_dsoc = (dh00 * y0 + dh01 * y1) / h + dh10 * d0 + dh11 * d1
        return docv_dsoc

    def get_docv_dtemp(self, soc_fraction: float, temperature_c: float = 25.0) -> float:
        """Calculates entropic temperature coefficient $dOCV/dT$ in V/K."""
        if self._d_ocv_d_temp_table is None:
            return self._d_ocv_d_temp

        soc = clamp(soc_fraction, self._soc[0], self._soc[-1])
        idx = bisect_right(self._soc, soc) - 1
        if idx < 0:
            idx = 0
        elif idx >= len(self._soc) - 1:
            idx = len(self._soc) - 2

        x0, x1 = self._soc[idx], self._soc[idx + 1]
        y0, y1 = self._d_ocv_d_temp_table[idx], self._d_ocv_d_temp_table[idx + 1]
        t = (soc - x0) / (x1 - x0) if (x1 - x0) > 0 else 0.0
        return y0 + t * (y1 - y0)

    # --------------------------------------------------------------------------
    # Serialization
    # --------------------------------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        """Serializes OCV curve configuration to dictionary."""
        return {
            "name": self._name,
            "soc_points": list(self._soc),
            "ocv_points_v": list(self._ocv),
            "d_ocv_d_temp_v_per_k": (
                list(self._d_ocv_d_temp_table)
                if self._d_ocv_d_temp_table is not None
                else self._d_ocv_d_temp
            ),
            "interpolation_method": self._method,
            "is_monotonic": self._is_monotonic,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "OCVCurve":
        """Reconstructs an OCVCurve from dictionary serialization."""
        return cls(
            soc_points=data["soc_points"],
            ocv_points_v=data["ocv_points_v"],
            d_ocv_d_temp_v_per_k=data.get("d_ocv_d_temp_v_per_k", 0.0),
            interpolation_method=data.get("interpolation_method", "PCHIP"),
            name=data.get("name", "CustomOCVCurve"),
        )
