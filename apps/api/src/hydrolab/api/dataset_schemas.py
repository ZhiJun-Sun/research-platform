"""B2 数据 API Schema。"""

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from hydrolab.datasets.enums import (
    DataFormat,
    DatasetSourceType,
    FieldSemantic,
    ImportJobStatus,
)


class FolderCreate(BaseModel):
    name: str
    parent_id: UUID | None = None


class FolderMove(BaseModel):
    parent_id: UUID | None = None


class FolderView(BaseModel):
    id: UUID
    name: str
    parent_id: UUID | None
    path_key: str


class DatasetCreate(BaseModel):
    name: str
    folder_id: UUID | None = None
    description: str = ""


class DatasetView(BaseModel):
    id: UUID
    name: str
    folder_id: UUID | None
    description: str


class ImportCreate(BaseModel):
    dataset_id: UUID
    source_type: DatasetSourceType
    source_url: str | None = None


class FakeUpload(BaseModel):
    filename: str
    content: str
    # xlsx/zip 等二进制数据必须以 base64 传输；文本格式（csv）可直接传原文。
    content_encoding: Literal["text", "base64"] = "text"


class MappingItem(BaseModel):
    source_name: str
    standard_name: str | None = None
    semantic: FieldSemantic
    unit: str | None = None
    order: int = 0
    confidence: float = Field(default=0, ge=0, le=1)
    user_modified: bool = True


class MappingConfirm(BaseModel):
    items: list[MappingItem]


class ImportView(BaseModel):
    id: UUID
    dataset_id: UUID
    status: ImportJobStatus
    source_type: DatasetSourceType
    detected_format: DataFormat
    progress: int
    error_code: str | None = None


class VersionView(BaseModel):
    id: UUID
    version_no: int
    status: str
    content_hash: str | None
    manifest: dict[str, Any]
