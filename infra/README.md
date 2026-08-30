# HydroLab 基础设施

## 当前状态（B0 完成时）

**真实基础设施尚未接入，也不阻塞开发。** 后端默认以全 Fake 适配器运行：

```bash
cd apps/api
uv sync
uv run pytest          # 43 项契约/单元测试
uv run uvicorn hydrolab.main:app --reload
```

## 部署目标（云服务器，后续批次接入）

```text
Ubuntu Server
├── 2 × RTX 4090 + NVIDIA Driver + NVIDIA Container Toolkit
├── PostgreSQL 16      ← 业务真相源
├── Redis 7            ← Celery broker / 短期状态
├── S3-compatible      ← MinIO 或兼容服务（大文件对象）
├── MLflow 3           ← 训练跟踪子系统
└── apps/api + apps/worker + apps/runner（独立进程，反向代理 + TLS）
```

## 真实服务启用的门禁

按 `plans/05-open-source-reuse-and-adapter-plan.md`，逐个 Spike 通过后切换环境变量：

| 服务 | Spike | 切换配置 |
|---|---|---|
| S3 对象存储 | S3-01 | `HYDROLAB_OBJECT_STORAGE_BACKEND=s3` |
| Celery 队列 | QUEUE-01 | `HYDROLAB_TASK_QUEUE_BACKEND=celery` |
| MLflow 跟踪 | TRACK-01 | `HYDROLAB_EXPERIMENT_TRACKER_BACKEND=mlflow` |
| Docker GPU Runner | Runner 安全 Spike | `HYDROLAB_RUN_EXECUTOR_BACKEND=docker` |

Compose 编排文件将在对应 Spike 开始时补充，避免提前固化未经验证的版本。
