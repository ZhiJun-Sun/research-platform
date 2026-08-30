"""B7 Checkpoint 复用与兼容性领域模型。"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from hydrolab.domain.entities import utcnow


class CheckpointMode(StrEnum):
    RESUME = "RESUME"
    FINETUNE = "FINETUNE"
    EVALUATE = "EVALUATE"
    PREDICT = "PREDICT"


class CompatibilityStatus(StrEnum):
    COMPATIBLE = "COMPATIBLE"
    REPAIRABLE = "REPAIRABLE"
    INCOMPATIBLE = "INCOMPATIBLE"


class Checkpoint(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    source_run_id: UUID
    source_experiment_version_id: UUID
    artifact_key: str
    artifact_sha256: str
    model_signature: str
    feature_names: list[str] = Field(default_factory=list)
    target_names: list[str] = Field(default_factory=list)
    scaler_signature: str | None = None
    optimizer_included: bool = False
    scheduler_included: bool = False
    source_config: dict[str, Any]
    created_at: datetime = Field(default_factory=utcnow)


class RepairAction(BaseModel):
    code: str
    title: str
    required: bool = True
    details: dict[str, Any] = Field(default_factory=dict)


class CompatibilityReport(BaseModel):
    checkpoint_id: UUID
    mode: CheckpointMode
    status: CompatibilityStatus
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    repair_plan: list[RepairAction] = Field(default_factory=list)
    checked_at: datetime = Field(default_factory=utcnow)
