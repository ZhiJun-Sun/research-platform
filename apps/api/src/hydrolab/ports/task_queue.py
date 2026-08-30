"""任务队列端口（plans/05 第 5 节）。

实现：FakeTaskQueue → CeleryTaskQueueAdapter。
规则：投递至少一次；消费者按 job_id + attempt 幂等；
revoke 只是取消信号，终态由 HydroLab 状态机确认。
"""

from typing import Protocol

from hydrolab.ports.dto import EnqueueReceipt, TaskEnvelope


class TaskQueue(Protocol):
    async def enqueue(self, envelope: TaskEnvelope) -> EnqueueReceipt: ...

    async def revoke(self, external_task_id: str) -> None: ...

    async def healthcheck(self) -> bool: ...
