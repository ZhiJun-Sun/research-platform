"""Offline regression gates for automatic publication and Worker isolation."""

import asyncio
import inspect
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from hydrolab.adapters.celery.task_queue import CeleryTaskQueueAdapter
from hydrolab.adapters.remote_executor import RemoteRunExecutor
from hydrolab.domain.entities import utcnow
from hydrolab.execution.publisher import OutboxPublisher
from hydrolab.execution.service import RunControlService
from hydrolab.experiments.entities import OutboxEvent
from hydrolab.experiments.enums import OutboxStatus
from hydrolab.experiments.memory import InMemoryOutbox
from hydrolab.ports.dto import TaskEnvelope

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "worker" / "src"))


def control_for(outbox, queue):
    return RunControlService(None, outbox, None, None, None, None, None, queue, RemoteRunExecutor())


async def test_publisher_retries_without_manual_api_call():
    delivered = asyncio.Event()
    outbox = InMemoryOutbox()
    event = await outbox.add(OutboxEvent(
        aggregate_type="run", aggregate_id=uuid4(), topic="run.requested", payload={},
    ))
    messages = []

    async def enqueue(message):
        messages.append(message)
        if len(messages) == 1:
            raise ConnectionError("broker unavailable")
        delivered.set()

    publisher = OutboxPublisher(control_for(outbox, MagicMock(enqueue=enqueue)), interval=0.01)
    publisher.start()
    first_task = publisher.task
    publisher.start()
    assert publisher.task is first_task
    try:
        await asyncio.wait_for(delivered.wait(), 1)
        assert event.status == OutboxStatus.PUBLISHED
        assert len(messages) == 2
        assert messages[0].job_id == messages[1].job_id == event.id
    finally:
        await publisher.stop()
    assert publisher.task.done()


async def test_expired_claim_cannot_confirm_or_reset_new_claim():
    outbox = InMemoryOutbox()
    event = await outbox.add(OutboxEvent(
        aggregate_type="run", aggregate_id=uuid4(), topic="run.requested", payload={},
    ))
    old = (await outbox.claim_pending())[0]
    assert await outbox.claim_pending() == []
    event.published_at = utcnow() - timedelta(minutes=10)
    new = (await outbox.claim_pending())[0]
    assert await outbox.mark_published(event.id, utcnow(), old.published_at) is None
    assert await outbox.reset_pending(event.id, old.published_at) is None
    assert await outbox.mark_published(event.id, utcnow(), new.published_at) is not None


async def test_unknown_topic_does_not_starve_training():
    outbox = InMemoryOutbox()
    for topic in ["unrelated", "run.requested"]:
        await outbox.add(OutboxEvent(
            aggregate_type="run", aggregate_id=uuid4(), topic=topic, payload={},
        ))
    queue = MagicMock(enqueue=AsyncMock())
    assert await control_for(outbox, queue).dispatch_pending() == 1


async def test_cancel_uses_control_queue_and_task_signature():
    from hydrolab_worker.tasks import create_celery_app

    queue = CeleryTaskQueueAdapter("memory://")
    queue._app.send_task = MagicMock(return_value=MagicMock(id="receipt"))
    message = TaskEnvelope(job_type="run.cancel", resource_id=uuid4())
    receipt = await queue.enqueue(message)
    assert receipt.queue == "hydrolab-control"
    kwargs = queue._app.send_task.call_args.kwargs
    assert kwargs["queue"] == "hydrolab-control"
    assert set(kwargs["kwargs"]) == {"job_id", "resource_id", "attempt"}
    assert create_celery_app("memory://").conf.task_default_queue == "hydrolab"


async def test_remote_executor_cannot_launch_docker():
    from hydrolab.core.errors import AppError

    executor = RemoteRunExecutor()
    assert not executor.real_executor
    assert "docker" not in inspect.getmodule(executor).__dict__
    with pytest.raises(AppError):
        await executor.start(None)
