"""B3 代码、模板、环境和参数预设 API。"""

import base64
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from hydrolab.api.code_asset_schemas import (
    CodeRepositoryView,
    CodeVersionView,
    CodeZipImport,
    DirectoryImport,
    DirectoryImportView,
    DirectoryPreviewView,
    EnvironmentVersionCreate,
    EnvironmentVersionView,
    EnvironmentView,
    GitImport,
    NamedAssetCreate,
    PresetCreate,
    PresetView,
    TemplateCreate,
    TemplateVersionCreate,
    TemplateVersionView,
    TemplateView,
)
from hydrolab.auth.dependencies import get_current_user
from hydrolab.code_assets.entities import (
    CodeRepository,
    CodeVersion,
    EnvironmentVersion,
    ExperimentTemplate,
    ParameterPreset,
    RuntimeEnvironment,
    TemplateVersion,
)
from hydrolab.domain.entities import User

router = APIRouter(tags=["code-assets"])


def _repo_view(item: CodeRepository) -> CodeRepositoryView:
    return CodeRepositoryView(id=item.id, name=item.name, description=item.description)


def _code_version_view(item: CodeVersion) -> CodeVersionView:
    return CodeVersionView(
        id=item.id,
        version_no=item.version_no,
        source_type=item.source_type,
        status=item.status,
        object_key=item.object_key,
        source_ref=item.source_ref,
        commit_sha=item.commit_sha,
        content_hash=item.content_hash,
        manifest=item.manifest,
    )


def _template_view(item: ExperimentTemplate) -> TemplateView:
    return TemplateView(
        id=item.id, code_repository_id=item.code_repository_id, name=item.name, description=item.description
    )


def _template_version_view(item: TemplateVersion) -> TemplateVersionView:
    return TemplateVersionView(
        id=item.id,
        version_no=item.version_no,
        code_version_id=item.code_version_id,
        mode=item.mode,
        argv=item.argv,
        parameters=item.parameters,
    )


def _environment_view(item: RuntimeEnvironment) -> EnvironmentView:
    return EnvironmentView(id=item.id, name=item.name, description=item.description)


def _environment_version_view(item: EnvironmentVersion) -> EnvironmentVersionView:
    return EnvironmentVersionView(
        id=item.id,
        version_no=item.version_no,
        status=item.status,
        base_image=item.base_image,
        python_version=item.python_version,
        image_digest=item.image_digest,
        content_hash=item.content_hash,
    )


def _preset_view(item: ParameterPreset) -> PresetView:
    return PresetView(id=item.id, template_version_id=item.template_version_id, name=item.name, values=item.values)


@router.get("/code-repositories", response_model=list[CodeRepositoryView])
async def list_repositories(request: Request, user: User = Depends(get_current_user)) -> list[CodeRepositoryView]:
    return [_repo_view(x) for x in await request.app.state.code_repositories.list_by_owner(user.id)]


@router.post("/code-repositories", response_model=CodeRepositoryView, status_code=201)
async def create_repository(
    body: NamedAssetCreate, request: Request, user: User = Depends(get_current_user)
) -> CodeRepositoryView:
    return _repo_view(await request.app.state.code_import_service.create_repository(user, body.name, body.description))


@router.post("/code-repositories/{repository_id}/zip-imports", response_model=CodeVersionView, status_code=201)
async def import_zip(
    repository_id: UUID, body: CodeZipImport, request: Request, user: User = Depends(get_current_user)
) -> CodeVersionView:
    try:
        archive = base64.b64decode(body.content_base64, validate=True)
    except ValueError as exc:
        from hydrolab.core.errors import validation_error

        raise validation_error("content_base64 不是有效 Base64") from exc
    return _code_version_view(
        await request.app.state.code_import_service.import_zip(user, repository_id, body.filename, archive)
    )


@router.post("/code-repositories/{repository_id}/git-imports", response_model=CodeVersionView, status_code=201)
async def register_git(
    repository_id: UUID, body: GitImport, request: Request, user: User = Depends(get_current_user)
) -> CodeVersionView:
    return _code_version_view(
        await request.app.state.code_import_service.register_git(user, repository_id, body.source_ref, body.commit_sha)
    )


def _preview_view(source_path: str, snapshot: object) -> DirectoryPreviewView:
    return DirectoryPreviewView(
        source_path=source_path,
        content_hash=snapshot.content_hash,  # type: ignore[attr-defined]
        file_count=len(snapshot.files),  # type: ignore[attr-defined]
        uncompressed_bytes=snapshot.total_bytes,  # type: ignore[attr-defined]
        archive_bytes=len(snapshot.archive),  # type: ignore[attr-defined]
        files=snapshot.files[:200],  # type: ignore[attr-defined]
        detected_manifests=snapshot.detected_manifests,  # type: ignore[attr-defined]
        entrypoints=snapshot.entrypoints,  # type: ignore[attr-defined]
        skipped_sample=snapshot.skipped[:50],  # type: ignore[attr-defined]
    )


@router.get("/code-import-roots", response_model=list[str])
async def list_import_roots(request: Request, user: User = Depends(get_current_user)) -> list[str]:
    """可导入的主机根目录白名单（前端用于提示合法路径）。"""
    return request.app.state.directory_import_service.allowed_roots


@router.post("/code-import-previews", response_model=DirectoryPreviewView)
async def preview_directory(
    body: DirectoryImport, request: Request, user: User = Depends(get_current_user)
) -> DirectoryPreviewView:
    """只读预览目录快照：不写对象存储，不创建 CodeVersion。"""
    import asyncio

    service = request.app.state.directory_import_service
    resolved, snapshot = await asyncio.to_thread(service.preview, body.path, body.extra_ignore)
    return _preview_view(str(resolved), snapshot)


@router.post(
    "/code-repositories/{repository_id}/directory-imports", response_model=DirectoryImportView, status_code=201
)
async def import_directory(
    repository_id: UUID, body: DirectoryImport, request: Request, user: User = Depends(get_current_user)
) -> DirectoryImportView:
    """把主机上的真实工程目录固化为不可变 CodeVersion（只读取，不执行）。"""
    version, snapshot = await request.app.state.directory_import_service.import_directory(
        user, repository_id, body.path, body.extra_ignore
    )
    source_path = str(snapshot and version.manifest.get("source_path", body.path))
    return DirectoryImportView(
        code_version=_code_version_view(version), preview=_preview_view(source_path, snapshot)
    )


@router.get("/code-repositories/{repository_id}/versions", response_model=list[CodeVersionView])
async def list_code_versions(
    repository_id: UUID, request: Request, user: User = Depends(get_current_user)
) -> list[CodeVersionView]:
    await request.app.state.code_import_service.get_repository(user, repository_id)
    return [_code_version_view(x) for x in await request.app.state.code_versions.list_by_repository(repository_id)]


@router.get("/templates", response_model=list[TemplateView])
async def list_templates(request: Request, user: User = Depends(get_current_user)) -> list[TemplateView]:
    return [_template_view(x) for x in await request.app.state.templates.list_by_owner(user.id)]


@router.post("/templates", response_model=TemplateView, status_code=201)
async def create_template(
    body: TemplateCreate, request: Request, user: User = Depends(get_current_user)
) -> TemplateView:
    return _template_view(
        await request.app.state.template_environment_service.create_template(
            user, body.code_repository_id, body.name, body.description
        )
    )


@router.post("/templates/{template_id}/versions", response_model=TemplateVersionView, status_code=201)
async def create_template_version(
    template_id: UUID, body: TemplateVersionCreate, request: Request, user: User = Depends(get_current_user)
) -> TemplateVersionView:
    return _template_version_view(
        await request.app.state.template_environment_service.create_template_version(
            user,
            template_id,
            body.code_version_id,
            body.mode,
            body.argv,
            body.parameters,
            body.input_contract,
            body.output_contract,
        )
    )


@router.get("/templates/{template_id}/versions", response_model=list[TemplateVersionView])
async def list_template_versions(
    template_id: UUID, request: Request, user: User = Depends(get_current_user)
) -> list[TemplateVersionView]:
    return [_template_version_view(x) for x in await request.app.state.template_versions.list_by_template(template_id)]


@router.get("/environments", response_model=list[EnvironmentView])
async def list_environments(request: Request, user: User = Depends(get_current_user)) -> list[EnvironmentView]:
    return [_environment_view(x) for x in await request.app.state.environments.list_by_owner(user.id)]


@router.post("/environments", response_model=EnvironmentView, status_code=201)
async def create_environment(
    body: NamedAssetCreate, request: Request, user: User = Depends(get_current_user)
) -> EnvironmentView:
    return _environment_view(
        await request.app.state.template_environment_service.create_environment(user, body.name, body.description)
    )


@router.post("/environments/{environment_id}/versions", response_model=EnvironmentVersionView, status_code=201)
async def create_environment_version(
    environment_id: UUID, body: EnvironmentVersionCreate, request: Request, user: User = Depends(get_current_user)
) -> EnvironmentVersionView:
    return _environment_version_view(
        await request.app.state.template_environment_service.create_environment_version(
            user, environment_id, body.base_image, body.python_version, body.dependency_file, body.dependency_content
        )
    )


@router.get("/environments/{environment_id}/versions", response_model=list[EnvironmentVersionView])
async def list_environment_versions(
    environment_id: UUID, request: Request, user: User = Depends(get_current_user)
) -> list[EnvironmentVersionView]:
    await request.app.state.template_environment_service.get_environment(user, environment_id)
    return [
        _environment_version_view(x)
        for x in await request.app.state.environment_versions.list_by_environment(environment_id)
    ]


@router.post("/parameter-presets", response_model=PresetView, status_code=201)
async def create_preset(body: PresetCreate, request: Request, user: User = Depends(get_current_user)) -> PresetView:
    return _preset_view(
        await request.app.state.template_environment_service.create_preset(
            user, body.template_version_id, body.name, body.values
        )
    )
