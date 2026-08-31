"""B8 结果登记、绘图规格、导出和 Run 对比服务。"""

from uuid import UUID

from hydrolab.core.errors import conflict, not_found, validation_error
from hydrolab.domain.entities import User
from hydrolab.experiments.repositories import ExperimentVersionStore, RunStore
from hydrolab.results.entities import ExportManifest, MetricPoint, PlotSpec, Result, ResultArtifact
from hydrolab.results.memory import (
    InMemoryArtifacts,
    InMemoryExports,
    InMemoryMetrics,
    InMemoryPlots,
    InMemoryResults,
)


class ResultService:
    def __init__(
        self,
        results: InMemoryResults,
        metrics: InMemoryMetrics,
        artifacts: InMemoryArtifacts,
        plots: InMemoryPlots,
        exports: InMemoryExports,
        runs: RunStore,
        versions: ExperimentVersionStore,
    ) -> None:
        self._results = results
        self._metrics = metrics
        self._artifacts = artifacts
        self._plots = plots
        self._exports = exports
        self._runs = runs
        self._versions = versions

    async def create_result(self, owner: User, run_id: UUID) -> Result:
        run = await self._runs.get(run_id)
        if run is None or run.owner_id != owner.id:
            raise not_found("Run 不存在")
        if run.status.value != "SUCCEEDED":
            raise conflict("只有成功 Run 可以登记结果")
        existing = await self._results.list_by_run(run_id)
        if existing:
            return existing[0]
        version = await self._versions.get(run.experiment_version_id)
        if version is None:
            raise conflict("Run 对应的实验版本不存在")
        dataset_version_id = version.resolved_config.get("dataset_version_id")
        if not isinstance(dataset_version_id, str):
            raise conflict("实验版本缺少冻结数据版本")
        return await self._results.add(Result(run_id=run_id, owner_id=owner.id, dataset_version_id=dataset_version_id))

    async def add_metrics(self, owner: User, result_id: UUID, items: list[MetricPoint]) -> list[MetricPoint]:
        await self._owned_result(owner, result_id)
        if not items:
            raise validation_error("至少需要一条指标")
        for item in items:
            item.result_id = result_id
        return await self._metrics.add_many(items)

    async def add_artifact(self, owner: User, result_id: UUID, item: ResultArtifact) -> ResultArtifact:
        await self._owned_result(owner, result_id)
        item.result_id = result_id
        return await self._artifacts.add(item)

    async def metrics(self, owner: User, result_id: UUID) -> list[MetricPoint]:
        await self._owned_result(owner, result_id)
        return await self._metrics.list_by_result(result_id)

    async def create_plot(
        self,
        owner: User,
        result_ids: list[UUID],
        plot_type: str,
        data_selection: dict[str, object],
        options: dict[str, object],
    ) -> PlotSpec:
        await self._validate_results(owner, result_ids)
        if not plot_type:
            raise validation_error("plot_type 不能为空")
        return await self._plots.add(
            PlotSpec(
                owner_id=owner.id,
                result_ids=result_ids,
                plot_type=plot_type,
                data_selection=data_selection,
                options=options,
            )
        )

    async def create_export(self, owner: User, result_ids: list[UUID], artifact_ids: list[UUID]) -> ExportManifest:
        await self._validate_results(owner, result_ids)
        return await self._exports.add(
            ExportManifest(
                owner_id=owner.id,
                result_ids=result_ids,
                artifact_ids=artifact_ids,
                manifest={"format": "zip", "schema_version": 1},
            )
        )

    async def compare(self, owner: User, result_ids: list[UUID]) -> dict[str, object]:
        if not 2 <= len(result_ids) <= 5:
            raise validation_error("一次必须比较 2 至 5 个结果")
        results = await self._validate_results(owner, result_ids)
        dataset_ids = {item.dataset_version_id for item in results}
        if len(dataset_ids) != 1:
            raise conflict("只能比较同一冻结数据版本的结果")
        values: dict[str, dict[str, float]] = {}
        for result in results:
            values[str(result.id)] = {
                item.name: item.value
                for item in await self._metrics.list_by_result(result.id)
                if item.basin_id is None and item.event_id is None
            }
        baseline = values[str(results[0].id)]
        return {
            "dataset_version_id": results[0].dataset_version_id,
            "baseline_result_id": str(results[0].id),
            "metrics": values,
            "delta_from_baseline": {
                result_id: {name: value - baseline.get(name, value) for name, value in metrics.items()}
                for result_id, metrics in values.items()
            },
        }

    async def _owned_result(self, owner: User, result_id: UUID) -> Result:
        result = await self._results.get(result_id)
        if result is None or result.owner_id != owner.id:
            raise not_found("结果不存在")
        return result

    async def _validate_results(self, owner: User, result_ids: list[UUID]) -> list[Result]:
        if not result_ids:
            raise validation_error("至少需要一个结果")
        return [await self._owned_result(owner, result_id) for result_id in result_ids]
