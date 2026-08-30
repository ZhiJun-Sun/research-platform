"""测试公共夹具。"""

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from hydrolab.main import create_app

# 测试默认使用全 Fake 后端，与外部环境完全解耦（强制覆盖，保证确定性）
os.environ["HYDROLAB_ENVIRONMENT"] = "test"
os.environ.setdefault("HYDROLAB_OBJECT_STORAGE_BACKEND", "fake")
os.environ.setdefault("HYDROLAB_TASK_QUEUE_BACKEND", "fake")
os.environ.setdefault("HYDROLAB_EXPERIMENT_TRACKER_BACKEND", "fake")
os.environ.setdefault("HYDROLAB_RUN_EXECUTOR_BACKEND", "fake")

DEV_ADMIN_EMAIL = "admin@hydrolab.cn"
DEV_ADMIN_PASSWORD = "admin123456"


@dataclass
class TestContext:
    client: AsyncClient
    app: object  # FastAPI，访问 app.state 做数据播种/内部断言


@pytest.fixture
async def ctx() -> AsyncIterator[TestContext]:
    app = create_app()
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield TestContext(client=client, app=app)


async def login(ctx: TestContext, email: str, password: str) -> dict[str, str]:
    resp = await ctx.client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def admin_headers(ctx: TestContext) -> dict[str, str]:
    return await login(ctx, DEV_ADMIN_EMAIL, DEV_ADMIN_PASSWORD)


async def invite_and_accept(
    ctx: TestContext,
    admin_headers: dict[str, str],
    email: str,
    display_name: str = "测试用户",
    password: str = "userpass123",
) -> dict[str, str]:
    """完整邀请流程，返回新用户的认证头。"""
    resp = await ctx.client.post(
        "/api/v1/admin/invitations", json={"email": email}, headers=admin_headers
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["token"]
    resp = await ctx.client.post(
        f"/api/v1/invitations/{token}/accept",
        json={"display_name": display_name, "password": password},
    )
    assert resp.status_code == 201, resp.text
    access = resp.json()["tokens"]["access_token"]
    return {"Authorization": f"Bearer {access}"}
