"""仅限 local/test 的前后端联调 Demo API。"""

import io
from datetime import UTC, datetime
from typing import Literal
from zipfile import ZipFile

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from hydrolab.auth.dependencies import get_current_user
from hydrolab.code_assets.entities import ParameterDefinition
from hydrolab.code_assets.enums import ParameterType
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


class DemoCatalogItem(BaseModel):
    id: str
    name: str
    subtitle: str
    status: str
    metadata: dict[str, str] = {}

    def __init__(
        self,
        id: str,
        name: str,
        subtitle: str,
        status: str,
        metadata: dict[str, str] | None = None,
    ) -> None:
        super().__init__(
            id=id,
            name=name,
            subtitle=subtitle,
            status=status,
            metadata=metadata or {},
        )


class DemoCatalog(BaseModel):
    datasets: list[DemoCatalogItem]
    code_repositories: list[DemoCatalogItem]
    templates: list[DemoCatalogItem]
    environments: list[DemoCatalogItem]
    experiments: list[DemoCatalogItem]
    checkpoints: list[DemoCatalogItem]
    results: list[DemoCatalogItem]


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


@router.post("/seed")
async def seed(request: Request, user: User = Depends(get_current_user)) -> dict[str, str]:
    """仅 local/test：通过既有领域服务建立完整可联调的 B2–B8 资产链。"""
    existing = await request.app.state.experiments.list_by_owner(user.id)
    if existing:
        return {"status": "already_seeded", "experiment_id": str(existing[0].id)}

    dataset = await request.app.state.asset_service.create_dataset(user, "北江目标流域", None, "前后端联调数据")
    job = await request.app.state.import_service.create(user, dataset.id, "UPLOAD")
    await request.app.state.import_service.fake_upload(
        user,
        job.id,
        "beijiang.csv",
        b"date,basin_id,precip,flow\n2022-01-01,11480390,2.4,7.1\n",
    )
    mapping = await request.app.state.field_mappings.get_by_job(job.id)
    assert mapping is not None
    data_version = await request.app.state.import_service.confirm_mapping(user, job.id, mapping.items)

    repository = await request.app.state.code_import_service.create_repository(user, "KG-MoE-MS", "前后端联调代码")
    archive = io.BytesIO()
    with ZipFile(archive, "w") as zip_file:
        zip_file.writestr("train.py", "print('HydroLab demo')")
    code_version = await request.app.state.code_import_service.import_zip(
        user, repository.id, "kg-moe.zip", archive.getvalue()
    )
    template = await request.app.state.template_environment_service.create_template(
        user, repository.id, "标准水文预测", "联调模板"
    )
    parameter_definitions = [
        ParameterDefinition(
            key="epochs",
            label="Epochs",
            type=ParameterType.INTEGER,
            required=True,
            minimum=1,
        )
    ]
    template_version = await request.app.state.template_environment_service.create_template_version(
        user,
        template.id,
        code_version.id,
        "TRAIN",
        ["python", "train.py"],
        parameter_definitions,
        {},
        {},
    )
    environment = await request.app.state.template_environment_service.create_environment(
        user, "env-v3 · PyTorch 2.4", "联调环境"
    )
    environment_version = await request.app.state.template_environment_service.create_environment_version(
        user, environment.id, f"python:3.11@sha256:{'a' * 64}", "3.11", None, None
    )
    draft = await request.app.state.experiment_service.create_draft(user, "Top-30 相似流域微调", "前后端联调实验")
    await request.app.state.experiment_service.update_draft(
        user,
        draft.id,
        {
            "dataset_version_id": data_version.id,
            "code_version_id": code_version.id,
            "template_version_id": template_version.id,
            "environment_version_id": environment_version.id,
            "parameter_values": {"epochs": 50},
        },
    )
    experiment, version, run = await request.app.state.experiment_service.submit(user, draft.id, "dev-demo-seed")
    completed = await request.app.state.run_control_service.start(run.id, 1)
    await request.app.state.run_control_service.complete_fake(completed.id, 0)
    checkpoint = await request.app.state.checkpoint_service.create(
        user,
        run.id,
        "demo/best.ckpt",
        "demo-sha256",
        "kg-moe-ms:v3",
        ["precip"],
        ["flow"],
        "scaler-v1",
        True,
        True,
    )
    result = await request.app.state.result_service.create_result(user, run.id)
    from hydrolab.results.entities import MetricPoint

    await request.app.state.result_service.add_metrics(
        user,
        result.id,
        [
            MetricPoint(result_id=result.id, name="NSE", value=0.846),
            MetricPoint(result_id=result.id, name="KGE", value=0.919),
            MetricPoint(result_id=result.id, name="RMSE", value=8.17),
        ],
    )
    baseline_draft = await request.app.state.experiment_service.create_draft(
        user, "Top-4 小样本迁移", "前后端联调对比基线"
    )
    await request.app.state.experiment_service.update_draft(
        user,
        baseline_draft.id,
        {
            "dataset_version_id": data_version.id,
            "code_version_id": code_version.id,
            "template_version_id": template_version.id,
            "environment_version_id": environment_version.id,
            "parameter_values": {"epochs": 30},
        },
    )
    _, _, baseline_run = await request.app.state.experiment_service.submit(user, baseline_draft.id, "dev-demo-baseline")
    baseline_started = await request.app.state.run_control_service.start(baseline_run.id, 1)
    await request.app.state.run_control_service.complete_fake(baseline_started.id, 0)
    baseline_result = await request.app.state.result_service.create_result(user, baseline_run.id)
    await request.app.state.result_service.add_metrics(
        user,
        baseline_result.id,
        [
            MetricPoint(result_id=baseline_result.id, name="NSE", value=0.812),
            MetricPoint(result_id=baseline_result.id, name="KGE", value=0.892),
            MetricPoint(result_id=baseline_result.id, name="RMSE", value=9.326),
        ],
    )
    return {
        "status": "seeded",
        "experiment_id": str(experiment.id),
        "experiment_version_id": str(version.id),
        "run_id": str(run.id),
        "checkpoint_id": str(checkpoint.id),
        "result_id": str(result.id),
    }


@router.get("/catalog", response_model=DemoCatalog)
async def catalog(user: User = Depends(get_current_user)) -> DemoCatalog:
    del user
    return DemoCatalog(
        datasets=[
            DemoCatalogItem(
                "dataset-bj-v3",
                "北江目标流域 v3",
                "33 个流域 · 2012—2022 · 1 hour",
                "READY",
                {"version": "v3", "hash": "sha256:9e1c…a402"},
            ),
            DemoCatalogItem(
                "dataset-camels-v2",
                "CAMELS-US v2",
                "531 个流域 · 日尺度",
                "READY",
                {"version": "v2", "hash": "sha256:52a4…0db1"},
            ),
        ],
        code_repositories=[
            DemoCatalogItem(
                "code-kgmoe",
                "KG-MoE-MS",
                "Git snapshot · commit 8fc2a1",
                "READY",
                {"version": "v5", "hash": "sha256:c78a…11fd"},
            ),
            DemoCatalogItem(
                "code-gru",
                "GRU Baseline",
                "ZIP import · commit e921d0",
                "READY",
                {"version": "v2", "hash": "sha256:8b42…3f1a"},
            ),
        ],
        templates=[
            DemoCatalogItem(
                "template-standard",
                "标准水文预测",
                "训练 / 评估 / 预测 · 6 参数",
                "READY",
                {"version": "v4", "mode": "TRAIN"},
            ),
            DemoCatalogItem(
                "template-finetune",
                "跨流域微调",
                "训练 + 评估 · 9 参数",
                "READY",
                {"version": "v2", "mode": "FINETUNE"},
            ),
        ],
        environments=[
            DemoCatalogItem(
                "env-pytorch-24",
                "env-v3 · PyTorch 2.4",
                "Python 3.11 · CUDA 12.4",
                "READY",
                {"image": "pytorch:2.4-cuda12.4"},
            ),
            DemoCatalogItem(
                "env-pytorch-22",
                "env-v2 · PyTorch 2.2",
                "Python 3.10 · CUDA 12.1",
                "READY",
                {"image": "pytorch:2.2-cuda12.1"},
            ),
        ],
        experiments=[
            DemoCatalogItem(
                "experiment-top30",
                "Top-30 相似流域微调",
                "KG-MoE-MS · 北江目标流域 v3",
                "ACTIVE",
                {"runs": "3", "mode": "FINETUNE"},
            ),
            DemoCatalogItem(
                "experiment-gru",
                "GRU 跨流域基线",
                "GRU Baseline · CAMELS-US v2",
                "ACTIVE",
                {"runs": "1", "mode": "TRAIN"},
            ),
        ],
        checkpoints=[
            DemoCatalogItem(
                "checkpoint-top30",
                "Top-30 Best",
                "来源 RUN-042 · epoch 42",
                "COMPATIBLE",
                {"model_signature": "kg-moe-ms:v3", "nse": "0.851"},
            ),
            DemoCatalogItem(
                "checkpoint-camels",
                "CAMELS Pretrain",
                "来源 RUN-038 · epoch 50",
                "COMPATIBLE",
                {"model_signature": "kg-moe-ms:v3", "nse": "0.784"},
            ),
        ],
        results=[
            DemoCatalogItem(
                "result-top30",
                "Top-30 相似流域微调",
                "RUN-042 · 北江目标流域 v3",
                "SUCCEEDED",
                {"nse": "0.846", "kge": "0.919", "rmse": "8.170"},
            ),
            DemoCatalogItem(
                "result-top4",
                "Top-4 小样本迁移",
                "RUN-041 · 北江目标流域 v3",
                "SUCCEEDED",
                {"nse": "0.812", "kge": "0.892", "rmse": "9.326"},
            ),
            DemoCatalogItem(
                "result-camels",
                "CAMELS 全量预训练",
                "RUN-038 · CAMELS-US v2",
                "SUCCEEDED",
                {"nse": "0.784", "kge": "0.861", "rmse": "10.482"},
            ),
        ],
    )


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
