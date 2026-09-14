"""配置装配测试（plans/06 P0）。

验证：memory/fake 为安全默认；显式配置 mysql/celery/mlflow/docker 时选择正确 Adapter；
缺配置时报稳定错误且不泄露 Secret。
注意：get_settings() 是 lru_cache，测试须在清理缓存后再构造。
"""

from __future__ import annotations

import importlib

import pytest

from hydrolab.adapters.celery import CeleryTaskQueueAdapter
from hydrolab.adapters.fake import FakeRunExecutor
from hydrolab.adapters.local import LocalFilesystemObjectStorage
from hydrolab.adapters.mlflow import MlflowTrackingAdapter
from hydrolab.adapters.s3 import S3ObjectStorageAdapter
from hydrolab.api import deps
from hydrolab.core.errors import AppError
from hydrolab.core.settings import get_settings


def _apply(env: dict[str, str]) -> None:
    import os

    for k, v in env.items():
        os.environ[k] = v
    get_settings.cache_clear()
    imports = importlib.import_module("hydrolab.api.deps")
    for name in ("get_object_storage", "get_task_queue", "get_experiment_tracker", "get_run_executor"):
        getattr(imports, name).cache_clear()


def _clear() -> None:
    import os

    for k in list(os.environ.keys()):
        if k.startswith("HYDROLAB_OBJECT") or k.startswith("HYDROLAB_TASK") \
           or k.startswith("HYDROLAB_EXPERIMENT") or k.startswith("HYDROLAB_RUN") \
           or k.startswith("HYDROLAB_S3") or k.startswith("HYDROLAB_REDIS") \
           or k.startswith("HYDROLAB_MLFLOW") or k.startswith("HYDROLAB_DATABASE"):
            os.environ.pop(k, None)
    get_settings.cache_clear()


def test_default_backend_is_memory_fake() -> None:
    """安全默认：不连外部库、全 Fake Adapter。"""
    import os

    _clear()
    os.environ["HYDROLAB_ENVIRONMENT"] = "test"
    settings = get_settings()
    assert settings.database_backend == "memory"
    assert settings.database_url is None  # 不含已硬编码的远程凭据
    assert settings.object_storage_backend == "fake"
    assert settings.task_queue_backend == "fake"
    assert settings.run_executor_backend == "fake"
    _clear()


def test_source_contains_no_secret() -> None:
    """源码里不得出现远程地址/密码。"""
    import os

    with open(os.path.join(os.path.dirname(__file__), "..", "src", "hydrolab", "core", "settings.py")) as f:
        content = f.read()
    assert "10.196.83.122" not in content
    assert "bambooRain" not in content
    # 不得出现真实 DSN 形态（asyncmy://user:pass@...）；local_storage_root 等变量名不算。
    assert "mysql+asyncmy://" not in content
    assert "asyncmy://root:" not in content


def test_s3_requires_endpoint() -> None:
    _clear()
    _apply({"HYDROLAB_OBJECT_STORAGE_BACKEND": "s3"})
    with pytest.raises(AppError):
        deps.get_object_storage()
    _clear()


def test_s3_selects_adapter_when_configured() -> None:
    _clear()
    _apply(
        {
            "HYDROLAB_OBJECT_STORAGE_BACKEND": "s3",
            "HYDROLAB_S3_ENDPOINT": "http://minio:9000",
            "HYDROLAB_S3_ACCESS_KEY": "ak",
            "HYDROLAB_S3_SECRET_KEY": "sk",
        }
    )
    assert isinstance(deps.get_object_storage(), S3ObjectStorageAdapter)
    _clear()


def test_local_storage_selects_local_adapter(tmp_path) -> None:
    _clear()
    _apply({"HYDROLAB_OBJECT_STORAGE_BACKEND": "local", "HYDROLAB_LOCAL_STORAGE_ROOT": str(tmp_path)})
    assert isinstance(deps.get_object_storage(), LocalFilesystemObjectStorage)
    _clear()


def test_celery_requires_redis() -> None:
    _clear()
    _apply({"HYDROLAB_TASK_QUEUE_BACKEND": "celery"})
    with pytest.raises(AppError):
        deps.get_task_queue()
    _clear()


def test_celery_selects_adapter_when_configured() -> None:
    _clear()
    _apply({"HYDROLAB_TASK_QUEUE_BACKEND": "celery", "HYDROLAB_REDIS_URL": "redis://x:6379/0"})
    assert isinstance(deps.get_task_queue(), CeleryTaskQueueAdapter)
    _clear()


def test_mlflow_requires_uri() -> None:
    _clear()
    _apply({"HYDROLAB_EXPERIMENT_TRACKER_BACKEND": "mlflow"})
    with pytest.raises(AppError):
        deps.get_experiment_tracker()
    _clear()


def test_mlflow_selects_adapter_when_configured() -> None:
    _clear()
    _apply({"HYDROLAB_EXPERIMENT_TRACKER_BACKEND": "mlflow", "HYDROLAB_MLFLOW_TRACKING_URI": "http://mlflow:5000"})
    assert isinstance(deps.get_experiment_tracker(), MlflowTrackingAdapter)
    _clear()


def test_docker_requires_image_whitelist() -> None:
    _clear()
    _apply({"HYDROLAB_RUN_EXECUTOR_BACKEND": "docker"})
    with pytest.raises(AppError):
        deps.get_run_executor()
    _clear()


def test_docker_selects_adapter_when_configured() -> None:
    _clear()
    _apply({"HYDROLAB_RUN_EXECUTOR_BACKEND": "docker", "HYDROLAB_RUNNER_IMAGE_WHITELIST": '["x@sha256:abc"]'})
    from hydrolab.adapters.remote_executor import RemoteRunExecutor

    assert isinstance(deps.get_run_executor(), RemoteRunExecutor)
    _clear()


def test_fake_run_executor_default() -> None:
    _clear()
    _apply({"HYDROLAB_RUN_EXECUTOR_BACKEND": "fake"})
    assert isinstance(deps.get_run_executor(), FakeRunExecutor)
    _clear()


def test_error_does_not_leak_secret() -> None:
    """缺配置报错信息不得包含端点地址或 Secret。"""
    _clear()
    _apply({"HYDROLAB_OBJECT_STORAGE_BACKEND": "s3", "HYDROLAB_S3_SECRET_KEY": "super-secret"})
    with pytest.raises(AppError) as exc:
        deps.get_object_storage()
    assert "super-secret" not in str(exc.value)
    _clear()
