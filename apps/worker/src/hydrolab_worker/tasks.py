"""HydroLab Celery Worker 最小消费闭环。

Worker 只接收稳定 ID；生产入口由 runtime.execute_run 从 MySQL 重新读取配置。
生产幂等使用 MySQL Run 锁和持久化终态；WorkerRuntime 留作可注入单元测试辅助。

业务服务不依赖本模块；API 通过 CeleryTaskQueueAdapter 投递 ``run.execute``。
"""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from celery import Celery


@dataclass(frozen=True)
class JobKey:
    job_id: str
    attempt: int


class IdempotencyGuard:
    """进程内幂等保护。

    生产环境应替换为数据库唯一约束/持久化 job_receipts 表；本类用于保证
    Worker 逻辑本身的 ``job_id + attempt`` 语义并支持单进程开发运行。
    """

    def __init__(self) -> None:
        self._completed: set[JobKey] = set()
        self._inflight: set[JobKey] = set()
        self._lock = threading.Lock()

    def begin(self, key: JobKey) -> bool:
        with self._lock:
            if key in self._completed or key in self._inflight:
                return False
            self._inflight.add(key)
            return True

    def complete(self, key: JobKey) -> None:
        with self._lock:
            self._inflight.discard(key)
            self._completed.add(key)

    def fail(self, key: JobKey) -> None:
        with self._lock:
            # 失败允许 Celery 重试同一 attempt；业务侧可递增 attempt。
            self._inflight.discard(key)

    def contains(self, key: JobKey) -> bool:
        with self._lock:
            return key in self._completed or key in self._inflight


RunHandler = Callable[[UUID, int], Awaitable[Any]]


class WorkerRuntime:
    """可注入的 Worker 运行时，方便单元测试与 API/数据库集成装配。"""

    def __init__(self, handler: RunHandler | None = None, guard: IdempotencyGuard | None = None) -> None:
        self.guard = guard or IdempotencyGuard()
        self.handler = handler

    async def execute(self, job_id: UUID, run_id: UUID, attempt: int) -> Any:
        key = JobKey(str(job_id), attempt)
        if not self.guard.begin(key):
            return {"status": "duplicate", "job_id": str(job_id), "attempt": attempt}
        try:
            if self.handler is None:
                raise RuntimeError("WorkerRuntime 未配置 Run handler；消费时必须注入数据库运行时")
            result = await self.handler(run_id, attempt)
        except Exception:
            self.guard.fail(key)
            raise
        self.guard.complete(key)
        return result


def create_celery_app(broker_url: str | None = None) -> Celery:
    """创建 Celery app；broker 由环境变量注入，不在代码中写死。"""
    url = broker_url or os.environ.get("HYDROLAB_REDIS_URL")
    if not url:
        raise RuntimeError("HYDROLAB_REDIS_URL 未配置，无法启动 Worker")
    app = Celery("hydrolab_worker", broker=url)
    app.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_track_started=True,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        task_default_queue="hydrolab",
        broker_transport_options={"visibility_timeout": 7 * 24 * 3600},
    )
    return app


celery_app = create_celery_app() if os.environ.get("HYDROLAB_REDIS_URL") else None
_runtime = WorkerRuntime()


def configure_runtime(handler: RunHandler, guard: IdempotencyGuard | None = None) -> None:
    """由部署入口注入“重新读库并启动 Run”的 handler。"""
    global _runtime
    _runtime = WorkerRuntime(handler=handler, guard=guard)


if celery_app is not None:

    @celery_app.task(
        name="run.execute",
        bind=True,
        autoretry_for=(Exception,),
        retry_backoff=True,
        retry_kwargs={"max_retries": 3},
    )
    def run_execute(self, job_id: str, resource_id: str, attempt: int = 1) -> Any:
        """Celery 任务入口：只接收稳定 ID，handler 负责重新读数据库。"""
        from hydrolab_worker.runtime import execute_run

        try:
            return asyncio.run(execute_run(UUID(resource_id), attempt))
        except ConnectionError as exc:
            raise self.retry(exc=exc, countdown=10, max_retries=None) from exc

    @celery_app.task(name="run.cancel")
    def run_cancel(job_id: str, resource_id: str, attempt: int = 1) -> Any:
        # The execute loop reads the durable cancel event directly from MySQL.
        # This queue is separate so a long training never blocks control delivery.
        return {"status": "requested", "run_id": resource_id}


__all__ = [
    "IdempotencyGuard",
    "JobKey",
    "WorkerRuntime",
    "celery_app",
    "configure_runtime",
    "create_celery_app",
]
