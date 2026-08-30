"""B7 Checkpoint API。"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from hydrolab.auth.dependencies import get_current_user
from hydrolab.checkpoints.entities import CheckpointMode
from hydrolab.domain.entities import User

router = APIRouter(tags=["checkpoints"])


class CreateCheckpoint(BaseModel):
    source_run_id: UUID
    artifact_key: str
    artifact_sha256: str
    model_signature: str
    feature_names: list[str] = []
    target_names: list[str] = []
    scaler_signature: str | None = None
    optimizer_included: bool = False
    scheduler_included: bool = False


class CheckCompatibility(BaseModel):
    mode: CheckpointMode
    candidate: dict[str, object]


@router.post("/checkpoints", status_code=201)
async def create(body: CreateCheckpoint, request: Request, user: User = Depends(get_current_user)) -> object:
    return await request.app.state.checkpoint_service.create(user, **body.model_dump())


@router.get("/checkpoints")
async def list_items(request: Request, user: User = Depends(get_current_user)) -> object:
    return await request.app.state.checkpoints.list_by_owner(user.id)


@router.post("/checkpoints/{checkpoint_id}/compatibility")
async def compatibility(
    checkpoint_id: UUID, body: CheckCompatibility, request: Request, user: User = Depends(get_current_user)
) -> object:
    return await request.app.state.checkpoint_service.check(user, checkpoint_id, body.mode, body.candidate)
