"""Default Battery Profiles and Digital Twin Instance Seeder.

Provides automatic declarative loading of configured battery pack profiles and
initialization of default digital twin instances for development and production workstations.
"""

from __future__ import annotations

import logging
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
