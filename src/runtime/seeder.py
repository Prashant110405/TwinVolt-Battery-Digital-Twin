"""Default Battery Profiles and Digital Twin Instance Seeder.

Provides automatic declarative loading of configured battery pack profiles and
initialization of default digital twin instances for development and production workstations.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Optional

from src.api.dependencies import ServiceContainer
from src.estimators.ekf import ExtendedKalmanFilter
from src.models.ecm.generic_ecm import GenericECMModel
from src.models.ecm.parameters import GenericECMParameters, RCBranchParameters
from src.models.parameters.linear_ocv import LinearOCVModel
from src.models.types import ModelMetadata

logger = logging.getLogger("twinvolt.seeder")


def seed_default_twins_and_packs(
    services: ServiceContainer,
    profiles_dir: Optional[Path] = None,
) -> None:
    """Seeds available battery profiles and initializes a default prototype digital twin if none exist.

    Args:
        services: Active ServiceContainer holding domain and application services.
        profiles_dir: Directory containing YAML battery pack profiles.
    """
    if profiles_dir is None:
        profiles_dir = Path(__file__).resolve().parent.parent.parent / "config" / "battery_profiles"

    if not profiles_dir.is_dir():
        return

    # 1. Seed battery pack profiles from YAML
    for yaml_file in sorted(profiles_dir.glob("*.yaml")):
        try:
            pack = services.pack_service.create_pack_from_file(yaml_file, overwrite=False)
            logger.info("Loaded battery pack profile: %s", pack.pack_id)
        except Exception as exc:
            logger.debug("Skipping existing or unreadable profile %s: %s", yaml_file.name, exc)

    # 2. Seed default digital twin if none currently exist
    if not services.twin_service.list_active_twins():
        prototype_pack = None
        try:
            prototype_pack = services.pack_service.get_pack("batt_nmc_3s1p_prototype")
        except Exception:
            existing = services.pack_service.list_packs()
            if existing:
                prototype_pack = existing[0]

        if prototype_pack is not None:
            v_min = prototype_pack.configuration.electrical_ratings.min_voltage_v
            v_max = prototype_pack.configuration.electrical_ratings.max_voltage_v
            nom_v = prototype_pack.configuration.electrical_ratings.nominal_voltage_v
            nom_cap = prototype_pack.configuration.electrical_ratings.nominal_capacity_ah

            ocv = LinearOCVModel(v_min_v=v_min, v_max_v=v_max)
            params = GenericECMParameters(
                nominal_capacity_ah=nom_cap,
                nominal_voltage_v=nom_v,
                series_resistance_r0_ohm=0.025,
                rc_branches=(
                    RCBranchParameters(resistance_r_ohm=0.015, capacitance_c_farad=120.0),
                ),
            )
            meta = ModelMetadata(
                model_id="ecm_twin_prototype",
                name="NMC 3S1P Prototype Twin",
                paradigm="EQUIVALENT_CIRCUIT",
            )
            model = GenericECMModel(metadata=meta, parameters=params, ocv_model=ocv)
            estimator = ExtendedKalmanFilter(
                estimator_id="ekf_twin_prototype",
                parameters=params,
                ocv_model=ocv,
            )

            twin = services.twin_service.create_twin(
                system_id="twin_prototype_3s1p",
                battery_pack=prototype_pack,
                battery_model=model,
                state_estimator=estimator,
            )
            twin.initialize(initial_soc=0.92, initial_temperature_c=25.0)
            logger.info("Seeded and initialized default digital twin: %s", twin.system_id)


def seed_benchmark_datasets(services: ServiceContainer) -> None:
    """Seeds synthetic demonstration benchmark datasets into the BenchmarkService.

    Registers two ready-to-use reference datasets so the Benchmarking view is populated
    on every cold start without requiring user uploads.

    Args:
        services: Active ServiceContainer with an accessible benchmark_service.
    """
    try:
        from src.benchmarking.dataset import DatasetBuilder, DatasetMetadata, ReferenceObservationFrame
        from src.benchmarking.types import (
            BenchmarkSignalType,
            CalibrationStatus,
            EvidenceRole,
            ReferenceMeasurement,
            ReferenceProvenance,
            ReferenceSignalChannel,
            ReferenceSourceType,
        )
        from src.services.exceptions import DuplicateEntityError
    except ImportError as exc:
        logger.warning("Could not import benchmarking types for seeding: %s", exc)
        return

    # Shared synthetic provenance record
    synth_prov = ReferenceProvenance(
        provenance_id="prov_synthetic_math_gen_v1",
        source_type=ReferenceSourceType.SYNTHETIC_MATHEMATICAL_GENERATOR,
        calibration_status=CalibrationStatus.FACTORY_NOMINAL,
        evidence_role=EvidenceRole.SYNTHETIC_REFERENCE,
        measurement_method="Analytical ECM simulation with linear OCV and Gaussian noise envelope",
        instrument_identifier="TwinVolt-SyntheticGen-v1.0",
        facility_or_environment="TwinVolt Seeder",
    )

    # ── Dataset 1: NMC Constant-Current Discharge Cycle ──────────────────────
    ds1_id = "ds_nmc_cc_discharge_demo_v1"
    if ds1_id not in {d["dataset_id"] for d in services.benchmark_service.list_datasets()}:
        try:
            meta1 = DatasetMetadata(
                dataset_id=ds1_id,
                dataset_name="NMC 3S1P — Constant-Current Discharge (Demo)",
                version="1.0.0",
                created_at_utc="2024-01-15T10:00:00Z",
                facility_or_provider="TwinVolt Synthetic Generator",
                operator_name="TwinVolt Seeder",
                test_bench_identifier="SYNTH-NMC-CC-01",
                description=(
                    "Synthetic 1 C-rate constant-current discharge profile for an NMC 3S1P "
                    "pack from 100 % to 10 % SOC. Voltage and current traces are generated "
                    "from an analytical ECM with a linear OCV model and 0.5 % Gaussian noise. "
                    "Use this dataset to validate the EKF SOC estimator against a known profile."
                ),
            )
            voltage_ch = ReferenceSignalChannel(
                signal_name="pack_voltage_v",
                signal_type=BenchmarkSignalType.VOLTAGE,
                unit="V",
                provenance=synth_prov,
                nominal_sampling_rate_hz=1.0,
                nominal_uncertainty_absolute=0.01,
            )
            current_ch = ReferenceSignalChannel(
                signal_name="pack_current_a",
                signal_type=BenchmarkSignalType.CURRENT,
                unit="A",
                provenance=synth_prov,
                nominal_sampling_rate_hz=1.0,
                nominal_uncertainty_absolute=0.05,
            )
            soc_ch = ReferenceSignalChannel(
                signal_name="soc_reference",
                signal_type=BenchmarkSignalType.SOC,
                unit="fraction",
                provenance=synth_prov,
                nominal_sampling_rate_hz=1.0,
                nominal_uncertainty_absolute=0.005,
            )

            builder1 = DatasetBuilder(meta1)
            builder1.add_reference_channel(voltage_ch)
            builder1.add_reference_channel(current_ch)
            builder1.add_reference_channel(soc_ch)

            # 91 frames: SOC 1.0 → 0.10 in steps of 0.01, every 10 s
            v_min, v_max = 9.0, 12.6   # 3S NMC: 3.0–4.2 V × 3
            discharge_current_a = -5.0  # 1 C for ~5 Ah pack
            import random
            rng = random.Random(42)
            base_ts = 1_705_312_800_000_000_000  # 2024-01-15 10:00:00 UTC in ns
            step_ns = 10_000_000_000              # 10 s

            for i in range(91):
                ts = base_ts + i * step_ns
                soc = round(1.0 - i * 0.01, 3)
                voltage = v_min + soc * (v_max - v_min) + rng.gauss(0, 0.005)
                voltage = max(v_min, min(v_max, voltage))
                current = discharge_current_a + rng.gauss(0, 0.025)

                frame = ReferenceObservationFrame(
                    timestamp_ns=ts,
                    sequence_number=i,
                    reference_signals={
                        "pack_voltage_v": ReferenceMeasurement(
                            value=round(voltage, 4),
                            unit="V",
                            timestamp_ns=ts,
                            signal_type=BenchmarkSignalType.VOLTAGE,
                            uncertainty_absolute=0.01,
                            provenance=synth_prov,
                        ),
                        "pack_current_a": ReferenceMeasurement(
                            value=round(current, 4),
                            unit="A",
                            timestamp_ns=ts,
                            signal_type=BenchmarkSignalType.CURRENT,
                            uncertainty_absolute=0.05,
                            provenance=synth_prov,
                        ),
                        "soc_reference": ReferenceMeasurement(
                            value=soc,
                            unit="fraction",
                            timestamp_ns=ts,
                            signal_type=BenchmarkSignalType.SOC,
                            uncertainty_absolute=0.005,
                            provenance=synth_prov,
                        ),
                    },
                    field_signals={
                        "temperature_c": round(25.0 + rng.gauss(0, 0.2), 2),
                    },
                    operating_context_hint="CC_DISCHARGE_1C",
                )
                builder1.add_frame(frame)

            services.benchmark_service.register_dataset(builder1.build())
            logger.info("Seeded benchmark dataset: %s", ds1_id)
        except DuplicateEntityError:
            pass
        except Exception as exc:
            logger.warning("Failed to seed benchmark dataset '%s': %s", ds1_id, exc)

    # ── Dataset 2: NMC Drive-Cycle Pulse Profile ──────────────────────────────
    ds2_id = "ds_nmc_drive_cycle_pulse_demo_v1"
    if ds2_id not in {d["dataset_id"] for d in services.benchmark_service.list_datasets()}:
        try:
            meta2 = DatasetMetadata(
                dataset_id=ds2_id,
                dataset_name="NMC 3S1P — Drive-Cycle Pulse Profile (Demo)",
                version="1.0.0",
                created_at_utc="2024-02-20T08:30:00Z",
                facility_or_provider="TwinVolt Synthetic Generator",
                operator_name="TwinVolt Seeder",
                test_bench_identifier="SYNTH-NMC-PULSE-01",
                description=(
                    "Synthetic variable-current drive-cycle profile with alternating discharge "
                    "and regenerative-braking pulses. Designed to stress-test the EKF estimator "
                    "under dynamic current inputs. SOH is held at 95 % throughout. "
                    "120 frames at 5-second intervals."
                ),
            )
            voltage_ch2 = ReferenceSignalChannel(
                signal_name="pack_voltage_v",
                signal_type=BenchmarkSignalType.VOLTAGE,
                unit="V",
                provenance=synth_prov,
                nominal_sampling_rate_hz=0.2,
                nominal_uncertainty_absolute=0.015,
            )
            current_ch2 = ReferenceSignalChannel(
                signal_name="pack_current_a",
                signal_type=BenchmarkSignalType.CURRENT,
                unit="A",
                provenance=synth_prov,
                nominal_sampling_rate_hz=0.2,
                nominal_uncertainty_absolute=0.1,
            )

            builder2 = DatasetBuilder(meta2)
            builder2.add_reference_channel(voltage_ch2)
            builder2.add_reference_channel(current_ch2)

            v_min2, v_max2 = 9.0, 12.6
            rng2 = random.Random(99)
            base_ts2 = 1_708_417_800_000_000_000  # 2024-02-20 08:30:00 UTC in ns
            step_ns2 = 5_000_000_000               # 5 s
            soc2 = 0.85

            pulse_pattern = [
                -8.0, -8.0, -8.0, 3.0, -8.0, -6.0, -10.0, 4.0, -8.0, -8.0,
            ]

            for i in range(120):
                ts2 = base_ts2 + i * step_ns2
                current2 = pulse_pattern[i % len(pulse_pattern)] + rng2.gauss(0, 0.15)
                # Approximate Coulomb-counting SOC update (5 s step, ~5 Ah nominal)
                soc2 = max(0.05, min(1.0, soc2 + current2 * (5.0 / 3600.0) / 5.0))
                voltage2 = v_min2 + soc2 * (v_max2 - v_min2) - abs(current2) * 0.04 + rng2.gauss(0, 0.008)
                voltage2 = max(v_min2, min(v_max2, voltage2))

                frame2 = ReferenceObservationFrame(
                    timestamp_ns=ts2,
                    sequence_number=i,
                    reference_signals={
                        "pack_voltage_v": ReferenceMeasurement(
                            value=round(voltage2, 4),
                            unit="V",
                            timestamp_ns=ts2,
                            signal_type=BenchmarkSignalType.VOLTAGE,
                            uncertainty_absolute=0.015,
                            provenance=synth_prov,
                        ),
                        "pack_current_a": ReferenceMeasurement(
                            value=round(current2, 4),
                            unit="A",
                            timestamp_ns=ts2,
                            signal_type=BenchmarkSignalType.CURRENT,
                            uncertainty_absolute=0.1,
                            provenance=synth_prov,
                        ),
                    },
                    field_signals={
                        "temperature_c": round(28.0 + rng2.gauss(0, 0.5), 2),
                        "soc_coulomb_count": round(soc2, 4),
                    },
                    operating_context_hint="DRIVE_CYCLE_PULSE",
                )
                builder2.add_frame(frame2)

            services.benchmark_service.register_dataset(builder2.build())
            logger.info("Seeded benchmark dataset: %s", ds2_id)
        except DuplicateEntityError:
            pass
        except Exception as exc:
            logger.warning("Failed to seed benchmark dataset '%s': %s", ds2_id, exc)
