"""B8 结果、绘图和 Run 对比测试。"""

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
        ],
        headers=headers,
    )
    assert metrics.status_code == 201, metrics.text
    plot = await ctx.client.post(
        "/api/v1/plots",
        json={"result_ids": [result_id], "plot_type": "hydrograph", "data_selection": {"basin_id": "11480390"}},
        headers=headers,
    )
    assert plot.status_code == 201, plot.text
    exported = await ctx.client.post("/api/v1/exports", json={"result_ids": [result_id]}, headers=headers)
    assert exported.status_code == 201, exported.text
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
