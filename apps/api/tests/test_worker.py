"""Celery Worker 最小闭环单测（QUEUE-01 / plans/06 P1）。

验证：WorkerRuntime 的 job_id+attempt 幂等语义——重复投递不重复启动；
失败允许重试；可注入 handler（消费时重新读库）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

import pytest

# worker 是独立包，未安装到 api venv；把其 src 加入 sys.path 以便测试导入
_WORKER_SRC = Path(__file__).resolve().parents[2] / "worker" / "src"
sys.path.insert(0, str(_WORKER_SRC))

from hydrolab_worker import IdempotencyGuard, JobKey, WorkerRuntime  # noqa: E402


async def test_duplicate_delivery_does_not_repeat_run() -> None:
    calls: list[int] = []

    async def handler(run_id, attempt):
        calls.append(attempt)
        return "ok"

    runtime = WorkerRuntime(handler=handler)
    job_id = uuid4()
    run_id = uuid4()
    await runtime.execute(job_id, run_id, 1)
    # 重复投递同一 job_id+attempt：不重复启动
    dup = await runtime.execute(job_id, run_id, 1)
    assert dup == {"status": "duplicate", "job_id": str(job_id), "attempt": 1}
    assert calls == [1]


async def test_failure_allows_retry_same_attempt() -> None:
    calls: list[int] = []

    async def flaky_handler(run_id, attempt):
        calls.append(attempt)
        if len(calls) == 1:
            raise RuntimeError("transient")
        return "recovered"

    runtime = WorkerRuntime(handler=flaky_handler)
    job_id = uuid4()
    with pytest.raises(RuntimeError):
        await runtime.execute(job_id, uuid4(), 1)
    # 失败后 guard 已释放，允许重试同一 attempt + 递增 attempt
    assert await runtime.execute(job_id, uuid4(), 2) == "recovered"
    assert calls == [1, 2]


def test_guard_semantics() -> None:
    guard = IdempotencyGuard()
    key = JobKey("j", 1)
    assert guard.begin(key) is True
    assert guard.begin(key) is False  # in-flight
    guard.complete(key)
    assert guard.contains(key) is True


async def test_runtime_requires_handler() -> None:
    runtime = WorkerRuntime()  # 未配置 handler
    with pytest.raises(RuntimeError):
        await runtime.execute(uuid4(), uuid4(), 1)


@pytest.mark.parametrize("lock_owned", [True, False])
async def test_production_handler_respects_database_ownership(monkeypatch, tmp_path, lock_owned):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from hydrolab_worker import runtime

    from hydrolab.adapters.fake import FakeRunExecutor, FakeTaskQueue
    from hydrolab.db.factory import _build_memory
    from hydrolab.experiments.entities import Run
    from hydrolab.ports.dto import RunState, RunStatusSnapshot

    stores = _build_memory()
    run = Run(experiment_id=uuid4(), experiment_version_id=uuid4(), owner_id=uuid4())
    await stores.runs.add(run)
    executor = FakeRunExecutor()
    executor.wait = AsyncMock(return_value=RunStatusSnapshot(
        run_id=run.id, state=RunState.SUCCEEDED, exit_code=0,
    ))
    executor.cleanup = AsyncMock()
    db_result = MagicMock()
    db_result.scalar.return_value = int(lock_owned)
    lock = SimpleNamespace(execute=AsyncMock(return_value=db_result))

    @asynccontextmanager
    async def connect():
        yield lock

    @asynccontextmanager
    async def session():
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        yield SimpleNamespace(execute=AsyncMock(return_value=result))

    engine = SimpleNamespace(connect=connect, dispose=AsyncMock())
    settings = SimpleNamespace(
        validate_production=lambda: None, database_backend="mysql", run_executor_backend="docker",
        database_url="unused", runner_image_whitelist=[], runner_workspace_root=tmp_path,
        runner_allow_network=False, runner_container_python="python", runner_default_timeout_seconds=60,
    )
    monkeypatch.setattr(runtime, "get_settings", lambda: settings)
    monkeypatch.setattr(runtime, "create_async_engine", lambda *a, **k: engine)
    monkeypatch.setattr(runtime, "async_sessionmaker", lambda *a, **k: session)
    monkeypatch.setattr(runtime, "build_domain_stores", lambda *a: stores)
    monkeypatch.setattr(runtime, "DockerGpuRunExecutor", lambda **k: executor)
    monkeypatch.setattr(runtime, "get_object_storage", lambda: None)
    monkeypatch.setattr(runtime, "get_task_queue", FakeTaskQueue)
    monkeypatch.setattr(runtime, "get_experiment_tracker", lambda: None)
    if not lock_owned:
        with pytest.raises(ConnectionError):
            await runtime.execute_run(run.id, 1)
        assert not executor.started_specs
    else:
        assert await runtime.execute_run(run.id, 1) == {"status": "SUCCEEDED"}
        assert await runtime.execute_run(run.id, 1) == {"status": "SUCCEEDED"}
        assert len(executor.started_specs) == 1
        assert not stores.gpu_leases.items
        executor.cleanup.assert_awaited_once()
    engine.dispose.assert_awaited()
