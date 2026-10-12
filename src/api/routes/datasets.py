"""Ephemeral dataset upload, profiling, preview, mapping and bounded series API."""

import os
from fastapi import APIRouter, HTTPException, Query, Request, status

from src.api.schemas.dataset import (
    DatasetMappingRequestDTO,
    DatasetPreviewDTO,
    DatasetSeriesDTO,
    DatasetSummaryDTO,
)
from src.services.dataset_lab import DatasetError, DatasetLabStore

router = APIRouter(prefix="/api/v1/datasets", tags=["Dataset Lab"])
DEFAULT_MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _store(request: Request) -> DatasetLabStore:
    store = getattr(request.app.state, "dataset_lab_store", None)
    if store is None:
        store = DatasetLabStore()
        request.app.state.dataset_lab_store = store
    return store


def _not_found(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail="Dataset was not found or its temporary session expired.")


@router.post("", response_model=DatasetSummaryDTO, status_code=status.HTTP_201_CREATED,
             summary="Upload and profile a temporary dataset")
async def upload_dataset(request: Request, filename: str = Query(..., min_length=1, max_length=255)) -> DatasetSummaryDTO:
    """Accepts raw CSV/JSON bytes. MIME type is ignored; the filename extension and contents are validated."""
    try:
        max_bytes = int(os.environ.get("TWINVOLT_DATASET_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES))
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Dataset upload limit is invalid in server configuration.") from exc
    if max_bytes <= 0:
        raise HTTPException(status_code=503, detail="Dataset upload is disabled by server configuration.")
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > max_bytes:
            raise HTTPException(status_code=413, detail=f"Upload exceeds the configured {max_bytes:,}-byte limit.")
        chunks.append(chunk)
    safe_name = filename.replace("\\", "/").split("/")[-1].strip()
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(status_code=422, detail="A simple filename is required.")
    try:
        result = _store(request).add(safe_name[:255], b"".join(chunks))
    except DatasetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DatasetSummaryDTO(**result)


@router.get("", response_model=list[DatasetSummaryDTO], summary="List temporary datasets")
async def list_datasets(request: Request) -> list[DatasetSummaryDTO]:
    return [DatasetSummaryDTO(**item) for item in _store(request).list()]


@router.get("/{dataset_id}", response_model=DatasetSummaryDTO, summary="Get dataset profile and quality report")
async def get_dataset(dataset_id: str, request: Request) -> DatasetSummaryDTO:
    try:
        return DatasetSummaryDTO(**_store(request).get(dataset_id))
    except KeyError as exc:
        raise _not_found(exc) from exc


@router.get("/{dataset_id}/preview", response_model=DatasetPreviewDTO, summary="Preview a bounded set of source rows")
async def preview_dataset(dataset_id: str, request: Request, offset: int = Query(0, ge=0), limit: int = Query(25, ge=1, le=100)) -> DatasetPreviewDTO:
    try:
        return DatasetPreviewDTO(**_store(request).preview(dataset_id, offset, limit))
    except KeyError as exc:
        raise _not_found(exc) from exc


@router.put("/{dataset_id}/mappings", response_model=DatasetSummaryDTO, summary="Confirm explicit quantity mappings and units")
async def map_dataset(dataset_id: str, payload: DatasetMappingRequestDTO, request: Request) -> DatasetSummaryDTO:
    try:
        result = _store(request).map_columns(dataset_id, {key: value.model_dump() for key, value in payload.mappings.items()})
        return DatasetSummaryDTO(**result)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except DatasetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{dataset_id}/series", response_model=DatasetSeriesDTO, summary="Query explicitly mapped series with bounded downsampling")
async def dataset_series(
    dataset_id: str, request: Request, columns: list[str] = Query(..., min_length=1), limit: int = Query(1500, ge=1, le=2000)
) -> DatasetSeriesDTO:
    try:
        result = _store(request).series(dataset_id, list(dict.fromkeys(name for name in columns if name)), limit)
        return DatasetSeriesDTO(**result)
    except KeyError as exc:
        raise _not_found(exc) from exc
    except DatasetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a temporary dataset")
async def delete_dataset(dataset_id: str, request: Request) -> None:
    try:
        _store(request).delete(dataset_id)
    except KeyError as exc:
        raise _not_found(exc) from exc
