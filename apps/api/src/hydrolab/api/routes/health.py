"""健康检查路由（plans/02 第 5.1 节）。

- /health/live：进程存活，不探测外部依赖；
- /health/ready：按部署配置探测启用的 Adapter，逐组件报告，
  Fake/Noop 模式不假装真实服务已连接。
"""

from typing import Protocol

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from hydrolab.api import deps
from hydrolab.core.settings import Settings, get_settings
from hydrolab.ports import ExperimentTracker, ObjectStorage, RunExecutor, TaskQueue


class _Healthcheckable(Protocol):
    async def healthcheck(self) -> bool: ...


router = APIRouter(tags=["health"])


class LiveResponse(BaseModel):
    status: str = "ok"


class ComponentHealth(BaseModel):
    backend: str
    healthy: bool
    detail: str | None = None


class ReadyResponse(BaseModel):
    status: str
    environment: str
    components: dict[str, ComponentHealth]


@router.get("/health/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    return LiveResponse()


@router.get("/health/ready", response_model=ReadyResponse)
async def ready(
    settings: Settings = Depends(get_settings),
    storage: ObjectStorage = Depends(deps.get_object_storage),
    queue: TaskQueue = Depends(deps.get_task_queue),
    tracker: ExperimentTracker = Depends(deps.get_experiment_tracker),
    executor: RunExecutor = Depends(deps.get_run_executor),
) -> ReadyResponse:
    checks: dict[str, tuple[str, _Healthcheckable]] = {
        "object_storage": (settings.object_storage_backend, storage),
        "task_queue": (settings.task_queue_backend, queue),
        "experiment_tracker": (settings.experiment_tracker_backend, tracker),
        "run_executor": (settings.run_executor_backend, executor),
    }
    components: dict[str, ComponentHealth] = {}
    all_ok = True
    for name, (backend, adapter) in checks.items():
        try:
            healthy = await adapter.healthcheck()
            components[name] = ComponentHealth(backend=backend, healthy=healthy)
            all_ok = all_ok and healthy
        except Exception as exc:
            components[name] = ComponentHealth(backend=backend, healthy=False, detail=str(exc))
            all_ok = False
    return ReadyResponse(
        status="ok" if all_ok else "degraded",
        environment=settings.environment,
        components=components,
    )
