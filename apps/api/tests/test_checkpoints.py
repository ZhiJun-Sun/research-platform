"""B7 Checkpoint 与兼容性 API 测试。"""

from tests.conftest import TestContext
from tests.test_execution import _queued_run


async def _checkpoint(ctx: TestContext) -> tuple[dict[str, str], str, dict[str, object]]:
    headers, run_id = await _queued_run(ctx)
    await ctx.client.post(f"/api/v1/runs/{run_id}/start", json={"gpu_count": 1}, headers=headers)
    await ctx.client.post(
        f"/api/v1/internal/runs/{run_id}/complete",
        json={"exit_code": 0},
        headers=headers,
    )
    payload = {
        "source_run_id": run_id,
        "artifact_key": "runs/model.ckpt",
        "artifact_sha256": "abc",
        "model_signature": "lstm-v1",
        "feature_names": ["precip", "temp"],
        "target_names": ["flow"],
        "scaler_signature": "scaler-v1",
        "optimizer_included": True,
    }
    created = await ctx.client.post("/api/v1/checkpoints", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    return headers, run_id, created.json()


def _source_candidate(source: dict[str, object]) -> dict[str, object]:
    candidate = {
        key: source[key]
        for key in (
            "dataset_version_id",
            "code_version_id",
            "template_version_id",
            "environment_version_id",
        )
    }
    candidate.update(
        {
            "feature_names": ["precip", "temp"],
            "target_names": ["flow"],
            "model_signature": "lstm-v1",
            "scaler_signature": "scaler-v1",
        }
    )
    return candidate


async def test_checkpoint_is_immutable_and_resume_requires_source_versions(ctx: TestContext) -> None:
    headers, _, checkpoint = await _checkpoint(ctx)
    candidate = _source_candidate(checkpoint["source_config"])
    compatible = await ctx.client.post(
        f"/api/v1/checkpoints/{checkpoint['id']}/compatibility",
        json={"mode": "RESUME", "candidate": candidate},
        headers=headers,
    )
    assert compatible.json()["status"] == "COMPATIBLE"
    candidate["dataset_version_id"] = "00000000-0000-0000-0000-000000000000"
    blocked = await ctx.client.post(
        f"/api/v1/checkpoints/{checkpoint['id']}/compatibility",
        json={"mode": "RESUME", "candidate": candidate},
        headers=headers,
    )
    assert blocked.json()["status"] == "INCOMPATIBLE"
    assert any("Resume" in item for item in blocked.json()["blockers"])


async def test_finetune_reports_repair_plan_for_feature_model_and_scaler_mismatch(ctx: TestContext) -> None:
    headers, _, checkpoint = await _checkpoint(ctx)
    candidate = _source_candidate(checkpoint["source_config"])
    candidate.update(
        {
            "feature_names": ["precip"],
            "model_signature": "lstm-v2",
            "scaler_signature": "scaler-v2",
        }
    )
    report = await ctx.client.post(
        f"/api/v1/checkpoints/{checkpoint['id']}/compatibility",
        json={"mode": "FINETUNE", "candidate": candidate},
        headers=headers,
    )
    assert report.json()["status"] == "REPAIRABLE"
    assert {item["code"] for item in report.json()["repair_plan"]} == {
        "FEATURE_MAPPING",
        "MODEL_KEY_MAPPING",
        "REFIT_SCALER",
    }
