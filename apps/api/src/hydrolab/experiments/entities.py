"""B4 Draft、Experiment、冻结版本、Run 与 Outbox 实体。"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from hydrolab.domain.entities import utcnow
from hydrolab.experiments.enums import DraftStatus, OutboxStatus, RunStageName, RunStatus


class ExperimentDraft(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    name: str
    description: str = ""
    dataset_version_id: UUID | None = None
    code_version_id: UUID | None = None
    template_version_id: UUID | None = None
    environment_version_id: UUID | None = None
    parameter_values: dict[str, Any] = Field(default_factory=dict)
    status: DraftStatus = DraftStatus.ACTIVE
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Experiment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ExperimentVersion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    experiment_id: UUID
    version_no: int
    resolved_config: dict[str, Any]
    config_hash: str
    frozen_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)


class Run(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    experiment_id: UUID
    experiment_version_id: UUID
    owner_id: UUID
    status: RunStatus = RunStatus.QUEUED
    idempotency_key: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class RunStage(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    name: RunStageName
    position: int
    status: RunStatus = RunStatus.QUEUED
    created_at: datetime = Field(default_factory=utcnow)


class OutboxEvent(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    aggregate_type: str
    aggregate_id: UUID
    topic: str
    payload: dict[str, Any]
    status: OutboxStatus = OutboxStatus.PENDING
    created_at: datetime = Field(default_factory=utcnow)
    published_at: datetime | None = None
