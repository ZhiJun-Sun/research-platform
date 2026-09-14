"""MySQL-backed single-host Docker execution; no API process or lifespan."""

import asyncio
from datetime import timedelta
from uuid import UUID

from hydrolab.adapters.docker import DockerGpuRunExecutor
from hydrolab.api.deps import get_experiment_tracker, get_object_storage, get_task_queue
from hydrolab.core.settings import get_settings
from hydrolab.db.factory import build_domain_stores
from hydrolab.db.models.experiments import OutboxModel
from hydrolab.domain.entities import utcnow
from hydrolab.execution.collector import ArtifactCollector
from hydrolab.execution.entities import RunExecution
from hydrolab.execution.service import RunControlService
from hydrolab.experiments.enums import RunStatus
from hydrolab.ports.dto import RunState
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


async def execute_run(run_id: UUID, attempt: int):
    settings = get_settings()
    settings.validate_production()
    if settings.database_backend != "mysql" or settings.run_executor_backend != "docker":
        raise RuntimeError("Worker requires MySQL and Docker")
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    stores = build_domain_stores(settings, sf)
    executor = DockerGpuRunExecutor(
        image_whitelist=settings.runner_image_whitelist,
        workspace_root=settings.runner_workspace_root,
        allow_network=settings.runner_allow_network,
        container_python=settings.runner_container_python,
        default_timeout_seconds=settings.runner_default_timeout_seconds,
    )
    storage = get_object_storage()
    control = RunControlService(
        stores.runs, stores.outbox, stores.gpu_leases, stores.executions,
        stores.run_events, stores.run_logs, stores.resource_samples,
        get_task_queue(), executor, tracker=get_experiment_tracker(),
        versions=stores.experiment_versions, code_versions=stores.code_versions,
        storage=storage, collector=ArtifactCollector(storage),
        dataset_versions=stores.dataset_versions, artifacts=stores.artifacts,
    )

    async def cancelled():
        async with sf() as session:
            return (await session.execute(select(OutboxModel.id).where(
                OutboxModel.aggregate_id == run_id,
                OutboxModel.topic == "run.cancel_requested",
            ).limit(1))).scalar_one_or_none() is not None

    lock_name = f"hydrolab:run:{run_id.hex}"
    try:
        async with engine.connect() as lock:
            acquired = (await lock.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": lock_name})).scalar()
            if acquired != 1:
                raise ConnectionError("Run is owned by another Worker; retry")
            try:
                run = await stores.runs.get(run_id)
                if run is None:
                    raise ValueError("Run missing")
                if run.status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
                    return {"status": run.status.value}
                if run.status in (RunStatus.PREPARING, RunStatus.RUNNING):
                    from docker.errors import NotFound

                    try:
                        handle = await executor.recover(run_id)
                    except NotFound:
                        # No known container: do not silently repeat a previously running training.
                        if run.status == RunStatus.RUNNING:
                            await control.finalize(run_id, 1)
                            return {"status": "FAILED"}
                        await stores.gpu_leases.release_run(run_id)
                        run.status = RunStatus.QUEUED
                        await stores.runs.save(run)
                    else:
                        if await stores.executions.get(run_id) is None:
                            leases = await stores.gpu_leases.list_by_run(run_id)
                            await stores.executions.add(RunExecution(
                                run_id=run_id, external_id=handle.external_id,
                                gpu_indices=[lease.gpu_index for lease in leases],
                                timeout_seconds=settings.runner_default_timeout_seconds,
                            ))
                        run.status = RunStatus.RUNNING
                        await stores.runs.save(run)
                if await cancelled():
                    return {"status": (await control.cancel(run_id)).status.value}
                if run.status == RunStatus.QUEUED:
                    from hydrolab.core.errors import AppError

                    try:
                        await control.start(run_id)
                    except AppError as exc:
                        if (await stores.runs.get(run_id)).status == RunStatus.QUEUED:
                            raise ConnectionError("GPU capacity unavailable; retry") from exc
                        raise
                execution = await stores.executions.get(run_id)
                while True:
                    # Holding a connection is not sufficient if MySQL closed it.
                    # Abort on lost lock before touching the container again.
                    owned = (await lock.execute(text(
                        "SELECT IS_USED_LOCK(:name) = CONNECTION_ID()"
                    ), {"name": lock_name})).scalar()
                    if owned != 1:
                        raise ConnectionError("Run ownership lost")
                    if await cancelled():
                        return {"status": (await control.cancel(run_id)).status.value}
                    await stores.gpu_leases.heartbeat(run_id, utcnow() + timedelta(minutes=2))
                    snapshot = await executor.wait(execution.external_id, timeout=0)
                    if snapshot.state not in (RunState.RUNNING, RunState.PREPARING):
                        result = await control.finalize(
                            run_id, snapshot.exit_code if snapshot.exit_code is not None else 1,
                        )
                        await executor.cleanup(execution.external_id)
                        return {"status": result.status.value}
                    if (utcnow() - execution.started_at).total_seconds() > execution.timeout_seconds:
                        await executor.cleanup(execution.external_id)
                        result = await control.finalize(run_id, 1)
                        return {"status": result.status.value}
                    await asyncio.sleep(1)
            finally:
                await lock.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock_name})
    finally:
        await engine.dispose()
