"""B8 结果、绘图和 Run 对比测试。"""

import io
import zipfile

from hydrolab.execution.collector import CollectedArtifact, CollectedMetric, CollectionReport
from hydrolab.ports.dto import ObjectRef
from hydrolab.results.service import ResultService
from tests.conftest import TestContext
from tests.test_execution import _queued_run


async def _completed_run(ctx: TestContext) -> tuple[dict[str, str], str]:
    headers, run_id = await _queued_run(ctx)
    await ctx.client.post(f"/api/v1/runs/{run_id}/start", json={"gpu_count": 1}, headers=headers)
    await ctx.client.post(
        f"/api/v1/internal/runs/{run_id}/complete",
        json={"exit_code": 0},
        headers=headers,
    )
    return headers, run_id


async def test_result_metrics_plot_and_export_are_traceable(ctx: TestContext) -> None:
    headers, run_id = await _completed_run(ctx)
    created = await ctx.client.post(f"/api/v1/runs/{run_id}/result", headers=headers)
    assert created.status_code == 201, created.text
    result_id = created.json()["id"]
    metrics = await ctx.client.post(
        f"/api/v1/results/{result_id}/metrics",
        json=[
            {"name": "NSE", "value": 0.846},
            {"name": "NSE", "value": 0.412, "basin_id": "11480390"},
            {"name": "NSE", "value": 0.711, "basin_id": "81000200"},
            {"name": "NSE", "value": 0.803, "basin_id": "81001590"},
            {"name": "NSE", "value": 0.84, "horizon": 1},
            {"name": "NSE", "value": 0.80, "horizon": 2},
            {"name": "NSE", "value": 0.76, "horizon": 3},
            {"name": "KGE", "value": 0.88, "horizon": 1},
            {"name": "KGE", "value": 0.83, "horizon": 2},
            {"name": "KGE", "value": 0.78, "horizon": 3},
        ],
        headers=headers,
    )
    assert metrics.status_code == 201, metrics.text
    listed_metrics = await ctx.client.get(f"/api/v1/results/{result_id}/metrics", headers=headers)
    assert [item["horizon"] for item in listed_metrics.json() if item["name"] == "NSE" and item["horizon"]] == [1, 2, 3]
    for plot_type, options in (
        ("basin_metric_distribution", {"metric": "NSE", "title": "流域 NSE 分布"}),
        ("grouped_metrics", {"metrics": ["NSE"], "title": "北江实验对比"}),
        ("horizon_lines", {"metric": "NSE", "title": "NSE 预测步长对比"}),
        ("nse_kge_panels", {"title": "NSE 与 KGE 预测步长对比"}),
    ):
        plot = await ctx.client.post(
            "/api/v1/plots",
            json={"result_ids": [result_id], "plot_type": plot_type, "options": options},
            headers=headers,
        )
        assert plot.status_code == 201, plot.text
        payload = plot.json()
        assert payload["plot"]["plot_type"] == plot_type
        assert {item["object_key"].rsplit(".", 1)[-1] for item in payload["artifacts"]} == {"png", "pdf", "svg", "csv"}
        for item in payload["artifacts"]:
            stream = await ctx.app.state.result_service._storage.open_range(
                ObjectRef(key=item["object_key"]), 0
            )
            assert stream.read()
    exported = await ctx.client.post("/api/v1/exports", json={"result_ids": [result_id]}, headers=headers)
    assert exported.status_code == 201, exported.text
    manifest = exported.json()["manifest"]
    assert manifest["format"] == "zip"
    stream = await ctx.app.state.result_service._storage.open_range(
        ObjectRef(key=manifest["object_key"]), 0
    )
    with zipfile.ZipFile(io.BytesIO(stream.read())) as bundle:
        names = set(bundle.namelist())
        assert "README.md" in names
        assert "scripts/replot_metrics.py" in names
        assert f"metrics/{result_id}.csv" in names
        assert any(name.endswith(".png") for name in names)
        assert "horizon" in bundle.read(f"metrics/{result_id}.csv").decode()
    listed = await ctx.client.get("/api/v1/results", headers=headers)
    assert listed.status_code == 200, listed.text
    assert [item["id"] for item in listed.json()] == [result_id]


async def test_compare_rejects_results_from_different_dataset_versions(ctx: TestContext) -> None:
    headers, first_run = await _completed_run(ctx)
    _, second_run = await _completed_run(ctx)
    first = await ctx.client.post(f"/api/v1/runs/{first_run}/result", headers=headers)
    second = await ctx.client.post(f"/api/v1/runs/{second_run}/result", headers=headers)
    first_id, second_id = first.json()["id"], second.json()["id"]
    for result_id, nse in ((first_id, 0.812), (second_id, 0.846)):
        await ctx.client.post(
            f"/api/v1/results/{result_id}/metrics",
            json=[{"name": "NSE", "value": nse}],
            headers=headers,
        )
    compared = await ctx.client.post(
        "/api/v1/results/compare",
        json={"result_ids": [first_id, second_id]},
        headers=headers,
    )
    assert compared.status_code == 409, compared.text
    assert "同一冻结数据版本" in compared.json()["error"]["message"]


async def test_collection_is_persisted_idempotently_and_readable_after_service_restart(
    ctx: TestContext,
) -> None:
    headers, run_id = await _completed_run(ctx)
    report = CollectionReport(
        experiment_dirs=["smoke"],
        metrics=[CollectedMetric(name="NSE@Avg", value=0.9)],
        artifacts=[
            CollectedArtifact(
                kind="predictions",
                relative_path="experiments/smoke/results/predictions.csv",
                object_key=f"run-artifacts/{run_id}/predictions.csv",
                sha256="a" * 64,
                size_bytes=10,
            )
        ],
    )

    first = await ctx.app.state.result_service.ingest_collection(run_id, report)
    second = await ctx.app.state.result_service.ingest_collection(run_id, report)
    assert first["metrics_added"] == 1
    assert first["artifacts_added"] == 1
    assert second["metrics_added"] == 0
    assert second["artifacts_added"] == 0

    restarted = ResultService(
        ctx.app.state.results,
        ctx.app.state.result_metrics,
        ctx.app.state.result_artifacts,
        ctx.app.state.plot_specs,
        ctx.app.state.export_manifests,
        ctx.app.state.runs,
        ctx.app.state.experiment_versions,
        ctx.app.state.result_service._storage,
    )
    persisted = await restarted.persisted_collection(run_id)
    assert persisted is not None
    assert [item.name for item in persisted["metrics"]] == ["NSE@Avg"]

    # RunControlService has no in-memory report in this Fake-runner test, so
    # this exercises the API's durable fallback used after process restarts.
    collection = await ctx.client.get(f"/api/v1/runs/{run_id}/collection", headers=headers)
    assert collection.status_code == 200, collection.text
    assert collection.json()["collected"] is True
    assert collection.json()["metrics"][0]["name"] == "NSE@Avg"
