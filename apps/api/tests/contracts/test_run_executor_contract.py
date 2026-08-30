"""FakeRunExecutor 行为测试：状态机、取消幂等、重复启动防护。"""

from uuid import uuid4

import pytest

from hydrolab.adapters.fake import FakeRunExecutor
from hydrolab.core.errors import AppError
from hydrolab.ports.dto import RunSpec, RunState


def _spec() -> RunSpec:
    return RunSpec(
        run_id=uuid4(),
        argv=["python", "train.py"],
        image_digest="sha256:" + "a" * 64,
        gpu_count=1,
    )


async def test_start_and_status() -> None:
    executor = FakeRunExecutor()
    handle = await executor.start(_spec())
    snapshot = await executor.status(handle)
    assert snapshot.state == RunState.RUNNING


async def test_start_requires_argv_and_digest() -> None:
    executor = FakeRunExecutor()
    with pytest.raises(AppError):
        await executor.start(_spec().model_copy(update={"argv": []}))
    with pytest.raises(AppError):
        await executor.start(_spec().model_copy(update={"image_digest": ""}))


async def test_duplicate_start_conflicts() -> None:
    executor = FakeRunExecutor()
    spec = _spec()
    await executor.start(spec)
    with pytest.raises(AppError) as exc:
        await executor.start(spec)
    assert exc.value.code == "CONFLICT"


async def test_cancel_is_idempotent_and_terminal_ignored() -> None:
    executor = FakeRunExecutor()
    handle = await executor.start(_spec())
    await executor.cancel(handle)
    assert (await executor.status(handle)).state == RunState.CANCELLED
    await executor.cancel(handle)  # 重复取消不报错

    other = await executor.start(_spec())
    executor.complete(other.external_id)
    await executor.cancel(other)  # 终态忽略取消
    assert (await executor.status(other)).state == RunState.SUCCEEDED


async def test_failure_transition() -> None:
    executor = FakeRunExecutor()
    handle = await executor.start(_spec())
    executor.fail(handle.external_id, "OOM")
    snapshot = await executor.status(handle)
    assert snapshot.state == RunState.FAILED
    assert snapshot.message == "OOM"
