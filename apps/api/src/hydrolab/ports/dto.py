"""端口层共享 DTO。

约束：
- 只使用标准库与 pydantic 类型，第三方 SDK 类型不得进入此模块；
- 外部系统 ID 仅作关联字段，业务真相源始终是 HydroLab PostgreSQL。
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------- ObjectStorage ----------
class ObjectRef(BaseModel):
    """对象引用。bucket 由部署配置决定时可省略。"""

    bucket: str | None = None
    key: str
    version_id: str | None = None


class UploadRequest(BaseModel):
    key: str
    size_bytes: int
    content_type: str = "application/octet-stream"
    sha256: str | None = None
    multipart: bool = False


class UploadSession(BaseModel):
    session_id: str
    key: str
    upload_url: str | None = None  # 预签名直传时提供；服务端中转时为空
    part_size: int | None = None
    expires_at: datetime


class UploadedPart(BaseModel):
    part_number: int
    etag: str
    size_bytes: int


class ObjectInfo(BaseModel):
    key: str
    size_bytes: int
    sha256: str | None = None
    etag: str | None = None
    version_id: str | None = None
    content_type: str = "application/octet-stream"


# ---------- TaskQueue ----------
class TaskEnvelope(BaseModel):
    """队列消息契约 v1：只携带稳定 ID，不传 ORM 对象/Secret/大配置。"""

    schema_version: Literal[1] = 1
    job_id: UUID = Field(default_factory=uuid4)
    job_type: str
    resource_id: UUID | None = None
    attempt: int = 1
    correlation_id: UUID = Field(default_factory=uuid4)
    not_before: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EnqueueReceipt(BaseModel):
    job_id: UUID
    external_task_id: str
    queue: str


# ---------- ExperimentTracker ----------
class TrackingContext(BaseModel):
    run_id: UUID
    experiment_version_id: UUID
    display_name: str
    tags: dict[str, str] = Field(default_factory=dict)


class ExternalRunRef(BaseModel):
    """外部跟踪系统 Run 引用（如 mlflow_run_id）。"""

    system: str  # "mlflow" | "none"
    external_run_id: str


class MetricRecord(BaseModel):
    name: str
    value: float
    step: int | None = None
    timestamp: datetime | None = None
    split: str | None = None
    basin_id: str | None = None


class ArtifactReference(BaseModel):
    artifact_id: UUID
    kind: str
    uri: str
    sha256: str | None = None


# ---------- RunExecutor ----------
class RunSpec(BaseModel):
    """Runner 唯一输入。命令为 argv 形式，禁止 shell 拼接。"""

    run_id: UUID
    argv: list[str]
    image_digest: str
    gpu_count: int = 0
    env: dict[str, str] = Field(default_factory=dict)
    read_only_mounts: list[str] = Field(default_factory=list)
    writable_mount: str | None = None
    timeout_seconds: int = 24 * 3600


class RunState(StrEnum):
    QUEUED = "QUEUED"
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    EVALUATING = "EVALUATING"
    PLOTTING = "PLOTTING"
    UPLOADING = "UPLOADING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLING = "CANCELLING"
    CANCELLED = "CANCELLED"


class RunHandle(BaseModel):
    run_id: UUID
    external_id: str
    state: RunState


class RunStatusSnapshot(BaseModel):
    run_id: UUID
    state: RunState
    exit_code: int | None = None
    message: str | None = None


class EventType(StrEnum):
    STATUS_CHANGED = "run.status.changed"
    STAGE_CHANGED = "run.stage.changed"
    PROGRESS_UPDATED = "run.progress.updated"
    METRIC_REPORTED = "run.metric.reported"
    LOG_AVAILABLE = "run.log.available"
    RESOURCE_SAMPLED = "run.resource.sampled"
    ARTIFACT_CREATED = "run.artifact.created"
    FAILED = "run.failed"
    COMPLETED = "run.completed"


class NormalizedRunEvent(BaseModel):
    """归一化 Run 事件（SSE / run_events 表共用，对应 contracts/events v1）。"""

    schema_version: Literal[1] = 1
    event_type: EventType
    run_id: UUID
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
