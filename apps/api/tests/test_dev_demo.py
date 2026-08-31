"""前后端本地联调 Demo API 测试。"""

from tests.conftest import TestContext


async def test_dev_demo_workspace_requires_auth_and_returns_runs(ctx: TestContext) -> None:
    unauthorized = await ctx.client.get("/api/v1/dev-demo/workspace")
    assert unauthorized.status_code == 401

    login = await ctx.client.post(
        "/api/v1/auth/login",
        json={"email": "admin@hydrolab.cn", "password": "admin123456"},
    )
    token = login.json()["tokens"]["access_token"]
    workspace = await ctx.client.get(
        "/api/v1/dev-demo/workspace",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert workspace.status_code == 200, workspace.text
    assert {run["id"] for run in workspace.json()["runs"]} >= {"demo-run-041", "demo-run-042"}


async def test_dev_demo_run_can_advance_and_cancel(ctx: TestContext) -> None:
    login = await ctx.client.post(
        "/api/v1/auth/login",
        json={"email": "admin@hydrolab.cn", "password": "admin123456"},
    )
    headers = {"Authorization": f"Bearer {login.json()['tokens']['access_token']}"}
    advanced = await ctx.client.post("/api/v1/dev-demo/runs/demo-run-042/advance", headers=headers)
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["epoch"] == 37
    cancelled = await ctx.client.post("/api/v1/dev-demo/runs/demo-run-042/cancel", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"
