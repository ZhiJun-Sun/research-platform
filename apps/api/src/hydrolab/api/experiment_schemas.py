"""B4 实验和 Run API Schema。"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from hydrolab.experiments.enums import DraftStatus, RunStatus


class DraftCreate(BaseModel):
    name: str
    description: str = ""


class DraftUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    dataset_version_id: UUID | None = None
    code_version_id: UUID | None = None
    template_version_id: UUID | None = None
    environment_version_id: UUID | None = None
    parameter_values: dict[str, Any] | None = None


class DraftView(BaseModel):
    id: UUID
    name: str
    description: str
    dataset_version_id: UUID | None
    code_version_id: UUID | None
    template_version_id: UUID | None
    environment_version_id: UUID | None
    parameter_values: dict[str, Any]
    status: DraftStatus


class ExperimentView(BaseModel):
    id: UUID
    name: str
    description: str


class ExperimentVersionView(BaseModel):
    id: UUID
    version_no: int
    resolved_config: dict[str, Any]
    config_hash: str


class RunView(BaseModel):
    id: UUID
    experiment_id: UUID
    experiment_version_id: UUID
    status: RunStatus


class SubmitResponse(BaseModel):
    experiment: ExperimentView
    version: ExperimentVersionView
    run: RunView


class BatchSubmitInput(BaseModel):
    """One immutable Run is created for each selected data version."""

    name_prefix: str
    description: str = ""
    dataset_version_ids: list[UUID]
    code_version_id: UUID
    template_version_id: UUID
    environment_version_id: UUID
    parameter_values: dict[str, Any] = Field(default_factory=dict)
    dry_run: bool = False


class BatchSubmitItem(BaseModel):
    dataset_version_id: UUID
    name: str
    argv: list[str]
    parameter_values: dict[str, Any]
    run: RunView | None = None


class BatchSubmitResponse(BaseModel):
    dry_run: bool
    items: list[BatchSubmitItem]


class RunStageView(BaseModel):
    name: str
    position: int
    status: RunStatus
