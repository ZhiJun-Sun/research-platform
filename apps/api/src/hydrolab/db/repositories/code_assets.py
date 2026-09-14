"""B3 代码、模板、环境、预设领域 SQL 仓储（实现 code_assets/store 的 Protocol）。"""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hydrolab.code_assets.entities import (
    CodeRepository,
    CodeVersion,
    EnvironmentVersion,
    ExperimentTemplate,
    ParameterDefinition,
    ParameterPreset,
    RuntimeEnvironment,
    TemplateVersion,
)
from hydrolab.code_assets.enums import (
    CodeSourceType,
    CodeVersionStatus,
    EnvironmentStatus,
    TemplateMode,
)
from hydrolab.db.models.code_assets import (
    CodeRepositoryModel,
    CodeVersionModel,
    EnvironmentModel,
    EnvironmentVersionModel,
    ParameterPresetModel,
    TemplateModel,
    TemplateVersionModel,
)


def _to_code_repository(m: CodeRepositoryModel) -> CodeRepository:
    return CodeRepository(
        id=m.id,
        owner_id=m.owner_id,
        name=m.name,
        description=m.description or "",
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _to_code_version(m: CodeVersionModel) -> CodeVersion:
    return CodeVersion(
        id=m.id,
        repository_id=m.repository_id,
        version_no=m.version_no,
        source_type=CodeSourceType(m.source_type),
        status=CodeVersionStatus(m.status),
        object_key=m.object_key,
        source_ref=m.source_ref,
        commit_sha=m.commit_sha,
        content_hash=m.content_hash,
        manifest=m.manifest or {},
        frozen_at=m.frozen_at,
        created_at=m.created_at,
    )


def _to_template(m: TemplateModel) -> ExperimentTemplate:
    return ExperimentTemplate(
        id=m.id,
        owner_id=m.owner_id,
        code_repository_id=m.code_repository_id,
        name=m.name,
        description=m.description or "",
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _to_template_version(m: TemplateVersionModel) -> TemplateVersion:
    return TemplateVersion(
        id=m.id,
        template_id=m.template_id,
        version_no=m.version_no,
        code_version_id=m.code_version_id,
        mode=TemplateMode(m.mode),
        argv=m.argv or [],
        parameters=[ParameterDefinition(**d) for d in (m.parameters or [])],
        input_contract=m.input_contract or {},
        output_contract=m.output_contract or {},
        frozen_at=m.frozen_at,
        created_at=m.created_at,
    )


def _to_environment(m: EnvironmentModel) -> RuntimeEnvironment:
    return RuntimeEnvironment(
        id=m.id,
        owner_id=m.owner_id,
        name=m.name,
        description=m.description or "",
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _to_environment_version(m: EnvironmentVersionModel) -> EnvironmentVersion:
    return EnvironmentVersion(
        id=m.id,
        environment_id=m.environment_id,
        version_no=m.version_no,
        status=EnvironmentStatus(m.status),
        base_image=m.base_image,
        python_version=m.python_version,
        dependency_file=m.dependency_file,
        dependency_content=m.dependency_content,
        image_digest=m.image_digest,
        content_hash=m.content_hash,
        frozen_at=m.frozen_at,
        created_at=m.created_at,
    )


def _to_preset(m: ParameterPresetModel) -> ParameterPreset:
    return ParameterPreset(
        id=m.id,
        owner_id=m.owner_id,
        template_version_id=m.template_version_id,
        name=m.name,
        values=m.values or {},
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SqlCodeRepositoryStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, repo: CodeRepository) -> CodeRepository:
        async with self._sf() as session:
            session.add(
                CodeRepositoryModel(
                    id=repo.id,
                    owner_id=repo.owner_id,
                    name=repo.name,
                    description=repo.description,
                    created_at=repo.created_at,
                    updated_at=repo.updated_at,
                )
            )
            await session.commit()
            return repo

    async def get(self, repo_id: UUID) -> CodeRepository | None:
        async with self._sf() as session:
            m = await session.get(CodeRepositoryModel, repo_id)
            return _to_code_repository(m) if m else None

    async def list_by_owner(self, owner_id: UUID) -> list[CodeRepository]:
        async with self._sf() as session:
            res = await session.execute(
                select(CodeRepositoryModel)
                .where(CodeRepositoryModel.owner_id == owner_id)
                .order_by(CodeRepositoryModel.created_at.desc())
            )
            return [_to_code_repository(m) for m in res.scalars().all()]


class SqlCodeVersionStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, version: CodeVersion) -> CodeVersion:
        async with self._sf() as session:
            session.add(
                CodeVersionModel(
                    id=version.id,
                    repository_id=version.repository_id,
                    version_no=version.version_no,
                    source_type=version.source_type.value,
                    status=version.status.value,
                    object_key=version.object_key,
                    source_ref=version.source_ref,
                    commit_sha=version.commit_sha,
                    content_hash=version.content_hash,
                    manifest=version.manifest,
                    frozen_at=version.frozen_at,
                    created_at=version.created_at,
                )
            )
            await session.commit()
            return version

    async def get(self, version_id: UUID) -> CodeVersion | None:
        async with self._sf() as session:
            m = await session.get(CodeVersionModel, version_id)
            return _to_code_version(m) if m else None

    async def list_by_repository(self, repository_id: UUID) -> list[CodeVersion]:
        async with self._sf() as session:
            res = await session.execute(
                select(CodeVersionModel)
                .where(CodeVersionModel.repository_id == repository_id)
                .order_by(CodeVersionModel.version_no.desc())
            )
            return [_to_code_version(m) for m in res.scalars().all()]

    async def next_version_no(self, repository_id: UUID) -> int:
        async with self._sf() as session:
            res = await session.execute(
                select(func.max(CodeVersionModel.version_no)).where(
                    CodeVersionModel.repository_id == repository_id
                )
            )
            mx = res.scalar_one()
            return (mx + 1) if mx is not None else 1


class SqlTemplateStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, template: ExperimentTemplate) -> ExperimentTemplate:
        async with self._sf() as session:
            session.add(
                TemplateModel(
                    id=template.id,
                    owner_id=template.owner_id,
                    code_repository_id=template.code_repository_id,
                    name=template.name,
                    description=template.description,
                    created_at=template.created_at,
                    updated_at=template.updated_at,
                )
            )
            await session.commit()
            return template

    async def get(self, template_id: UUID) -> ExperimentTemplate | None:
        async with self._sf() as session:
            m = await session.get(TemplateModel, template_id)
            return _to_template(m) if m else None

    async def list_by_owner(self, owner_id: UUID) -> list[ExperimentTemplate]:
        async with self._sf() as session:
            res = await session.execute(
                select(TemplateModel)
                .where(TemplateModel.owner_id == owner_id)
                .order_by(TemplateModel.created_at.desc())
            )
            return [_to_template(m) for m in res.scalars().all()]


class SqlTemplateVersionStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, version: TemplateVersion) -> TemplateVersion:
        async with self._sf() as session:
            session.add(
                TemplateVersionModel(
                    id=version.id,
                    template_id=version.template_id,
                    version_no=version.version_no,
                    code_version_id=version.code_version_id,
                    mode=version.mode.value,
                    argv=version.argv,
                    parameters=[p.model_dump() for p in version.parameters],
                    input_contract=version.input_contract,
                    output_contract=version.output_contract,
                    frozen_at=version.frozen_at,
                    created_at=version.created_at,
                )
            )
            await session.commit()
            return version

    async def get(self, version_id: UUID) -> TemplateVersion | None:
        async with self._sf() as session:
            m = await session.get(TemplateVersionModel, version_id)
            return _to_template_version(m) if m else None

    async def list_by_template(self, template_id: UUID) -> list[TemplateVersion]:
        async with self._sf() as session:
            res = await session.execute(
                select(TemplateVersionModel)
                .where(TemplateVersionModel.template_id == template_id)
                .order_by(TemplateVersionModel.version_no.desc())
            )
            return [_to_template_version(m) for m in res.scalars().all()]

    async def next_version_no(self, template_id: UUID) -> int:
        async with self._sf() as session:
            res = await session.execute(
                select(func.max(TemplateVersionModel.version_no)).where(
                    TemplateVersionModel.template_id == template_id
                )
            )
            mx = res.scalar_one()
            return (mx + 1) if mx is not None else 1


class SqlEnvironmentStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, environment: RuntimeEnvironment) -> RuntimeEnvironment:
        async with self._sf() as session:
            session.add(
                EnvironmentModel(
                    id=environment.id,
                    owner_id=environment.owner_id,
                    name=environment.name,
                    description=environment.description,
                    created_at=environment.created_at,
                    updated_at=environment.updated_at,
                )
            )
            await session.commit()
            return environment

    async def get(self, environment_id: UUID) -> RuntimeEnvironment | None:
        async with self._sf() as session:
            m = await session.get(EnvironmentModel, environment_id)
            return _to_environment(m) if m else None

    async def list_by_owner(self, owner_id: UUID) -> list[RuntimeEnvironment]:
        async with self._sf() as session:
            res = await session.execute(
                select(EnvironmentModel)
                .where(EnvironmentModel.owner_id == owner_id)
                .order_by(EnvironmentModel.created_at.desc())
            )
            return [_to_environment(m) for m in res.scalars().all()]


class SqlEnvironmentVersionStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, version: EnvironmentVersion) -> EnvironmentVersion:
        async with self._sf() as session:
            session.add(
                EnvironmentVersionModel(
                    id=version.id,
                    environment_id=version.environment_id,
                    version_no=version.version_no,
                    status=version.status.value,
                    base_image=version.base_image,
                    python_version=version.python_version,
                    dependency_file=version.dependency_file,
                    dependency_content=version.dependency_content,
                    image_digest=version.image_digest,
                    content_hash=version.content_hash,
                    frozen_at=version.frozen_at,
                    created_at=version.created_at,
                )
            )
            await session.commit()
            return version

    async def get(self, version_id: UUID) -> EnvironmentVersion | None:
        async with self._sf() as session:
            m = await session.get(EnvironmentVersionModel, version_id)
            return _to_environment_version(m) if m else None

    async def list_by_environment(self, environment_id: UUID) -> list[EnvironmentVersion]:
        async with self._sf() as session:
            res = await session.execute(
                select(EnvironmentVersionModel)
                .where(EnvironmentVersionModel.environment_id == environment_id)
                .order_by(EnvironmentVersionModel.version_no.desc())
            )
            return [_to_environment_version(m) for m in res.scalars().all()]

    async def next_version_no(self, environment_id: UUID) -> int:
        async with self._sf() as session:
            res = await session.execute(
                select(func.max(EnvironmentVersionModel.version_no)).where(
                    EnvironmentVersionModel.environment_id == environment_id
                )
            )
            mx = res.scalar_one()
            return (mx + 1) if mx is not None else 1


class SqlPresetStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, preset: ParameterPreset) -> ParameterPreset:
        async with self._sf() as session:
            session.add(
                ParameterPresetModel(
                    id=preset.id,
                    owner_id=preset.owner_id,
                    template_version_id=preset.template_version_id,
                    name=preset.name,
                    values=preset.values,
                    created_at=preset.created_at,
                    updated_at=preset.updated_at,
                )
            )
            await session.commit()
            return preset

    async def get(self, preset_id: UUID) -> ParameterPreset | None:
        async with self._sf() as session:
            m = await session.get(ParameterPresetModel, preset_id)
            return _to_preset(m) if m else None

    async def list_by_template_version(
        self, template_version_id: UUID
    ) -> list[ParameterPreset]:
        async with self._sf() as session:
            res = await session.execute(
                select(ParameterPresetModel)
                .where(ParameterPresetModel.template_version_id == template_version_id)
                .order_by(ParameterPresetModel.created_at.desc())
            )
            return [_to_preset(m) for m in res.scalars().all()]


__all__ = [
    "SqlCodeRepositoryStore",
    "SqlCodeVersionStore",
    "SqlEnvironmentStore",
    "SqlEnvironmentVersionStore",
    "SqlPresetStore",
    "SqlTemplateStore",
    "SqlTemplateVersionStore",
]
