"""代码仓库、模板、运行环境、预设领域 ORM 模型（B3）。"""

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from hydrolab.db.base import Base, UTCDateTime, json_column, uuid_column


class CodeRepositoryModel(Base):
    __tablename__ = "code_repositories"

    id = mapped_column(uuid_column(), primary_key=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    created_at = mapped_column(UTCDateTime())
    updated_at = mapped_column(UTCDateTime())


class CodeVersionModel(Base):
    __tablename__ = "code_versions"

    id = mapped_column(uuid_column(), primary_key=True)
    repository_id = mapped_column(uuid_column(), ForeignKey("code_repositories.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    object_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    manifest = mapped_column(json_column())
    frozen_at = mapped_column(UTCDateTime(), nullable=True)
    created_at = mapped_column(UTCDateTime())


class TemplateModel(Base):
    __tablename__ = "experiment_templates"

    id = mapped_column(uuid_column(), primary_key=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    code_repository_id = mapped_column(uuid_column(), ForeignKey("code_repositories.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    created_at = mapped_column(UTCDateTime())
    updated_at = mapped_column(UTCDateTime())


class TemplateVersionModel(Base):
    __tablename__ = "template_versions"

    id = mapped_column(uuid_column(), primary_key=True)
    template_id = mapped_column(uuid_column(), ForeignKey("experiment_templates.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    code_version_id = mapped_column(uuid_column(), ForeignKey("code_versions.id"))
    mode: Mapped[str] = mapped_column(String(20))
    argv = mapped_column(json_column())
    parameters = mapped_column(json_column())
    input_contract = mapped_column(json_column())
    output_contract = mapped_column(json_column())
    frozen_at = mapped_column(UTCDateTime())
    created_at = mapped_column(UTCDateTime())


class EnvironmentModel(Base):
    __tablename__ = "runtime_environments"

    id = mapped_column(uuid_column(), primary_key=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    created_at = mapped_column(UTCDateTime())
    updated_at = mapped_column(UTCDateTime())


class EnvironmentVersionModel(Base):
    __tablename__ = "environment_versions"

    id = mapped_column(uuid_column(), primary_key=True)
    environment_id = mapped_column(uuid_column(), ForeignKey("runtime_environments.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    base_image: Mapped[str] = mapped_column(String(500))
    python_version: Mapped[str] = mapped_column(String(20))
    dependency_file: Mapped[str | None] = mapped_column(String(500), nullable=True)
    dependency_content: Mapped[str | None] = mapped_column(String(10000), nullable=True)
    image_digest: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(100))
    frozen_at = mapped_column(UTCDateTime(), nullable=True)
    created_at = mapped_column(UTCDateTime())


class ParameterPresetModel(Base):
    __tablename__ = "parameter_presets"

    id = mapped_column(uuid_column(), primary_key=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    template_version_id = mapped_column(uuid_column(), ForeignKey("template_versions.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    values = mapped_column(json_column())
    created_at = mapped_column(UTCDateTime())
    updated_at = mapped_column(UTCDateTime())