"""B7 Checkpoint 创建、兼容检查与复用请求服务。"""

from typing import Any
from uuid import UUID

from hydrolab.checkpoints.entities import (
    Checkpoint,
    CheckpointMode,
    CompatibilityReport,
    CompatibilityStatus,
    RepairAction,
)
from hydrolab.checkpoints.memory import InMemoryCheckpoints
from hydrolab.core.errors import conflict, not_found, validation_error
from hydrolab.domain.entities import User
from hydrolab.experiments.repositories import ExperimentVersionStore, RunStore


class CheckpointService:
    def __init__(self, checkpoints: InMemoryCheckpoints, runs: RunStore, versions: ExperimentVersionStore) -> None:
        self._checkpoints, self._runs, self._versions = checkpoints, runs, versions

    async def create(
        self,
        owner: User,
        source_run_id: UUID,
        artifact_key: str,
        artifact_sha256: str,
        model_signature: str,
        feature_names: list[str],
        target_names: list[str],
        scaler_signature: str | None,
        optimizer_included: bool,
        scheduler_included: bool,
    ) -> Checkpoint:
        run = await self._runs.get(source_run_id)
        if run is None or run.owner_id != owner.id:
            raise not_found("来源 Run 不存在")
        if run.status.value != "SUCCEEDED":
            raise conflict("只有成功 Run 可以创建 Checkpoint")
        version = await self._versions.get(run.experiment_version_id)
        if version is None:
            raise conflict("来源实验版本不存在")
        if not artifact_key or not artifact_sha256 or not model_signature:
            raise validation_error("Checkpoint 元数据不完整")
        return await self._checkpoints.add(
            Checkpoint(
                owner_id=owner.id,
                source_run_id=run.id,
                source_experiment_version_id=version.id,
                artifact_key=artifact_key,
                artifact_sha256=artifact_sha256,
                model_signature=model_signature,
                feature_names=feature_names,
                target_names=target_names,
                scaler_signature=scaler_signature,
                optimizer_included=optimizer_included,
                scheduler_included=scheduler_included,
                source_config=version.resolved_config,
            )
        )

    async def check(
        self, owner: User, checkpoint_id: UUID, mode: CheckpointMode, candidate: dict[str, Any]
    ) -> CompatibilityReport:
        checkpoint = await self._owned(owner, checkpoint_id)
        blockers: list[str] = []
        warnings: list[str] = []
        repairs: list[RepairAction] = []
        source = checkpoint.source_config
        for key in ("dataset_version_id", "code_version_id", "template_version_id", "environment_version_id"):
            if not candidate.get(key):
                blockers.append(f"缺少 {key}")
        source_features = set(checkpoint.feature_names)
        candidate_features = set(candidate.get("feature_names", []))
        if source_features != candidate_features:
            missing, extra = sorted(source_features - candidate_features), sorted(candidate_features - source_features)
            repairs.append(
                RepairAction(
                    code="FEATURE_MAPPING", title="修正输入特征映射", details={"missing": missing, "extra": extra}
                )
            )
        if set(checkpoint.target_names) != set(candidate.get("target_names", [])):
            blockers.append("预测目标不匹配")
        if candidate.get("model_signature") != checkpoint.model_signature:
            repairs.append(RepairAction(code="MODEL_KEY_MAPPING", title="提供模型权重 key 映射或更换兼容模型"))
        if candidate.get("scaler_signature") != checkpoint.scaler_signature:
            repairs.append(RepairAction(code="REFIT_SCALER", title="重新拟合或显式加载兼容 Scaler"))
        if mode == CheckpointMode.RESUME:
            for key in ("dataset_version_id", "code_version_id", "template_version_id", "environment_version_id"):
                if candidate.get(key) != source.get(key):
                    blockers.append(f"Resume 必须使用来源 {key}")
            if not checkpoint.optimizer_included:
                blockers.append("Checkpoint 不包含 Optimizer，不能 Resume")
        elif mode == CheckpointMode.FINETUNE and not checkpoint.optimizer_included:
            warnings.append("Checkpoint 不含 Optimizer；将以权重初始化进行 Fine-tune")
        if blockers:
            status = CompatibilityStatus.INCOMPATIBLE
        elif repairs:
            status = CompatibilityStatus.REPAIRABLE
        else:
            status = CompatibilityStatus.COMPATIBLE
        return CompatibilityReport(
            checkpoint_id=checkpoint.id,
            mode=mode,
            status=status,
            blockers=blockers,
            warnings=warnings,
            repair_plan=repairs,
        )

    async def _owned(self, owner: User, checkpoint_id: UUID) -> Checkpoint:
        checkpoint = await self._checkpoints.get(checkpoint_id)
        if checkpoint is None or checkpoint.owner_id != owner.id:
            raise not_found("Checkpoint 不存在")
        return checkpoint
