from uuid import uuid4

import pytest

from hydrolab.execution.memory import InMemoryExecutions, InMemoryGpuLeases
from hydrolab.execution.reconciler import RecoveryReconciler
from hydrolab.experiments.entities import Run
from hydrolab.experiments.enums import RunStatus
from hydrolab.experiments.memory import InMemoryRuns
from hydrolab.ports.dto import RunHandle, RunState


class Missing(Exception):
    pass


class FakeExecutor:
    def __init__(self):
        self.handles = {}
        self.cleaned = []
        self.labeled = []

    async def recover(self, run_id):
        if run_id not in self.handles:
            raise Missing()
        return self.handles[run_id]

    async def cleanup(self, external_id):
        self.cleaned.append(external_id)

    async def list_labeled_containers(self):
        return list(self.labeled)


def _run(status):
    return Run(experiment_id=uuid4(), experiment_version_id=uuid4(), owner_id=uuid4(), status=status)


@pytest.mark.asyncio
async def test_running_orphan_fails_and_releases_gpu():
    runs, executions, leases, executor = InMemoryRuns(), InMemoryExecutions(), InMemoryGpuLeases(1), FakeExecutor()
    run = _run(RunStatus.RUNNING)
    await runs.add(run)
    await leases.acquire(run.id, 1, run.updated_at)
    reconciler = RecoveryReconciler(runs, executions, leases, executor, not_found_exc=(Missing,))
    report = await reconciler.reconcile_once()
    assert report["failed_orphan"] == 1
    assert (await runs.get(run.id)).status == RunStatus.FAILED
    assert await leases.list_by_run(run.id) == []


@pytest.mark.asyncio
async def test_preparing_without_container_requeues():
    runs, executions, leases, executor = InMemoryRuns(), InMemoryExecutions(), InMemoryGpuLeases(1), FakeExecutor()
    run = _run(RunStatus.PREPARING)
    await runs.add(run)
    await leases.acquire(run.id, 1, run.updated_at)
    reconciler = RecoveryReconciler(runs, executions, leases, executor, not_found_exc=(Missing,))
    report = await reconciler.reconcile_once()
    assert report["requeued"] == 1
    assert (await runs.get(run.id)).status == RunStatus.QUEUED
    assert await leases.list_by_run(run.id) == []


@pytest.mark.asyncio
async def test_existing_container_recreates_execution():
    runs, executions, leases, executor = InMemoryRuns(), InMemoryExecutions(), InMemoryGpuLeases(1), FakeExecutor()
    run = _run(RunStatus.PREPARING)
    await runs.add(run)
    lease = await leases.acquire(run.id, 1, run.updated_at)
    executor.handles[run.id] = RunHandle(run_id=run.id, external_id="docker-x", state=RunState.RUNNING)
    reconciler = RecoveryReconciler(runs, executions, leases, executor, not_found_exc=(Missing,))
    report = await reconciler.reconcile_once()
    assert report["reattached"] == 1
    assert (await runs.get(run.id)).status == RunStatus.RUNNING
    assert (await executions.get(run.id)).external_id == "docker-x"
    assert (await executions.get(run.id)).gpu_indices == [lease[0].gpu_index]


@pytest.mark.asyncio
async def test_terminal_leftover_container_is_cleaned():
    runs, executions, leases, executor = InMemoryRuns(), InMemoryExecutions(), InMemoryGpuLeases(1), FakeExecutor()
    run = _run(RunStatus.SUCCEEDED)
    await runs.add(run)
    executor.labeled.append((run.id, "docker-leftover"))
    reconciler = RecoveryReconciler(runs, executions, leases, executor, not_found_exc=(Missing,))
    report = await reconciler.reconcile_once()
    assert report["cleaned_leftover"] == 1
    assert executor.cleaned == ["docker-leftover"]
