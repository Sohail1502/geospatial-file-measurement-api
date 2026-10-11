from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class FileInfoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    filename: str
    feature_count: int
    crs: Optional[str]
    status: str
    error_message: Optional[str] = None
    created_at: datetime


class FeatureMeasurement(BaseModel):
    feature_id: int | str
    geometry_type: str
    geometry: dict[str, Any]
    crs: str
    properties: dict[str, Any] = Field(default_factory=dict)
    measurement_type: Optional[str] = None
    value: Optional[float] = None
    unit: Optional[str] = None
    projected_crs: Optional[str] = None
    note: Optional[str] = None


class MeasurementsResponse(BaseModel):
    id: str
    filename: str
    status: str
    source_crs: Optional[str]
    feature_count: int
    features: list[FeatureMeasurement]
