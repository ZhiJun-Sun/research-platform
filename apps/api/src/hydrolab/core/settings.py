"""应用配置。

规则（见 plans/03-backend-implementation-roadmap.md 第 3 节）：
- 全部通过环境变量注入，前缀 ``HYDROLAB_``；
- 后端实现通过枚举开关选择：fake / local / 真实服务；
- 生产环境禁止默认密钥，启动时强校验；
- 未启用真实后端时，对应配置允许为空，不阻塞代码优先开发。
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ObjectStorageBackend = Literal["fake", "local", "s3"]
TaskQueueBackend = Literal["fake", "celery"]
ExperimentTrackerBackend = Literal["fake", "noop", "mlflow"]
RunExecutorBackend = Literal["fake", "subprocess", "docker"]
Environment = Literal["local", "test", "staging", "production"]
DatabaseBackend = Literal["memory", "mysql"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HYDROLAB_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Environment = "local"
    public_base_url: str = "http://127.0.0.1:8000"
    cors_origins: list[str] = ["http://127.0.0.1:5173", "http://localhost:5173"]

    # --- 安全 ---
    auth_secret: str = "dev-only-insecure-secret"
    cookie_domain: str | None = None
    runner_signing_key: str = "dev-only-runner-key"

    # --- 首个管理员 bootstrap（仅系统无用户时生效一次） ---
    # local/test 下未显式配置时使用文档化的开发默认值，便于无数据库联调；
    # production 必须显式配置且禁止默认值。
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: str | None = None
    bootstrap_admin_name: str = "平台管理员"

    # --- 基础设施连接（未启用真实后端时可为空） ---
    # 默认 database_backend=memory：进程内仓储，无数据库也可开发/测试，绝不连接外部库。
    # 真实数据库需通过环境变量 HYDROLAB_DATABASE_BACKEND=mysql + HYDROLAB_DATABASE_URL 显式启用。
    # 禁止在源码中写死远程地址/账号/密码；凭证只从环境变量注入。
    database_backend: DatabaseBackend = "memory"
    database_url: str | None = None
    redis_url: str | None = None
    mlflow_tracking_uri: str | None = None

    # --- S3-compatible object storage ---
    s3_endpoint: str | None = None
    s3_region: str = "us-east-1"
    s3_bucket: str = "hydrolab"
    s3_access_key: str | None = None
    s3_secret_key: str | None = None
    s3_addressing_style: Literal["virtual", "path"] = "virtual"

    # --- 后端实现选择 ---
    object_storage_backend: ObjectStorageBackend = "fake"
    task_queue_backend: TaskQueueBackend = "fake"
    experiment_tracker_backend: ExperimentTrackerBackend = "fake"
    run_executor_backend: RunExecutorBackend = "fake"

    # --- local 后端根目录 ---
    local_storage_root: Path = Path(".hydrolab-data/objects")

    # --- 本地目录代码导入白名单 ---
    # 只有位于这些根目录之内的路径可被导入为 CodeVersion，防止任意主机路径外泄。
    code_import_roots: list[Path] = []

    # --- subprocess Runner（本机真实执行，无 Docker/GPU 时的可用实现） ---
    # 运行工作区根目录：每个 Run 在其下获得独立目录（code/ output/）。
    runner_workspace_root: Path = Path(".hydrolab-data/runs")
    # 解释器：默认使用当前 Python；生产建议显式指向环境版本对应的解释器。
    runner_python_executable: str | None = None
    # 只读数据根：Runner 会把它软链/映射到工作目录，供代码以相对路径访问。
    runner_data_root: Path | None = None
    runner_default_timeout_seconds: int = 6 * 3600

    # --- Docker GPU Runner（RUN_EXECUTOR_BACKEND=docker 时生效） ---
    # 镜像 digest 白名单；生产禁止通配符。空列表表示关闭真实镜像准入（不安全）。
    runner_image_whitelist: list[str] = Field(default_factory=list)
    # 容器默认禁网；按需放开。
    runner_allow_network: bool = False
    # 容器内受控解释器。
    runner_container_python: str = "/usr/local/bin/python"

    # --- 配额 ---
    storage_quota_bytes: int = 500 * 1024**3
    storage_low_watermark_bytes: int = 50 * 1024**3

    @field_validator("auth_secret", "runner_signing_key")
    @classmethod
    def _no_default_secret_in_production(cls, value: str, info) -> str:  # type: ignore[no-untyped-def]
        # 生产环境强校验在 validate_production 中统一执行；
        # 此处仅保证字段存在，避免分散校验逻辑。
        return value

    def validate_production(self) -> None:
        """生产启动前调用：禁止默认密钥和缺失的真实服务配置。"""
        if self.environment != "production":
            return
        problems: list[str] = []
        if self.auth_secret.startswith("dev-only"):
            problems.append("HYDROLAB_AUTH_SECRET 仍为默认值")
        if self.runner_signing_key.startswith("dev-only"):
            problems.append("HYDROLAB_RUNNER_SIGNING_KEY 仍为默认值")
        if not self.database_url:
            problems.append("HYDROLAB_DATABASE_URL 未配置")
        if self.object_storage_backend == "s3" and not self.s3_endpoint:
            problems.append("S3 后端已启用但 HYDROLAB_S3_ENDPOINT 未配置")
        if self.task_queue_backend == "celery" and not self.redis_url:
            problems.append("Celery 后端已启用但 HYDROLAB_REDIS_URL 未配置")
        if self.experiment_tracker_backend == "mlflow" and not self.mlflow_tracking_uri:
            problems.append("MLflow 后端已启用但 HYDROLAB_MLFLOW_TRACKING_URI 未配置")
        if self.run_executor_backend == "subprocess":
            problems.append("subprocess Runner 缺少容器隔离，禁止在生产环境启用")
        if self.run_executor_backend == "docker" and not self.runner_image_whitelist:
            problems.append("Docker Runner 必须配置非空镜像白名单 HYDROLAB_RUNNER_IMAGE_WHITELIST")
        if self.run_executor_backend == "docker" and (
            self.database_backend != "mysql" or self.task_queue_backend != "celery"
        ):
            problems.append("独立 Docker Worker 要求 MySQL 与 Celery 后端")
        if not self.bootstrap_admin_email or not self.bootstrap_admin_password:
            problems.append("生产环境必须显式配置 BOOTSTRAP_ADMIN_EMAIL/PASSWORD")
        if problems:
            raise RuntimeError("生产配置校验失败: " + "; ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()
