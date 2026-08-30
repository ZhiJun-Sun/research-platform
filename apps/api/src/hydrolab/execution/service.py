"""B5 Fake Runner 控制面与 B6 观测事件服务。"""

from datetime import timedelta
from uuid import UUID

from hydrolab.adapters.fake.run_executor import FakeRunExecutor
from hydrolab.adapters.fake.task_queue import FakeTaskQueue
from hydrolab.core.errors import conflict, not_found
from hydrolab.domain.entities import utcnow
from hydrolab.execution.entities import ResourceSample, RunExecution
from hydrolab.execution.memory import (
    InMemoryExecutions,
    InMemoryGpuLeases,
    InMemoryLogs,
    InMemoryResourceSamples,
    InMemoryRunEvents,
)
from hydrolab.experiments.entities import Run
from hydrolab.experiments.enums import OutboxStatus, RunStatus
from hydrolab.experiments.repositories import OutboxStore, RunStore
from hydrolab.ports.dto import EventType, RunHandle, RunSpec, RunState, TaskEnvelope


class RunControlService:
    def __init__(
        self,
        runs: RunStore,
        outbox: OutboxStore,
        leases: InMemoryGpuLeases,
        executions: InMemoryExecutions,
        events: InMemoryRunEvents,
        logs: InMemoryLogs,
        samples: InMemoryResourceSamples,
        queue: FakeTaskQueue,
        executor: FakeRunExecutor,
    ) -> None:
        self._runs, self._outbox, self._leases, self._executions = runs, outbox, leases, executions
        self._events, self._logs, self._samples, self._queue, self._executor = events, logs, samples, queue, executor

    async def dispatch_pending(self) -> int:
        count = 0
        for event in await self._outbox.list_pending():
            if event.topic != "run.requested":
                continue
            await self._queue.enqueue(
                TaskEnvelope(job_type="run.execute", resource_id=event.aggregate_id, payload=event.payload)
            )
            event.status, event.published_at = OutboxStatus.PUBLISHED, utcnow()
            count += 1
        return count

    async def start(self, run_id: UUID, gpu_count: int = 1) -> Run:
        run = await self._get_run(run_id)
        if run.status != RunStatus.QUEUED:
            raise conflict("仅 QUEUED Run 可启动", {"status": run.status.value})
        leases = await self._leases.acquire(run_id, gpu_count, utcnow() + timedelta(minutes=2))
        if not leases:
            raise conflict("当前没有足够的可用 GPU")
        run.status, run.updated_at = RunStatus.PREPARING, utcnow()
        await self._event(EventType.STATUS_CHANGED, run_id, {"status": run.status.value})
        spec = RunSpec(
            run_id=run_id, argv=["python", "train.py"], image_digest="fake@sha256:hydrolab", gpu_count=gpu_count
        )
        try:
            handle = await self._executor.start(spec)
        except Exception:
            await self._leases.release_run(run_id)
            run.status = RunStatus.FAILED
            raise
        await self._executions.add(
            RunExecution(
                run_id=run_id,
                external_id=handle.external_id,
                gpu_indices=[x.gpu_index for x in leases],
                timeout_seconds=spec.timeout_seconds,
            )
        )
        run.status, run.updated_at = RunStatus.RUNNING, utcnow()
        await self._event(
            EventType.STATUS_CHANGED, run_id, {"status": run.status.value, "gpu_indices": [x.gpu_index for x in leases]}
        )
        await self._logs.append(run_id, "Fake runner started\n")
        return run

    async def cancel(self, run_id: UUID) -> Run:
        run = await self._get_run(run_id)
        if run.status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
            return run
        execution = await self._executions.get(run_id)
        if execution:
            await self._executor.cancel(
                RunHandle(run_id=run_id, external_id=execution.external_id, state=RunState.RUNNING)
            )
        run.status, run.updated_at = RunStatus.CANCELLED, utcnow()
        await self._leases.release_run(run_id)
        await self._executions.remove(run_id)
        await self._event(EventType.STATUS_CHANGED, run_id, {"status": run.status.value})
        return run

    async def complete_fake(self, run_id: UUID, exit_code: int = 0) -> Run:
        run = await self._get_run(run_id)
        execution = await self._executions.get(run_id)
        if execution is None:
            raise conflict("Run 未在执行")
        self._executor.complete(execution.external_id, exit_code)
        run.status, run.updated_at = (RunStatus.SUCCEEDED if exit_code == 0 else RunStatus.FAILED), utcnow()
        await self._leases.release_run(run_id)
        await self._executions.remove(run_id)
        await self._event(
            EventType.COMPLETED if exit_code == 0 else EventType.FAILED,
            run_id,
            {"status": run.status.value, "exit_code": exit_code},
        )
        return run

    async def report_progress(
        self, run_id: UUID, percent: float, stage: str = "TRAINING", eta_seconds: int | None = None
    ) -> None:
        await self._event(
            EventType.PROGRESS_UPDATED, run_id, {"percent": percent, "stage": stage, "eta_seconds": eta_seconds}
        )

    async def report_metric(self, run_id: UUID, name: str, value: float, step: int | None = None) -> None:
        await self._event(EventType.METRIC_REPORTED, run_id, {"name": name, "value": value, "step": step})

    async def report_resource(
        self, run_id: UUID, gpu_index: int, utilization_percent: float, memory_used_mb: int, memory_total_mb: int
    ) -> None:
        await self._samples.add(
            ResourceSample(
                run_id=run_id,
                gpu_index=gpu_index,
                utilization_percent=utilization_percent,
                memory_used_mb=memory_used_mb,
                memory_total_mb=memory_total_mb,
            )
        )
        await self._event(
            EventType.RESOURCE_SAMPLED,
            run_id,
            {"gpu_index": gpu_index, "utilization_percent": utilization_percent, "memory_used_mb": memory_used_mb},
        )

    async def _get_run(self, run_id: UUID) -> Run:
        run = await self._runs.get(run_id)
        if run is None:
            raise not_found("Run 不存在")
        return run

    async def _event(self, event_type: EventType, run_id: UUID, payload: dict[str, object]) -> None:
        await self._events.append(event_type, run_id, payload)
