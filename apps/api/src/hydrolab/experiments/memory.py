"""B4 InMemory Repository 实现。"""

from uuid import UUID

from hydrolab.experiments.entities import Experiment, ExperimentDraft, ExperimentVersion, OutboxEvent, Run, RunStage
from hydrolab.experiments.enums import OutboxStatus


class InMemoryDrafts:
    def __init__(self) -> None:
        self.items: dict[UUID, ExperimentDraft] = {}

    async def add(self, item: ExperimentDraft) -> ExperimentDraft:
        self.items[item.id] = item
        return item

    async def get(self, item_id: UUID) -> ExperimentDraft | None:
        return self.items.get(item_id)

    async def update(self, item: ExperimentDraft) -> ExperimentDraft:
        self.items[item.id] = item
        return item

    async def list_by_owner(self, owner_id: UUID) -> list[ExperimentDraft]:
        return [x for x in self.items.values() if x.owner_id == owner_id]


class InMemoryExperiments:
    def __init__(self) -> None:
        self.items: dict[UUID, Experiment] = {}

    async def add(self, item: Experiment) -> Experiment:
        self.items[item.id] = item
        return item

    async def get(self, item_id: UUID) -> Experiment | None:
        return self.items.get(item_id)

    async def list_by_owner(self, owner_id: UUID) -> list[Experiment]:
        return [x for x in self.items.values() if x.owner_id == owner_id]


class InMemoryExperimentVersions:
    def __init__(self) -> None:
        self.items: dict[UUID, ExperimentVersion] = {}

    async def add(self, item: ExperimentVersion) -> ExperimentVersion:
        self.items[item.id] = item
        return item

    async def get(self, item_id: UUID) -> ExperimentVersion | None:
        return self.items.get(item_id)

    async def list_by_experiment(self, experiment_id: UUID) -> list[ExperimentVersion]:
        return sorted(
            (x for x in self.items.values() if x.experiment_id == experiment_id),
            key=lambda x: x.version_no,
            reverse=True,
        )

    async def next_version_no(self, experiment_id: UUID) -> int:
        return len(await self.list_by_experiment(experiment_id)) + 1


class InMemoryRuns:
    def __init__(self) -> None:
        self.items: dict[UUID, Run] = {}

    async def add(self, item: Run) -> Run:
        self.items[item.id] = item
        return item

    async def get(self, item_id: UUID) -> Run | None:
        return self.items.get(item_id)

    async def list_by_experiment(self, experiment_id: UUID) -> list[Run]:
        return sorted(
            (x for x in self.items.values() if x.experiment_id == experiment_id),
            key=lambda x: x.created_at,
            reverse=True,
        )

    async def get_by_idempotency(self, owner_id: UUID, key: str) -> Run | None:
        return next((x for x in self.items.values() if x.owner_id == owner_id and x.idempotency_key == key), None)


class InMemoryRunStages:
    def __init__(self) -> None:
        self.items: dict[UUID, RunStage] = {}

    async def add(self, item: RunStage) -> RunStage:
        self.items[item.id] = item
        return item

    async def list_by_run(self, run_id: UUID) -> list[RunStage]:
        return sorted((x for x in self.items.values() if x.run_id == run_id), key=lambda x: x.position)


class InMemoryOutbox:
    def __init__(self) -> None:
        self.items: dict[UUID, OutboxEvent] = {}

    async def add(self, item: OutboxEvent) -> OutboxEvent:
        self.items[item.id] = item
        return item

    async def list_pending(self) -> list[OutboxEvent]:
        return [x for x in self.items.values() if x.status == OutboxStatus.PENDING]
