"""前后端本地联调 Demo API 测试。"""

from tests.conftest import TestContext


async def _headers(ctx: TestContext) -> dict[str, str]:
    login = await ctx.client.post(
        "/api/v1/auth/login",
        json={"email": "admin@hydrolab.cn", "password": "admin123456"},
    )
    return {"Authorization": f"Bearer {login.json()['tokens']['access_token']}"}


async def test_dev_demo_workspace_requires_auth_and_returns_runs(ctx: TestContext) -> None:
    unauthorized = await ctx.client.get("/api/v1/dev-demo/workspace")
    assert unauthorized.status_code == 401

    headers = await _headers(ctx)
    workspace = await ctx.client.get("/api/v1/dev-demo/workspace", headers=headers)
    assert workspace.status_code == 200, workspace.text
    assert {run["id"] for run in workspace.json()["runs"]} >= {"demo-run-041", "demo-run-042"}

    catalog = await ctx.client.get("/api/v1/dev-demo/catalog", headers=headers)
    assert catalog.status_code == 200, catalog.text
    expected_sections = {
        "datasets",
        "code_repositories",
        "templates",
        "environments",
        "experiments",
        "checkpoints",
        "results",
    }
    assert all(catalog.json()[key] for key in expected_sections)


async def test_dev_demo_seed_creates_real_b2_to_b8_assets(ctx: TestContext) -> None:
    headers = await _headers(ctx)
    seeded = await ctx.client.post("/api/v1/dev-demo/seed", headers=headers)
    assert seeded.status_code == 200, seeded.text
    assert seeded.json()["status"] == "seeded"

    datasets = await ctx.client.get("/api/v1/datasets", headers=headers)
    repositories = await ctx.client.get("/api/v1/code-repositories", headers=headers)
    templates = await ctx.client.get("/api/v1/templates", headers=headers)
    environments = await ctx.client.get("/api/v1/environments", headers=headers)
    experiments = await ctx.client.get("/api/v1/experiments", headers=headers)
    checkpoints = await ctx.client.get("/api/v1/checkpoints", headers=headers)
    results = await ctx.client.get("/api/v1/results", headers=headers)
    for response in (datasets, repositories, templates, environments, experiments, checkpoints, results):
        assert response.status_code == 200, response.text
        assert response.json()
    assert len(results.json()) == 2
    compared = await ctx.client.post(
        "/api/v1/results/compare",
        json={"result_ids": [item["id"] for item in results.json()]},
        headers=headers,
    )
    assert compared.status_code == 200, compared.text
    assert len(compared.json()["metrics"]) == 2

    repeated = await ctx.client.post("/api/v1/dev-demo/seed", headers=headers)
    assert repeated.json()["status"] == "already_seeded"


async def test_dev_demo_run_can_advance_and_cancel(ctx: TestContext) -> None:
    headers = await _headers(ctx)
    advanced = await ctx.client.post("/api/v1/dev-demo/runs/demo-run-042/advance", headers=headers)
    assert advanced.status_code == 200, advanced.text
    assert advanced.json()["epoch"] == 37
    cancelled = await ctx.client.post("/api/v1/dev-demo/runs/demo-run-042/cancel", headers=headers)
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"
