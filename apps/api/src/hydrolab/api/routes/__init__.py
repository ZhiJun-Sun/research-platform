"""API v1 路由聚合。"""

from fastapi import APIRouter

from hydrolab.api.routes.auth import router as auth_router
from hydrolab.api.routes.checkpoints import router as checkpoints_router
from hydrolab.api.routes.code_assets import router as code_assets_router
from hydrolab.api.routes.datasets import router as datasets_router
from hydrolab.api.routes.execution import router as execution_router
from hydrolab.api.routes.experiments import router as experiments_router
from hydrolab.api.routes.grants import router as grants_router
from hydrolab.api.routes.health import router as health_router
from hydrolab.api.routes.invitations import router as invitations_router
from hydrolab.api.routes.results import router as results_router
from hydrolab.api.routes.sharing import router as sharing_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(checkpoints_router)
api_v1_router.include_router(code_assets_router)
api_v1_router.include_router(datasets_router)
api_v1_router.include_router(execution_router)
api_v1_router.include_router(experiments_router)
api_v1_router.include_router(invitations_router)
api_v1_router.include_router(grants_router)
# health 同时暴露在 /api/v1 下：前端与反向代理只需转发 /api 前缀即可探活；
# 根路径 /health/* 仍由 main.py 挂载，供 compose healthcheck 等既有调用方使用。
api_v1_router.include_router(health_router)
api_v1_router.include_router(results_router)
api_v1_router.include_router(sharing_router)
