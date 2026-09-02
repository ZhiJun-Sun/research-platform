"""B8 结果、诊断、绘图和对比领域实体。"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from hydrolab.domain.entities import utcnow


class Result(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    owner_id: UUID
    dataset_version_id: str
    created_at: datetime = Field(default_factory=utcnow)


class MetricPoint(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    result_id: UUID
    name: str
    value: float
    split: str = "test"
    horizon: int | None = None
    basin_id: str | None = None
    event_id: str | None = None


class ResultArtifact(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    result_id: UUID
    kind: str
    object_key: str
    sha256: str


class PlotSpec(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    result_ids: list[UUID]
    plot_type: str
    data_selection: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)
    script_ref: str = "hydrolab.plot.v1"
    created_at: datetime = Field(default_factory=utcnow)


class ExportManifest(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    result_ids: list[UUID]
    artifact_ids: list[UUID]
    manifest: dict[str, Any]
    created_at: datetime = Field(default_factory=utcnow)
