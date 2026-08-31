"""B3 API 请求和响应模型。"""

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from hydrolab.code_assets.entities import ParameterDefinition
from hydrolab.code_assets.enums import CodeSourceType, CodeVersionStatus, EnvironmentStatus, TemplateMode


class NamedAssetCreate(BaseModel):
    name: str
    description: str = ""


class CodeZipImport(BaseModel):
    filename: str
    content_base64: str


class GitImport(BaseModel):
    source_ref: str
    commit_sha: str | None = None


class CodeRepositoryView(BaseModel):
    id: UUID
    name: str
    description: str


class CodeVersionView(BaseModel):
    id: UUID
    version_no: int
    source_type: CodeSourceType
    status: CodeVersionStatus
    object_key: str | None = None
    source_ref: str | None = None
    commit_sha: str | None = None
    content_hash: str | None
    manifest: dict[str, Any]


class TemplateCreate(BaseModel):
    code_repository_id: UUID
    name: str
    description: str = ""


class TemplateVersionCreate(BaseModel):
    code_version_id: UUID
    mode: TemplateMode
    argv: list[str]
    parameters: list[ParameterDefinition] = Field(default_factory=list)
    input_contract: dict[str, Any] = Field(default_factory=dict)
    output_contract: dict[str, Any] = Field(default_factory=dict)


class TemplateView(BaseModel):
    id: UUID
    code_repository_id: UUID
    name: str
    description: str


class TemplateVersionView(BaseModel):
    id: UUID
    version_no: int
    code_version_id: UUID
    mode: TemplateMode
    argv: list[str]
    parameters: list[ParameterDefinition]


class EnvironmentVersionCreate(BaseModel):
    base_image: str
    python_version: str
    dependency_file: str | None = None
    dependency_content: str | None = None


class EnvironmentView(BaseModel):
    id: UUID
    name: str
    description: str


class EnvironmentVersionView(BaseModel):
    id: UUID
    version_no: int
    status: EnvironmentStatus
    base_image: str
    python_version: str
    content_hash: str


class PresetCreate(BaseModel):
    template_version_id: UUID
    name: str
    values: dict[str, Any]


class PresetView(BaseModel):
    id: UUID
    template_version_id: UUID
    name: str
    values: dict[str, Any]
