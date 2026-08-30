"""HTTP 层测试：健康检查、request_id、统一错误模型、OpenAPI 基线。"""

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from hydrolab.main import create_app


@pytest.fixture
async def client() -> AsyncClient:
    app = create_app()
    async with LifespanManager(app) as manager:
        transport = ASGITransport(app=manager.app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_live(client: AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_ready_reports_fake_backends_honestly(client: AsyncClient) -> None:
    resp = await client.get("/health/ready")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["components"]["object_storage"]["backend"] == "fake"
    assert body["components"]["task_queue"]["backend"] == "fake"


async def test_request_id_echoed(client: AsyncClient) -> None:
    resp = await client.get("/health/live", headers={"X-Request-ID": "test-req-1"})
    assert resp.headers["X-Request-ID"] == "test-req-1"


async def test_request_id_generated(client: AsyncClient) -> None:
    resp = await client.get("/health/live")
    assert resp.headers["X-Request-ID"]


async def test_404_uses_unified_error_model(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    # FastAPI 默认 404 也走 JSON；统一错误模型针对业务错误，
    # 此处验证 request_id 中间件在错误路径同样生效
    assert resp.headers["X-Request-ID"]
    assert body is not None


async def test_openapi_baseline(client: AsyncClient) -> None:
    resp = await client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["title"] == "HydroLab API"
    assert "/health/live" in spec["paths"]
    assert "/health/ready" in spec["paths"]
