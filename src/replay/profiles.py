"""Standard Battery Drive Cycle Profiles and Time-Series Generators.

Provides benchmark driving schedules (WLTP Class 3, US06, DST, Pulse Discharge, Constant Current)
for deterministic simulation, validation, and tracking evaluation.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Optional, Sequence

from src.models.math import assert_finite, clamp
from src.replay.exceptions import InvalidProfileError
from src.telemetry.enums import TelemetryQuality
from src.telemetry.snapshots import TelemetrySnapshot


@dataclass(frozen=True)
class ProfilePoint:
    """Individual time-series observation point within a drive cycle.

    All physical quantities use explicit SI units:
    - time_s: Elapsed simulation time in seconds (>= 0.0).
    - current_a: Pack load/charge current in Amperes (>0 discharge, <0 charge, 0 rest).
    - ambient_temperature_c: Ambient temperature in Celsius.
    - voltage_v: Optional reference/measured terminal voltage in Volts.
    - soc_fraction: Optional reference State of Charge fraction in [0.0, 1.0].
    """

    time_s: float
    current_a: float
    ambient_temperature_c: float = 25.0
    voltage_v: Optional[float] = None
    soc_fraction: Optional[float] = None

    def __post_init__(self) -> None:
        assert_finite(self.time_s, "time_s")
        assert_finite(self.current_a, "current_a")
        assert_finite(self.ambient_temperature_c, "ambient_temperature_c")

        if self.time_s < 0.0:
            raise InvalidProfileError(f"time_s cannot be negative, got {self.time_s}s.")
        if self.ambient_temperature_c <= -273.15:
            raise InvalidProfileError(
                f"ambient_temperature_c below absolute zero: {self.ambient_temperature_c}°C."
            )
        if self.voltage_v is not None:
            assert_finite(self.voltage_v, "voltage_v")
            if self.voltage_v <= 0.0:
                raise InvalidProfileError(f"voltage_v must be strictly positive, got {self.voltage_v}V.")
        if self.soc_fraction is not None:
            assert_finite(self.soc_fraction, "soc_fraction")
            if not (0.0 <= self.soc_fraction <= 1.0):
                raise InvalidProfileError(
                    f"soc_fraction must be in [0.0, 1.0], got {self.soc_fraction}."
                )

    def to_dict(self) -> dict[str, Any]:
        """Serializes profile point to dictionary."""
        return {
            "time_s": self.time_s,
            "current_a": self.current_a,
            "ambient_temperature_c": self.ambient_temperature_c,
            "voltage_v": self.voltage_v,
            "soc_fraction": self.soc_fraction,
        }


@dataclass(frozen=True)
class DriveCycleProfile:
    """Immutable collection of sequential time-series points representing a drive cycle."""

    name: str
    points: tuple[ProfilePoint, ...]
    description: str = ""
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise InvalidProfileError("Drive cycle name must be a non-empty string.")
        if not self.points:
            raise InvalidProfileError(f"Drive cycle '{self.name}' must contain at least one point.")

        # Validate strictly monotonic timestamp ordering
        prev_t = -1.0
        for idx, pt in enumerate(self.points):
            if not isinstance(pt, ProfilePoint):
                raise InvalidProfileError(
                    f"points[{idx}] must be ProfilePoint, got {type(pt).__name__}."
                )
            if pt.time_s <= prev_t and idx > 0:
                raise InvalidProfileError(
                    f"Non-monotonic timestamps in profile '{self.name}' at index {idx}: "
                    f"time_s={pt.time_s} <= prev_time_s={prev_t}."
                )
            prev_t = pt.time_s

    @property
    def sample_count(self) -> int:
        """Total number of sample points in the drive cycle."""
        return len(self.points)

    @property
    def duration_s(self) -> float:
        """Total duration of the drive cycle in seconds."""
        if not self.points:
            return 0.0
        return self.points[-1].time_s - self.points[0].time_s

    @property
    def peak_discharge_current_a(self) -> float:
        """Maximum discharge current (> 0 A)."""
        currents = [p.current_a for p in self.points if p.current_a > 0]
        return max(currents) if currents else 0.0

    @property
    def peak_charge_current_a(self) -> float:
        """Maximum charge/regenerative current (< 0 A, returned as negative)."""
        currents = [p.current_a for p in self.points if p.current_a < 0]
        return min(currents) if currents else 0.0

    @property
    def time_points_s(self) -> tuple[float, ...]:
        """Tuple of all time points in seconds."""
        return tuple(p.time_s for p in self.points)

    @property
    def current_points_a(self) -> tuple[float, ...]:
        """Tuple of all load currents in Amperes."""
        return tuple(p.current_a for p in self.points)

    def to_snapshots(
        self,
        system_id: str = "battery_system",
        start_timestamp_ns: int = 1_000_000_000_000_000_000,
        sample_interval_s: Optional[float] = None,
    ) -> tuple[TelemetrySnapshot, ...]:
        """Materializes an ordered sequence of canonical TelemetrySnapshot objects from this profile.

        Args:
            system_id: System identifier to stamp on snapshots.
            start_timestamp_ns: Base start epoch nanoseconds.
            sample_interval_s: Optional resampling interval in seconds (linear interpolation).

        Returns:
            Tuple of canonical TelemetrySnapshot instances.
        """
        if sample_interval_s is not None and sample_interval_s <= 0:
            raise InvalidProfileError(
                f"sample_interval_s must be strictly positive, got {sample_interval_s}."
            )

        snapshots: list[TelemetrySnapshot] = []

        if sample_interval_s is None:
            # Direct 1:1 mapping from profile points
            for idx, pt in enumerate(self.points):
                ts_ns = start_timestamp_ns + int(pt.time_s * 1_000_000_000)
                snap = TelemetrySnapshot(
                    snapshot_id=f"snap_{system_id}_{idx:06d}",
                    system_id=system_id,
                    timestamp_ns=ts_ns,
                    sequence_number=idx + 1,
                    pack_current_a=pt.current_a,
                    pack_voltage_v=pt.voltage_v,
                    ambient_temperature_c=pt.ambient_temperature_c,
                    soc_fraction=pt.soc_fraction,
                    quality=TelemetryQuality.VALID,
                    metadata={"profile_name": self.name},
                )
                snapshots.append(snap)
        else:
            # Resample at fixed dt
            t_total = self.duration_s
            t_curr = 0.0
            idx = 0
            while t_curr <= t_total + 1e-9:
                curr_a, amb_t, volt_v, soc_f = self._interpolate_at(t_curr)
                ts_ns = start_timestamp_ns + int(t_curr * 1_000_000_000)
                snap = TelemetrySnapshot(
                    snapshot_id=f"snap_{system_id}_{idx:06d}",
                    system_id=system_id,
                    timestamp_ns=ts_ns,
                    sequence_number=idx + 1,
                    pack_current_a=curr_a,
                    pack_voltage_v=volt_v,
                    ambient_temperature_c=amb_t,
                    soc_fraction=soc_f,
                    quality=TelemetryQuality.VALID,
                    metadata={"profile_name": self.name},
                )
                snapshots.append(snap)
                t_curr += sample_interval_s
                idx += 1

        return tuple(snapshots)

    def _interpolate_at(
        self, t_query: float
    ) -> tuple[float, float, Optional[float], Optional[float]]:
        """Piecewise linear interpolation at query time."""
        if t_query <= self.points[0].time_s:
            p = self.points[0]
            return p.current_a, p.ambient_temperature_c, p.voltage_v, p.soc_fraction
        if t_query >= self.points[-1].time_s:
            p = self.points[-1]
            return p.current_a, p.ambient_temperature_c, p.voltage_v, p.soc_fraction

        # Binary search
        low = 0
        high = len(self.points) - 1
        while low <= high:
            mid = (low + high) // 2
            if self.points[mid].time_s <= t_query:
                low = mid + 1
            else:
                high = mid - 1

        p0 = self.points[high]
        p1 = self.points[low]
        dt = p1.time_s - p0.time_s
        alpha = (t_query - p0.time_s) / dt if dt > 0 else 0.0

        i_interp = p0.current_a + alpha * (p1.current_a - p0.current_a)
        t_interp = p0.ambient_temperature_c + alpha * (p1.ambient_temperature_c - p0.ambient_temperature_c)

        v_interp = None
        if p0.voltage_v is not None and p1.voltage_v is not None:
            v_interp = p0.voltage_v + alpha * (p1.voltage_v - p0.voltage_v)

        soc_interp = None
        if p0.soc_fraction is not None and p1.soc_fraction is not None:
            soc_interp = p0.soc_fraction + alpha * (p1.soc_fraction - p0.soc_fraction)

        return i_interp, t_interp, v_interp, soc_interp


# ==============================================================================
# Standard Profile Generator Factories
# ==============================================================================
def create_constant_current_profile(
    duration_s: float,
    current_a: float,
    dt_s: float = 1.0,
    ambient_temp_c: float = 25.0,
    name: Optional[str] = None,
) -> DriveCycleProfile:
    """Generates a constant current discharge or charge profile.

    Args:
        duration_s: Total profile duration in seconds (> 0).
        current_a: Applied current (>0 for discharge, <0 for charge).
        dt_s: Sample step interval in seconds (> 0).
        ambient_temp_c: Ambient temperature in Celsius.
        name: Profile display name.

    Returns:
        DriveCycleProfile instance.
    """
    if duration_s <= 0:
        raise InvalidProfileError(f"duration_s must be strictly positive, got {duration_s}s.")
    if dt_s <= 0:
        raise InvalidProfileError(f"dt_s must be strictly positive, got {dt_s}s.")

    points: list[ProfilePoint] = []
    t = 0.0
    while t <= duration_s + 1e-9:
        points.append(
            ProfilePoint(
                time_s=round(t, 6),
                current_a=float(current_a),
                ambient_temperature_c=float(ambient_temp_c),
            )
        )
        t += dt_s

    prof_name = name or f"Constant_Current_{current_a}A_{duration_s}s"
    return DriveCycleProfile(
        name=prof_name,
        points=tuple(points),
        description=f"Constant current test profile at {current_a}A for {duration_s}s.",
    )


def create_pulse_discharge_profile(
    pulse_current_a: float,
    rest_current_a: float = 0.0,
    pulse_duration_s: float = 10.0,
    rest_duration_s: float = 20.0,
    cycles: int = 5,
    dt_s: float = 1.0,
    ambient_temp_c: float = 25.0,
    name: Optional[str] = None,
) -> DriveCycleProfile:
    """Generates a periodic multi-step pulse discharge profile (HPPC-style).

    Args:
        pulse_current_a: Active discharge pulse current in Amperes.
        rest_current_a: Quiescent rest current in Amperes.
        pulse_duration_s: Active pulse phase duration in seconds (> 0).
        rest_duration_s: Resting phase duration in seconds (> 0).
        cycles: Number of pulse-rest repetitions (>= 1).
        dt_s: Sample step interval in seconds (> 0).
        ambient_temp_c: Ambient temperature in Celsius.
        name: Profile display name.

    Returns:
        DriveCycleProfile instance.
    """
    if pulse_duration_s <= 0 or rest_duration_s <= 0:
        raise InvalidProfileError("Pulse and rest durations must be strictly positive.")
    if cycles < 1:
        raise InvalidProfileError(f"cycles must be >= 1, got {cycles}.")
    if dt_s <= 0:
        raise InvalidProfileError(f"dt_s must be strictly positive, got {dt_s}s.")

    points: list[ProfilePoint] = []
    t = 0.0

    for c in range(cycles):
        # Pulse phase
        t_pulse_end = t + pulse_duration_s
        while t < t_pulse_end - 1e-9:
            points.append(
                ProfilePoint(
                    time_s=round(t, 6),
                    current_a=float(pulse_current_a),
                    ambient_temperature_c=float(ambient_temp_c),
                )
            )
            t += dt_s

        # Rest phase
        t_rest_end = t + rest_duration_s
        while t < t_rest_end - 1e-9:
            points.append(
                ProfilePoint(
                    time_s=round(t, 6),
                    current_a=float(rest_current_a),
                    ambient_temperature_c=float(ambient_temp_c),
                )
            )
            t += dt_s

    # Final resting point
    points.append(
        ProfilePoint(
            time_s=round(t, 6),
            current_a=float(rest_current_a),
            ambient_temperature_c=float(ambient_temp_c),
        )
    )

    prof_name = name or f"Pulse_Discharge_{pulse_current_a}A_{cycles}x"
    return DriveCycleProfile(
        name=prof_name,
        points=tuple(points),
        description=f"Periodic pulse discharge ({cycles} cycles of {pulse_duration_s}s pulse / {rest_duration_s}s rest).",
    )


def create_wltp_class3_profile(
    peak_current_a: float = 50.0,
    time_scale_s: float = 1800.0,
    dt_s: float = 1.0,
    ambient_temp_c: float = 25.0,
    name: Optional[str] = None,
) -> DriveCycleProfile:
    """Generates a normalized WLTP (Worldwide Harmonized Light Vehicles Test Procedure) Class 3 profile.

    Synthesizes the four distinct speed phases (Low, Medium, High, Extra-High) with dynamic
    accelerations, cruise sections, and regenerative braking events.

    Args:
        peak_current_a: Peak discharge current in Amperes (> 0).
        time_scale_s: Profile total duration in seconds (standard is 1800.0s).
        dt_s: Sampling interval in seconds (> 0).
        ambient_temp_c: Ambient temperature in Celsius.
        name: Profile display name.

    Returns:
        DriveCycleProfile instance.
    """
    if peak_current_a <= 0:
        raise InvalidProfileError("peak_current_a must be strictly positive.")
    if time_scale_s <= 0 or dt_s <= 0:
        raise InvalidProfileError("time_scale_s and dt_s must be strictly positive.")

    points: list[ProfilePoint] = []
    t = 0.0

    # Synthetic multi-phase WLTP Class 3 acceleration/velocity profile
    while t <= time_scale_s + 1e-9:
        tau = t / time_scale_s  # Normalized time in [0, 1]

        # Phase 1: Low speed urban (0.0 to 0.3)
        if tau < 0.30:
            phase_tau = tau / 0.30
            raw_val = 0.35 * math.sin(2.0 * math.pi * 4.0 * phase_tau) + 0.20 * math.sin(2.0 * math.pi * 10.0 * phase_tau)
            # Add stop-and-go idle periods
            if (int(t) % 60) < 15:
                raw_val = 0.0

        # Phase 2: Medium speed suburban (0.3 to 0.55)
        elif tau < 0.55:
            phase_tau = (tau - 0.30) / 0.25
            raw_val = 0.55 * math.sin(2.0 * math.pi * 3.0 * phase_tau) + 0.30 * math.sin(2.0 * math.pi * 7.0 * phase_tau)

        # Phase 3: High speed rural (0.55 to 0.80)
        elif tau < 0.80:
            phase_tau = (tau - 0.55) / 0.25
            raw_val = 0.75 * math.sin(2.0 * math.pi * 2.0 * phase_tau) + 0.20 * math.cos(2.0 * math.pi * 5.0 * phase_tau)

        # Phase 4: Extra-high speed motorway (0.80 to 1.0)
        else:
            phase_tau = (tau - 0.80) / 0.20
            raw_val = 0.90 * math.sin(2.0 * math.pi * 1.5 * phase_tau) + 0.15 * math.sin(2.0 * math.pi * 4.0 * phase_tau)

        # Map raw normalized value to current (positive discharge, negative regen)
        # Scale regen to max 35% of peak discharge
        if raw_val >= 0:
            curr_a = clamp(raw_val, 0.0, 1.0) * peak_current_a
        else:
            curr_a = clamp(raw_val, -0.35, 0.0) * peak_current_a

        points.append(
            ProfilePoint(
                time_s=round(t, 6),
                current_a=round(curr_a, 4),
                ambient_temperature_c=float(ambient_temp_c),
            )
        )
        t += dt_s

    prof_name = name or f"WLTP_Class3_{peak_current_a}A_{int(time_scale_s)}s"
    return DriveCycleProfile(
        name=prof_name,
        points=tuple(points),
        description=f"Standard WLTP Class 3 drive cycle scaled to {peak_current_a}A peak.",
    )


def create_us06_profile(
    peak_current_a: float = 80.0,
    time_scale_s: float = 600.0,
    dt_s: float = 1.0,
    ambient_temp_c: float = 25.0,
    name: Optional[str] = None,
) -> DriveCycleProfile:
    """Generates an aggressive, high-acceleration US06 Supplemental Federal Test Procedure profile.

    Characterized by rapid accelerations, high cruising speeds, and aggressive regenerative braking.

    Args:
        peak_current_a: Peak acceleration discharge current in Amperes (> 0).
        time_scale_s: Total profile duration in seconds (standard is 600.0s).
        dt_s: Sampling step interval in seconds (> 0).
        ambient_temp_c: Ambient temperature in Celsius.
        name: Profile display name.

    Returns:
        DriveCycleProfile instance.
    """
    if peak_current_a <= 0:
        raise InvalidProfileError("peak_current_a must be strictly positive.")
    if time_scale_s <= 0 or dt_s <= 0:
        raise InvalidProfileError("time_scale_s and dt_s must be strictly positive.")

    points: list[ProfilePoint] = []
    t = 0.0

    while t <= time_scale_s + 1e-9:
        tau = t / time_scale_s
        # US06 high-frequency aggressive transients
        freq1 = math.sin(2.0 * math.pi * 8.0 * tau)
        freq2 = math.cos(2.0 * math.pi * 18.0 * tau)
        freq3 = math.sin(2.0 * math.pi * 2.0 * tau)

        raw = 0.50 * freq1 + 0.30 * freq2 + 0.40 * freq3

        # Add heavy acceleration spikes
        if 0.15 < tau < 0.25 or 0.65 < tau < 0.75:
            raw += 0.45

        # Limit and scale
        if raw >= 0:
            curr_a = clamp(raw, 0.0, 1.0) * peak_current_a
        else:
            curr_a = clamp(raw, -0.45, 0.0) * peak_current_a

        points.append(
            ProfilePoint(
                time_s=round(t, 6),
                current_a=round(curr_a, 4),
                ambient_temperature_c=float(ambient_temp_c),
            )
        )
        t += dt_s

    prof_name = name or f"US06_Aggressive_{peak_current_a}A_{int(time_scale_s)}s"
    return DriveCycleProfile(
        name=prof_name,
        points=tuple(points),
        description=f"Aggressive US06 drive cycle scaled to {peak_current_a}A peak.",
    )


def create_dst_profile(
    peak_discharge_a: float = 40.0,
    regenerative_charge_a: float = -20.0,
    cycles: int = 3,
    dt_s: float = 1.0,
    ambient_temp_c: float = 25.0,
    name: Optional[str] = None,
) -> DriveCycleProfile:
    """Generates the USABC Dynamic Stress Test (DST) 360-second power profile.

    Standard laboratory cycle containing 7 discrete power steps of varying discharge and charge.

    Args:
        peak_discharge_a: Peak discharge current in Amperes (> 0).
        regenerative_charge_a: Maximum regenerative charge current in Amperes (< 0).
        cycles: Number of 360-second DST cycle repetitions (>= 1).
        dt_s: Sampling interval in seconds (> 0).
        ambient_temp_c: Ambient temperature in Celsius.
        name: Profile display name.

    Returns:
        DriveCycleProfile instance.
    """
    if peak_discharge_a <= 0:
        raise InvalidProfileError("peak_discharge_a must be strictly positive.")
    if regenerative_charge_a >= 0:
        raise InvalidProfileError("regenerative_charge_a must be negative (< 0).")
    if cycles < 1 or dt_s <= 0:
        raise InvalidProfileError("cycles must be >= 1 and dt_s must be strictly positive.")

    # DST 360s standard schedule normalized steps (fraction of peak):
    # (duration_s, fraction_of_peak)
    dst_steps = [
        (16.0, 0.125),   # C/8 discharge
        (28.0, 0.250),   # C/4 discharge
        (12.0, 0.500),   # C/2 discharge
        (8.0, 1.000),    # 1C peak discharge
        (16.0, 0.000),   # Rest
        (24.0, -0.500),  # Regenerative braking
        (36.0, 0.250),   # Medium discharge
        (8.0, 0.750),    # High discharge
        (32.0, 0.125),   # Low discharge
        (180.0, 0.000),  # Extended rest
    ]

    points: list[ProfilePoint] = []
    t = 0.0

    for _ in range(cycles):
        for dur, frac in dst_steps:
            t_end = t + dur
            curr = frac * peak_discharge_a if frac >= 0 else abs(frac) * regenerative_charge_a
            while t < t_end - 1e-9:
                points.append(
                    ProfilePoint(
                        time_s=round(t, 6),
                        current_a=round(curr, 4),
                        ambient_temperature_c=float(ambient_temp_c),
                    )
                )
                t += dt_s

    # Final boundary point
    points.append(
        ProfilePoint(
            time_s=round(t, 6),
            current_a=0.0,
            ambient_temperature_c=float(ambient_temp_c),
        )
    )

    prof_name = name or f"DST_{peak_discharge_a}A_{cycles}cycles"
    return DriveCycleProfile(
        name=prof_name,
        points=tuple(points),
        description=f"USABC Dynamic Stress Test ({cycles} cycles of 360s).",
    )
