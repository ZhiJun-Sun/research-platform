"""B4 实验草稿提交与 Run 元数据测试。"""

import base64
import io
from zipfile import ZipFile

from tests.conftest import TestContext, login


async def _ready_assets(ctx: TestContext) -> tuple[dict[str, str], dict[str, str]]:
    headers = await login(ctx, "admin@hydrolab.cn", "admin123456")
    dataset = await ctx.client.post("/api/v1/datasets", json={"name": "北江"}, headers=headers)
    job = await ctx.client.post(
        "/api/v1/dataset-imports", json={"dataset_id": dataset.json()["id"], "source_type": "UPLOAD"}, headers=headers
    )
    await ctx.client.post(
        f"/api/v1/dataset-imports/{job.json()['id']}/fake-upload",
        json={"filename": "data.csv", "content": "date,flow\n2020-01-01,1\n"},
        headers=headers,
    )
    mapping = await ctx.client.get(f"/api/v1/dataset-imports/{job.json()['id']}/mapping", headers=headers)
    data_version = await ctx.client.post(
        f"/api/v1/dataset-imports/{job.json()['id']}/confirm-mapping",
        json={"items": mapping.json()["items"]},
        headers=headers,
    )

    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr("train.py", "print('ok')")
    repo = await ctx.client.post("/api/v1/code-repositories", json={"name": "model"}, headers=headers)
    code_version = await ctx.client.post(
        f"/api/v1/code-repositories/{repo.json()['id']}/zip-imports",
        json={"filename": "model.zip", "content_base64": base64.b64encode(stream.getvalue()).decode()},
        headers=headers,
    )
    template = await ctx.client.post(
        "/api/v1/templates", json={"code_repository_id": repo.json()["id"], "name": "train"}, headers=headers
    )
    template_version = await ctx.client.post(
        f"/api/v1/templates/{template.json()['id']}/versions",
        json={
            "code_version_id": code_version.json()["id"],
            "mode": "TRAIN",
            "argv": ["python", "train.py"],
            "parameters": [{"key": "epochs", "label": "Epochs", "type": "INTEGER", "required": True, "minimum": 1}],
        },
        headers=headers,
    )
    environment = await ctx.client.post("/api/v1/environments", json={"name": "py311"}, headers=headers)
    environment_version = await ctx.client.post(
        f"/api/v1/environments/{environment.json()['id']}/versions",
        json={"base_image": "python:3.11@sha256:abc", "python_version": "3.11"},
        headers=headers,
    )
    return headers, {
        "dataset_version_id": data_version.json()["id"],
        "code_version_id": code_version.json()["id"],
        "template_version_id": template_version.json()["id"],
        "environment_version_id": environment_version.json()["id"],
    }


async def test_submit_draft_freezes_config_creates_queued_run_and_outbox(ctx: TestContext) -> None:
    headers, assets = await _ready_assets(ctx)
    draft = await ctx.client.post("/api/v1/experiment-drafts", json={"name": "北江基线"}, headers=headers)
    updated = await ctx.client.patch(
        f"/api/v1/experiment-drafts/{draft.json()['id']}",
        json={**assets, "parameter_values": {"epochs": 20}},
        headers=headers,
    )
    assert updated.status_code == 200, updated.text
    submitted = await ctx.client.post(
        f"/api/v1/experiment-drafts/{draft.json()['id']}/submit", headers={**headers, "Idempotency-Key": "run-a"}
    )
    assert submitted.status_code == 201, submitted.text
    result = submitted.json()
    assert result["run"]["status"] == "QUEUED"
    assert result["version"]["resolved_config"]["parameters"] == {"epochs": 20}
    stages = await ctx.client.get(f"/api/v1/runs/{result['run']['id']}/stages", headers=headers)
    assert [stage["name"] for stage in stages.json()] == ["TRAINING", "EVALUATING", "PLOTTING", "UPLOADING"]
    assert len(await ctx.app.state.outbox.list_pending()) == 1


async def test_submit_is_idempotent_and_submitted_draft_is_immutable(ctx: TestContext) -> None:
    headers, assets = await _ready_assets(ctx)
    draft = await ctx.client.post("/api/v1/experiment-drafts", json={"name": "idempotent"}, headers=headers)
    await ctx.client.patch(
        f"/api/v1/experiment-drafts/{draft.json()['id']}",
        json={**assets, "parameter_values": {"epochs": 2}},
        headers=headers,
    )
    first = await ctx.client.post(
        f"/api/v1/experiment-drafts/{draft.json()['id']}/submit", headers={**headers, "Idempotency-Key": "same"}
    )
    second = await ctx.client.post(
        f"/api/v1/experiment-drafts/{draft.json()['id']}/submit", headers={**headers, "Idempotency-Key": "same"}
    )
    assert first.json()["run"]["id"] == second.json()["run"]["id"]
    changed = await ctx.client.patch(
        f"/api/v1/experiment-drafts/{draft.json()['id']}", json={"name": "changed"}, headers=headers
    )
    assert changed.status_code == 409


async def test_submit_rejects_missing_or_invalid_parameter_values(ctx: TestContext) -> None:
    headers, assets = await _ready_assets(ctx)
    draft = await ctx.client.post("/api/v1/experiment-drafts", json={"name": "invalid"}, headers=headers)
    await ctx.client.patch(f"/api/v1/experiment-drafts/{draft.json()['id']}", json=assets, headers=headers)
    missing = await ctx.client.post(f"/api/v1/experiment-drafts/{draft.json()['id']}/submit", headers=headers)
    assert missing.status_code == 422
    await ctx.client.patch(
        f"/api/v1/experiment-drafts/{draft.json()['id']}", json={"parameter_values": {"epochs": 0}}, headers=headers
    )
    invalid = await ctx.client.post(f"/api/v1/experiment-drafts/{draft.json()['id']}/submit", headers=headers)
    assert invalid.status_code == 422


async def test_batch_submit_previews_then_creates_one_run_per_dataset(ctx: TestContext) -> None:
    headers, assets = await _ready_assets(ctx)
    dataset = await ctx.client.post("/api/v1/datasets", json={"name": "北江二号"}, headers=headers)
    job = await ctx.client.post(
        "/api/v1/dataset-imports", json={"dataset_id": dataset.json()["id"], "source_type": "UPLOAD"}, headers=headers
    )
    await ctx.client.post(
        f"/api/v1/dataset-imports/{job.json()['id']}/fake-upload",
        json={"filename": "data-2.csv", "content": "date,flow\n2020-01-01,2\n"},
        headers=headers,
    )
    mapping = await ctx.client.get(f"/api/v1/dataset-imports/{job.json()['id']}/mapping", headers=headers)
    second_version = await ctx.client.post(
        f"/api/v1/dataset-imports/{job.json()['id']}/confirm-mapping",
        json={"items": mapping.json()["items"]},
        headers=headers,
    )
    body = {
        "name_prefix": "北江批量实验",
        "description": "两个流域版本并行排队",
        "dataset_version_ids": [assets["dataset_version_id"], second_version.json()["id"]],
        "code_version_id": assets["code_version_id"],
        "template_version_id": assets["template_version_id"],
        "environment_version_id": assets["environment_version_id"],
        "parameter_values": {"epochs": 2},
    }
    preview = await ctx.client.post("/api/v1/runs/batch", json={**body, "dry_run": True}, headers=headers)
    assert preview.status_code == 201, preview.text
    assert [item["run"] for item in preview.json()["items"]] == [None, None]
    assert len(await ctx.app.state.runs.list_queued()) == 0

    submitted = await ctx.client.post("/api/v1/runs/batch", json=body, headers=headers)
    assert submitted.status_code == 201, submitted.text
    items = submitted.json()["items"]
    assert len(items) == 2
    assert all(item["run"]["status"] == "QUEUED" for item in items)
    assert len(await ctx.app.state.runs.list_queued()) == 2
    assert len(await ctx.app.state.outbox.list_pending()) == 2
