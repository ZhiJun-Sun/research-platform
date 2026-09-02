"""B5/B6 Fake Runner、GPU lease 与 Run 观测 API 测试。"""

from uuid import UUID

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


async def test_gpu_fifo_scheduler_starts_two_and_queues_the_third(ctx: TestContext) -> None:
    """双 GPU 时调度器同轮启动两个 Run；第三个保持 FIFO 等待直到出现空卡。"""
    from hydrolab.execution.scheduler import GpuFifoScheduler

    _, first = await _queued_run(ctx)
    _, second = await _queued_run(ctx)
    _, third = await _queued_run(ctx)
    scheduler = GpuFifoScheduler(ctx.app.state.runs, ctx.app.state.run_control_service)

    first_tick = await scheduler.tick()
    assert first_tick == {"finalized": 0, "started": 2}
    assert (await ctx.app.state.runs.get(UUID(first))).status == "RUNNING"
    assert (await ctx.app.state.runs.get(UUID(second))).status == "RUNNING"
    assert (await ctx.app.state.runs.get(UUID(third))).status == "QUEUED"
    assert set(ctx.app.state.gpu_leases.items) == {0, 1}
    # GPU 租约必须成为子进程环境：不能只“显示分到卡”，实际却让两个训练都抢 GPU0。
    executor = ctx.app.state.run_control_service._executor
    current_specs = []
    for run_id in (UUID(first), UUID(second)):
        execution = await ctx.app.state.executions.get(run_id)
        assert execution is not None
        current_specs.append(executor.started_specs[execution.external_id])
    assert {spec.env["CUDA_VISIBLE_DEVICES"] for spec in current_specs} == {"0", "1"}

    # Fake 执行器需要显式结束；租约释放后，下一个 tick 应自动启动第三条。
    await ctx.app.state.run_control_service.complete_fake(UUID(first))
    second_tick = await scheduler.tick()
    assert second_tick == {"finalized": 0, "started": 1}
    assert (await ctx.app.state.runs.get(UUID(third))).status == "RUNNING"
    assert set(ctx.app.state.gpu_leases.items) == {0, 1}
