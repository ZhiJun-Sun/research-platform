"""B8 结果 InMemory 仓储。"""

from uuid import UUID

from hydrolab.results.entities import ExportManifest, MetricPoint, PlotSpec, Result, ResultArtifact


class InMemoryResults:
    def __init__(self) -> None:
        self.items: dict[UUID, Result] = {}

    async def add(self, item: Result) -> Result:
        self.items[item.id] = item
        return item

    async def get(self, item_id: UUID) -> Result | None:
        return self.items.get(item_id)

    async def list_by_owner(self, owner_id: UUID) -> list[Result]:
        return [item for item in self.items.values() if item.owner_id == owner_id]

    async def list_by_run(self, run_id: UUID) -> list[Result]:
        return [item for item in self.items.values() if item.run_id == run_id]


class InMemoryMetrics:
    def __init__(self) -> None:
        self.items: list[MetricPoint] = []

    async def add_many(self, items: list[MetricPoint]) -> list[MetricPoint]:
        self.items.extend(items)
        return items

    async def list_by_result(self, result_id: UUID) -> list[MetricPoint]:
        return [item for item in self.items if item.result_id == result_id]


class InMemoryArtifacts:
    def __init__(self) -> None:
        self.items: dict[UUID, ResultArtifact] = {}

    async def add(self, item: ResultArtifact) -> ResultArtifact:
        self.items[item.id] = item
        return item

    async def get(self, item_id: UUID) -> ResultArtifact | None:
        return self.items.get(item_id)

    async def list_by_result(self, result_id: UUID) -> list[ResultArtifact]:
        return [item for item in self.items.values() if item.result_id == result_id]


class InMemoryPlots:
    def __init__(self) -> None:
        self.items: dict[UUID, PlotSpec] = {}

    async def add(self, item: PlotSpec) -> PlotSpec:
        self.items[item.id] = item
        return item


class InMemoryExports:
    def __init__(self) -> None:
        self.items: dict[UUID, ExportManifest] = {}

    async def add(self, item: ExportManifest) -> ExportManifest:
        self.items[item.id] = item
        return item
