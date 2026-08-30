"""TaskQueue 端口契约测试（Fake 实现；Celery 实现接入时复用同组断言）。"""

from uuid import uuid4

import pytest

from hydrolab.adapters.fake import FakeTaskQueue
from hydrolab.core.errors import AppError
from hydrolab.ports.dto import TaskEnvelope


@pytest.fixture
def queue() -> FakeTaskQueue:
    return FakeTaskQueue()


def _envelope(job_type: str = "run.execute") -> TaskEnvelope:
    return TaskEnvelope(job_type=job_type, resource_id=uuid4())


async def test_enqueue_returns_receipt_with_stable_job_id(queue: FakeTaskQueue) -> None:
    envelope = _envelope()
    receipt = await queue.enqueue(envelope)
    assert receipt.job_id == envelope.job_id
    assert receipt.external_task_id
    assert queue.enqueued == [envelope]


async def test_envelope_carries_only_stable_ids(queue: FakeTaskQueue) -> None:
    envelope = _envelope()
    payload = envelope.model_dump(mode="json")
    assert payload["schema_version"] == 1
    assert payload["job_type"] == "run.execute"
    assert isinstance(payload["job_id"], str)


async def test_duplicate_delivery_is_visible_to_consumer(queue: FakeTaskQueue) -> None:
    queue.injector.inject_duplicate("enqueue")
    envelope = _envelope()
    await queue.enqueue(envelope)
    # broker 至少一次语义：同一 envelope 可能出现两次，消费者须幂等
    assert len(queue.enqueued) == 2
    assert queue.enqueued[0].job_id == queue.enqueued[1].job_id


async def test_enqueue_failure_injection(queue: FakeTaskQueue) -> None:
    queue.injector.inject_failure("enqueue", AppError("DEPENDENCY_UNAVAILABLE", "broker down"))
    with pytest.raises(AppError) as exc:
        await queue.enqueue(_envelope())
    assert exc.value.code == "DEPENDENCY_UNAVAILABLE"
    # 故障注入仅一次，随后恢复
    await queue.enqueue(_envelope())


async def test_revoke_records_cancel_signal(queue: FakeTaskQueue) -> None:
    receipt = await queue.enqueue(_envelope())
    await queue.revoke(receipt.external_task_id)
    assert queue.revoked == [receipt.external_task_id]


async def test_healthcheck(queue: FakeTaskQueue) -> None:
    assert await queue.healthcheck() is True
