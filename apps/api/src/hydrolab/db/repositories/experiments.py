"""B4 实验、Draft、冻结版本、Run、RunStage 与 Outbox 领域 SQL 仓储。

约定与 identity.py 保持一致：async_sessionmaker[AsyncSession] 注入，
`async with self._sf() as session:` 使用，模块级 `_to_X(m)` 转换器，
枚举字段以 `.value` 存取、读取时用 `Enum(value)` 还原。
"""

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hydrolab.db.models.experiments import (
    DraftModel,
    ExperimentModel,
    ExperimentVersionModel,
    OutboxModel,
    RunModel,
    RunStageModel,
)
from hydrolab.db.unit_of_work import commit_or_defer, session_scope
from hydrolab.domain.entities import utcnow
from hydrolab.experiments.entities import (
    Experiment,
    ExperimentDraft,
    ExperimentVersion,
    OutboxEvent,
    Run,
    RunStage,
)
from hydrolab.experiments.enums import DraftStatus, OutboxStatus, RunStageName, RunStatus
from hydrolab.experiments.errors import StaleStateError


def _to_draft(m: DraftModel) -> ExperimentDraft:
    return ExperimentDraft(
        id=m.id,
        owner_id=m.owner_id,
        name=m.name,
        description=m.description,
        dataset_version_id=m.dataset_version_id,
        code_version_id=m.code_version_id,
        template_version_id=m.template_version_id,
        environment_version_id=m.environment_version_id,
        parameter_values=m.parameter_values or {},
        status=DraftStatus(m.status),
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _to_experiment(m: ExperimentModel) -> Experiment:
    return Experiment(
        id=m.id,
        owner_id=m.owner_id,
        name=m.name,
        description=m.description,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _to_experiment_version(m: ExperimentVersionModel) -> ExperimentVersion:
    return ExperimentVersion(
        id=m.id,
        experiment_id=m.experiment_id,
        version_no=m.version_no,
        resolved_config=m.resolved_config or {},
        config_hash=m.config_hash,
        frozen_at=m.frozen_at,
        created_at=m.created_at,
    )


def _to_run(m: RunModel) -> Run:
    return Run(
        id=m.id,
        experiment_id=m.experiment_id,
        experiment_version_id=m.experiment_version_id,
        owner_id=m.owner_id,
        status=RunStatus(m.status),
        idempotency_key=m.idempotency_key,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _to_run_stage(m: RunStageModel) -> RunStage:
    return RunStage(
        id=m.id,
        run_id=m.run_id,
        name=RunStageName(m.name),
        position=m.position,
        status=RunStatus(m.status),
        created_at=m.created_at,
    )


def _to_outbox(m: OutboxModel) -> OutboxEvent:
    return OutboxEvent(
        id=m.id,
        aggregate_type=m.aggregate_type,
        aggregate_id=m.aggregate_id,
        topic=m.topic,
        payload=m.payload or {},
        status=OutboxStatus(m.status),
        created_at=m.created_at,
        published_at=m.published_at,
    )


class SqlDraftStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, item: ExperimentDraft) -> ExperimentDraft:
        async with self._sf() as session:
            session.add(
                DraftModel(
                    id=item.id,
                    owner_id=item.owner_id,
                    name=item.name,
                    description=item.description,
                    dataset_version_id=item.dataset_version_id,
                    code_version_id=item.code_version_id,
                    template_version_id=item.template_version_id,
                    environment_version_id=item.environment_version_id,
                    parameter_values=item.parameter_values,
                    status=item.status.value,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
            )
            await session.commit()
            return item

    async def get(self, item_id: UUID) -> ExperimentDraft | None:
        async with self._sf() as session:
            m = await session.get(DraftModel, item_id)
            return _to_draft(m) if m else None

    async def update(self, item: ExperimentDraft) -> ExperimentDraft:
        async with session_scope(self._sf) as session:
            m = await session.get(DraftModel, item.id)
            if m is None:
                return item
            m.name = item.name
            m.description = item.description
            m.dataset_version_id = item.dataset_version_id
            m.code_version_id = item.code_version_id
            m.template_version_id = item.template_version_id
            m.environment_version_id = item.environment_version_id
            m.parameter_values = item.parameter_values
            m.status = item.status.value
            m.updated_at = item.updated_at
            await commit_or_defer(session)
            return item

    async def list_by_owner(self, owner_id: UUID) -> list[ExperimentDraft]:
        async with self._sf() as session:
            res = await session.execute(
                select(DraftModel)
                .where(DraftModel.owner_id == owner_id)
                .order_by(DraftModel.created_at.desc())
            )
            return [_to_draft(m) for m in res.scalars().all()]


class SqlExperimentStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, item: Experiment) -> Experiment:
        async with session_scope(self._sf) as session:
            session.add(
                ExperimentModel(
                    id=item.id,
                    owner_id=item.owner_id,
                    name=item.name,
                    description=item.description,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
            )
            await commit_or_defer(session)
            return item

    async def get(self, item_id: UUID) -> Experiment | None:
        async with self._sf() as session:
            m = await session.get(ExperimentModel, item_id)
            return _to_experiment(m) if m else None

    async def list_by_owner(self, owner_id: UUID) -> list[Experiment]:
        async with self._sf() as session:
            res = await session.execute(
                select(ExperimentModel)
                .where(ExperimentModel.owner_id == owner_id)
                .order_by(ExperimentModel.created_at.desc())
            )
            return [_to_experiment(m) for m in res.scalars().all()]


class SqlExperimentVersionStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, item: ExperimentVersion) -> ExperimentVersion:
        async with session_scope(self._sf) as session:
            session.add(
                ExperimentVersionModel(
                    id=item.id,
                    experiment_id=item.experiment_id,
                    version_no=item.version_no,
                    resolved_config=item.resolved_config,
                    config_hash=item.config_hash,
                    frozen_at=item.frozen_at,
                    created_at=item.created_at,
                )
            )
            await commit_or_defer(session)
            return item

    async def get(self, item_id: UUID) -> ExperimentVersion | None:
        async with self._sf() as session:
            m = await session.get(ExperimentVersionModel, item_id)
            return _to_experiment_version(m) if m else None

    async def list_by_experiment(self, experiment_id: UUID) -> list[ExperimentVersion]:
        async with self._sf() as session:
            res = await session.execute(
                select(ExperimentVersionModel)
                .where(ExperimentVersionModel.experiment_id == experiment_id)
                .order_by(ExperimentVersionModel.version_no.desc())
            )
            return [_to_experiment_version(m) for m in res.scalars().all()]

    async def next_version_no(self, experiment_id: UUID) -> int:
        async with self._sf() as session:
            res = await session.execute(
                select(func.max(ExperimentVersionModel.version_no)).where(
                    ExperimentVersionModel.experiment_id == experiment_id
                )
            )
            max_no = res.scalar_one_or_none()
            return (max_no if max_no is not None else 0) + 1


class SqlRunStore:
    # 终态：任何写操作都不得把这些状态覆盖为其它任何状态。
    _TERMINAL = (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED)
    _TERMINAL_VALUES = tuple(s.value for s in _TERMINAL)

    async def save(
        self,
        item: Run,
        expected_status: RunStatus | list[RunStatus] | tuple[RunStatus, ...] | None = None,
    ) -> Run:
        """原子保存 Run 状态（CAS + 终态保护）。

        - expected_status 给出时，只有当前状态命中该集合才会更新（并发 CAS）；
          否则视为状态已被并发方推进，抛出 StaleStateError。
        - 无论是否给 expected_status，终态（SUCCEEDED/FAILED/CANCELLED）都不会被
          覆盖为其它状态；只有「同终态幂等重写」或「非终态 → 任意」放行。
        返回时 item 保持悬挂状态以供调用方判断，实际以数据库为准。
        """
        async with self._sf() as session:
            new = item.status.value
            values = {"status": new, "updated_at": item.updated_at}
            guard = or_(
                RunModel.status == new,
                RunModel.status.not_in(self._TERMINAL_VALUES),
            )
            if expected_status is None:
                stmt = (
                    update(RunModel)
                    .where(RunModel.id == item.id, guard)
                    .values(values)
                )
            else:
                expected = (
                    expected_status
                    if isinstance(expected_status, (list, tuple))
                    else [expected_status]
                )
                expected_values = [s.value for s in expected]
                stmt = (
                    update(RunModel)
                    .where(
                        RunModel.id == item.id,
                        RunModel.status.in_(expected_values),
                        guard,
                    )
                    .values(values)
                )
            res = await session.execute(stmt)
            if res.rowcount == 0:
                await session.rollback()
                current = await session.get(RunModel, item.id)
                if current is None:
                    raise ValueError("Run missing")
                raise StaleStateError(
                    f"Run 状态当前为 {RunStatus(current.status).value}，"
                    f"无法从期望前置状态写入 {new}"
                )
            await session.commit()
            return item

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, item: Run) -> Run:
        async with session_scope(self._sf) as session:
            session.add(
                RunModel(
                    id=item.id,
                    experiment_id=item.experiment_id,
                    experiment_version_id=item.experiment_version_id,
                    owner_id=item.owner_id,
                    status=item.status.value,
                    idempotency_key=item.idempotency_key,
                    created_at=item.created_at,
                    updated_at=item.updated_at,
                )
            )
            await commit_or_defer(session)
            return item

    async def get(self, item_id: UUID) -> Run | None:
        async with self._sf() as session:
            m = await session.get(RunModel, item_id)
            return _to_run(m) if m else None

    async def list_by_experiment(self, experiment_id: UUID) -> list[Run]:
        async with self._sf() as session:
            res = await session.execute(
                select(RunModel)
                .where(RunModel.experiment_id == experiment_id)
                .order_by(RunModel.created_at.desc())
            )
            return [_to_run(m) for m in res.scalars().all()]

    async def list_by_owner(self, owner_id: UUID) -> list[Run]:
        async with self._sf() as session:
            res = await session.execute(
                select(RunModel)
                .where(RunModel.owner_id == owner_id)
                .order_by(RunModel.created_at.desc())
            )
            return [_to_run(m) for m in res.scalars().all()]

    async def list_queued(self) -> list[Run]:
        """FIFO 队列视图：最早提交的 QUEUED Run 优先获得 GPU。"""
        async with self._sf() as session:
            res = await session.execute(
                select(RunModel)
                .where(RunModel.status == RunStatus.QUEUED.value)
                .order_by(RunModel.created_at.asc())
            )
            return [_to_run(m) for m in res.scalars().all()]

    async def list_active(self) -> list[Run]:
        """调度器轮询用：返回所有持有执行状态的 Run。"""
        async with self._sf() as session:
            res = await session.execute(
                select(RunModel).where(
                    RunModel.status.in_([RunStatus.PREPARING.value, RunStatus.RUNNING.value])
                )
            )
            return [_to_run(m) for m in res.scalars().all()]

    async def get_by_idempotency(self, owner_id: UUID, key: str) -> Run | None:
        async with self._sf() as session:
            res = await session.execute(
                select(RunModel).where(
                    RunModel.owner_id == owner_id, RunModel.idempotency_key == key
                )
            )
            m = res.scalar_one_or_none()
            return _to_run(m) if m else None


class SqlRunStageStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, item: RunStage) -> RunStage:
        async with session_scope(self._sf) as session:
            session.add(
                RunStageModel(
                    id=item.id,
                    run_id=item.run_id,
                    name=item.name.value,
                    position=item.position,
                    status=item.status.value,
                    created_at=item.created_at,
                )
            )
            await commit_or_defer(session)
            return item

    async def list_by_run(self, run_id: UUID) -> list[RunStage]:
        async with self._sf() as session:
            res = await session.execute(
                select(RunStageModel)
                .where(RunStageModel.run_id == run_id)
                .order_by(RunStageModel.position.asc())
            )
            return [_to_run_stage(m) for m in res.scalars().all()]


class SqlOutboxStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, item: OutboxEvent) -> OutboxEvent:
        async with session_scope(self._sf) as session:
            session.add(
                OutboxModel(
                    id=item.id,
                    aggregate_type=item.aggregate_type,
                    aggregate_id=item.aggregate_id,
                    topic=item.topic,
                    payload=item.payload,
                    status=item.status.value,
                    created_at=item.created_at,
                    published_at=item.published_at,
                )
            )
            await commit_or_defer(session)
            return item

    async def list_pending(self) -> list[OutboxEvent]:
        async with self._sf() as session:
            res = await session.execute(
                select(OutboxModel)
                .where(OutboxModel.status == OutboxStatus.PENDING.value)
                .order_by(OutboxModel.created_at.asc())
            )
            return [_to_outbox(m) for m in res.scalars().all()]

    async def claim_pending(self, limit: int = 100, stale_after_seconds: int = 300) -> list[OutboxEvent]:
        """Atomically reserve a batch so multiple dispatchers do not publish twice.

        MySQL uses row locks with ``SKIP LOCKED``.  Other test databases may ignore
        the locking hint, but still exercise the same state transition.
        """
        async with self._sf() as session:
            async with session.begin():
                stale_before = utcnow() - timedelta(seconds=stale_after_seconds)
                result = await session.execute(
                    select(OutboxModel)
                    .where(
                        OutboxModel.topic.in_(["run.requested", "run.cancel_requested"]),
                        or_(
                            OutboxModel.status == OutboxStatus.PENDING.value,
                            and_(
                                OutboxModel.status == OutboxStatus.PUBLISHING.value,
                                or_(
                                    OutboxModel.published_at.is_(None),
                                    OutboxModel.published_at <= stale_before,
                                ),
                            ),
                        )
                    )
                    .order_by(OutboxModel.created_at.asc())
                    .limit(limit)
                    .with_for_update(skip_locked=True)
                )
                rows = list(result.scalars().all())
                # MySQL DATETIME columns currently store whole seconds.
                claimed_at = utcnow().replace(microsecond=0)
                for row in rows:
                    row.status = OutboxStatus.PUBLISHING.value
                    row.published_at = claimed_at
                return [_to_outbox(row) for row in rows]

    async def mark_published(
        self, event_id: UUID, published_at: datetime, claimed_at: datetime
    ) -> OutboxEvent | None:
        async with self._sf() as session:
            row = await session.get(OutboxModel, event_id, with_for_update=True)
            if row is None or row.status != OutboxStatus.PUBLISHING.value or row.published_at != claimed_at:
                return None
            row.status = OutboxStatus.PUBLISHED.value
            row.published_at = published_at
            await session.commit()
            return _to_outbox(row)

    async def reset_pending(self, event_id: UUID, claimed_at: datetime) -> OutboxEvent | None:
        async with self._sf() as session:
            row = await session.get(OutboxModel, event_id, with_for_update=True)
            if row is None or row.status != OutboxStatus.PUBLISHING.value or row.published_at != claimed_at:
                return None
            row.status = OutboxStatus.PENDING.value
            row.published_at = None
            await session.commit()
            return _to_outbox(row)


__all__ = [
    "SqlDraftStore",
    "SqlExperimentStore",
    "SqlExperimentVersionStore",
    "SqlOutboxStore",
    "SqlRunStageStore",
    "SqlRunStore",
]
