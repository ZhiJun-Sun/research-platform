"""B2 文件夹、数据集、版本、导入、字段映射与 Artifact 领域实体。"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from hydrolab.datasets.enums import (
    ArtifactKind,
    ArtifactStatus,
    DataFormat,
    DatasetSourceType,
    DatasetVersionStatus,
    FieldSemantic,
    ImportJobStatus,
)
from hydrolab.domain.entities import utcnow


class AssetFolder(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    parent_id: UUID | None = None
    name: str
    path_key: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class Dataset(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    folder_id: UUID | None = None
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class DatasetVersion(BaseModel):
    """READY 后不可修改内容字段；映射修正必须创建新版本。"""

    id: UUID = Field(default_factory=uuid4)
    dataset_id: UUID
    version_no: int
    source_type: DatasetSourceType
    status: DatasetVersionStatus = DatasetVersionStatus.PENDING
    object_prefix: str
    manifest: dict[str, Any] = Field(default_factory=dict)
    content_hash: str | None = None
    parent_version_id: UUID | None = None
    frozen_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class Artifact(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    resource_type: str
    resource_id: UUID
    kind: ArtifactKind
    object_key: str
    media_type: str = "application/octet-stream"
    size_bytes: int = 0
    sha256: str | None = None
    status: ArtifactStatus = ArtifactStatus.PENDING_UPLOAD
    created_at: datetime = Field(default_factory=utcnow)


class FieldMappingItem(BaseModel):
    source_name: str
    standard_name: str | None = None
    semantic: FieldSemantic = FieldSemantic.IGNORE
    unit: str | None = None
    order: int = 0
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    user_modified: bool = False


class FieldMapping(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    import_job_id: UUID
    items: list[FieldMappingItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)
    confirmed_at: datetime | None = None


class DatasetImportJob(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    dataset_id: UUID
    source_type: DatasetSourceType
    status: ImportJobStatus = ImportJobStatus.CREATED
    source_url: str | None = None
    source_version_id: UUID | None = None
    artifact_id: UUID | None = None
    detected_format: DataFormat = DataFormat.UNKNOWN
    # BUNDLE 格式下的包内文件清单（探测阶段写入，供冻结与物化使用）
    bundle_entries: list[str] = Field(default_factory=list)
    progress: int = Field(default=0, ge=0, le=100)
    error_code: str | None = None
    error_message: str | None = None
    idempotency_key: str | None = None
    retry_of_job_id: UUID | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
