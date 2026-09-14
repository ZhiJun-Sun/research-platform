"""数据集、导入、字段映射、Artifact 领域 ORM 模型（B2）。"""

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from hydrolab.db.base import Base, UTCDateTime, json_column, uuid_column


class FolderModel(Base):
    __tablename__ = "asset_folders"

    id = mapped_column(uuid_column(), primary_key=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    parent_id = mapped_column(uuid_column(), ForeignKey("asset_folders.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    path_key: Mapped[str] = mapped_column(String(500), index=True)
    created_at = mapped_column(UTCDateTime())
    updated_at = mapped_column(UTCDateTime())


class DatasetModel(Base):
    __tablename__ = "datasets"

    id = mapped_column(uuid_column(), primary_key=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    folder_id = mapped_column(uuid_column(), ForeignKey("asset_folders.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")
    created_at = mapped_column(UTCDateTime())
    updated_at = mapped_column(UTCDateTime())


class DatasetVersionModel(Base):
    __tablename__ = "dataset_versions"
    # 显式指定 collation：否则 MySQL 8.0 对 utf8mb4 默认 0900_ai_ci，
    # 与库/其他表的 utf8mb4_unicode_ci 不一致会导致外键 3780 错误。
    __table_args__ = ({"mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_unicode_ci"},)

    id = mapped_column(uuid_column(), primary_key=True)
    dataset_id = mapped_column(uuid_column(), ForeignKey("datasets.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)
    source_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="PENDING")
    object_prefix: Mapped[str] = mapped_column(String(500))
    manifest = mapped_column(json_column())
    content_hash: Mapped[str | None] = mapped_column(String(100), nullable=True)
    parent_version_id = mapped_column(uuid_column(), ForeignKey("dataset_versions.id"), nullable=True)
    frozen_at = mapped_column(UTCDateTime(), nullable=True)
    created_at = mapped_column(UTCDateTime())


class ArtifactModel(Base):
    __tablename__ = "artifacts"

    id = mapped_column(uuid_column(), primary_key=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    resource_type: Mapped[str] = mapped_column(String(40))
    resource_id = mapped_column(uuid_column(), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    object_key: Mapped[str] = mapped_column(String(500))
    media_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    sha256: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="PENDING_UPLOAD")
    created_at = mapped_column(UTCDateTime())


class FieldMappingModel(Base):
    __tablename__ = "field_mappings"

    id = mapped_column(uuid_column(), primary_key=True)
    import_job_id = mapped_column(uuid_column(), ForeignKey("dataset_import_jobs.id"), index=True)
    items = mapped_column(json_column())
    created_at = mapped_column(UTCDateTime())
    confirmed_at = mapped_column(UTCDateTime(), nullable=True)


class DatasetImportJobModel(Base):
    __tablename__ = "dataset_import_jobs"

    id = mapped_column(uuid_column(), primary_key=True)
    owner_id = mapped_column(uuid_column(), ForeignKey("users.id"), index=True)
    dataset_id = mapped_column(uuid_column(), ForeignKey("datasets.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(30), default="CREATED")
    source_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    source_version_id = mapped_column(uuid_column(), nullable=True)
    artifact_id = mapped_column(uuid_column(), nullable=True)
    detected_format: Mapped[str] = mapped_column(String(30), default="UNKNOWN")
    bundle_entries = mapped_column(json_column())
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    retry_of_job_id = mapped_column(uuid_column(), nullable=True)
    created_at = mapped_column(UTCDateTime())
    updated_at = mapped_column(UTCDateTime())
