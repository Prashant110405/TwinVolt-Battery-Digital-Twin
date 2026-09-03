from typing import Any
from fastapi import APIRouter, Depends, status

from src.api.dependencies import get_pack_service
from src.api.schemas.pack import (
    BatteryPackResponseDTO,
    BatteryProfileCreateDTO,
    PackListResponseDTO,
)
from src.domain.battery.entities import BatteryPack
from src.services.pack_service import PackManagementService

router = APIRouter(prefix="/api/v1/packs", tags=["Battery Packs"])


def _serialize_pack(pack: BatteryPack) -> BatteryPackResponseDTO:
    """Helper transforming a domain BatteryPack into an API response DTO."""
    chemistry_val = "UNKNOWN"
    if pack.modules and hasattr(pack.modules[0], "config") and hasattr(pack.modules[0].config, "cell_config"):
        chem = pack.modules[0].config.cell_config.chemistry
        chemistry_val = chem.value if hasattr(chem, "value") else str(chem)

    return BatteryPackResponseDTO(
        pack_id=pack.pack_id,
        display_name=pack.identification.display_name,
        manufacturer=pack.identification.manufacturer,
        chemistry=chemistry_val,
        series_count=pack.series_count,
        parallel_count=pack.parallel_count,
        total_cell_count=pack.total_cell_count,
        total_module_count=pack.total_module_count,
        nominal_voltage_v=pack.nominal_voltage_v,
        nominal_capacity_ah=pack.nominal_capacity_ah,
        nominal_energy_wh=pack.nominal_energy_wh,
        min_pack_voltage_v=pack.configuration.electrical_ratings.min_voltage_v,
        max_pack_voltage_v=pack.configuration.electrical_ratings.max_voltage_v,
    )


@router.post(
    "",
    response_model=BatteryPackResponseDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Register Battery Pack from Declarative Profile",
)
async def create_pack(
    payload: BatteryProfileCreateDTO,
    pack_service: PackManagementService = Depends(get_pack_service),
) -> BatteryPackResponseDTO:
    """Parses a declarative battery profile specification and registers the resulting BatteryPack domain entity."""
    pack = pack_service.create_pack_from_profile(payload.model_dump())
    return _serialize_pack(pack)


@router.get(
    "",
    response_model=PackListResponseDTO,
    summary="List All Registered Battery Packs",
)
async def list_packs(
    pack_service: PackManagementService = Depends(get_pack_service),
) -> PackListResponseDTO:
    """Returns a collection of all registered battery packs in the platform."""
    packs = pack_service.list_packs()
    return PackListResponseDTO(
        packs=[_serialize_pack(p) for p in packs],
        total_count=len(packs),
    )


@router.get(
    "/{pack_id}",
    response_model=BatteryPackResponseDTO,
    summary="Get Battery Pack Details",
)
async def get_pack(
    pack_id: str,
    pack_service: PackManagementService = Depends(get_pack_service),
) -> BatteryPackResponseDTO:
    """Retrieves full specification metadata for a specific registered battery pack."""
    pack = pack_service.get_pack(pack_id)
    return _serialize_pack(pack)


@router.delete(
    "/{pack_id}",
    summary="Delete Battery Pack",
)
async def delete_pack(
    pack_id: str,
    pack_service: PackManagementService = Depends(get_pack_service),
) -> dict[str, Any]:
    """Deletes a battery pack from the active registry."""
    deleted = pack_service.delete_pack(pack_id)
    return {"deleted": deleted, "pack_id": pack_id}
