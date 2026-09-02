"""B4 实验草稿、版本和 Run 元数据 API。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request

from hydrolab.api.experiment_schemas import (
    BatchSubmitInput,
    BatchSubmitItem,
    BatchSubmitResponse,
    DraftCreate,
    DraftUpdate,
    DraftView,
    ExperimentVersionView,
    ExperimentView,
    RunStageView,
    RunView,
    SubmitResponse,
)
from hydrolab.auth.dependencies import get_current_user
from hydrolab.domain.entities import User
from hydrolab.experiments.entities import Experiment, ExperimentDraft, ExperimentVersion, Run, RunStage

router = APIRouter(tags=["experiments"])


def _draft(item: ExperimentDraft) -> DraftView:
    return DraftView(**item.model_dump())


def _experiment(item: Experiment) -> ExperimentView:
    return ExperimentView(id=item.id, name=item.name, description=item.description)


def _version(item: ExperimentVersion) -> ExperimentVersionView:
    return ExperimentVersionView(
        id=item.id, version_no=item.version_no, resolved_config=item.resolved_config, config_hash=item.config_hash
    )


def _run(item: Run) -> RunView:
    return RunView(
        id=item.id,
        experiment_id=item.experiment_id,
        experiment_version_id=item.experiment_version_id,
        status=item.status,
    )


def _stage(item: RunStage) -> RunStageView:
    return RunStageView(name=item.name, position=item.position, status=item.status)


@router.get("/experiment-drafts", response_model=list[DraftView])
async def list_drafts(request: Request, user: User = Depends(get_current_user)) -> list[DraftView]:
    return [_draft(x) for x in await request.app.state.experiment_drafts.list_by_owner(user.id)]


@router.post("/experiment-drafts", response_model=DraftView, status_code=201)
async def create_draft(body: DraftCreate, request: Request, user: User = Depends(get_current_user)) -> DraftView:
    return _draft(await request.app.state.experiment_service.create_draft(user, body.name, body.description))


@router.patch("/experiment-drafts/{draft_id}", response_model=DraftView)
async def update_draft(
    draft_id: UUID, body: DraftUpdate, request: Request, user: User = Depends(get_current_user)
) -> DraftView:
    return _draft(
        await request.app.state.experiment_service.update_draft(user, draft_id, body.model_dump(exclude_none=True))
    )


@router.post("/experiment-drafts/{draft_id}/submit", response_model=SubmitResponse, status_code=201)
async def submit_draft(draft_id: UUID, request: Request, user: User = Depends(get_current_user)) -> SubmitResponse:
    experiment, version, run = await request.app.state.experiment_service.submit(
        user, draft_id, request.headers.get("idempotency-key")
    )
    return SubmitResponse(experiment=_experiment(experiment), version=_version(version), run=_run(run))


@router.post("/runs/batch", response_model=BatchSubmitResponse, status_code=201)
async def submit_batch(
    body: BatchSubmitInput, request: Request, user: User = Depends(get_current_user)
) -> BatchSubmitResponse:
    items = await request.app.state.experiment_service.submit_batch(
        user,
        name_prefix=body.name_prefix,
        description=body.description,
        dataset_version_ids=body.dataset_version_ids,
        code_version_id=body.code_version_id,
        template_version_id=body.template_version_id,
        environment_version_id=body.environment_version_id,
        parameter_values=body.parameter_values,
        dry_run=body.dry_run,
    )
    return BatchSubmitResponse(
        dry_run=body.dry_run,
        items=[
            BatchSubmitItem(
                dataset_version_id=item["dataset_version_id"],
                name=item["name"],
                argv=item["argv"],
                parameter_values=item["parameter_values"],
                run=_run(item["run"]) if item["run"] is not None else None,
            )
            for item in items
        ],
    )


@router.get("/experiments", response_model=list[ExperimentView])
async def list_experiments(request: Request, user: User = Depends(get_current_user)) -> list[ExperimentView]:
    return [_experiment(x) for x in await request.app.state.experiments.list_by_owner(user.id)]


@router.get("/experiments/{experiment_id}", response_model=ExperimentView)
async def get_experiment(
    experiment_id: UUID, request: Request, user: User = Depends(get_current_user)
) -> ExperimentView:
    return _experiment(await request.app.state.experiment_service.get_experiment(user, experiment_id))


@router.get("/experiments/{experiment_id}/versions", response_model=list[ExperimentVersionView])
async def list_versions(
    experiment_id: UUID, request: Request, user: User = Depends(get_current_user)
) -> list[ExperimentVersionView]:
    await request.app.state.experiment_service.get_experiment(user, experiment_id)
    return [_version(x) for x in await request.app.state.experiment_versions.list_by_experiment(experiment_id)]


@router.get("/experiments/{experiment_id}/runs", response_model=list[RunView])
async def list_runs(experiment_id: UUID, request: Request, user: User = Depends(get_current_user)) -> list[RunView]:
    await request.app.state.experiment_service.get_experiment(user, experiment_id)
    return [_run(x) for x in await request.app.state.runs.list_by_experiment(experiment_id)]


@router.get("/runs/{run_id}/stages", response_model=list[RunStageView])
async def list_run_stages(run_id: UUID, request: Request, user: User = Depends(get_current_user)) -> list[RunStageView]:
    return [_stage(x) for x in await request.app.state.run_stages.list_by_run(run_id)]
