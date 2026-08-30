"""API v1 路由聚合。"""

from fastapi import APIRouter

from hydrolab.api.routes.auth import router as auth_router
from hydrolab.api.routes.code_assets import router as code_assets_router
from hydrolab.api.routes.datasets import router as datasets_router
from hydrolab.api.routes.execution import router as execution_router
from hydrolab.api.routes.experiments import router as experiments_router
from hydrolab.api.routes.grants import router as grants_router
from hydrolab.api.routes.invitations import router as invitations_router
from hydrolab.api.routes.sharing import router as sharing_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(auth_router)
api_v1_router.include_router(code_assets_router)
api_v1_router.include_router(datasets_router)
api_v1_router.include_router(execution_router)
api_v1_router.include_router(experiments_router)
api_v1_router.include_router(invitations_router)
api_v1_router.include_router(grants_router)
api_v1_router.include_router(sharing_router)
