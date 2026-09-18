"""B8 结果、绘图、导出与对比 API。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from hydrolab.auth.dependencies import get_current_user
from hydrolab.core.errors import not_found
from hydrolab.domain.entities import User
from hydrolab.results.entities import MetricPoint, ResultArtifact

router = APIRouter(tags=["results"])


class MetricInput(BaseModel):
    name: str
    value: float
    split: str = "test"
    horizon: int | None = None
    basin_id: str | None = None
    event_id: str | None = None


class ArtifactInput(BaseModel):
    kind: str
    object_key: str
    sha256: str


class PlotInput(BaseModel):
    result_ids: list[UUID]
    plot_type: str
    data_selection: dict[str, object] = Field(default_factory=dict)
    options: dict[str, object] = Field(default_factory=dict)


class ExportInput(BaseModel):
    result_ids: list[UUID]
    artifact_ids: list[UUID] = Field(default_factory=list)


class CompareInput(BaseModel):
    result_ids: list[UUID]


@router.get("/results")
async def list_results(request: Request, user: User = Depends(get_current_user)) -> object:
    return await request.app.state.results.list_by_owner(user.id)


@router.post("/runs/{run_id}/result", status_code=201)
async def create_result(run_id: UUID, request: Request, user: User = Depends(get_current_user)) -> object:
    return await request.app.state.result_service.create_result(user, run_id)


@router.post("/runs/{run_id}/result/ingest", status_code=201)
async def ingest_result(run_id: UUID, request: Request, user: User = Depends(get_current_user)) -> object:
    """把真实执行采集到的产物一次性登记为 Result + Metrics + Artifacts。

    这是 e2e 链路的收口：Runner 采集 → 结果域，前端随后可直接绘图/对比/导出。
    """
    run = await request.app.state.runs.get(run_id)
    if run is None or (run.owner_id != user.id and not user.is_admin):
        raise not_found("Run 不存在")
    result_service = request.app.state.result_service
    report = request.app.state.run_control_service.collection_report(run_id)
    if report is None:
        persisted = await result_service.persisted_collection(run_id)
        if persisted is None:
            result = await result_service.create_result(user, run_id)
            return {
                "result": result,
                "metrics_added": 0,
                "artifacts_added": 0,
                "metrics_total": 0,
                "artifacts_total": 0,
                "warnings": ["没有采集报告"],
            }
        return {
            "result": persisted["result"],
            "metrics_added": 0,
            "artifacts_added": 0,
            "metrics_total": len(persisted["metrics"]),
            "artifacts_total": len(persisted["artifacts"]),
            "warnings": [],
        }
    return await result_service.ingest_collection(run_id, report)


@router.post("/results/{result_id}/metrics", status_code=201)
async def add_metrics(
    result_id: UUID, body: list[MetricInput], request: Request, user: User = Depends(get_current_user)
) -> object:
    return await request.app.state.result_service.add_metrics(
        user, result_id, [MetricPoint(result_id=result_id, **item.model_dump()) for item in body]
    )


@router.get("/results/{result_id}/metrics")
async def list_metrics(result_id: UUID, request: Request, user: User = Depends(get_current_user)) -> object:
    return await request.app.state.result_service.metrics(user, result_id)


@router.post("/results/{result_id}/artifacts", status_code=201)
async def add_artifact(
    result_id: UUID, body: ArtifactInput, request: Request, user: User = Depends(get_current_user)
) -> object:
    return await request.app.state.result_service.add_artifact(
        user, result_id, ResultArtifact(result_id=result_id, **body.model_dump())
    )


@router.post("/plots", status_code=201)
async def create_plot(body: PlotInput, request: Request, user: User = Depends(get_current_user)) -> object:
    return await request.app.state.result_service.create_plot(user, **body.model_dump())


@router.post("/exports", status_code=201)
async def create_export(body: ExportInput, request: Request, user: User = Depends(get_current_user)) -> object:
    return await request.app.state.result_service.create_export(user, **body.model_dump())


@router.post("/results/compare")
async def compare(body: CompareInput, request: Request, user: User = Depends(get_current_user)) -> object:
    return await request.app.state.result_service.compare(user, body.result_ids)
