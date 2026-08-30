"""B5/B6 执行控制与观测实体。"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from hydrolab.domain.entities import utcnow
from hydrolab.ports.dto import EventType


class GpuLease(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    gpu_index: int
    run_id: UUID
    expires_at: datetime
    heartbeat_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)


class RunExecution(BaseModel):
    run_id: UUID
    external_id: str
    gpu_indices: list[int]
    started_at: datetime = Field(default_factory=utcnow)
    timeout_seconds: int


class RunEvent(BaseModel):
    id: int
    event_type: EventType
    run_id: UUID
    occurred_at: datetime = Field(default_factory=utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)


class RunLogChunk(BaseModel):
    id: int
    run_id: UUID
    content: str
    stream: str = "stdout"
    created_at: datetime = Field(default_factory=utcnow)


class ResourceSample(BaseModel):
    run_id: UUID
    gpu_index: int
    utilization_percent: float = Field(ge=0, le=100)
    memory_used_mb: int = Field(ge=0)
    memory_total_mb: int = Field(gt=0)
    sampled_at: datetime = Field(default_factory=utcnow)
