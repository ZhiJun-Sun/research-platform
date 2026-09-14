"""B4 InMemory Repository 实现。"""

from datetime import datetime, timedelta
from uuid import UUID

from hydrolab.domain.entities import utcnow
from hydrolab.experiments.entities import Experiment, ExperimentDraft, ExperimentVersion, OutboxEvent, Run, RunStage
from hydrolab.experiments.enums import OutboxStatus, RunStatus
from hydrolab.experiments.errors import StaleStateError


class InMemoryDrafts:
    def __init__(self) -> None:
        self.items: dict[UUID, ExperimentDraft] = {}

    async def add(self, item: ExperimentDraft) -> ExperimentDraft:
        self.items[item.id] = item
        return item

    async def get(self, item_id: UUID) -> ExperimentDraft | None:
        return self.items.get(item_id)

    async def update(self, item: ExperimentDraft) -> ExperimentDraft:
        self.items[item.id] = item
        return item

    async def list_by_owner(self, owner_id: UUID) -> list[ExperimentDraft]:
        return [x for x in self.items.values() if x.owner_id == owner_id]


class InMemoryExperiments:
    def __init__(self) -> None:
        self.items: dict[UUID, Experiment] = {}

    async def add(self, item: Experiment) -> Experiment:
        self.items[item.id] = item
        return item

    async def get(self, item_id: UUID) -> Experiment | None:
        return self.items.get(item_id)

    async def list_by_owner(self, owner_id: UUID) -> list[Experiment]:
        return [x for x in self.items.values() if x.owner_id == owner_id]


class InMemoryExperimentVersions:
    def __init__(self) -> None:
        self.items: dict[UUID, ExperimentVersion] = {}

    async def add(self, item: ExperimentVersion) -> ExperimentVersion:
        self.items[item.id] = item
        return item

    async def get(self, item_id: UUID) -> ExperimentVersion | None:
        return self.items.get(item_id)

    async def list_by_experiment(self, experiment_id: UUID) -> list[ExperimentVersion]:
        return sorted(
            (x for x in self.items.values() if x.experiment_id == experiment_id),
            key=lambda x: x.version_no,
            reverse=True,
        )

    async def next_version_no(self, experiment_id: UUID) -> int:
        return len(await self.list_by_experiment(experiment_id)) + 1


class InMemoryRuns:
    _TERMINAL = (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED)

    def __init__(self) -> None:
        self.items: dict[UUID, Run] = {}
        # 记录最近一次 add/save 提交时的状态。内存仓储与调用方共享 Run 对象，
        # 调用方在 save 前会就地改写 status，因此 CAS 只能对比「上次持久化」的状态，
        # 不能读共享对象当前的 status（那已是新值）。
        self._persisted: dict[UUID, RunStatus] = {}

    async def save(
        self,
        item: Run,
        expected_status: RunStatus | list[RunStatus] | tuple[RunStatus, ...] | None = None,
    ) -> Run:
        if item.id not in self.items:
            raise ValueError("Run missing")
        current = self._persisted[item.id]
        if expected_status is not None:
            expected = (
                expected_status if isinstance(expected_status, (list, tuple)) else [expected_status]
            )
            if current not in expected:
                raise StaleStateError(
                    f"Run 状态当前为 {current.value}，无法在期望前置状态 "
                    f"{[s.value for s in expected]} 下写入 {item.status.value}"
                )
        if current in self._TERMINAL and item.status != current:
            raise StaleStateError("不允许覆盖已进入终态的 Run 状态")
        self.items[item.id] = item
        self._persisted[item.id] = item.status
        return item

    async def add(self, item: Run) -> Run:
        self.items[item.id] = item
        self._persisted[item.id] = item.status
        return item

    async def get(self, item_id: UUID) -> Run | None:
        return self.items.get(item_id)

    async def list_by_experiment(self, experiment_id: UUID) -> list[Run]:
        return sorted(
            (x for x in self.items.values() if x.experiment_id == experiment_id),
            key=lambda x: x.created_at,
            reverse=True,
        )

    async def list_by_owner(self, owner_id: UUID) -> list[Run]:
        return sorted(
            (x for x in self.items.values() if x.owner_id == owner_id),
            key=lambda x: x.created_at,
            reverse=True,
        )

    async def list_queued(self) -> list[Run]:
        """FIFO 队列视图：最早提交的 QUEUED Run 优先获得 GPU。"""
        return sorted(
            (x for x in self.items.values() if x.status == RunStatus.QUEUED),
            key=lambda x: x.created_at,
        )

    async def list_active(self) -> list[Run]:
        """调度器轮询用：返回所有持有执行状态的 Run。"""
        active = {RunStatus.PREPARING, RunStatus.RUNNING}
        return [x for x in self.items.values() if x.status in active]

    async def get_by_idempotency(self, owner_id: UUID, key: str) -> Run | None:
        return next((x for x in self.items.values() if x.owner_id == owner_id and x.idempotency_key == key), None)


class InMemoryRunStages:
    def __init__(self) -> None:
        self.items: dict[UUID, RunStage] = {}

    async def add(self, item: RunStage) -> RunStage:
        self.items[item.id] = item
        return item

    async def list_by_run(self, run_id: UUID) -> list[RunStage]:
        return sorted((x for x in self.items.values() if x.run_id == run_id), key=lambda x: x.position)


class InMemoryOutbox:
    def __init__(self) -> None:
        self.items: dict[UUID, OutboxEvent] = {}

    async def add(self, item: OutboxEvent) -> OutboxEvent:
        self.items[item.id] = item
        return item

    async def list_pending(self) -> list[OutboxEvent]:
        return [x for x in self.items.values() if x.status == OutboxStatus.PENDING]

    async def claim_pending(self, limit: int = 100, stale_after_seconds: int = 300) -> list[OutboxEvent]:
        claimed: list[OutboxEvent] = []
        now = utcnow()
        stale_before = now - timedelta(seconds=stale_after_seconds)
        for item in sorted(self.items.values(), key=lambda value: value.created_at):
            if item.topic not in ("run.requested", "run.cancel_requested"):
                continue
            if item.status == OutboxStatus.PUBLISHING and item.published_at and item.published_at > stale_before:
                continue
            if item.status not in (OutboxStatus.PENDING, OutboxStatus.PUBLISHING):
                continue
            item.status = OutboxStatus.PUBLISHING
            item.published_at = now
            claimed.append(item.model_copy(deep=True))
            if len(claimed) >= limit:
                break
        return claimed

    async def mark_published(
        self, event_id: UUID, published_at: datetime, claimed_at: datetime
    ) -> OutboxEvent | None:
        item = self.items.get(event_id)
        if item is None or item.status != OutboxStatus.PUBLISHING or item.published_at != claimed_at:
            return None
        item.status = OutboxStatus.PUBLISHED
        item.published_at = published_at
        return item

    async def reset_pending(self, event_id: UUID, claimed_at: datetime) -> OutboxEvent | None:
        item = self.items.get(event_id)
        if item is None or item.status != OutboxStatus.PUBLISHING or item.published_at != claimed_at:
            return None
        item.status = OutboxStatus.PENDING
        item.published_at = None
        return item
