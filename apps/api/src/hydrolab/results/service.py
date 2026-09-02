"""B8 结果登记、绘图规格、导出和 Run 对比服务。"""

import csv
import io
import zipfile
from uuid import UUID, uuid4

from hydrolab.core.errors import conflict, not_found, validation_error
from hydrolab.domain.entities import User
from hydrolab.experiments.repositories import ExperimentVersionStore, RunStore
from hydrolab.ports.dto import ObjectRef
from hydrolab.ports.object_storage import ObjectStorage
from hydrolab.results.entities import ExportManifest, MetricPoint, PlotSpec, Result, ResultArtifact
from hydrolab.results.memory import (
    InMemoryArtifacts,
    InMemoryExports,
    InMemoryMetrics,
    InMemoryPlots,
    InMemoryResults,
)
from hydrolab.results.rendering import (
    digest,
    render_basin_metric_distribution,
    render_grouped_metrics,
    render_horizon_lines,
    render_nse_kge_panels,
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
        storage: ObjectStorage,
    ) -> None:
        self._results = results
        self._metrics = metrics
        self._artifacts = artifacts
        self._plots = plots
        self._exports = exports
        self._runs = runs
        self._versions = versions
        self._storage = storage

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
    ) -> dict[str, object]:
        await self._validate_results(owner, result_ids)
        renderers = {
            "basin_metric_distribution": render_basin_metric_distribution,
            "grouped_metrics": render_grouped_metrics,
            "horizon_lines": render_horizon_lines,
            "nse_kge_panels": render_nse_kge_panels,
        }
        renderer = renderers.get(plot_type)
        if renderer is None:
            raise validation_error("不支持的图表类型", {"plot_type": plot_type, "supported": sorted(renderers)})
        metrics = {result_id: await self._metrics.list_by_result(result_id) for result_id in result_ids}
        plot = await self._plots.add(
            PlotSpec(
                owner_id=owner.id,
                result_ids=result_ids,
                plot_type=plot_type,
                data_selection=data_selection,
                options=options,
            )
        )
        artifacts: list[ResultArtifact] = []
        for rendered in renderer(result_ids=result_ids, metrics_by_result=metrics, options=options):
            key = f"plots/{plot.id}/{rendered.filename}"
            self._put_bytes(key, rendered.payload)
            artifact = ResultArtifact(
                result_id=result_ids[0],
                kind="PLOT",
                object_key=key,
                sha256=digest(rendered.payload),
            )
            artifacts.append(await self._artifacts.add(artifact))
        return {"plot": plot, "artifacts": artifacts}

    def _put_bytes(self, key: str, payload: bytes) -> None:
        """The local and fake adapters expose a controlled server-side writer for generated artifacts."""
        put_bytes = getattr(self._storage, "put_bytes", None)
        if not callable(put_bytes):
            raise conflict("当前对象存储不支持服务端生成图表")
        put_bytes(key, payload)


    async def create_export(self, owner: User, result_ids: list[UUID], artifact_ids: list[UUID]) -> ExportManifest:
        results = await self._validate_results(owner, result_ids)
        selected = await self._export_artifacts(owner, result_ids, artifact_ids)
        archive = io.BytesIO()
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            readme = ["# HydroLab result export", "", "## Included results"]
            for result in results:
                readme.append(f"- result_id: {result.id}; run_id: {result.run_id}; dataset_version_id: {result.dataset_version_id}")
                bundle.writestr(f"metrics/{result.id}.csv", self._metrics_csv(await self._metrics.list_by_result(result.id)))
            readme.extend(["", "## Included artifacts"])
            for artifact in selected:
                filename = artifact.object_key.rsplit("/", 1)[-1]
                bundle.writestr(f"artifacts/{artifact.id}_{filename}", await self._read_bytes(artifact.object_key))
                readme.append(f"- {artifact.kind}: {artifact.object_key} (sha256: {artifact.sha256})")
            bundle.writestr("scripts/replot_metrics.py", self._replay_script())
            readme.extend([
                "",
                "## Reproduce a metric comparison figure",
                "Run `python scripts/replot_metrics.py metrics/<result-id>.csv` after installing matplotlib.",
                "Metrics CSV preserves split, horizon, basin, and event dimensions.",
            ])
            bundle.writestr("README.md", "\n".join(readme) + "\n")
        payload = archive.getvalue()
        export = ExportManifest(
            owner_id=owner.id,
            result_ids=result_ids,
            artifact_ids=[item.id for item in selected],
            manifest={
                "format": "zip",
                "schema_version": 1,
                "object_key": f"exports/{owner.id}/{uuid4().hex}.zip",
                "sha256": digest(payload),
                "size_bytes": len(payload),
                "files": ["README.md", *[f"metrics/{item.id}.csv" for item in results]],
            },
        )
        self._put_bytes(str(export.manifest["object_key"]), payload)
        return await self._exports.add(export)

    async def _export_artifacts(
        self, owner: User, result_ids: list[UUID], artifact_ids: list[UUID]
    ) -> list[ResultArtifact]:
        selected: list[ResultArtifact] = []
        if artifact_ids:
            for artifact_id in artifact_ids:
                artifact = await self._artifacts.get(artifact_id)
                if artifact is None or artifact.result_id not in result_ids:
                    raise not_found("导出资产不存在或不属于所选结果")
                selected.append(artifact)
            return selected
        for result_id in result_ids:
            selected.extend(await self._artifacts.list_by_result(result_id))
        return selected

    @staticmethod
    def _metrics_csv(metrics: list[MetricPoint]) -> str:
        text = io.StringIO()
        writer = csv.writer(text)
        writer.writerow(["name", "value", "split", "horizon", "basin_id", "event_id"])
        for item in metrics:
            writer.writerow([item.name, item.value, item.split, item.horizon or "", item.basin_id or "", item.event_id or ""])
        return text.getvalue()

    @staticmethod
    def _replay_script() -> str:
        return '''"""Recreate a HydroLab metric figure from an exported CSV."""
import csv
import sys
from pathlib import Path

import matplotlib.pyplot as plt

if len(sys.argv) != 2:
    raise SystemExit("Usage: python replot_metrics.py metrics/<result-id>.csv")

path = Path(sys.argv[1])
with path.open(newline="", encoding="utf-8") as handle:
    rows = list(csv.DictReader(handle))

plt.rcParams.update({"font.family": "DejaVu Sans", "axes.unicode_minus": False})
figure, axis = plt.subplots(figsize=(8, 4.8))
for row in rows:
    axis.scatter(row["name"], float(row["value"]), label=row["name"])
axis.set_title("HydroLab exported metrics", fontweight="bold")
axis.set_xlabel("Metric")
axis.set_ylabel("Value")
axis.grid(axis="y", alpha=0.25, linewidth=0.8)
axis.spines["top"].set_visible(False)
axis.spines["right"].set_visible(False)
figure.tight_layout()
figure.savefig(path.with_suffix(".png"), dpi=220, bbox_inches="tight")
'''

    async def _read_bytes(self, key: str) -> bytes:
        stream = await self._storage.open_range(ObjectRef(key=key), 0)
        return stream.read()


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
