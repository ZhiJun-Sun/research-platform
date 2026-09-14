"""B2 文件夹、数据集、版本、导入、字段映射与 Artifact 领域 SQL 仓储（实现 repositories/__init__.py 的 Protocol）。"""

from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hydrolab.datasets.entities import (
    Artifact,
    AssetFolder,
    Dataset,
    DatasetImportJob,
    DatasetVersion,
    FieldMapping,
    FieldMappingItem,
)
from hydrolab.datasets.enums import (
    ArtifactKind,
    ArtifactStatus,
    DataFormat,
    DatasetSourceType,
    DatasetVersionStatus,
    FieldSemantic,
    ImportJobStatus,
)
from hydrolab.db.models.datasets import (
    ArtifactModel,
    DatasetImportJobModel,
    DatasetModel,
    DatasetVersionModel,
    FieldMappingModel,
    FolderModel,
)


def _to_folder(m: FolderModel) -> AssetFolder:
    return AssetFolder(
        id=m.id,
        owner_id=m.owner_id,
        parent_id=m.parent_id,
        name=m.name,
        path_key=m.path_key,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _to_dataset(m: DatasetModel) -> Dataset:
    return Dataset(
        id=m.id,
        owner_id=m.owner_id,
        folder_id=m.folder_id,
        name=m.name,
        description=m.description,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _to_version(m: DatasetVersionModel) -> DatasetVersion:
    return DatasetVersion(
        id=m.id,
        dataset_id=m.dataset_id,
        version_no=m.version_no,
        source_type=DatasetSourceType(m.source_type),
        status=DatasetVersionStatus(m.status),
        object_prefix=m.object_prefix,
        manifest=m.manifest or {},
        content_hash=m.content_hash,
        parent_version_id=m.parent_version_id,
        frozen_at=m.frozen_at,
        created_at=m.created_at,
    )


def _to_artifact(m: ArtifactModel) -> Artifact:
    return Artifact(
        id=m.id,
        owner_id=m.owner_id,
        resource_type=m.resource_type,
        resource_id=m.resource_id,
        kind=ArtifactKind(m.kind),
        object_key=m.object_key,
        media_type=m.media_type,
        size_bytes=m.size_bytes,
        sha256=m.sha256,
        status=ArtifactStatus(m.status),
        created_at=m.created_at,
    )


def _to_mapping(m: FieldMappingModel) -> FieldMapping:
    items: list[FieldMappingItem] = []
    for raw in m.items or []:
        items.append(
            FieldMappingItem(
                source_name=raw["source_name"],
                standard_name=raw.get("standard_name"),
                semantic=FieldSemantic(raw["semantic"]),
                unit=raw.get("unit"),
                order=raw.get("order", 0),
                confidence=raw.get("confidence", 0.0),
                user_modified=raw.get("user_modified", False),
            )
        )
    return FieldMapping(
        id=m.id,
        import_job_id=m.import_job_id,
        items=items,
        created_at=m.created_at,
        confirmed_at=m.confirmed_at,
    )


def _to_job(m: DatasetImportJobModel) -> DatasetImportJob:
    return DatasetImportJob(
        id=m.id,
        owner_id=m.owner_id,
        dataset_id=m.dataset_id,
        source_type=DatasetSourceType(m.source_type),
        status=ImportJobStatus(m.status),
        source_url=m.source_url,
        source_version_id=m.source_version_id,
        artifact_id=m.artifact_id,
        detected_format=DataFormat(m.detected_format),
        bundle_entries=m.bundle_entries or [],
        progress=m.progress,
        error_code=m.error_code,
        error_message=m.error_message,
        idempotency_key=m.idempotency_key,
        retry_of_job_id=m.retry_of_job_id,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SqlFolderRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, folder: AssetFolder) -> AssetFolder:
        async with self._sf() as session:
            session.add(
                FolderModel(
                    id=folder.id,
                    owner_id=folder.owner_id,
                    parent_id=folder.parent_id,
                    name=folder.name,
                    path_key=folder.path_key,
                    created_at=folder.created_at,
                    updated_at=folder.updated_at,
                )
            )
            await session.commit()
            return folder

    async def get(self, folder_id: UUID) -> AssetFolder | None:
        async with self._sf() as session:
            m = await session.get(FolderModel, folder_id)
            return _to_folder(m) if m else None

    async def update(self, folder: AssetFolder) -> AssetFolder:
        async with self._sf() as session:
            m = await session.get(FolderModel, folder.id)
            if m is None:
                return folder
            m.parent_id = folder.parent_id
            m.name = folder.name
            m.path_key = folder.path_key
            m.updated_at = folder.updated_at
            await session.commit()
            return folder

    async def list_by_owner(self, owner_id: UUID) -> list[AssetFolder]:
        async with self._sf() as session:
            res = await session.execute(
                select(FolderModel)
                .where(FolderModel.owner_id == owner_id)
                .order_by(FolderModel.created_at.desc())
            )
            return [_to_folder(m) for m in res.scalars().all()]


class SqlDatasetRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, dataset: Dataset) -> Dataset:
        async with self._sf() as session:
            session.add(
                DatasetModel(
                    id=dataset.id,
                    owner_id=dataset.owner_id,
                    folder_id=dataset.folder_id,
                    name=dataset.name,
                    description=dataset.description,
                    created_at=dataset.created_at,
                    updated_at=dataset.updated_at,
                )
            )
            await session.commit()
            return dataset

    async def get(self, dataset_id: UUID) -> Dataset | None:
        async with self._sf() as session:
            m = await session.get(DatasetModel, dataset_id)
            return _to_dataset(m) if m else None

    async def update(self, dataset: Dataset) -> Dataset:
        async with self._sf() as session:
            m = await session.get(DatasetModel, dataset.id)
            if m is None:
                return dataset
            m.folder_id = dataset.folder_id
            m.name = dataset.name
            m.description = dataset.description
            m.updated_at = dataset.updated_at
            await session.commit()
            return dataset

    async def list_by_owner(self, owner_id: UUID) -> list[Dataset]:
        async with self._sf() as session:
            res = await session.execute(
                select(DatasetModel)
                .where(DatasetModel.owner_id == owner_id)
                .order_by(DatasetModel.created_at.desc())
            )
            return [_to_dataset(m) for m in res.scalars().all()]


class SqlDatasetVersionRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, version: DatasetVersion) -> DatasetVersion:
        async with self._sf() as session:
            session.add(
                DatasetVersionModel(
                    id=version.id,
                    dataset_id=version.dataset_id,
                    version_no=version.version_no,
                    source_type=version.source_type.value,
                    status=version.status.value,
                    object_prefix=version.object_prefix,
                    manifest=version.manifest,
                    content_hash=version.content_hash,
                    parent_version_id=version.parent_version_id,
                    frozen_at=version.frozen_at,
                    created_at=version.created_at,
                )
            )
            await session.commit()
            return version

    async def get(self, version_id: UUID) -> DatasetVersion | None:
        async with self._sf() as session:
            m = await session.get(DatasetVersionModel, version_id)
            return _to_version(m) if m else None

    async def update(self, version: DatasetVersion) -> DatasetVersion:
        async with self._sf() as session:
            m = await session.get(DatasetVersionModel, version.id)
            if m is None:
                return version
            m.source_type = version.source_type.value
            m.status = version.status.value
            m.manifest = version.manifest
            m.content_hash = version.content_hash
            m.parent_version_id = version.parent_version_id
            m.frozen_at = version.frozen_at
            await session.commit()
            return version

    async def list_by_dataset(self, dataset_id: UUID) -> list[DatasetVersion]:
        async with self._sf() as session:
            res = await session.execute(
                select(DatasetVersionModel)
                .where(DatasetVersionModel.dataset_id == dataset_id)
                .order_by(DatasetVersionModel.version_no.desc())
            )
            return [_to_version(m) for m in res.scalars().all()]

    async def next_version_no(self, dataset_id: UUID) -> int:
        async with self._sf() as session:
            res = await session.execute(
                select(func.max(DatasetVersionModel.version_no)).where(
                    DatasetVersionModel.dataset_id == dataset_id
                )
            )
            max_no = res.scalar_one()
            return (max_no + 1) if max_no is not None else 1


class SqlArtifactRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, artifact: Artifact) -> Artifact:
        async with self._sf() as session:
            session.add(
                ArtifactModel(
                    id=artifact.id,
                    owner_id=artifact.owner_id,
                    resource_type=artifact.resource_type,
                    resource_id=artifact.resource_id,
                    kind=artifact.kind.value,
                    object_key=artifact.object_key,
                    media_type=artifact.media_type,
                    size_bytes=artifact.size_bytes,
                    sha256=artifact.sha256,
                    status=artifact.status.value,
                    created_at=artifact.created_at,
                )
            )
            await session.commit()
            return artifact

    async def get(self, artifact_id: UUID) -> Artifact | None:
        async with self._sf() as session:
            m = await session.get(ArtifactModel, artifact_id)
            return _to_artifact(m) if m else None

    async def update(self, artifact: Artifact) -> Artifact:
        async with self._sf() as session:
            m = await session.get(ArtifactModel, artifact.id)
            if m is None:
                return artifact
            m.object_key = artifact.object_key
            m.media_type = artifact.media_type
            m.size_bytes = artifact.size_bytes
            m.sha256 = artifact.sha256
            m.status = artifact.status.value
            await session.commit()
            return artifact


class SqlFieldMappingRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, mapping: FieldMapping) -> FieldMapping:
        async with self._sf() as session:
            session.add(
                FieldMappingModel(
                    id=mapping.id,
                    import_job_id=mapping.import_job_id,
                    items=[item.model_dump() for item in mapping.items],
                    created_at=mapping.created_at,
                    confirmed_at=mapping.confirmed_at,
                )
            )
            await session.commit()
            return mapping

    async def get_by_job(self, job_id: UUID) -> FieldMapping | None:
        async with self._sf() as session:
            res = await session.execute(
                select(FieldMappingModel).where(FieldMappingModel.import_job_id == job_id)
            )
            m = res.scalar_one_or_none()
            return _to_mapping(m) if m else None

    async def update(self, mapping: FieldMapping) -> FieldMapping:
        async with self._sf() as session:
            m = await session.get(FieldMappingModel, mapping.id)
            if m is None:
                return mapping
            m.items = [item.model_dump() for item in mapping.items]
            m.confirmed_at = mapping.confirmed_at
            await session.commit()
            return mapping


class SqlImportJobRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, job: DatasetImportJob) -> DatasetImportJob:
        async with self._sf() as session:
            session.add(
                DatasetImportJobModel(
                    id=job.id,
                    owner_id=job.owner_id,
                    dataset_id=job.dataset_id,
                    source_type=job.source_type.value,
                    status=job.status.value,
                    source_url=job.source_url,
                    source_version_id=job.source_version_id,
                    artifact_id=job.artifact_id,
                    detected_format=job.detected_format.value,
                    bundle_entries=job.bundle_entries,
                    progress=job.progress,
                    error_code=job.error_code,
                    error_message=job.error_message,
                    idempotency_key=job.idempotency_key,
                    retry_of_job_id=job.retry_of_job_id,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                )
            )
            await session.commit()
            return job

    async def get(self, job_id: UUID) -> DatasetImportJob | None:
        async with self._sf() as session:
            m = await session.get(DatasetImportJobModel, job_id)
            return _to_job(m) if m else None

    async def update(self, job: DatasetImportJob) -> DatasetImportJob:
        async with self._sf() as session:
            m = await session.get(DatasetImportJobModel, job.id)
            if m is None:
                return job
            m.dataset_id = job.dataset_id
            m.source_type = job.source_type.value
            m.status = job.status.value
            m.source_url = job.source_url
            m.source_version_id = job.source_version_id
            m.artifact_id = job.artifact_id
            m.detected_format = job.detected_format.value
            m.bundle_entries = job.bundle_entries
            m.progress = job.progress
            m.error_code = job.error_code
            m.error_message = job.error_message
            m.idempotency_key = job.idempotency_key
            m.retry_of_job_id = job.retry_of_job_id
            m.updated_at = job.updated_at
            await session.commit()
            return job

    async def get_by_idempotency(self, owner_id: UUID, key: str) -> DatasetImportJob | None:
        async with self._sf() as session:
            res = await session.execute(
                select(DatasetImportJobModel).where(
                    DatasetImportJobModel.owner_id == owner_id,
                    DatasetImportJobModel.idempotency_key == key,
                )
            )
            m = res.scalar_one_or_none()
            return _to_job(m) if m else None


__all__ = [
    "SqlArtifactRepository",
    "SqlDatasetRepository",
    "SqlDatasetVersionRepository",
    "SqlFieldMappingRepository",
    "SqlFolderRepository",
    "SqlImportJobRepository",
]