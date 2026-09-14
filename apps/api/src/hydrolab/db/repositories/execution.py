"""B5/B6 执行控制与观测 SQL 仓储。"""

import asyncio
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from hydrolab.db.models.execution import (
    GpuLeaseModel,
    ResourceSampleModel,
    RunEventModel,
    RunExecutionModel,
    RunLogChunkModel,
)
from hydrolab.domain.entities import utcnow
from hydrolab.execution.entities import GpuLease, ResourceSample, RunEvent, RunExecution, RunLogChunk
from hydrolab.ports.dto import EventType


def _to_lease(m: GpuLeaseModel) -> GpuLease:
    return GpuLease(
        id=m.id,
        gpu_index=m.gpu_index,
        run_id=m.run_id,
        expires_at=m.expires_at,
        heartbeat_at=m.heartbeat_at,
        created_at=m.created_at,
    )


def _to_execution(m: RunExecutionModel) -> RunExecution:
    return RunExecution(
        run_id=m.run_id,
        external_id=m.external_id,
        gpu_indices=m.gpu_indices or [],
        started_at=m.started_at,
        timeout_seconds=m.timeout_seconds,
    )


def _to_event(m: RunEventModel) -> RunEvent:
    return RunEvent(
        id=m.id,
        event_type=EventType(m.event_type),
        run_id=m.run_id,
        occurred_at=m.occurred_at,
        payload=m.payload or {},
    )


def _to_log(m: RunLogChunkModel) -> RunLogChunk:
    return RunLogChunk(
        id=m.id,
        run_id=m.run_id,
        content=m.content,
        stream=m.stream,
        created_at=m.created_at,
    )


def _to_sample(m: ResourceSampleModel) -> ResourceSample:
    return ResourceSample(
        run_id=m.run_id,
        gpu_index=m.gpu_index,
        utilization_percent=m.utilization_percent,
        memory_used_mb=m.memory_used_mb,
        memory_total_mb=m.memory_total_mb,
        sampled_at=m.sampled_at,
    )


class SqlGpuLeases:
    # 死锁 / 锁等待超时是并发租约竞争的常见结果，属于可重试的瞬态错误。
    _DEADLOCK_CODES = (1213, 1205)

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], gpu_count: int = 2, max_deadlock_retries: int = 3
    ) -> None:
        self._sf = session_factory
        self.gpu_count = gpu_count
        self._max_deadlock_retries = max_deadlock_retries

    @staticmethod
    def _is_deadlock(exc: OperationalError) -> bool:
        orig = getattr(exc, "orig", None)
        code = None
        if orig is not None:
            args = getattr(orig, "args", None)
            if args:
                try:
                    code = int(args[0])
                except (TypeError, ValueError):
                    code = None
        return code in SqlGpuLeases._DEADLOCK_CODES

    async def acquire(self, run_id: UUID, count: int, expires_at: datetime) -> list[GpuLease]:
        for attempt in range(self._max_deadlock_retries + 1):
            try:
                return await self._acquire_once(run_id, count, expires_at)
            except OperationalError as exc:
                if self._is_deadlock(exc) and attempt < self._max_deadlock_retries:
                    await asyncio.sleep(0.05 * (attempt + 1))
                    continue
                raise
        return []

    async def _acquire_once(self, run_id: UUID, count: int, expires_at: datetime) -> list[GpuLease]:
        async with self._sf() as session:
            try:
                # The unique gpu_index constraint is the final race guard when
                # two API workers try to claim the same slot concurrently.
                # An expired heartbeat does not prove the container has stopped.
                # Only confirmed termination/reconciliation may release its slot.
                res = await session.execute(
                    select(GpuLeaseModel.gpu_index)
                    .where(GpuLeaseModel.gpu_index < self.gpu_count)
                    .with_for_update()
                )
                used = {x for x in res.scalars().all()}
                available = [i for i in range(self.gpu_count) if i not in used]
                if len(available) < count:
                    await session.rollback()
                    return []
                leases = [
                    GpuLease(gpu_index=i, run_id=run_id, expires_at=expires_at)
                    for i in available[:count]
                ]
                session.add_all(
                    [
                        GpuLeaseModel(
                            id=x.id,
                            gpu_index=x.gpu_index,
                            run_id=x.run_id,
                            expires_at=x.expires_at,
                            heartbeat_at=x.heartbeat_at,
                            created_at=x.created_at,
                        )
                        for x in leases
                    ]
                )
                await session.commit()
                return leases
            except IntegrityError:
                # A concurrent claimant won the unique slot race.  Treat it as
                # normal resource contention so the caller can retry/queue.
                await session.rollback()
                return []

    async def list_by_run(self, run_id: UUID) -> list[GpuLease]:
        async with self._sf() as session:
            res = await session.execute(select(GpuLeaseModel).where(GpuLeaseModel.run_id == run_id))
            return [_to_lease(m) for m in res.scalars().all()]

    async def heartbeat(self, run_id: UUID, expires_at: datetime) -> list[GpuLease]:
        async with self._sf() as session:
            res = await session.execute(select(GpuLeaseModel).where(GpuLeaseModel.run_id == run_id))
            items = list(res.scalars().all())
            now = utcnow()
            for m in items:
                m.heartbeat_at = now
                m.expires_at = expires_at
            await session.commit()
            return [_to_lease(m) for m in items]

    async def release_run(self, run_id: UUID) -> None:
        async with self._sf() as session:
            await session.execute(delete(GpuLeaseModel).where(GpuLeaseModel.run_id == run_id))
            await session.commit()


class SqlExecutions:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, item: RunExecution) -> RunExecution:
        async with self._sf() as session:
            session.add(
                RunExecutionModel(
                    run_id=item.run_id,
                    external_id=item.external_id,
                    gpu_indices=item.gpu_indices,
                    started_at=item.started_at,
                    timeout_seconds=item.timeout_seconds,
                )
            )
            await session.commit()
            return item

    async def get(self, run_id: UUID) -> RunExecution | None:
        async with self._sf() as session:
            m = await session.get(RunExecutionModel, run_id)
            return _to_execution(m) if m else None

    async def remove(self, run_id: UUID) -> None:
        async with self._sf() as session:
            m = await session.get(RunExecutionModel, run_id)
            if m is not None:
                await session.delete(m)
            await session.commit()


class SqlRunEvents:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def append(
        self, event_type: EventType, run_id: UUID, payload: dict[str, object]
    ) -> RunEvent:
        async with self._sf() as session:
            m = RunEventModel(
                event_type=event_type.value,
                run_id=run_id,
                occurred_at=utcnow(),
                payload=payload,
            )
            session.add(m)
            await session.flush()
            await session.commit()
            return _to_event(m)

    async def list_after(self, run_id: UUID, after_id: int = 0) -> list[RunEvent]:
        async with self._sf() as session:
            res = await session.execute(
                select(RunEventModel)
                .where(RunEventModel.run_id == run_id, RunEventModel.id > after_id)
                .order_by(RunEventModel.id)
            )
            return [_to_event(m) for m in res.scalars().all()]


class SqlLogs:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def append(self, run_id: UUID, content: str, stream: str = "stdout") -> RunLogChunk:
        async with self._sf() as session:
            m = RunLogChunkModel(
                run_id=run_id,
                content=content,
                stream=stream,
                created_at=utcnow(),
            )
            session.add(m)
            await session.flush()
            await session.commit()
            return _to_log(m)

    async def list_after(self, run_id: UUID, after_id: int = 0) -> list[RunLogChunk]:
        async with self._sf() as session:
            res = await session.execute(
                select(RunLogChunkModel)
                .where(RunLogChunkModel.run_id == run_id, RunLogChunkModel.id > after_id)
                .order_by(RunLogChunkModel.id)
            )
            return [_to_log(m) for m in res.scalars().all()]


class SqlResourceSamples:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sf = session_factory

    async def add(self, item: ResourceSample) -> ResourceSample:
        async with self._sf() as session:
            session.add(
                ResourceSampleModel(
                    run_id=item.run_id,
                    gpu_index=item.gpu_index,
                    utilization_percent=item.utilization_percent,
                    memory_used_mb=item.memory_used_mb,
                    memory_total_mb=item.memory_total_mb,
                    sampled_at=item.sampled_at,
                )
            )
            await session.commit()
            return item

    async def list_by_run(self, run_id: UUID) -> list[ResourceSample]:
        async with self._sf() as session:
            res = await session.execute(
                select(ResourceSampleModel).where(ResourceSampleModel.run_id == run_id)
            )
            return [_to_sample(m) for m in res.scalars().all()]
