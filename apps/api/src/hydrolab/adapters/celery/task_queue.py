"""Celery + Redis TaskQueue 真实实现（QUEUE-01 Spike 适配器）。

职责：只承担消息投递与撤销信号，Worker 唤醒后重新读库校验状态。
消息契约（plans/05 §5.2）：只传稳定 ID，不传 ORM 对象/Secret/大配置。
可靠性（§5.3）：投递至少一次；消费者以 job_id+attempt 幂等；
Celery 状态不作为 Run 真相源；revoke 只是取消信号。

安全：凭证走 settings，异常信息不包含 broker 连接串。
"""

from __future__ import annotations

from hydrolab.core.errors import dependency_unavailable
from hydrolab.ports.dto import EnqueueReceipt, TaskEnvelope


class CeleryTaskQueueAdapter:
    """把 TaskEnvelope 投递到 Celery broker（默认 Redis）。

    enqueue/revoke 为同步 Celery API，用 asyncio.to_thread 包裹避免阻塞事件循环。
    """

    def __init__(self, broker_url: str, queue: str = "hydrolab") -> None:
        self._broker_url = broker_url
        self._queue = queue
        self._app = self._make_app()
        self._enqueued: list[tuple[TaskEnvelope, str]] = []
        self._revoked: list[str] = []

    def _make_app(self):
        from celery import Celery

        return Celery("hydrolab", broker=self._broker_url, include=[])

    def _task_name(self, envelope: TaskEnvelope) -> str:
        # 约定：job_type -> Celery task name（Worker 侧用同名 task 消费）
        return envelope.job_type

    async def enqueue(self, envelope: TaskEnvelope) -> EnqueueReceipt:
        import asyncio

        task_name = self._task_name(envelope)
        try:
            # apply_async 通过 broker 投递；kwargs 只含稳定 ID
            result = await asyncio.to_thread(
                self._app.send_task,
                task_name,
                kwargs=self._serialize(envelope),
                queue="hydrolab-control" if envelope.job_type == "run.cancel" else self._queue,
                task_id=str(envelope.job_id),
                countdown=0,
            )
            external_id = result.id
        except Exception as exc:
            raise dependency_unavailable(
                "Celery 投递失败", {"reason": exc.__class__.__name__}
            ) from exc
        self._enqueued.append((envelope, external_id))
        return EnqueueReceipt(
            job_id=envelope.job_id, external_task_id=external_id,
            queue="hydrolab-control" if envelope.job_type == "run.cancel" else self._queue,
        )

    def _serialize(self, envelope: TaskEnvelope) -> dict:
        # 消息只携带稳定 ID 与必要调度字段（不传 payload 内的大对象）
        data = envelope.model_dump(mode="json", include={"job_id", "resource_id", "attempt"})
        # 明确去掉不适合进 broker 的字段（payload 交由 Worker 读库重取）
        data.pop("payload", None)
        return data

    async def revoke(self, external_task_id: str) -> None:
        import asyncio

        try:
            await asyncio.to_thread(
                self._app.control.revoke, external_task_id, terminate=False
            )
        except Exception as exc:
            raise dependency_unavailable(
                "Celery 撤销失败", {"reason": exc.__class__.__name__}
            ) from exc
        self._revoked.append(external_task_id)

    async def healthcheck(self) -> bool:
        import asyncio

        try:
            conn = await asyncio.to_thread(
                self._app.connection, self._broker_url
            )
            await asyncio.to_thread(conn.connect)
            conn.close()
            return True
        except Exception:
            return False

    # 测试辅助
    def enqueued_count(self) -> int:
        return len(self._enqueued)

    def revoked_ids(self) -> list[str]:
        return list(self._revoked)
