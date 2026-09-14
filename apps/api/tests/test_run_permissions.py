"""跨用户资源权限：观测与内部接口必须拒绝非所有者/非管理员访问。"""

from tests.conftest import TestContext, invite_and_accept, login
from tests.test_experiments import _ready_assets


async def _admin_run(ctx: TestContext) -> tuple[dict[str, str], str]:
    headers, assets = await _ready_assets(ctx)
    draft = await ctx.client.post("/api/v1/experiment-drafts", json={"name": "perm test"}, headers=headers)
    await ctx.client.patch(
        f"/api/v1/experiment-drafts/{draft.json()['id']}",
        json={**assets, "parameter_values": {"epochs": 1}},
        headers=headers,
    )
    submitted = await ctx.client.post(
        f"/api/v1/experiment-drafts/{draft.json()['id']}/submit", headers=headers
    )
    run_id = submitted.json()["run"]["id"]
    await ctx.client.post(f"/api/v1/runs/{run_id}/start", json={"gpu_count": 1}, headers=headers)
    return headers, run_id


async def test_observation_and_internal_endpoints_reject_non_owner(
    ctx: TestContext,
) -> None:
    admin_headers, run_id = await _admin_run(ctx)
    # 非管理员、非所有者的第二个用户
    other_headers = await invite_and_accept(ctx, admin_headers, "viewer@hydrolab.cn", "观察者", "viewer1234")

    # 观测接口：均应为 403
    for method, url, kwargs in [
        ("GET", f"/api/v1/runs/{run_id}/events", {}),
        ("GET", f"/api/v1/runs/{run_id}/logs", {}),
        ("GET", f"/api/v1/runs/{run_id}/resources", {}),
        ("GET", f"/api/v1/runs/{run_id}/collection", {}),
        ("POST", f"/api/v1/runs/{run_id}/await", {"json": {"timeout_seconds": 1}}),
    ]:
        resp = await getattr(ctx.client, method.lower())(url, headers=other_headers, **kwargs)
        assert resp.status_code == 403, f"{method} {url} 应拒绝非所有者: {resp.text}"

    # 控制接口：同样拒绝非所有者
    start = await ctx.client.post(f"/api/v1/runs/{run_id}/start", json={"gpu_count": 1}, headers=other_headers)
    assert start.status_code == 403
    cancel = await ctx.client.post(f"/api/v1/runs/{run_id}/cancel", headers=other_headers)
    assert cancel.status_code == 403

    # 内部写接口：非管理员连"内部"上报都应被拒绝
    progress = await ctx.client.post(
        f"/api/v1/internal/runs/{run_id}/progress",
        json={"percent": 10, "stage": "TRAINING"},
        headers=other_headers,
    )
    assert progress.status_code == 403

    # 所有者（管理员）自己的观测仍然可用
    events = await ctx.client.get(f"/api/v1/runs/{run_id}/events", headers=admin_headers)
    assert events.status_code == 200


async def test_internal_endpoints_require_admin(ctx: TestContext) -> None:
    admin_headers, run_id = await _admin_run(ctx)
    other_headers = await invite_and_accept(ctx, admin_headers, "manager@hydrolab.cn", "成员", "member1234")

    # 非管理员的内部上报：403
    metric = await ctx.client.post(
        f"/api/v1/internal/runs/{run_id}/metrics",
        json={"name": "nse", "value": 0.5, "step": 1},
        headers=other_headers,
    )
    assert metric.status_code == 403

    # 管理员内部上报：200
    ok = await ctx.client.post(
        f"/api/v1/internal/runs/{run_id}/metrics",
        json={"name": "nse", "value": 0.5, "step": 1},
        headers=admin_headers,
    )
    assert ok.status_code == 200

    non_admin_dispatch = await ctx.client.post(
        "/api/v1/internal/outbox/dispatch", headers=other_headers
    )
    assert non_admin_dispatch.status_code == 403