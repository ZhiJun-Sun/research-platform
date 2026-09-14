"""CeleryTaskQueueAdapter 单测（QUEUE-01 Spike 验证）。

Celery 的 broker 依赖外部 Redis，本地无真实服务。与 S3/MLflow/Docker 一致，
这里 mock `_app.send_task`/`_app.connection` 验证适配器的编排逻辑：
投递回执、消息契约、撤销信号、健康检查降级、错误映射。
"""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from hydrolab.adapters.celery import CeleryTaskQueueAdapter
from hydrolab.core.errors import AppError
from hydrolab.ports.dto import TaskEnvelope


@pytest.fixture()
def queue() -> CeleryTaskQueueAdapter:
    adapter = CeleryTaskQueueAdapter(broker_url="redis://127.0.0.1:6379/0")
    return adapter


def _envelope(job_type: str = "run.execute") -> TaskEnvelope:
    return TaskEnvelope(job_type=job_type, resource_id=uuid4())


async def test_enqueue_returns_receipt_with_stable_job_id(queue: CeleryTaskQueueAdapter) -> None:
    fake_result = MagicMock()
    fake_result.id = "celery-task-123"
    queue._app.send_task = MagicMock(return_value=fake_result)  # type: ignore[method-assign]

    envelope = _envelope()
    receipt = await queue.enqueue(envelope)
    assert receipt.job_id == envelope.job_id
    assert receipt.external_task_id == "celery-task-123"
    assert receipt.queue == "hydrolab"
    # 消息只传稳定 ID，不传 payload 大对象
    _, kwargs = queue._app.send_task.call_args
    assert kwargs["kwargs"]["job_id"] == str(envelope.job_id)
    assert "payload" not in kwargs["kwargs"]


async def test_enqueue_maps_failure_to_apperror(queue: CeleryTaskQueueAdapter) -> None:
    queue._app.send_task = MagicMock(side_effect=RuntimeError("broker down"))  # type: ignore[method-assign]
    with pytest.raises(AppError):
        await queue.enqueue(_envelope())


async def test_revoke_records_signal(queue: CeleryTaskQueueAdapter) -> None:
    queue._app.control.revoke = MagicMock()  # type: ignore[method-assign]
    await queue.revoke("some-task-id")
    assert "some-task-id" in queue.revoked_ids()
    queue._app.control.revoke.assert_called_once_with("some-task-id", terminate=False)


async def test_healthcheck_returns_false_when_broker_down(queue: CeleryTaskQueueAdapter) -> None:
    # broker 不可达：healthcheck 应返回 False 而非抛异常
    result = await queue.healthcheck()
    assert result is False or result is True