"""HydroLab 异步任务 Worker（Celery 消费端）。

职责（plans/02 第 1 节）：run.execute 等异步任务消费。
消费端只接收稳定 ID；Run/Job 配置由注入的 handler 重新读数据库。
幂等：job_id + attempt（见 tasks.py）。

生产：`celery -A hydrolab_worker.tasks:celery_app worker -Q hydrolab`，
由 runtime.execute_run 装配 MySQL/Docker；configure_runtime 仅保留给旧的测试辅助运行时。
"""

from hydrolab_worker.tasks import (
    IdempotencyGuard,
    JobKey,
    WorkerRuntime,
    celery_app,
    configure_runtime,
)

__all__ = [
    "IdempotencyGuard",
    "JobKey",
    "WorkerRuntime",
    "celery_app",
    "configure_runtime",
]
