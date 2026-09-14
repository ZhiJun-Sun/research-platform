"""依赖装配：按 Settings 选择端口实现。

真实实现（S3/Celery/MLflow/Docker)在对应后端被选中时按需 import，
未选中的 SDK 不会被加载，保证核心包轻量、无外部依赖时仍可运行。
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
from hydrolab.core.errors import validation_error
from hydrolab.core.settings import Settings, get_settings
from hydrolab.ports import ExperimentTracker, ObjectStorage, RunExecutor, TaskQueue


@lru_cache
def get_object_storage() -> ObjectStorage:
    settings: Settings = get_settings()
    if settings.object_storage_backend == "fake":
        return FakeObjectStorage()
    if settings.object_storage_backend == "local":
        return LocalFilesystemObjectStorage(settings.local_storage_root)
    if settings.object_storage_backend == "s3":
        from hydrolab.adapters.s3 import S3ObjectStorageAdapter

        if not settings.s3_endpoint:
            raise validation_error("s3 后端已启用但 HYDROLAB_S3_ENDPOINT 未配置")
        return S3ObjectStorageAdapter(
            endpoint=settings.s3_endpoint,
            bucket=settings.s3_bucket,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
            addressing_style=settings.s3_addressing_style,
        )
    raise validation_error("未知 object_storage_backend", {"backend": settings.object_storage_backend})


@lru_cache
def get_task_queue() -> TaskQueue:
    settings = get_settings()
    if settings.task_queue_backend == "fake":
        return FakeTaskQueue()
    if settings.task_queue_backend == "celery":
        from hydrolab.adapters.celery import CeleryTaskQueueAdapter

        if not settings.redis_url:
            raise validation_error("celery 后端已启用但 HYDROLAB_REDIS_URL 未配置")
        return CeleryTaskQueueAdapter(broker_url=settings.redis_url)
    raise validation_error("未知 task_queue_backend", {"backend": settings.task_queue_backend})


@lru_cache
def get_experiment_tracker() -> ExperimentTracker:
    settings = get_settings()
    if settings.experiment_tracker_backend == "fake":
        return FakeExperimentTracker()
    if settings.experiment_tracker_backend == "noop":
        return NoopExperimentTracker()
    if settings.experiment_tracker_backend == "mlflow":
        from hydrolab.adapters.mlflow import MlflowTrackingAdapter

        if not settings.mlflow_tracking_uri:
            raise validation_error("mlflow 后端已启用但 HYDROLAB_MLFLOW_TRACKING_URI 未配置")
        return MlflowTrackingAdapter(tracking_uri=settings.mlflow_tracking_uri)
    raise validation_error(
        "未知 experiment_tracker_backend", {"backend": settings.experiment_tracker_backend}
    )


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
    if settings.run_executor_backend == "docker":
        from hydrolab.adapters.remote_executor import RemoteRunExecutor

        if not settings.runner_image_whitelist:
            raise validation_error(
                "docker 后端已启用但未配置镜像白名单 HYDROLAB_RUNNER_IMAGE_WHITELIST"
            )
        return RemoteRunExecutor()
    raise validation_error("未知 run_executor_backend", {"backend": settings.run_executor_backend})
