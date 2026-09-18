"""B5 Runner 控制面与 B6 观测事件服务。

支持两种执行后端：
- FakeRunExecutor：只推进状态机与事件，不执行真实训练（默认，测试用）；
- SubprocessRunExecutor：物化冻结代码到独立工作目录并真实执行 argv，采集真实产物。
"""

import asyncio
import json
from datetime import timedelta
from pathlib import Path, PurePosixPath
from typing import Any, cast
from uuid import UUID

from hydrolab.adapters.fake.run_executor import FakeRunExecutor
from hydrolab.core.errors import conflict, not_found, validation_error
from hydrolab.domain.entities import utcnow
from hydrolab.execution.collector import ArtifactCollector, CollectionReport
from hydrolab.execution.entities import ResourceSample, RunExecution
from hydrolab.execution.memory import (
    InMemoryExecutions,
    InMemoryGpuLeases,
    InMemoryLogs,
    InMemoryResourceSamples,
    InMemoryRunEvents,
)
from hydrolab.experiments.entities import OutboxEvent, Run
from hydrolab.experiments.enums import RunStatus
from hydrolab.experiments.errors import StaleStateError
from hydrolab.experiments.repositories import ExperimentVersionStore, OutboxStore, RunStore
from hydrolab.ports.dto import (
    EventType,
    ExternalRunRef,
    MetricRecord,
    ObjectRef,
    RunHandle,
    RunSpec,
    RunState,
    TaskEnvelope,
    TrackingContext,
)
from hydrolab.ports.experiment_tracker import ExperimentTracker
from hydrolab.ports.run_executor import RunExecutor
from hydrolab.ports.task_queue import TaskQueue


class RunControlService:
    def __init__(
        self,
        runs: RunStore,
        outbox: OutboxStore,
        leases: InMemoryGpuLeases,
        executions: InMemoryExecutions,
        events: InMemoryRunEvents,
        logs: InMemoryLogs,
        samples: InMemoryResourceSamples,
        queue: TaskQueue,
        executor: RunExecutor,
        tracker: ExperimentTracker | None = None,
        versions: ExperimentVersionStore | None = None,
        code_versions: Any | None = None,
        template_versions: Any | None = None,
        storage: Any | None = None,
        collector: ArtifactCollector | None = None,
        dataset_versions: Any | None = None,
        artifacts: Any | None = None,
        result_service: Any | None = None,
    ) -> None:
        self._runs, self._outbox, self._leases, self._executions = runs, outbox, leases, executions
        self._events, self._logs, self._samples, self._queue, self._executor = events, logs, samples, queue, executor
        self._tracker = tracker
        self._versions = versions
        self._code_versions = code_versions
        self._template_versions = template_versions
        self._storage = storage
        self._collector = collector
        self._dataset_versions = dataset_versions
        self._artifacts = artifacts
        self._result_service = result_service
        self._reports: dict[UUID, CollectionReport] = {}
        self._tracking_refs: dict[UUID, ExternalRunRef] = {}

    @property
    def is_real_executor(self) -> bool:
        """True 表示当前后端会真实执行训练进程（Fake 显式标记 False）。"""
        return bool(getattr(self._executor, "real_executor", False))

    def collection_report(self, run_id: UUID) -> CollectionReport | None:
        return self._reports.get(run_id)

    async def dispatch_pending(self) -> int:
        count = 0
        for event in await self._outbox.claim_pending(limit=1):
            if event.topic not in ("run.requested", "run.cancel_requested"):
                await self._outbox.reset_pending(event.id, event.published_at)
                continue
            try:
                async with asyncio.timeout(30):
                    await self._queue.enqueue(TaskEnvelope(
                        job_id=event.id,
                        job_type="run.cancel" if event.topic == "run.cancel_requested" else "run.execute",
                        resource_id=event.aggregate_id,
                        payload=event.payload,
                    ))
            except Exception:
                await self._outbox.reset_pending(event.id, event.published_at)
                raise
            await self._outbox.mark_published(event.id, utcnow(), event.published_at)
            count += 1
        return count

    async def start(self, run_id: UUID, gpu_count: int = 1) -> Run:
        run = await self._get_run(run_id)
        if getattr(self._executor, "remote_executor", False):
            if run.status != RunStatus.QUEUED:
                raise conflict("仅 QUEUED Run 可调度")
            # Submission already created a durable run.requested event.
            return run
        if run.status != RunStatus.QUEUED:
            raise conflict("仅 QUEUED Run 可启动", {"status": run.status.value})
        leases = await self._leases.acquire(run_id, gpu_count, utcnow() + timedelta(minutes=2))
        if not leases:
            raise conflict("当前没有足够的可用 GPU")
        run.status, run.updated_at = RunStatus.PREPARING, utcnow()
        await self._runs.save(run, expected_status=RunStatus.QUEUED)
        await self._event(EventType.STATUS_CHANGED, run_id, {"status": run.status.value})
        try:
            spec = await self._build_spec(run, gpu_count)
            # lease 是 GPU 分配的唯一事实来源；SubprocessRunExecutor 会将 env 原样
            # 传给子进程，因此 CUDA_VISIBLE_DEVICES 可确保双 Run 分别落在 GPU 0/1。
            spec.env["CUDA_VISIBLE_DEVICES"] = ",".join(str(lease.gpu_index) for lease in leases)
            spec.env["HYDROLAB_GPU_INDICES"] = spec.env["CUDA_VISIBLE_DEVICES"]
            spec.gpu_indices = [lease.gpu_index for lease in leases]
        except Exception:
            await self._leases.release_run(run_id)
            run.status, run.updated_at = RunStatus.FAILED, utcnow()
            await self._runs.save(run, expected_status=RunStatus.PREPARING)
            await self._event(EventType.FAILED, run_id, {"status": run.status.value, "stage": "PREPARING"})
            raise
        try:
            handle = await self._executor.start(spec)
        except Exception:
            await self._leases.release_run(run_id)
            run.status = RunStatus.FAILED
            await self._runs.save(run, expected_status=RunStatus.PREPARING)
            raise
        await self._executions.add(
            RunExecution(
                run_id=run_id,
                external_id=handle.external_id,
                gpu_indices=[x.gpu_index for x in leases],
                timeout_seconds=spec.timeout_seconds,
            )
        )
        run.status, run.updated_at = RunStatus.RUNNING, utcnow()
        await self._runs.save(run, expected_status=RunStatus.PREPARING)
        await self._event(
            EventType.STATUS_CHANGED, run_id, {"status": run.status.value, "gpu_indices": [x.gpu_index for x in leases]}
        )
        await self._logs.append(
            run_id,
            f"{'Subprocess' if self.is_real_executor else 'Fake'} runner started: {' '.join(spec.argv)}\n",
        )
        await self._track_start(run, spec, [x.gpu_index for x in leases])
        return run

    async def _track_start(self, run: Run, spec: RunSpec, gpu_indices: list[int]) -> None:
        """在外部跟踪系统登记 Run（失败不反向覆盖业务 Run 状态，可重放）。"""
        if self._tracker is None:
            return
        try:
            ref = await self._tracker.start_run(
                TrackingContext(
                    run_id=run.id,
                    experiment_version_id=run.experiment_version_id,
                    display_name=self._experiment_name(run),
                    tags={
                        "hydrolab.run.status": run.status.value,
                        "hydrolab.gpu_indices": ",".join(str(i) for i in gpu_indices),
                    },
                )
            )
            self._tracking_refs[run.id] = ref
            await self._tracker.log_parameters(
                ref,
                {"argv": " ".join(spec.argv), "image_digest": spec.image_digest, **spec.env},
            )
        except Exception as exc:
            await self._logs.append(
                run.id, f"[tracker] 登记失败（不影响业务状态）: {exc.__class__.__name__}\n"
            )

    async def _build_spec(self, run: Run, gpu_count: int) -> RunSpec:
        """从冻结 ExperimentVersion 解析真实执行规格。

        Fake 后端保留原有占位命令以兼容既有测试；真实后端必须解析出可执行 argv，
        并把冻结代码物化到独立工作目录。
        """
        if not self.is_real_executor:
            return RunSpec(
                run_id=run.id, argv=["python", "train.py"], image_digest="fake@sha256:hydrolab", gpu_count=gpu_count
            )
        if self._versions is None or self._code_versions is None:
            raise validation_error("真实 Runner 需要注入实验版本与代码版本仓储")
        version = await self._versions.get(run.experiment_version_id)
        if version is None:
            raise conflict("Run 对应的实验版本不存在")
        config = version.resolved_config
        argv = list(config.get("argv") or [])
        if not argv:
            raise validation_error("冻结配置缺少可执行 argv")

        code_version_id = config.get("code_version_id")
        code = await self._code_versions.get(UUID(str(code_version_id))) if code_version_id else None
        if code is None or not code.object_key:
            raise conflict("冻结代码版本缺少对象内容，无法物化执行")

        archive = await self._read_object(code.object_key)
        dataset_version_id = config.get("dataset_version_id")
        dataset_files = await self._materialize_dataset(dataset_version_id)
        workspace = self._executor.prepare_workspace(  # type: ignore[attr-defined]
            run.id, archive, dataset_files
        )

        argv = self._render_argv(argv, config.get("parameters") or {}, run, self._process_output_dir(workspace))
        image_digest = config.get("environment_image_digest")
        if getattr(self._executor, "requires_image_digest", False) and not image_digest:
            raise validation_error("Docker Runner 要求环境版本提供不可变 image_digest")
        await self._event(
            EventType.STAGE_CHANGED,
            run.id,
            {
                "stage": "PREPARING",
                "workspace": str(workspace),
                "argv": argv,
                "dataset_version_id": str(dataset_version_id) if dataset_version_id else None,
                "dataset_file_count": len(dataset_files) if dataset_files else 0,
            },
        )
        return RunSpec(
            run_id=run.id,
            argv=argv,
            image_digest=str(
                image_digest
                or config.get("environment_content_hash")
                or "local:subprocess"
            ),
            gpu_count=0 if gpu_count is None else gpu_count,
            env={"HYDROLAB_EXPERIMENT": self._experiment_name(run)},
            read_only_mounts=[str(workspace / "code")],
            writable_mount=str(workspace / "output"),
            timeout_seconds=getattr(self._executor, "_default_timeout", 6 * 3600),
        )

    @staticmethod
    def _experiment_name(run: Run) -> str:
        return f"hydrolab_{run.id.hex[:12]}"

    def _process_output_dir(self, workspace: object) -> str:
        """返回训练进程可写输出目录的进程内路径。

        Docker 容器内固定为 /workspace/output（宿主机目录已作为 rw 挂载）；
        subprocess 直接指向宿主机工作区的 output。训练脚本必须写这里，
        代码挂载保持只读。
        """
        if getattr(self._executor, "requires_image_digest", False):
            return "/workspace/output"
        return str(Path(workspace) / "output")

    def _render_argv(
        self, argv: list[str], parameters: dict[str, Any], run: Run, output_dir: str = "/workspace/output"
    ) -> list[str]:
        """渲染 argv 占位符：{run_name}/{run_id}/{OUTPUT_DIR} 与冻结参数 {key}。"""
        context: dict[str, str] = {
            "run_id": str(run.id),
            "run_name": self._experiment_name(run),
            "experiment": self._experiment_name(run),
            "OUTPUT_DIR": output_dir,
        }
        for key, value in parameters.items():
            context[str(key)] = "" if value is None else str(value)
        rendered: list[str] = []
        for token in argv:
            text = str(token)
            for key, value in context.items():
                text = text.replace("{" + key + "}", value)
            rendered.append(text)
        return rendered

    async def _materialize_dataset(self, dataset_version_id: Any) -> dict[str, bytes] | None:
        """把冻结数据集版本的内容取回为 {相对路径: 字节}。

        返回 None 表示未选定数据版本或缺少仓储注入，此时 Runner 回落到
        全局 DATA_ROOT 兼容路径。选定了数据版本就必须能取到内容，
        取不到宁可让 Run 失败，也不能静默跑到别的数据上——那会产出
        无法追溯的结果。

        BUNDLE 格式按 zip 内原始相对路径展开；单文件格式直接落为同名文件。
        """
        if not dataset_version_id:
            return None
        if self._dataset_versions is None or self._artifacts is None:
            return None
        version = await self._dataset_versions.get(UUID(str(dataset_version_id)))
        if version is None:
            raise conflict("Run 选定的数据集版本不存在", {"dataset_version_id": str(dataset_version_id)})

        manifest = version.manifest or {}
        artifact_id = manifest.get("artifact_id")
        if not artifact_id:
            raise conflict("数据集版本缺少源文件登记，无法物化")
        artifact = await self._artifacts.get(UUID(str(artifact_id)))
        if artifact is None or not artifact.object_key:
            raise conflict("数据集源文件缺少对象内容，无法物化")

        payload = await self._read_object(artifact.object_key)
        if str(manifest.get("format") or "").upper() == "BUNDLE":
            return self._expand_bundle(payload)

        # 单文件：保留原始文件名，使训练代码的 datasets/<name> 相对路径生效
        filename = PurePosixPath(artifact.object_key).name
        return {filename: payload}

    @staticmethod
    def _expand_bundle(payload: bytes) -> dict[str, bytes]:
        """展开数据包 zip；导入期已校验过安全性，此处再做一次纵深防御。"""
        import io
        import zipfile

        files: dict[str, bytes] = {}
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                name = info.filename
                if name.startswith("/") or ".." in PurePosixPath(name).parts:
                    raise validation_error("数据包含非法路径", {"path": name})
                files[name] = archive.read(info)
        if not files:
            raise conflict("数据集版本内容为空，无法物化")
        return files

    async def _read_object(self, key: str) -> bytes:
        if self._storage is None:
            raise validation_error("真实 Runner 需要注入对象存储")
        root = getattr(self._storage, "_root", None)
        if root is not None:
            path = Path(root) / key
            if path.is_file():
                return path.read_bytes()
        objects = getattr(self._storage, "objects", None)
        if isinstance(objects, dict) and key in objects:
            payload = objects[key]
            return payload if isinstance(payload, bytes) else bytes(payload)
        stream = await self._storage.open_range(ObjectRef(key=key), 0)
        try:
            return stream.read()
        finally:
            stream.close()

    async def await_completion(
        self, run_id: UUID, timeout: float | None = None  # noqa: ASYNC109 - orchestration timeout API
    ) -> Run:
        """等待真实执行结束，随后采集产物并落地结果。"""
        run = await self._get_run(run_id)
        execution = await self._executions.get(run_id)
        if execution is None:
            return run
        waiter = getattr(self._executor, "wait", None)
        if waiter is None:
            return run
        snapshot = await waiter(execution.external_id, timeout)
        if snapshot.state in (RunState.RUNNING, RunState.PREPARING, RunState.CANCELLING):
            return run  # 仍在执行，调用方可再次等待
        return await self.finalize(run_id, snapshot.exit_code if snapshot.exit_code is not None else 1)

    async def finalize(self, run_id: UUID, exit_code: int) -> Run:
        """真实执行结束后的收尾：采集产物、释放租约、发出终态事件。"""
        if getattr(self._executor, "remote_executor", False):
            raise conflict("仅 Worker 可确认训练终态")
        run = await self._get_run(run_id)
        report: CollectionReport | None = None
        if run.status in (RunStatus.CANCELLED, RunStatus.SUCCEEDED, RunStatus.FAILED):
            return run
        if exit_code == 0 and self._collector is not None and self.is_real_executor:
            workspace = self._executor.workspace_for(run_id)  # type: ignore[attr-defined]
            report = await asyncio.to_thread(
                self._collector.collect, str(run_id), [workspace / "output", workspace / "code"]
            )
            self._reports[run_id] = report
            for warning in report.warnings[:20]:
                await self._logs.append(run_id, f"[collector] {warning}\n")
            for artifact in report.artifacts + report.configs + report.checkpoints:
                await self._event(
                    EventType.ARTIFACT_CREATED,
                    run_id,
                    {
                        "kind": artifact.kind,
                        "object_key": artifact.object_key,
                        "sha256": artifact.sha256,
                        "relative_path": artifact.relative_path,
                        "size_bytes": artifact.size_bytes,
                    },
                )
            for metric in report.metrics:
                await self._event(
                    EventType.METRIC_REPORTED,
                    run_id,
                    {"name": metric.name, "value": metric.value, "step": metric.horizon},
                )
            await self._logs.append(
                run_id,
                json.dumps(
                    {
                        "collected_metrics": len(report.metrics),
                        "collected_artifacts": len(report.artifacts),
                        "collected_checkpoints": len(report.checkpoints),
                    },
                    ensure_ascii=False,
                )
                + "\n",
            )
            if self._result_service is not None:
                persisted = await self._result_service.ingest_collection(run_id, report)
                await self._logs.append(
                    run_id,
                    json.dumps(
                        {
                            "persisted_metrics": persisted["metrics_total"],
                            "persisted_artifacts": persisted["artifacts_total"],
                        },
                        ensure_ascii=False,
                    )
                    + "\n",
                )

        run.status, run.updated_at = (RunStatus.SUCCEEDED if exit_code == 0 else RunStatus.FAILED), utcnow()
        try:
            await self._runs.save(run, expected_status=[RunStatus.RUNNING, RunStatus.PREPARING])
        except StaleStateError:
            # 并发方已把 Run 推进/收敛到其它状态；终态不得被覆盖。
            fresh = await self._get_run(run_id)
            await self._leases.release_run(run_id)
            await self._executions.remove(run_id)
            return fresh
        await self._leases.release_run(run_id)
        await self._executions.remove(run_id)
        await self._event(
            EventType.COMPLETED if exit_code == 0 else EventType.FAILED,
            run_id,
            {
                "status": run.status.value,
                "exit_code": exit_code,
                "metrics_collected": 0 if report is None else len(report.metrics),
            },
        )
        await self._track_finish(run_id, run.status.value, None if report is None else report.metrics)
        return run

    async def _track_finish(
        self, run_id: UUID, status: str, metrics: list[Any] | None = None
    ) -> None:
        """把指标与终态同步到外部跟踪系统；失败不反向覆盖业务 Run 状态。"""
        if self._tracker is None:
            return
        ref = self._tracking_refs.get(run_id)
        if ref is None:
            return
        try:
            if metrics:
                await self._tracker.log_metrics(
                    ref,
                    [
                        MetricRecord(name=m.name, value=m.value, step=m.horizon)
                        for m in metrics
                    ],
                )
            await self._tracker.finish_run(ref, status)
        except Exception as exc:
            await self._logs.append(
                run_id, f"[tracker] 同步终态失败（不影响业务状态）: {exc.__class__.__name__}\n"
            )
            self._tracking_refs.pop(run_id, None)

    async def cancel(self, run_id: UUID) -> Run:
        run = await self._get_run(run_id)
        if run.status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED):
            return run
        if getattr(self._executor, "remote_executor", False):
            await self._outbox.add(OutboxEvent(
                aggregate_type="run", aggregate_id=run_id, topic="run.cancel_requested", payload={},
            ))
            return run
        execution = await self._executions.get(run_id)
        if execution:
            await self._executor.cancel(
                RunHandle(run_id=run_id, external_id=execution.external_id, state=RunState.RUNNING)
            )
        run.status, run.updated_at = RunStatus.CANCELLED, utcnow()
        try:
            await self._runs.save(run)
        except StaleStateError:
            # 并发已完成/已取消：以数据库当前状态收敛，终态不被覆盖。
            fresh = await self._get_run(run_id)
            await self._leases.release_run(run_id)
            await self._executions.remove(run_id)
            return fresh
        await self._leases.release_run(run_id)
        await self._executions.remove(run_id)
        await self._event(EventType.STATUS_CHANGED, run_id, {"status": run.status.value})
        return run

    async def complete_fake(self, run_id: UUID, exit_code: int = 0) -> Run:
        if getattr(self._executor, "remote_executor", False):
            raise conflict("仅 Worker 可确认训练终态")
        run = await self._get_run(run_id)
        execution = await self._executions.get(run_id)
        if execution is None:
            raise conflict("Run 未在执行")
        # 此入口仅由 Fake Runner 的测试/内部接口调用；运行时显式收窄。
        fake_executor = cast(FakeRunExecutor, self._executor)
        fake_executor.complete(execution.external_id, exit_code)
        run.status, run.updated_at = (RunStatus.SUCCEEDED if exit_code == 0 else RunStatus.FAILED), utcnow()
        await self._leases.release_run(run_id)
        await self._executions.remove(run_id)
        await self._event(
            EventType.COMPLETED if exit_code == 0 else EventType.FAILED,
            run_id,
            {"status": run.status.value, "exit_code": exit_code},
        )
        return run

    async def report_progress(
        self, run_id: UUID, percent: float, stage: str = "TRAINING", eta_seconds: int | None = None
    ) -> None:
        await self._event(
            EventType.PROGRESS_UPDATED, run_id, {"percent": percent, "stage": stage, "eta_seconds": eta_seconds}
        )

    async def report_metric(self, run_id: UUID, name: str, value: float, step: int | None = None) -> None:
        await self._event(EventType.METRIC_REPORTED, run_id, {"name": name, "value": value, "step": step})

    async def report_resource(
        self, run_id: UUID, gpu_index: int, utilization_percent: float, memory_used_mb: int, memory_total_mb: int
    ) -> None:
        await self._samples.add(
            ResourceSample(
                run_id=run_id,
                gpu_index=gpu_index,
                utilization_percent=utilization_percent,
                memory_used_mb=memory_used_mb,
                memory_total_mb=memory_total_mb,
            )
        )
        await self._event(
            EventType.RESOURCE_SAMPLED,
            run_id,
            {"gpu_index": gpu_index, "utilization_percent": utilization_percent, "memory_used_mb": memory_used_mb},
        )

    async def _get_run(self, run_id: UUID) -> Run:
        run = await self._runs.get(run_id)
        if run is None:
            raise not_found("Run 不存在")
        return run

    async def _event(self, event_type: EventType, run_id: UUID, payload: dict[str, object]) -> None:
        await self._events.append(event_type, run_id, payload)
