"""内存版 TaskQueue：记录投递、支持重复注入与撤销信号。"""

from hydrolab.adapters.fake.base import FailureInjector
from hydrolab.ports.dto import EnqueueReceipt, TaskEnvelope


class FakeTaskQueue:
    def __init__(self) -> None:
        self.injector = FailureInjector()
        self.enqueued: list[TaskEnvelope] = []
        self.revoked: list[str] = []

    async def enqueue(self, envelope: TaskEnvelope) -> EnqueueReceipt:
        self.injector._record("enqueue", envelope)
        self.enqueued.append(envelope)
        if self.injector._should_duplicate("enqueue"):
            # 模拟 broker 至少一次投递语义下的重复消息
            self.enqueued.append(envelope.model_copy())
        return EnqueueReceipt(
            job_id=envelope.job_id,
            external_task_id=f"fake-task-{envelope.job_id.hex[:12]}-a{envelope.attempt}",
            queue="fake",
        )

    async def revoke(self, external_task_id: str) -> None:
        self.injector._record("revoke", external_task_id)
        self.revoked.append(external_task_id)

    async def healthcheck(self) -> bool:
        self.injector._record("healthcheck")
        return True
