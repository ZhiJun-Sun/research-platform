"""统一错误模型测试。"""

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from hydrolab.core.errors import (
    AppError,
    conflict,
    not_found,
    register_error_handlers,
    unauthenticated,
    validation_error,
)


def _app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise conflict("版本冲突", {"expected": 3, "actual": 2})

    @app.get("/validate")
    async def validate(q: int) -> dict[str, int]:
        return {"q": q}

    return app


async def test_app_error_shape() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_app()), base_url="http://t"
    ) as client:
        resp = await client.get("/boom", headers={"X-Request-ID": "rid-9"})
    assert resp.status_code == 409
    error = resp.json()["error"]
    assert error["code"] == "CONFLICT"
    assert error["details"] == {"expected": 3, "actual": 2}
    assert error["request_id"] == "rid-9"


async def test_request_validation_shape() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=_app()), base_url="http://t"
    ) as client:
        resp = await client.get("/validate?q=abc")
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["details"]["issues"]


def test_error_factories() -> None:
    assert validation_error("x").status_code == 422
    assert unauthenticated().code == "UNAUTHENTICATED"
    assert not_found().status_code == 404
    assert isinstance(AppError("C", "m"), Exception)
