"""Transport schemas for the ephemeral Dataset Lab API."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class DatasetMappingDTO(BaseModel):
    column: Optional[str] = None
    unit: Optional[str] = None


class DatasetMappingRequestDTO(BaseModel):
    mappings: dict[str, DatasetMappingDTO] = Field(default_factory=dict)


class DatasetSummaryDTO(BaseModel):
    dataset_id: str
    filename: str
    created_at: str
    size_bytes: int
    row_count: int
    column_count: int
    profile: dict[str, Any]


class DatasetPreviewDTO(BaseModel):
    columns: list[str]
    offset: int
    limit: int
    total_rows: int
    rows: list[dict[str, Any]]


class DatasetSeriesDTO(BaseModel):
    points: list[dict[str, Any]]
    raw_row_count: int
    rendered_point_count: int
    stride: int
    downsampling: str
    x_axis: str
    x_min_ns: Optional[int] = None
    x_max_ns: Optional[int] = None
    derived: dict[str, Any]
