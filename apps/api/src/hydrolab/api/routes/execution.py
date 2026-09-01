"""B5/B6 执行控制与观测 API。"""

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from hydrolab.auth.dependencies import get_current_user
from hydrolab.domain.entities import User

router = APIRouter(tags=["run-execution"])


class StartRequest(BaseModel):
    gpu_count: int = Field(default=1, ge=1, le=2)


class CompleteRequest(BaseModel):
    exit_code: int = 0


class ProgressRequest(BaseModel):
    percent: float = Field(ge=0, le=100)
    stage: str = "TRAINING"
    eta_seconds: int | None = None


class MetricRequest(BaseModel):
    name: str
    value: float
    step: int | None = None


class ResourceRequest(BaseModel):
    gpu_index: int = Field(ge=0, le=1)
    utilization_percent: float = Field(ge=0, le=100)
    memory_used_mb: int = Field(ge=0)
    memory_total_mb: int = Field(gt=0)


@router.post("/internal/outbox/dispatch")
async def dispatch(request: Request, user: User = Depends(get_current_user)) -> dict[str, int]:
    return {"dispatched": await request.app.state.run_control_service.dispatch_pending()}


@router.post("/runs/{run_id}/start")
async def start(run_id: UUID, body: StartRequest, request: Request, user: User = Depends(get_current_user)) -> object:
    return await request.app.state.run_control_service.start(run_id, body.gpu_count)


@router.post("/runs/{run_id}/cancel")
async def cancel(run_id: UUID, request: Request, user: User = Depends(get_current_user)) -> object:
    return await request.app.state.run_control_service.cancel(run_id)


@router.post("/internal/runs/{run_id}/complete")
async def complete(
    run_id: UUID, body: CompleteRequest, request: Request, user: User = Depends(get_current_user)
) -> object:
    service = request.app.state.run_control_service
    # 真实执行器下走采集收尾；Fake 执行器保持原状态机语义。
    if service.is_real_executor:
        return await service.finalize(run_id, body.exit_code)
    return await service.complete_fake(run_id, body.exit_code)


class AwaitRequest(BaseModel):
    timeout_seconds: float = Field(default=1800, gt=0, le=24 * 3600)


@router.post("/runs/{run_id}/await")
async def await_run(
    run_id: UUID, body: AwaitRequest, request: Request, user: User = Depends(get_current_user)
) -> object:
    """阻塞等待真实执行结束并采集产物。Fake 后端直接返回当前 Run。"""
    return await request.app.state.run_control_service.await_completion(run_id, body.timeout_seconds)


@router.get("/runs/{run_id}/collection")
async def collection(run_id: UUID, request: Request, user: User = Depends(get_current_user)) -> object:
    """真实执行的产物采集报告（指标条数、artifact 清单、警告）。"""
    report = request.app.state.run_control_service.collection_report(run_id)
    if report is None:
        return {"collected": False, "metrics": [], "artifacts": [], "warnings": []}
    return {
        "collected": True,
        "experiment_dirs": report.experiment_dirs,
        "metrics": [
            {"name": item.name, "value": item.value, "split": item.split, "horizon": item.horizon}
            for item in report.metrics
        ],
        "artifacts": [
            {
                "kind": item.kind,
                "relative_path": item.relative_path,
                "object_key": item.object_key,
                "sha256": item.sha256,
                "size_bytes": item.size_bytes,
            }
            for item in report.artifacts + report.configs + report.checkpoints
        ],
        "warnings": report.warnings,
    }


@router.post("/internal/runs/{run_id}/progress")
async def progress(
    run_id: UUID, body: ProgressRequest, request: Request, user: User = Depends(get_current_user)
) -> dict[str, bool]:
    await request.app.state.run_control_service.report_progress(run_id, body.percent, body.stage, body.eta_seconds)
    return {"accepted": True}


@router.post("/internal/runs/{run_id}/metrics")
async def metric(
    run_id: UUID, body: MetricRequest, request: Request, user: User = Depends(get_current_user)
) -> dict[str, bool]:
    await request.app.state.run_control_service.report_metric(run_id, body.name, body.value, body.step)
    return {"accepted": True}


@router.post("/internal/runs/{run_id}/resources")
async def resource(
    run_id: UUID, body: ResourceRequest, request: Request, user: User = Depends(get_current_user)
) -> dict[str, bool]:
    await request.app.state.run_control_service.report_resource(
        run_id, body.gpu_index, body.utilization_percent, body.memory_used_mb, body.memory_total_mb
    )
    return {"accepted": True}


@router.get("/runs/{run_id}/events")
async def events(run_id: UUID, request: Request, after_id: int = 0, user: User = Depends(get_current_user)) -> object:
    return await request.app.state.run_events.list_after(run_id, after_id)


@router.get("/runs/{run_id}/logs")
async def logs(run_id: UUID, request: Request, after_id: int = 0, user: User = Depends(get_current_user)) -> object:
    return await request.app.state.run_logs.list_after(run_id, after_id)


@router.get("/runs/{run_id}/resources")
async def resources(run_id: UUID, request: Request, user: User = Depends(get_current_user)) -> object:
    return await request.app.state.resource_samples.list_by_run(run_id)


@router.get("/runs/{run_id}/events/stream")
async def stream(run_id: UUID, request: Request, user: User = Depends(get_current_user)) -> StreamingResponse:
    after_id = int(request.headers.get("Last-Event-ID", "0"))

    async def generate() -> AsyncIterator[str]:
        for event in await request.app.state.run_events.list_after(run_id, after_id):
            payload = json.dumps(event.model_dump(mode="json"), default=str)
            yield f"id: {event.id}\nevent: {event.event_type.value}\ndata: {payload}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
