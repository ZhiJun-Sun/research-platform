"""依赖装配：按 Settings 选择端口实现。

真实实现（S3/Celery/MLflow/Docker）尚未通过对应 Spike 前，
选择它们会得到明确的 DEPENDENCY_UNAVAILABLE 错误，而不是隐式失败。
"""

from functools import lru_cache

from hydrolab.adapters.fake import (
    FakeExperimentTracker,
    FakeObjectStorage,
    FakeRunExecutor,
    FakeTaskQueue,
    NoopExperimentTracker,
)
from hydrolab.adapters.local import LocalFilesystemObjectStorage
from hydrolab.adapters.local.run_executor import SubprocessRunExecutor
from hydrolab.core.errors import dependency_unavailable
from hydrolab.core.settings import Settings, get_settings
from hydrolab.ports import ExperimentTracker, ObjectStorage, RunExecutor, TaskQueue


def _pending(name: str, spike: str) -> Exception:
    return dependency_unavailable(
        f"{name} 真实适配器尚未实现，需先通过 {spike} 准入门禁（见 plans/05）"
    )


@lru_cache
def get_object_storage() -> ObjectStorage:
    settings: Settings = get_settings()
    if settings.object_storage_backend == "fake":
        return FakeObjectStorage()
    if settings.object_storage_backend == "local":
        return LocalFilesystemObjectStorage(settings.local_storage_root)
    raise _pending("S3ObjectStorageAdapter", "S3-01")


@lru_cache
def get_task_queue() -> TaskQueue:
    settings = get_settings()
    if settings.task_queue_backend == "fake":
        return FakeTaskQueue()
    raise _pending("CeleryTaskQueueAdapter", "QUEUE-01")


@lru_cache
def get_experiment_tracker() -> ExperimentTracker:
    settings = get_settings()
    if settings.experiment_tracker_backend == "fake":
        return FakeExperimentTracker()
    if settings.experiment_tracker_backend == "noop":
        return NoopExperimentTracker()
    raise _pending("MlflowTrackingAdapter", "TRACK-01")


@lru_cache
def get_run_executor() -> RunExecutor:
    settings = get_settings()
    if settings.run_executor_backend == "fake":
        return FakeRunExecutor()
    if settings.run_executor_backend == "subprocess":
        # 本机真实执行：无容器隔离，仅允许非生产环境（validate_production 已拦截）。
        return SubprocessRunExecutor(
            workspace_root=settings.runner_workspace_root,
            python_executable=settings.runner_python_executable,
            data_root=settings.runner_data_root,
            default_timeout_seconds=settings.runner_default_timeout_seconds,
        )
    raise _pending("DockerGpuRunExecutor", "Runner 安全 Spike")
