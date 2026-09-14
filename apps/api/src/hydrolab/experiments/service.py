"""B4 实验 Draft、冻结版本和 Run 提交服务。"""

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from hydrolab.access.policy import AccessPolicy
from hydrolab.code_assets.entities import ParameterDefinition
from hydrolab.code_assets.enums import CodeVersionStatus, EnvironmentStatus, ParameterType
from hydrolab.code_assets.repositories import CodeVersionStore, EnvironmentVersionStore, TemplateVersionStore
from hydrolab.core.errors import conflict, not_found, validation_error
from hydrolab.datasets.enums import DatasetVersionStatus
from hydrolab.datasets.repositories import DatasetVersionRepository
from hydrolab.domain.entities import ResourceGrant, User, utcnow
from hydrolab.domain.enums import ResourceType, Role
from hydrolab.experiments.entities import Experiment, ExperimentDraft, ExperimentVersion, OutboxEvent, Run, RunStage
from hydrolab.experiments.enums import DraftStatus, RunStageName
from hydrolab.experiments.repositories import (
    DraftStore,
    ExperimentStore,
    ExperimentVersionStore,
    OutboxStore,
    RunStageStore,
    RunStore,
)
from hydrolab.repositories import GrantRepository


class ExperimentService:
    def __init__(
        self,
        drafts: DraftStore,
        experiments: ExperimentStore,
        versions: ExperimentVersionStore,
        runs: RunStore,
        stages: RunStageStore,
        outbox: OutboxStore,
        datasets: DatasetVersionRepository,
        code_versions: CodeVersionStore,
        template_versions: TemplateVersionStore,
        environment_versions: EnvironmentVersionStore,
        grants: GrantRepository,
        policy: AccessPolicy,
        transaction_factory: Any | None = None,
    ) -> None:
        self._drafts, self._experiments, self._versions, self._runs = drafts, experiments, versions, runs
        self._stages, self._outbox = stages, outbox
        self._datasets, self._code_versions = datasets, code_versions
        self._template_versions, self._environment_versions = template_versions, environment_versions
        self._grants, self._policy = grants, policy
        # 事务工厂：SQL 模式注入可异步进入的 UnitOfWork 工厂，使 submit 一次
        # 提交全部原子落地；memory 模式为 None，走原「各自提交」路径。
        self._tx = transaction_factory

    async def create_draft(self, owner: User, name: str, description: str = "") -> ExperimentDraft:
        if not name.strip():
            raise validation_error("实验名称不能为空")
        return await self._drafts.add(ExperimentDraft(owner_id=owner.id, name=name.strip(), description=description))

    async def update_draft(self, owner: User, draft_id: UUID, changes: dict[str, Any]) -> ExperimentDraft:
        draft = await self._require_draft_owner(owner, draft_id)
        if draft.status != DraftStatus.ACTIVE:
            raise conflict("已提交的草稿不可修改")
        allowed = {
            "name",
            "description",
            "dataset_version_id",
            "code_version_id",
            "template_version_id",
            "environment_version_id",
            "parameter_values",
        }
        extra = set(changes) - allowed
        if extra:
            raise validation_error("草稿包含不允许修改的字段", {"keys": sorted(extra)})
        for key, value in changes.items():
            setattr(draft, key, value)
        if not draft.name.strip():
            raise validation_error("实验名称不能为空")
        draft.updated_at = utcnow()
        return await self._drafts.update(draft)

    async def submit(
        self, owner: User, draft_id: UUID, idempotency_key: str | None
    ) -> tuple[Experiment, ExperimentVersion, Run]:
        draft = await self._require_draft_owner(owner, draft_id)
        if idempotency_key:
            existing = await self._runs.get_by_idempotency(owner.id, idempotency_key)
            if existing:
                return await self._resolve_existing(existing)
        if draft.status != DraftStatus.ACTIVE:
            raise conflict("草稿已提交；请创建新草稿后再次提交")
        config = await self._resolve_config(owner, draft)
        try:
            return await self._submit_in_tx(owner, draft, config, idempotency_key)
        except IntegrityError as exc:
            # 并发提交：另一方在本事务提交前已用同一幂等键先落库（唯一约束），
            # 本事务整体回滚，不会残留多余 Experiment/Version。回读胜者的 Run。
            if not idempotency_key:
                raise conflict("并发提交冲突，请重试") from None
            winner = await self._runs.get_by_idempotency(owner.id, idempotency_key)
            if winner is None:
                raise exc
            return await self._resolve_existing(winner)

    async def _resolve_existing(self, existing: Run) -> tuple[Experiment, ExperimentVersion, Run]:
        experiment = await self._experiments.get(existing.experiment_id)
        version = await self._versions.get(existing.experiment_version_id)
        if experiment is None or version is None:
            raise conflict("幂等 Run 的关联记录不完整")
        return experiment, version, existing

    async def _submit_in_tx(
        self, owner: User, draft: ExperimentDraft, config: dict[str, Any], idempotency_key: str | None
    ) -> tuple[Experiment, ExperimentVersion, Run]:
        if self._tx is None:
            return await self._do_submit(owner, draft, config, idempotency_key)
        async with self._tx() as _uow:
            return await self._do_submit(owner, draft, config, idempotency_key)

    async def _do_submit(
        self, owner: User, draft: ExperimentDraft, config: dict[str, Any], idempotency_key: str | None
    ) -> tuple[Experiment, ExperimentVersion, Run]:
        experiment = await self._experiments.add(
            Experiment(owner_id=owner.id, name=draft.name, description=draft.description)
        )
        await self._grants.add(
            ResourceGrant(
                resource_type=ResourceType.EXPERIMENT,
                resource_id=experiment.id,
                subject_id=owner.id,
                role=Role.OWNER,
                granted_by=owner.id,
            )
        )
        encoded = json.dumps(config, sort_keys=True, separators=(",", ":"))
        version = await self._versions.add(
            ExperimentVersion(
                experiment_id=experiment.id,
                version_no=1,
                resolved_config=config,
                config_hash=hashlib.sha256(encoded.encode()).hexdigest(),
            )
        )
        run = await self._runs.add(
            Run(
                experiment_id=experiment.id,
                experiment_version_id=version.id,
                owner_id=owner.id,
                idempotency_key=idempotency_key,
            )
        )
        for position, name in enumerate(RunStageName):
            await self._stages.add(RunStage(run_id=run.id, name=name, position=position))
        await self._outbox.add(
            OutboxEvent(
                aggregate_type="RUN",
                aggregate_id=run.id,
                topic="run.requested",
                payload={"run_id": str(run.id), "experiment_version_id": str(version.id)},
            )
        )
        draft.status, draft.updated_at = DraftStatus.SUBMITTED, utcnow()
        await self._drafts.update(draft)
        return experiment, version, run

    async def submit_batch(
        self,
        owner: User,
        *,
        name_prefix: str,
        description: str,
        dataset_version_ids: list[UUID],
        code_version_id: UUID,
        template_version_id: UUID,
        environment_version_id: UUID,
        parameter_values: dict[str, Any],
        dry_run: bool,
    ) -> list[dict[str, Any]]:
        """Expand selected data versions into independently reproducible queued Runs."""
        if not name_prefix.strip():
            raise validation_error("批量实验名称不能为空")
        if not dataset_version_ids:
            raise validation_error("至少需要选择一个数据版本")
        if len(dataset_version_ids) != len(set(dataset_version_ids)):
            raise validation_error("数据版本不可重复选择")

        prepared: list[tuple[ExperimentDraft, dict[str, Any], str]] = []
        for index, dataset_version_id in enumerate(dataset_version_ids, start=1):
            name = f"{name_prefix.strip()} · 数据集 {index}"
            draft = ExperimentDraft(
                owner_id=owner.id,
                name=name,
                description=description,
                dataset_version_id=dataset_version_id,
                code_version_id=code_version_id,
                template_version_id=template_version_id,
                environment_version_id=environment_version_id,
                parameter_values=parameter_values,
            )
            prepared.append((draft, await self._resolve_config(owner, draft), name))

        if dry_run:
            return [
                {
                    "dataset_version_id": draft.dataset_version_id,
                    "name": name,
                    "argv": config["argv"],
                    "parameter_values": config["parameters"],
                    "run": None,
                }
                for draft, config, name in prepared
            ]

        items: list[dict[str, Any]] = []
        for draft, config, name in prepared:
            # 逐项事务语义：每一条批量 Run 的 Experiment/Version/Run/Stages/Outbox
            # 在一个事务内原子提交，避免中途失败留下半成品。
            _experiment, _version, run = await self._submit_in_tx(owner, draft, config, None)
            items.append(
                {
                    "dataset_version_id": draft.dataset_version_id,
                    "name": name,
                    "argv": config["argv"],
                    "parameter_values": config["parameters"],
                    "run": run,
                }
            )
        return items

    async def get_experiment(self, actor: User, experiment_id: UUID) -> Experiment:
        experiment = await self._experiments.get(experiment_id)
        if experiment is None:
            raise not_found("实验不存在")
        await self._policy.require(actor, ResourceType.EXPERIMENT, experiment_id, Role.VIEWER)
        return experiment

    async def _require_draft_owner(self, owner: User, draft_id: UUID) -> ExperimentDraft:
        draft = await self._drafts.get(draft_id)
        if draft is None or draft.owner_id != owner.id:
            raise not_found("实验草稿不存在")
        return draft

    async def _resolve_config(self, owner: User, draft: ExperimentDraft) -> dict[str, Any]:
        dataset_version_id = draft.dataset_version_id
        code_version_id = draft.code_version_id
        template_version_id = draft.template_version_id
        environment_version_id = draft.environment_version_id
        if not all([dataset_version_id, code_version_id, template_version_id, environment_version_id]):
            raise validation_error("提交实验前必须选择数据、代码、模板和运行环境版本")
        assert dataset_version_id is not None
        assert code_version_id is not None
        assert template_version_id is not None
        assert environment_version_id is not None
        dataset = await self._datasets.get(dataset_version_id)
        code = await self._code_versions.get(code_version_id)
        template = await self._template_versions.get(template_version_id)
        environment = await self._environment_versions.get(environment_version_id)
        if dataset is None or dataset.status != DatasetVersionStatus.READY:
            raise conflict("数据版本必须为 READY")
        if code is None or code.status != CodeVersionStatus.READY:
            raise conflict("代码版本必须为 READY")
        if template is None:
            raise not_found("模板版本不存在")
        if environment is None or environment.status != EnvironmentStatus.READY:
            raise conflict("运行环境版本必须为 READY")
        await self._policy.require(owner, ResourceType.DATASET, dataset.dataset_id, Role.VIEWER)
        await self._policy.require(owner, ResourceType.CODE_REPOSITORY, code.repository_id, Role.VIEWER)
        if template.code_version_id != code.id:
            raise validation_error("所选模板版本未引用所选代码版本")
        self._validate_values(template.parameters, draft.parameter_values)
        values = {item.key: item.default for item in template.parameters if item.default is not None}
        values.update(draft.parameter_values)
        return {
            "dataset_version_id": str(dataset.id),
            "dataset_content_hash": dataset.content_hash,
            "code_version_id": str(code.id),
            "code_content_hash": code.content_hash,
            "template_version_id": str(template.id),
            "template_mode": template.mode.value,
            "argv": template.argv,
            "environment_version_id": str(environment.id),
            "environment_content_hash": environment.content_hash,
            "environment_image_digest": environment.image_digest,
            "parameters": values,
        }

    @staticmethod
    def _validate_values(definitions: list[ParameterDefinition], values: dict[str, Any]) -> None:
        known = {item.key: item for item in definitions}
        if unknown := set(values) - set(known):
            raise validation_error("实验参数包含未知字段", {"keys": sorted(unknown)})
        missing = [
            item.key for item in definitions if item.required and item.key not in values and item.default is None
        ]
        if missing:
            raise validation_error("实验参数缺少必填字段", {"keys": missing})
        for key, value in values.items():
            definition = known[key]
            if definition.type == ParameterType.INTEGER and (not isinstance(value, int) or isinstance(value, bool)):
                raise validation_error("实验参数类型不匹配", {"key": key})
            if definition.type == ParameterType.NUMBER and (
                not isinstance(value, (int, float)) or isinstance(value, bool)
            ):
                raise validation_error("实验参数类型不匹配", {"key": key})
            if definition.type == ParameterType.BOOLEAN and not isinstance(value, bool):
                raise validation_error("实验参数类型不匹配", {"key": key})
            if definition.type == ParameterType.STRING and not isinstance(value, str):
                raise validation_error("实验参数类型不匹配", {"key": key})
            if definition.type == ParameterType.SELECT and value not in definition.choices:
                raise validation_error("实验参数选项不合法", {"key": key})
            if definition.minimum is not None and value < definition.minimum:
                raise validation_error("实验参数小于最小值", {"key": key})
            if definition.maximum is not None and value > definition.maximum:
                raise validation_error("实验参数大于最大值", {"key": key})
