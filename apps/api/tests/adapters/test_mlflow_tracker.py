"""MlflowTrackingAdapter 单测（TRACK-01 Spike 验证）。

本地/远程均无可用 MLflow 服务，mock `_client()` 返回的可控 fake 客户端，
验证适配器的编排逻辑：创建 Run、参数、指标、Artifact、结束、健康检查、错误映射。
失败可重放、不反向覆盖业务 Run 状态（§6.3）。
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from hydrolab.adapters.mlflow import MlflowTrackingAdapter
from hydrolab.core.errors import AppError
from hydrolab.ports.dto import ArtifactReference, MetricRecord, TrackingContext


class FakeMlflowClient:
    def __init__(self) -> None:
        self.experiments: dict[str, dict] = {}
        self.runs: list[dict] = []
        self.logged: list[tuple[str, dict]] = []

    def get_experiment_by_name(self, name: str):
        exp = next((e for e in self.experiments.values() if e["name"] == name), None)
        if exp is None:
            return None
        return type("Experiment", (), {"experiment_id": exp["id"], "name": exp["name"]})()

    def create_experiment(self, name: str) -> str:
        eid = f"exp-{len(self.experiments)+1}"
        self.experiments[eid] = {"id": eid, "name": name}
        return eid

    def create_run(self, experiment_id: str, run_name: str, tags: dict):
        run_id = f"mlflow-run-{len(self.runs)+1}"
        self.runs.append({"run_id": run_id, "tags": tags})
        info = type("Info", (), {"run_id": run_id})()
        return type("Run", (), {"info": info})()

    def search_runs(self, experiment_id, filter_string="", order_by=None, max_results=None):
        import re

        match = re.search(r'=\s*"([^"]+)"', filter_string)
        wanted = match.group(1) if match else None
        matched = [r for r in self.runs if wanted is None or r["tags"].get("hydrolab.run_id") == wanted]
        matched = sorted(matched, key=lambda r: r["run_id"])[- (max_results or len(matched)):]
        return [type("Run", (), {"info": type("Info", (), {"run_id": r["run_id"]})()})() for r in matched]

    def log_batch(self, run_id: str, **kwargs) -> None:
        self.logged.append((run_id, kwargs))

    def set_terminated(self, run_id: str, status: str) -> None:
        self.logged.append((run_id, {"status": status}))

    def search_experiments(self) -> list:
        return list(self.experiments.values())


@pytest.fixture()
def tracker() -> MlflowTrackingAdapter:
    adapter = MlflowTrackingAdapter(tracking_uri="http://mlflow:5000")
    fake = FakeMlflowClient()
    adapter._client = lambda: fake  # type: ignore[method-assign]
    return adapter


def _context() -> TrackingContext:
    return TrackingContext(
        run_id=uuid4(), experiment_version_id=uuid4(), display_name="contract-run"
    )


async def test_full_tracking_lifecycle(tracker: MlflowTrackingAdapter) -> None:
    ref = await tracker.start_run(_context())
    assert ref.system == "mlflow"
    assert ref.external_run_id.startswith("mlflow-run-")

    await tracker.log_parameters(ref, {"lr": 0.001, "epochs": 10})
    await tracker.log_metrics(
        ref, [MetricRecord(name="nse", value=0.82, step=10, split="val")]
    )
    await tracker.log_artifact_reference(
        ref,
        ArtifactReference(
            artifact_id=uuid4(), kind="checkpoint", uri="s3://hydrolab/ckpt/1", sha256="ab"
        ),
    )
    await tracker.finish_run(ref, "SUCCEEDED")
    assert await tracker.healthcheck() is True


async def test_healthcheck_returns_false_when_down() -> None:
    class Broken:
        def search_experiments(self):
            raise RuntimeError("mlflow down")

    adapter = MlflowTrackingAdapter(tracking_uri="http://mlflow:5000")
    adapter._client = lambda: Broken()  # type: ignore[method-assign]
    assert await adapter.healthcheck() is False


async def test_start_run_is_idempotent_across_restart(tracker: MlflowTrackingAdapter) -> None:
    """重启/重放后复用同一条 MLflow run，不创建重复 run。"""
    ctx = _context()
    first = await tracker.start_run(ctx)
    # 模拟进程内 _started 映射丢失（Worker 重启）
    tracker._started.clear()  # type: ignore[attr-defined]
    second = await tracker.start_run(ctx)
    assert second.external_run_id == first.external_run_id
    # 只真正创建了一次 run
    assert [r["run_id"] for r in tracker._client().runs] == [first.external_run_id]


async def test_failure_maps_to_apperror(tracker: MlflowTrackingAdapter) -> None:

    tracker._client().log_batch = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("network")
    )
    ref = await tracker.start_run(_context())
    with pytest.raises(AppError):
        await tracker.log_parameters(ref, {"lr": 1.0})