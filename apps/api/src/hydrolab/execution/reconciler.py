"""Run/容器/租约恢复对账器（A7）。

跨进程中断后，恢复依赖消息重投并不够：Worker 崩溃可能留下 PREPARING/RUNNING 的
Run、已确认终态但残留的容器、或有租约但无容器。本对账器周期性地把运行状态与
Docker 容器、GPU 租约对齐：

- RUNNING 且容器已确认为不存在 → 标记 FAILED（不自动重跑训练），才释放 GPU；
- PREPARING 且无容器 → 回退到 QUEUED（可重新准备），释放 GPU；
- 容器仍在但缺执行记录 → 按固定容器名重建执行记录；
- 已终态 Run 的遗留容器 → 按 `hydrolab.run_id` label 清理。

关键约束：**过期心跳不等于容器已停止**，GPU 只允许在「容器确认为结束」后释放
（见运行时注释）。对账器仅在 recover 抛出 not-found 时断言容器已结束并释放租约。
"""

from __future__ import annotations

import logging
from contextlib import suppress
from typing import Any, Protocol
from uuid import UUID

from hydrolab.domain.entities import utcnow
from hydrolab.execution.entities import RunExecution
from hydrolab.experiments.enums import RunStatus
from hydrolab.experiments.errors import StaleStateError


class RecoveryRunStore(Protocol):
    async def list_active(self) -> list[Any]: ...
    async def get(self, run_id: UUID) -> Any | None: ...
    async def save(self, item: Any, expected_status: Any = None) -> None: ...


class RecoveryExecutions(Protocol):
    async def get(self, run_id: UUID) -> Any | None: ...
    async def add(self, item: Any) -> None: ...


class RecoveryLeases(Protocol):
    async def list_by_run(self, run_id: UUID) -> list[Any]: ...
    async def release_run(self, run_id: UUID) -> None: ...


class RecoveryExecutor(Protocol):
    async def recover(self, run_id: UUID) -> Any: ...
    async def cleanup(self, external_id: str) -> None: ...
    async def list_labeled_containers(self) -> list[tuple[UUID, str]]: ...


class _NotFound:
    pass


def _default_not_found() -> tuple[type[BaseException], ...]:
    try:
        from docker.errors import NotFound

        return (NotFound,)
    except Exception:  # pragma: no cover - docker 可选依赖
        return (Exception,)


class RecoveryReconciler:
    _TERMINAL = (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED)

    def __init__(
        self,
        runs: RecoveryRunStore,
        executions: RecoveryExecutions,
        leases: RecoveryLeases,
        executor: RecoveryExecutor,
        *,
        default_timeout_seconds: int = 6 * 3600,
        not_found_exc: tuple[type[BaseException], ...] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._runs, self._executions, self._leases, self._executor = runs, executions, leases, executor
        self._timeout = default_timeout_seconds
        # not-found 是「容器确认为不存在」的唯一依据。生产装配应显式传入
        # docker.errors.NotFound，避免把 docker daemon 短暂不可达误判为容器已结束。
        self._not_found = not_found_exc if not_found_exc is not None else _default_not_found()
        self._logger = logger or logging.getLogger("hydrolab.reconciler")

    def is_not_found(self, exc: BaseException) -> bool:
        return any(isinstance(exc, cls) for cls in self._not_found)

    async def reconcile_once(self) -> dict[str, int]:
        report = {"failed_orphan": 0, "requeued": 0, "reattached": 0, "cleaned_leftover": 0}
        active = await self._runs.list_active()
        active_ids = {run.id for run in active}
        for run in active:
            try:
                outcome = await self._assess(run)
            except StaleStateError:
                # 并发方已推进/进入终态：收敛到数据库当前状态，跳过。
                continue
            except Exception as exc:
                self._logger.warning("reconcile_assess_failed run=%s type=%s", run.id, type(exc).__name__)
                continue
            if outcome:
                report[outcome] += 1

        # 清理已终态 Run 的遗留容器：列出带 hydrolab.run_id label 的容器，
        # 其 Run 不在活跃集合且已终态/不存在 → cleanup。
        try:
            labeled = await self._executor.list_labeled_containers()
        except Exception as exc:
            self._logger.warning("reconcile_list_containers_failed type=%s", type(exc).__name__)
            labeled = []
        for run_id, external_id in labeled:
            if run_id in active_ids:
                # 容器对应的 Run 仍在活跃执行，交由 _assess/运行中逻辑处理。
                continue
            run = await self._runs.get(run_id)
            if run is None or run.status in self._TERMINAL:
                with suppress(Exception):
                    await self._executor.cleanup(external_id)
                    report["cleaned_leftover"] += 1
        return report

    async def _assess(self, run: Any) -> str | None:
        try:
            handle = await self._executor.recover(run.id)
        except Exception as exc:
            if not self.is_not_found(exc):
                # docker 其它异常（如 daemon 不可达）：不能据此断言容器已结束，跳过。
                self._logger.warning(
                    "reconcile_recover_unknown run=%s type=%s", run.id, type(exc).__name__
                )
                return None
            # 容器确认为不存在。
            if run.status == RunStatus.RUNNING:
                await self._leases.release_run(run.id)
                run.status, run.updated_at = RunStatus.FAILED, utcnow()
                await self._runs.save(run, expected_status=RunStatus.RUNNING)
                self._logger.warning("reconcile_failed_orphan run=%s", run.id)
                return "failed_orphan"
            # PREPARING：准备尚未启动容器，安全回退到 QUEUED 重试。
            await self._leases.release_run(run.id)
            run.status, run.updated_at = RunStatus.QUEUED, utcnow()
            await self._runs.save(run, expected_status=RunStatus.PREPARING)
            self._logger.info("reconcile_requeued run=%s", run.id)
            return "requeued"

        # 容器仍在：确保执行记录存在，并把 PREPARING 推进到 RUNNING。
        if await self._executions.get(run.id) is None:
            leases = await self._leases.list_by_run(run.id)
            await self._executions.add(
                RunExecution(
                    run_id=run.id,
                    external_id=handle.external_id,
                    gpu_indices=[lease.gpu_index for lease in leases],
                    timeout_seconds=self._timeout,
                )
            )
        if run.status == RunStatus.PREPARING:
            run.status, run.updated_at = RunStatus.RUNNING, utcnow()
            await self._runs.save(run, expected_status=RunStatus.PREPARING)
        return "reattached"