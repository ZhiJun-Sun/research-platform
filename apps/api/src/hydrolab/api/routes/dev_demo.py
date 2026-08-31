"""仅限 local/test 的前后端联调 Demo API。"""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hydrolab.auth.dependencies import get_current_user
from hydrolab.domain.entities import User

router = APIRouter(prefix="/dev-demo", tags=["dev-demo"])


class DemoRun(BaseModel):
    id: str
    name: str
    model: str
    dataset: str
    gpu: str
    epoch: int
    total_epochs: int
    nse: float | None
    status: Literal["QUEUED", "RUNNING", "SUCCEEDED", "CANCELLED"]
    eta: str | None


class DemoWorkspace(BaseModel):
    generated_at: datetime
    user_name: str
    runs: list[DemoRun]
    gpu_count: int = 2
    queued_count: int = 1


_RUNS: dict[str, DemoRun] = {
    "demo-run-042": DemoRun(
        id="demo-run-042",
        name="Top-30 相似流域微调",
        model="KG-MoE-MS",
        dataset="北江目标流域 v3",
        gpu="GPU 0",
        epoch=36,
        total_epochs=50,
        nse=0.846,
        status="RUNNING",
        eta="18 分钟",
    ),
    "demo-run-041": DemoRun(
        id="demo-run-041",
        name="Top-4 小样本迁移",
        model="KG-MoE-MS",
        dataset="北江目标流域 v3",
        gpu="—",
        epoch=50,
        total_epochs=50,
        nse=0.812,
        status="SUCCEEDED",
        eta=None,
    ),
    "demo-run-043": DemoRun(
        id="demo-run-043",
        name="GRU 跨流域基线",
        model="GRU Baseline",
        dataset="CAMELS-US v2",
        gpu="—",
        epoch=0,
        total_epochs=30,
        nse=None,
        status="QUEUED",
        eta="等待 GPU",
    ),
}


@router.get("/workspace", response_model=DemoWorkspace)
async def workspace(user: User = Depends(get_current_user)) -> DemoWorkspace:
    return DemoWorkspace(
        generated_at=datetime.now(UTC),
        user_name=user.display_name,
        runs=list(_RUNS.values()),
        queued_count=len([run for run in _RUNS.values() if run.status == "QUEUED"]),
    )


@router.post("/runs/{run_id}/advance", response_model=DemoRun)
async def advance(run_id: str, user: User = Depends(get_current_user)) -> DemoRun:
    del user
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Demo Run 不存在")
    if run.status == "QUEUED":
        run.status, run.gpu, run.epoch, run.eta = "RUNNING", "GPU 1", 1, "42 分钟"
    elif run.status == "RUNNING":
        run.epoch = min(run.epoch + 1, run.total_epochs)
        run.nse = round((run.nse or 0.7) + 0.002, 3)
        if run.epoch == run.total_epochs:
            run.status, run.gpu, run.eta = "SUCCEEDED", "—", None
    return run


@router.post("/runs/{run_id}/cancel", response_model=DemoRun)
async def cancel(run_id: str, user: User = Depends(get_current_user)) -> DemoRun:
    del user
    run = _RUNS.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Demo Run 不存在")
    if run.status in {"QUEUED", "RUNNING"}:
        run.status, run.gpu, run.eta = "CANCELLED", "—", None
    return run
