"""单机 GPU FIFO 调度器。

面向单机双卡的研究工作流：Run 提交后保持 QUEUED，调度器周期性回收已完成任务，
然后按创建时间顺序启动可用 GPU 容量内的下一个 Run。它不承担持久队列职责；
生产级多节点调度仍应由后续 Celery / Docker Runner 实现。
"""
from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Protocol

from hydrolab.core.logging import get_logger, log_with
from hydrolab.execution.service import RunControlService
from hydrolab.experiments.entities import Run


class SchedulerRunStore(Protocol):
    async def list_queued(self) -> list[Run]: ...
    async def list_active(self) -> list[Run]: ...


class GpuFifoScheduler:
    """一张 GPU 一个 Run 的非阻塞 FIFO 调度器。"""

    def __init__(
        self,
        runs: SchedulerRunStore,
        control: RunControlService,
        *,
        poll_interval_seconds: float = 1.0,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds 必须大于 0")
        self._runs = runs
        self._control = control
        self._poll_interval_seconds = poll_interval_seconds
        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._tick_lock = asyncio.Lock()
        self._logger = get_logger("hydrolab.scheduler")

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """启动后台循环；重复调用是幂等的。"""
        if self.running:
            return
        self._stopping = False
        self._task = asyncio.create_task(self._run(), name="hydrolab-gpu-fifo-scheduler")
        log_with(self._logger, 20, "scheduler_started", poll_interval=self._poll_interval_seconds)

    async def stop(self) -> None:
        """停止循环，不取消正在运行的训练进程。"""
        self._stopping = True
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        log_with(self._logger, 20, "scheduler_stopped")

    async def tick(self) -> dict[str, int]:
        """执行一轮调度，供测试与内部观测调用。

        先以 timeout=0 非阻塞检查活跃 Run，已退出就 finalize 并释放 GPU；
        再按 FIFO 尝试启动 QUEUED Run。抢不到卡不是错误，Run 保持 QUEUED 等待下轮。
        """
        async with self._tick_lock:
            finalized = await self._reap_finished_runs()
            started = await self._start_queued_runs()
            return {"finalized": finalized, "started": started}

    async def _run(self) -> None:
        while not self._stopping:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                # 一个异常不能杀掉所有排队任务；下个 tick 继续尝试。
                self._logger.exception("scheduler_tick_failed")
            await asyncio.sleep(self._poll_interval_seconds)

    async def _reap_finished_runs(self) -> int:
        finalized = 0
        for run in await self._runs.list_active():
            # Fake runner 需要显式 complete，不能由调度器自动结束。
            if not self._control.is_real_executor:
                continue
            before = run.status
            await self._control.await_completion(run.id, timeout=0)
            if before != run.status:
                finalized += 1
                log_with(
                    self._logger,
                    20,
                    "run_finalized",
                    run_id=str(run.id),
                    status=run.status.value,
                )
        return finalized

    async def _start_queued_runs(self) -> int:
        started = 0
        for run in await self._runs.list_queued():
            # 单机策略：一张卡一个 Run。start() 是原子抢租约，故即便未来有其他
            # 启动路径竞争，也不会出现同一 GPU 被两个 Run 分配的情况。
            try:
                await self._control.start(run.id, gpu_count=1)
            except Exception as cause:
                # 资源不足是正常排队状态；Run 留在 QUEUED，等待下一个 tick。
                # 用错误文案兼容当前 AppError，不把特定错误类型耦合进调度器。
                if "当前没有足够的可用 GPU" in str(cause):
                    break
                # start() 在 PREPARING 失败时已将 Run 标为 FAILED 并释放租约；
                # 记录后继续下一个，不能因一个坏实验阻塞整队。
                log_with(
                    self._logger,
                    40,
                    "run_start_failed",
                    run_id=str(run.id),
                    error=str(cause),
                )
                continue
            started += 1
            log_with(self._logger, 20, "run_scheduled", run_id=str(run.id))
        return started
