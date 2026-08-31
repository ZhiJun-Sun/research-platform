"""B8 结果、绘图、导出与对比 API。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from hydrolab.auth.dependencies import get_current_user
from hydrolab.domain.entities import User
from hydrolab.results.entities import MetricPoint, ResultArtifact

router = APIRouter(tags=["results"])


class MetricInput(BaseModel):
    name: str
    value: float
    split: str = "test"
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


@router.post("/runs/{run_id}/result", status_code=201)
async def create_result(run_id: UUID, request: Request, user: User = Depends(get_current_user)) -> object:
    return await request.app.state.result_service.create_result(user, run_id)


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
