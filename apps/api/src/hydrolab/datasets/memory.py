"""B2 进程内 Repository 实现。"""

from uuid import UUID

from hydrolab.datasets.entities import (
    Artifact,
    AssetFolder,
    Dataset,
    DatasetImportJob,
    DatasetVersion,
    FieldMapping,
)


class InMemoryFolderRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, AssetFolder] = {}

    async def add(self, folder: AssetFolder) -> AssetFolder:
        self._items[folder.id] = folder
        return folder

    async def get(self, folder_id: UUID) -> AssetFolder | None:
        return self._items.get(folder_id)

    async def update(self, folder: AssetFolder) -> AssetFolder:
        self._items[folder.id] = folder
        return folder

    async def list_by_owner(self, owner_id: UUID) -> list[AssetFolder]:
        return [item for item in self._items.values() if item.owner_id == owner_id]


class InMemoryDatasetRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, Dataset] = {}

    async def add(self, dataset: Dataset) -> Dataset:
        self._items[dataset.id] = dataset
        return dataset

    async def get(self, dataset_id: UUID) -> Dataset | None:
        return self._items.get(dataset_id)

    async def update(self, dataset: Dataset) -> Dataset:
        self._items[dataset.id] = dataset
        return dataset

    async def list_by_owner(self, owner_id: UUID) -> list[Dataset]:
        return [item for item in self._items.values() if item.owner_id == owner_id]


class InMemoryDatasetVersionRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, DatasetVersion] = {}

    async def add(self, version: DatasetVersion) -> DatasetVersion:
        self._items[version.id] = version
        return version

    async def get(self, version_id: UUID) -> DatasetVersion | None:
        return self._items.get(version_id)

    async def update(self, version: DatasetVersion) -> DatasetVersion:
        self._items[version.id] = version
        return version

    async def list_by_dataset(self, dataset_id: UUID) -> list[DatasetVersion]:
        return sorted(
            (v for v in self._items.values() if v.dataset_id == dataset_id),
            key=lambda version: version.version_no,
            reverse=True,
        )

    async def next_version_no(self, dataset_id: UUID) -> int:
        versions = await self.list_by_dataset(dataset_id)
        return (max((v.version_no for v in versions), default=0)) + 1


class InMemoryImportJobRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, DatasetImportJob] = {}

    async def add(self, job: DatasetImportJob) -> DatasetImportJob:
        self._items[job.id] = job
        return job

    async def get(self, job_id: UUID) -> DatasetImportJob | None:
        return self._items.get(job_id)

    async def update(self, job: DatasetImportJob) -> DatasetImportJob:
        self._items[job.id] = job
        return job

    async def get_by_idempotency(self, owner_id: UUID, key: str) -> DatasetImportJob | None:
        return next(
            (
                job
                for job in self._items.values()
                if job.owner_id == owner_id and job.idempotency_key == key
            ),
            None,
        )


class InMemoryFieldMappingRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, FieldMapping] = {}

    async def add(self, mapping: FieldMapping) -> FieldMapping:
        self._items[mapping.id] = mapping
        return mapping

    async def get_by_job(self, job_id: UUID) -> FieldMapping | None:
        return next((m for m in self._items.values() if m.import_job_id == job_id), None)

    async def update(self, mapping: FieldMapping) -> FieldMapping:
        self._items[mapping.id] = mapping
        return mapping


class InMemoryArtifactRepository:
    def __init__(self) -> None:
        self._items: dict[UUID, Artifact] = {}

    async def add(self, artifact: Artifact) -> Artifact:
        self._items[artifact.id] = artifact
        return artifact

    async def get(self, artifact_id: UUID) -> Artifact | None:
        return self._items.get(artifact_id)

    async def update(self, artifact: Artifact) -> Artifact:
        self._items[artifact.id] = artifact
        return artifact
