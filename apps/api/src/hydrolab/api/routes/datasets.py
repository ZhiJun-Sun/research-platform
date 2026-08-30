"""B2 数据/文件夹/导入 API。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from hydrolab.api.dataset_schemas import (
    DatasetCreate,
    DatasetView,
    FakeUpload,
    FolderCreate,
    FolderMove,
    FolderView,
    ImportCreate,
    ImportView,
    MappingConfirm,
    VersionView,
)
from hydrolab.auth.dependencies import get_current_user
from hydrolab.datasets.entities import (
    AssetFolder,
    Dataset,
    DatasetImportJob,
    DatasetVersion,
    FieldMappingItem,
)
from hydrolab.domain.entities import User

router = APIRouter(tags=["datasets"])


def _folder_view(folder: AssetFolder) -> FolderView:
    return FolderView(id=folder.id, name=folder.name, parent_id=folder.parent_id, path_key=folder.path_key)


def _dataset_view(dataset: Dataset) -> DatasetView:
    return DatasetView(
        id=dataset.id,
        name=dataset.name,
        folder_id=dataset.folder_id,
        description=dataset.description,
    )


def _import_view(job: DatasetImportJob) -> ImportView:
    return ImportView(
        id=job.id,
        dataset_id=job.dataset_id,
        status=job.status,
        source_type=job.source_type,
        detected_format=job.detected_format,
        progress=job.progress,
        error_code=job.error_code,
    )


def _version_view(version: DatasetVersion) -> VersionView:
    return VersionView(
        id=version.id,
        version_no=version.version_no,
        status=version.status.value,
        content_hash=version.content_hash,
        manifest=version.manifest,
    )


@router.get("/folders", response_model=list[FolderView])
async def list_folders(request: Request, user: User = Depends(get_current_user)) -> list[FolderView]:
    return [_folder_view(folder) for folder in await request.app.state.asset_service.list_folders(user)]


@router.post("/folders", response_model=FolderView, status_code=201)
async def create_folder(
    body: FolderCreate, request: Request, user: User = Depends(get_current_user)
) -> FolderView:
    return _folder_view(
        await request.app.state.asset_service.create_folder(user, body.name, body.parent_id)
    )


@router.patch("/folders/{folder_id}", response_model=FolderView)
async def move_folder(
    folder_id: UUID, body: FolderMove, request: Request, user: User = Depends(get_current_user)
) -> FolderView:
    return _folder_view(
        await request.app.state.asset_service.move_folder(user, folder_id, body.parent_id)
    )


@router.get("/datasets", response_model=list[DatasetView])
async def list_datasets(
    request: Request,
    q: str | None = None,
    folder_id: UUID | None = None,
    user: User = Depends(get_current_user),
) -> list[DatasetView]:
    datasets = await request.app.state.asset_service.list_datasets(user, q, folder_id)
    return [_dataset_view(dataset) for dataset in datasets]


@router.post("/datasets", response_model=DatasetView, status_code=201)
async def create_dataset(
    body: DatasetCreate, request: Request, user: User = Depends(get_current_user)
) -> DatasetView:
    return _dataset_view(
        await request.app.state.asset_service.create_dataset(
            user, body.name, body.folder_id, body.description
        )
    )


@router.get("/datasets/{dataset_id}", response_model=DatasetView)
async def get_dataset(
    dataset_id: UUID, request: Request, user: User = Depends(get_current_user)
) -> DatasetView:
    return _dataset_view(await request.app.state.asset_service.get_dataset(user, dataset_id))


@router.get("/datasets/{dataset_id}/versions", response_model=list[VersionView])
async def list_versions(
    dataset_id: UUID, request: Request, user: User = Depends(get_current_user)
) -> list[VersionView]:
    await request.app.state.asset_service.get_dataset(user, dataset_id)
    versions = await request.app.state.dataset_versions.list_by_dataset(dataset_id)
    return [_version_view(version) for version in versions]


@router.post("/dataset-imports", response_model=ImportView, status_code=201)
async def create_import(
    body: ImportCreate, request: Request, user: User = Depends(get_current_user)
) -> ImportView:
    job = await request.app.state.import_service.create(
        user,
        body.dataset_id,
        body.source_type,
        source_url=body.source_url,
        idempotency_key=request.headers.get("idempotency-key"),
    )
    return _import_view(job)


@router.get("/dataset-imports/{job_id}", response_model=ImportView)
async def get_import(
    job_id: UUID, request: Request, user: User = Depends(get_current_user)
) -> ImportView:
    return _import_view(await request.app.state.import_service.get_job(user, job_id))


@router.post("/dataset-imports/{job_id}/fake-upload", response_model=ImportView)
async def fake_upload(
    job_id: UUID, body: FakeUpload, request: Request, user: User = Depends(get_current_user)
) -> ImportView:
    job = await request.app.state.import_service.fake_upload(
        user, job_id, body.filename, body.content.encode()
    )
    return _import_view(job)


@router.get("/dataset-imports/{job_id}/mapping")
async def get_mapping(job_id: UUID, request: Request, user: User = Depends(get_current_user)) -> object:
    await request.app.state.import_service.get_job(user, job_id)
    return await request.app.state.field_mappings.get_by_job(job_id)


@router.post("/dataset-imports/{job_id}/confirm-mapping", response_model=VersionView)
async def confirm_mapping(
    job_id: UUID, body: MappingConfirm, request: Request, user: User = Depends(get_current_user)
) -> VersionView:
    items = [FieldMappingItem(**item.model_dump()) for item in body.items]
    version = await request.app.state.import_service.confirm_mapping(user, job_id, items)
    return _version_view(version)


@router.post("/dataset-imports/{job_id}/cancel", response_model=ImportView)
async def cancel_import(
    job_id: UUID, request: Request, user: User = Depends(get_current_user)
) -> ImportView:
    return _import_view(await request.app.state.import_service.cancel(user, job_id))


@router.post("/dataset-imports/{job_id}/retry", response_model=ImportView, status_code=201)
async def retry_import(
    job_id: UUID, request: Request, user: User = Depends(get_current_user)
) -> ImportView:
    return _import_view(await request.app.state.import_service.retry(user, job_id))
