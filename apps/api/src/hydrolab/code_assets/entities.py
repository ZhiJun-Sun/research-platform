"""B3 版本化代码、模板、环境与预设实体。"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from hydrolab.code_assets.enums import (
    CodeSourceType,
    CodeVersionStatus,
    EnvironmentStatus,
    ParameterType,
    TemplateMode,
)
from hydrolab.domain.entities import utcnow


class CodeRepository(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class CodeVersion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    repository_id: UUID
    version_no: int
    source_type: CodeSourceType
    status: CodeVersionStatus = CodeVersionStatus.PENDING
    object_key: str | None = None
    source_ref: str | None = None
    commit_sha: str | None = None
    content_hash: str | None = None
    manifest: dict[str, Any] = Field(default_factory=dict)
    frozen_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ExperimentTemplate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    code_repository_id: UUID
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class ParameterDefinition(BaseModel):
    key: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    label: str
    type: ParameterType
    required: bool = False
    default: Any = None
    minimum: float | None = None
    maximum: float | None = None
    choices: list[str] = Field(default_factory=list)
    description: str = ""


class TemplateVersion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    template_id: UUID
    version_no: int
    code_version_id: UUID
    mode: TemplateMode
    argv: list[str] = Field(min_length=1)
    parameters: list[ParameterDefinition] = Field(default_factory=list)
    input_contract: dict[str, Any] = Field(default_factory=dict)
    output_contract: dict[str, Any] = Field(default_factory=dict)
    frozen_at: datetime = Field(default_factory=utcnow)
    created_at: datetime = Field(default_factory=utcnow)


class RuntimeEnvironment(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    name: str
    description: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class EnvironmentVersion(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    environment_id: UUID
    version_no: int
    status: EnvironmentStatus = EnvironmentStatus.DRAFT
    base_image: str
    python_version: str
    dependency_file: str | None = None
    dependency_content: str | None = None
    image_digest: str | None = None
    content_hash: str
    frozen_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)


class ParameterPreset(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    owner_id: UUID
    template_version_id: UUID
    name: str
    values: dict[str, Any]
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
