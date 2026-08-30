"""统一错误模型（plans/02 第 5.3 节）。

响应格式::

    {"error": {"code", "message", "details", "request_id"}}
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

REQUEST_ID_HEADER = "X-Request-ID"


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    """业务错误基类。code 使用稳定枚举字符串，不携带前端文案。"""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}


# --- 基础错误码（plans/02 5.3） ---
def validation_error(message: str, details: dict[str, Any] | None = None) -> AppError:
    return AppError("VALIDATION_ERROR", message, status_code=422, details=details)


def unauthenticated(message: str = "未认证") -> AppError:
    return AppError("UNAUTHENTICATED", message, status_code=401)


def forbidden(message: str = "无权访问该资源") -> AppError:
    return AppError("FORBIDDEN", message, status_code=403)


def not_found(message: str = "资源不存在") -> AppError:
    return AppError("NOT_FOUND", message, status_code=404)


def conflict(message: str, details: dict[str, Any] | None = None) -> AppError:
    return AppError("CONFLICT", message, status_code=409, details=details)


def dependency_unavailable(message: str, details: dict[str, Any] | None = None) -> AppError:
    return AppError("DEPENDENCY_UNAVAILABLE", message, status_code=503, details=details)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request.headers.get(
        REQUEST_ID_HEADER, "unknown"
    )


def _error_json(
    request: Request,
    code: str,
    message: str,
    status: int,
    details: dict[str, Any],
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=code, message=message, details=details, request_id=_request_id(request)
        )
    )
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        return _error_json(request, exc.code, exc.message, exc.status_code, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_json(
            request,
            "VALIDATION_ERROR",
            "请求参数不合法",
            422,
            {"issues": jsonable_encoder(exc.errors())},
        )
