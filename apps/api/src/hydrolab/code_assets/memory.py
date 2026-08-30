"""B3 InMemory Repository 实现。"""

from typing import Generic, TypeVar
from uuid import UUID

from hydrolab.code_assets.entities import (
    CodeRepository,
    CodeVersion,
    EnvironmentVersion,
    ExperimentTemplate,
    ParameterPreset,
    RuntimeEnvironment,
    TemplateVersion,
)

T = TypeVar("T")


class _Memory(Generic[T]):
    def __init__(self) -> None:
        self.items: dict[UUID, T] = {}

    async def add(self, item: T) -> T:
        self.items[item.id] = item  # type: ignore[attr-defined]
        return item

    async def get(self, item_id: UUID) -> T | None:
        return self.items.get(item_id)


class InMemoryCodeRepositories(_Memory[CodeRepository]):
    async def list_by_owner(self, owner_id: UUID) -> list[CodeRepository]:
        return [item for item in self.items.values() if item.owner_id == owner_id]


class InMemoryCodeVersions(_Memory[CodeVersion]):
    async def list_by_repository(self, repository_id: UUID) -> list[CodeVersion]:
        return sorted(
            (x for x in self.items.values() if x.repository_id == repository_id),
            key=lambda x: x.version_no,
            reverse=True,
        )

    async def next_version_no(self, repository_id: UUID) -> int:
        return len(await self.list_by_repository(repository_id)) + 1


class InMemoryTemplates(_Memory[ExperimentTemplate]):
    async def list_by_owner(self, owner_id: UUID) -> list[ExperimentTemplate]:
        return [item for item in self.items.values() if item.owner_id == owner_id]


class InMemoryTemplateVersions(_Memory[TemplateVersion]):
    async def list_by_template(self, template_id: UUID) -> list[TemplateVersion]:
        return sorted(
            (x for x in self.items.values() if x.template_id == template_id), key=lambda x: x.version_no, reverse=True
        )

    async def next_version_no(self, template_id: UUID) -> int:
        return len(await self.list_by_template(template_id)) + 1


class InMemoryEnvironments(_Memory[RuntimeEnvironment]):
    async def list_by_owner(self, owner_id: UUID) -> list[RuntimeEnvironment]:
        return [item for item in self.items.values() if item.owner_id == owner_id]


class InMemoryEnvironmentVersions(_Memory[EnvironmentVersion]):
    async def list_by_environment(self, environment_id: UUID) -> list[EnvironmentVersion]:
        return sorted(
            (x for x in self.items.values() if x.environment_id == environment_id),
            key=lambda x: x.version_no,
            reverse=True,
        )

    async def next_version_no(self, environment_id: UUID) -> int:
        return len(await self.list_by_environment(environment_id)) + 1


class InMemoryPresets(_Memory[ParameterPreset]):
    async def list_by_template_version(self, template_version_id: UUID) -> list[ParameterPreset]:
        return [item for item in self.items.values() if item.template_version_id == template_version_id]
