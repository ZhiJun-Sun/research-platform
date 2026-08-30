"""B5/B6 Fake Runner、GPU lease 与 Run 观测 API 测试。"""

from tests.conftest import TestContext
from tests.test_experiments import _ready_assets


async def _queued_run(ctx: TestContext) -> tuple[dict[str, str], str]:
    headers, assets = await _ready_assets(ctx)
    draft = await ctx.client.post("/api/v1/experiment-drafts", json={"name": "runner test"}, headers=headers)
    await ctx.client.patch(
        f"/api/v1/experiment-drafts/{draft.json()['id']}",
        json={**assets, "parameter_values": {"epochs": 1}},
        headers=headers,
    )
    submitted = await ctx.client.post(
        f"/api/v1/experiment-drafts/{draft.json()['id']}/submit", headers=headers
    )
    return headers, submitted.json()["run"]["id"]


async def test_fake_runner_lifecycle_releases_dual_gpu_leases(ctx: TestContext) -> None:
    headers, first_run = await _queued_run(ctx)
    await ctx.client.post("/api/v1/internal/outbox/dispatch", headers=headers)
    started = await ctx.client.post(f"/api/v1/runs/{first_run}/start", json={"gpu_count": 2}, headers=headers)
    assert started.status_code == 200
    assert started.json()["status"] == "RUNNING"
    assert len(ctx.app.state.gpu_leases.items) == 2

    completed = await ctx.client.post(
        f"/api/v1/internal/runs/{first_run}/complete", json={"exit_code": 0}, headers=headers
    )
    assert completed.json()["status"] == "SUCCEEDED"
    assert not ctx.app.state.gpu_leases.items


async def test_fake_runner_rejects_contention_and_cancel_releases_lease(ctx: TestContext) -> None:
    headers, first_run = await _queued_run(ctx)
    _, second_run = await _queued_run(ctx)
    await ctx.client.post(f"/api/v1/runs/{first_run}/start", json={"gpu_count": 2}, headers=headers)
    blocked = await ctx.client.post(f"/api/v1/runs/{second_run}/start", json={"gpu_count": 1}, headers=headers)
    assert blocked.status_code == 409
    cancelled = await ctx.client.post(f"/api/v1/runs/{first_run}/cancel", headers=headers)
    assert cancelled.json()["status"] == "CANCELLED"
    assert not ctx.app.state.gpu_leases.items
    started = await ctx.client.post(f"/api/v1/runs/{second_run}/start", json={"gpu_count": 1}, headers=headers)
    assert started.status_code == 200


async def test_run_events_support_cursor_and_sse_resume(ctx: TestContext) -> None:
    headers, run_id = await _queued_run(ctx)
    await ctx.client.post(f"/api/v1/runs/{run_id}/start", json={"gpu_count": 1}, headers=headers)
    await ctx.client.post(
        f"/api/v1/internal/runs/{run_id}/progress",
        json={"percent": 25, "stage": "TRAINING", "eta_seconds": 120},
        headers=headers,
    )
    await ctx.client.post(
        f"/api/v1/internal/runs/{run_id}/metrics",
        json={"name": "nse", "value": 0.71, "step": 3},
        headers=headers,
    )
    events = await ctx.client.get(f"/api/v1/runs/{run_id}/events", headers=headers)
    assert [item["event_type"] for item in events.json()][-2:] == ["run.progress.updated", "run.metric.reported"]
    cursor = events.json()[-2]["id"]
    resumed = await ctx.client.get(f"/api/v1/runs/{run_id}/events", params={"after_id": cursor}, headers=headers)
    assert len(resumed.json()) == 1
    stream_headers = {**headers, "Last-Event-ID": str(cursor)}
    stream = await ctx.client.get(
        f"/api/v1/runs/{run_id}/events/stream", headers=stream_headers
    )
    assert stream.status_code == 200
    assert "run.metric.reported" in stream.text
