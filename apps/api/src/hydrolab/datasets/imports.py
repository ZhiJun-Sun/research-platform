"""数据导入、探测、字段映射与版本冻结服务。"""

import csv
import io
from uuid import UUID

from hydrolab.access.policy import AccessPolicy
from hydrolab.core.errors import conflict, not_found, validation_error
from hydrolab.datasets.entities import Artifact, DatasetImportJob, DatasetVersion, FieldMapping, FieldMappingItem
from hydrolab.datasets.enums import (
    ArtifactKind,
    ArtifactStatus,
    DataFormat,
    DatasetSourceType,
    DatasetVersionStatus,
    FieldSemantic,
    ImportJobStatus,
)
from hydrolab.datasets.repositories import (
    ArtifactRepository,
    DatasetRepository,
    DatasetVersionRepository,
    FieldMappingRepository,
    ImportJobRepository,
)
from hydrolab.domain.entities import User, utcnow
from hydrolab.domain.enums import ResourceType, Role
from hydrolab.ports import ObjectStorage
from hydrolab.ports.dto import ObjectRef


class ImportService:
    def __init__(
        self,
        datasets: DatasetRepository,
        versions: DatasetVersionRepository,
        jobs: ImportJobRepository,
        mappings: FieldMappingRepository,
        artifacts: ArtifactRepository,
        storage: ObjectStorage,
        policy: AccessPolicy,
    ) -> None:
        self._datasets = datasets
        self._versions = versions
        self._jobs = jobs
        self._mappings = mappings
        self._artifacts = artifacts
        self._storage = storage
        self._policy = policy

    async def create(
        self,
        owner: User,
        dataset_id: UUID,
        source_type: DatasetSourceType,
        *,
        source_url: str | None = None,
        idempotency_key: str | None = None,
    ) -> DatasetImportJob:
        await self._policy.require(owner, ResourceType.DATASET, dataset_id, Role.OWNER)
        if idempotency_key:
            existing = await self._jobs.get_by_idempotency(owner.id, idempotency_key)
            if existing:
                return existing
        if source_type == DatasetSourceType.URL and not source_url:
            raise validation_error("URL 导入必须提供 source_url")
        status = (
            ImportJobStatus.UPLOADING
            if source_type == DatasetSourceType.UPLOAD
            else ImportJobStatus.CREATED
        )
        job = DatasetImportJob(
            owner_id=owner.id,
            dataset_id=dataset_id,
            source_type=source_type,
            source_url=source_url,
            idempotency_key=idempotency_key,
            status=status,
        )
        return await self._jobs.add(job)

    async def fake_upload(
        self, owner: User, job_id: UUID, filename: str, content: bytes
    ) -> DatasetImportJob:
        job = await self._get_owner_job(owner, job_id)
        if job.status not in (ImportJobStatus.CREATED, ImportJobStatus.UPLOADING):
            raise conflict("当前导入状态不允许上传", {"status": job.status.value})
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        formats = {
            "csv": DataFormat.CSV,
            "parquet": DataFormat.PARQUET,
            "nc": DataFormat.NETCDF,
            "netcdf": DataFormat.NETCDF,
        }
        key = f"imports/{job.id}/{filename}"
        # S3-01 后替换为预签名直传 + complete。
        self._storage.put_bytes(key, content)  # type: ignore[attr-defined]
        info = await self._storage.head(ObjectRef(key=key))
        artifact = Artifact(
            owner_id=owner.id,
            resource_type="DATASET_IMPORT",
            resource_id=job.id,
            kind=ArtifactKind.DATASET_SOURCE,
            object_key=key,
            size_bytes=info.size_bytes,
            sha256=info.sha256,
            status=ArtifactStatus.READY,
        )
        await self._artifacts.add(artifact)
        job.artifact_id = artifact.id
        job.detected_format = formats.get(suffix, DataFormat.UNKNOWN)
        job.status = ImportJobStatus.PROBING
        job.progress = 60
        await self._jobs.update(job)
        await self._probe(job, content)
        return job

    async def confirm_mapping(
        self, owner: User, job_id: UUID, items: list[FieldMappingItem]
    ) -> DatasetVersion:
        job = await self._get_owner_job(owner, job_id)
        if job.status != ImportJobStatus.MAPPING_REQUIRED:
            raise conflict("当前导入不等待字段映射确认", {"status": job.status.value})
        self._validate_mapping(items)
        mapping = await self._mappings.get_by_job(job.id)
        if mapping is None:
            raise not_found("字段映射不存在")
        mapping.items = items
        mapping.confirmed_at = utcnow()
        await self._mappings.update(mapping)
        artifact = await self._artifacts.get(job.artifact_id) if job.artifact_id else None
        if artifact is None or artifact.status != ArtifactStatus.READY:
            raise conflict("源文件尚未完成校验")
        version = DatasetVersion(
            dataset_id=job.dataset_id,
            version_no=await self._versions.next_version_no(job.dataset_id),
            source_type=job.source_type,
            status=DatasetVersionStatus.READY,
            object_prefix=f"datasets/{job.dataset_id}",
            manifest={
                "format": job.detected_format.value,
                "artifact_id": str(artifact.id),
                "field_mapping": [item.model_dump(mode="json") for item in items],
            },
            content_hash=artifact.sha256,
            frozen_at=utcnow(),
        )
        await self._versions.add(version)
        job.status = ImportJobStatus.SUCCEEDED
        job.progress = 100
        await self._jobs.update(job)
        return version

    async def get_job(self, actor: User, job_id: UUID) -> DatasetImportJob:
        job = await self._jobs.get(job_id)
        if job is None:
            raise not_found("导入任务不存在")
        await self._policy.require(actor, ResourceType.DATASET, job.dataset_id, Role.VIEWER)
        return job

    async def cancel(self, owner: User, job_id: UUID) -> DatasetImportJob:
        job = await self._get_owner_job(owner, job_id)
        if job.status not in (ImportJobStatus.SUCCEEDED, ImportJobStatus.FAILED, ImportJobStatus.CANCELLED):
            job.status = ImportJobStatus.CANCELLED
            job.progress = 0
            await self._jobs.update(job)
        return job

    async def retry(self, owner: User, job_id: UUID) -> DatasetImportJob:
        old = await self._get_owner_job(owner, job_id)
        if old.status not in (ImportJobStatus.FAILED, ImportJobStatus.CANCELLED):
            raise conflict("只有失败或取消的导入可以重试")
        status = (
            ImportJobStatus.UPLOADING
            if old.source_type == DatasetSourceType.UPLOAD
            else ImportJobStatus.CREATED
        )
        return await self._jobs.add(
            DatasetImportJob(
                owner_id=owner.id,
                dataset_id=old.dataset_id,
                source_type=old.source_type,
                source_url=old.source_url,
                retry_of_job_id=old.id,
                status=status,
            )
        )

    async def _get_owner_job(self, owner: User, job_id: UUID) -> DatasetImportJob:
        job = await self._jobs.get(job_id)
        if job is None or job.owner_id != owner.id:
            raise not_found("导入任务不存在")
        return job

    async def _probe(self, job: DatasetImportJob, content: bytes) -> None:
        columns: list[str] = []
        if job.detected_format == DataFormat.CSV:
            try:
                columns = next(csv.reader(io.StringIO(content.decode("utf-8-sig"))), [])
            except UnicodeDecodeError:
                job.status = ImportJobStatus.FAILED
                job.error_code = "UNSUPPORTED_ENCODING"
                await self._jobs.update(job)
                return
        items = []
        for index, name in enumerate(columns):
            semantic = self._semantic(name)
            items.append(
                FieldMappingItem(
                    source_name=name,
                    semantic=semantic,
                    standard_name=name if semantic != FieldSemantic.IGNORE else None,
                    order=index,
                    confidence=0.9 if semantic != FieldSemantic.IGNORE else 0.3,
                )
            )
        await self._mappings.add(FieldMapping(import_job_id=job.id, items=items))
        job.status = ImportJobStatus.MAPPING_REQUIRED
        job.progress = 80
        await self._jobs.update(job)

    @staticmethod
    def _semantic(name: str) -> FieldSemantic:
        low = name.lower()
        if low in {"date", "time", "timestamp", "datetime"}:
            return FieldSemantic.TIME
        if low in {"flow", "streamflow", "discharge", "target", "qobs"}:
            return FieldSemantic.TARGET
        if low in {"basin_id", "gauge_id", "station_id"}:
            return FieldSemantic.BASIN_ID
        return FieldSemantic.FEATURE if low else FieldSemantic.IGNORE

    @staticmethod
    def _validate_mapping(items: list[FieldMappingItem]) -> None:
        if not any(item.semantic == FieldSemantic.TIME for item in items):
            raise validation_error("字段映射必须指定一个时间字段")
        if sum(item.semantic == FieldSemantic.TIME for item in items) != 1:
            raise validation_error("只能指定一个时间字段")
        names = [item.standard_name for item in items if item.standard_name]
        if len(names) != len(set(names)):
            raise validation_error("标准字段名称不能重复")
