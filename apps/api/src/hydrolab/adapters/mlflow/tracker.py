"""MLflow Tracking 真实实现（TRACK-01 Spike 适配器）。

映射（plans/05 §6.2）：
- HydroLab Run -> MLflow run
- resolved parameters -> MLflow params（扁平化且限长）
- MetricPoint -> MLflow metrics
- Artifact -> 记录 HydroLab Artifact URI/hash（不双写大文件）
- Checkpoint -> model/checkpoint 元数据 + checkpoint_id tag

边界（§6.3）：业务真相源在 PostgreSQL；MLflow 失败不得反向把成功训练改成 FAILED；
同步记录独立状态并可重放（重放不产生第二个 MLflow Run）。
"""

from __future__ import annotations

from hydrolab.core.errors import dependency_unavailable
from hydrolab.ports.dto import (
    ArtifactReference,
    ExternalRunRef,
    MetricRecord,
    TrackingContext,
)

_EXPERIMENT_NAME = "hydrolab"


class MlflowTrackingAdapter:
    """用 MLflow Tracking 客户端实现 ExperimentTracker 端口。

    同步 SDK 调用用 asyncio.to_thread 包裹，避免阻塞事件循环。
    """

    def __init__(self, tracking_uri: str, experiment_name: str = _EXPERIMENT_NAME) -> None:
        self._tracking_uri = tracking_uri
        self._experiment_name = experiment_name
        self._started: dict[str, str] = {}

    def _client(self):
        from mlflow.tracking import MlflowClient

        return MlflowClient(tracking_uri=self._tracking_uri)

    def _ensure_experiment(self, client) -> str:
        exp = client.get_experiment_by_name(self._experiment_name)
        if exp is not None:
            return exp.experiment_id
        return client.create_experiment(self._experiment_name)

    async def start_run(self, context: TrackingContext) -> ExternalRunRef:
        import asyncio

        existing = self._started.get(str(context.run_id))
        if existing:
            return ExternalRunRef(system="mlflow", external_run_id=existing)
        try:
            client = self._client()
            experiment_id = self._ensure_experiment(client)
            # 幂等：重启/重放时复用同一条 MLflow run，绝不创建重复 run。
            replayed = await asyncio.to_thread(
                client.search_runs,
                experiment_id,
                filter_string=f'tags."hydrolab.run_id" = "{context.run_id}"',
                order_by=["start_time desc"],
                max_results=1,
            )
            if replayed:
                external_id = replayed[0].info.run_id
            else:
                run = await asyncio.to_thread(
                    client.create_run,
                    experiment_id=experiment_id,
                    run_name=context.display_name,
                    tags={
                        "hydrolab.run_id": str(context.run_id),
                        "hydrolab.experiment_version_id": str(context.experiment_version_id),
                        **context.tags,
                    },
                )
                external_id = run.info.run_id
        except Exception as exc:
            raise dependency_unavailable(
                "MLflow 创建 Run 失败", {"reason": exc.__class__.__name__}
            ) from exc
        self._started[str(context.run_id)] = external_id
        return ExternalRunRef(system="mlflow", external_run_id=external_id)

    async def log_parameters(self, run: ExternalRunRef, values: dict[str, object]) -> None:
        import asyncio

        try:
            client = self._client()
            # 扁平化且限制单个 param 长度，避免 MLflow 拒绝
            flat: dict[str, str] = {}
            for k, v in values.items():
                if isinstance(v, (dict, list)):
                    import json as _json

                    flat[k] = _json.dumps(v, ensure_ascii=False)[:250]
                else:
                    flat[k] = str(v)[:250]
            await asyncio.to_thread(client.log_batch, run.external_run_id, params=flat)
        except Exception as exc:
            raise dependency_unavailable(
                "MLflow 记录参数失败", {"reason": exc.__class__.__name__}
            ) from exc

    async def log_metrics(self, run: ExternalRunRef, points: list[MetricRecord]) -> None:
        import asyncio

        try:
            from mlflow.entities import Metric

            metrics = [
                Metric(
                    key=p.name,
                    value=float(p.value),
                    timestamp=int(p.timestamp.timestamp() * 1000) if p.timestamp else None,
                    step=p.step or 0,
                )
                for p in points
            ]
            client = self._client()
            await asyncio.to_thread(client.log_batch, run.external_run_id, metrics=metrics)
        except Exception as exc:
            raise dependency_unavailable(
                "MLflow 记录指标失败", {"reason": exc.__class__.__name__}
            ) from exc

    async def log_artifact_reference(
        self, run: ExternalRunRef, artifact: ArtifactReference
    ) -> None:
        import asyncio

        try:
            from mlflow.entities import RunTag

            client = self._client()
            tags = [
                RunTag(f"hydrolab.artifact.{artifact.kind}.uri", artifact.uri),
                RunTag(f"hydrolab.artifact.{artifact.kind}.id", str(artifact.artifact_id)),
            ]
            if artifact.sha256:
                tags.append(RunTag(f"hydrolab.artifact.{artifact.kind}.sha256", artifact.sha256))
            await asyncio.to_thread(client.log_batch, run.external_run_id, tags=tags)
        except Exception as exc:
            raise dependency_unavailable(
                "MLflow 记录 Artifact 失败", {"reason": exc.__class__.__name__}
            ) from exc

    async def finish_run(self, run: ExternalRunRef, status: str) -> None:
        import asyncio

        try:
            client = self._client()
            # MLflow 状态与业务 Run 解耦：仅记录终态，不反向覆盖业务状态
            await asyncio.to_thread(
                client.set_terminated, run.external_run_id, status="FINISHED"
            )
        except Exception as exc:
            raise dependency_unavailable(
                "MLflow 结束 Run 失败", {"reason": exc.__class__.__name__}
            ) from exc

    async def healthcheck(self) -> bool:
        import asyncio

        try:
            client = self._client()
            await asyncio.to_thread(client.search_experiments)
            return True
        except Exception:
            return False