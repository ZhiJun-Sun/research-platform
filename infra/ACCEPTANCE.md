# P0 并行子工程验收记录（生产部署封装与验收工具）

> 对应 `plans/08`。本记录由并行子工程（部署封装）输出，供主代理审阅；仅涉及部署/脚本/文档，
> **未改动**主代理负责的核心执行、Outbox、GPU lease、Docker adapter 代码。

## 1. 修改文件清单

| 文件 | 变更 | 说明 |
|---|---|---|
| `apps/api/Dockerfile` | 修改 | 改用 `uv sync --no-dev --all-extras`（装入真实 Adapter 依赖、排除 dev）；基础镜像 `python3.12`；去掉 `--frozen`（因 uv.lock 与 pyproject 不一致时构建失败） |
| `apps/worker/Dockerfile` | 新增 | Worker 生产镜像：复用 api 的 `--all-extras`（含 celery/redis/mysql/mlflow/s3/docker），worker src 经 PYTHONPATH 暴露，启动 `celery -A hydrolab_worker.tasks:celery_app` |
| `infra/docker-compose.production.yml` | 修改 | 新增独立 `worker` 服务、各服务健康检查与依赖；移除指向占位镜像的 `runner` 服务；api/worker 显式真实 backend 环境变量 |
| `infra/.env.production.example` | 修改 | 生产模板显式选真实后端（`mysql/s3/celery/mlflow/docker`），不再默认 fake；列出全部强制变量 |
| `scripts/verify-p0-deployment.sh` | 新增 | 部署前检查脚本：不输出秘密、退出码区分、compose 展开、镜像关键包、GPU 条件、禁静默 fake、无 Docker 时明确跳过 |
| `infra/README.md` | 修改 | 增加状态分类（已实现/需服务器条件/未完成）、零部署命令、真实 Adapter 门禁现状 |
| `infra/ACCEPTANCE.md` | 新增 | 本验收记录 |

## 2. 执行过的命令与结果

| 命令 | 结果 |
|---|---|
| `bash scripts/verify-p0-deployment.sh --env-file infra/.env.production.example --no-docker` | 退出码 0，全部检查通过 |
| 同上，改用 fake backend 的假 env | 退出码 1，正确检出生产 backend 为 fake 并列出失败项 |
| `docker compose -f infra/docker-compose.production.yml config` | 本机无 Docker daemon，但 `--no-docker` 下该命令静态解析成功（config 不需 daemon） |
| `apps/api/.venv/bin/python -m pytest -q` | **148 passed, 8 skipped**（skip 为既有 `tests/db/test_mysql_*`，需 `HYDROLAB_TEST_DATABASE_URL`） |
| `apps/api/.venv/bin/python -m ruff check <本次改动文件>` | 通过（仅剩执行器端口固有 ASYNC109 属既有风格） |

## 3. 无法完成的项及原因

- **Docker 镜像实际构建 / Compose `up` / 容器级验证**：本机无 Docker daemon（`docker info` 不可用）。已做静态审阅（Dockerfile 语法、依赖 extras、启动命令），未执行构建。
- **真实外部服务联合冒烟（MySQL/MinIO/Redis/MLflow/Docker）**：开发机访问不了内网服务器，故未做真机链路验收；需在有这些服务的服务器上执行 `verify-p0-deployment.sh` 与 e2e。

## 4. 与主代理核心改动可能的接口冲突

部署封装未改动主代理负责的文件（`execution/service.py`、`db/repositories/experiments.py`、`db/repositories/execution.py`、`adapters/docker/*`、`experiments/*`）。但有几处**依赖既有接口**，需主代理确认：

- `apps/worker/src/hydrolab_worker/tasks.py` 的 `celery_app` 在 `HYDROLAB_REDIS_URL` 未设置时恒为 `None`；Worker 镜像靠 Compose 注入该变量启动，需确认这与 Worker 运行约定一致。
- Compose 中 `HYDROLAB_MLFLOW_TRACKING_URI` 指向 `mlflow:5000`；若主代理对 tracker 的接入方式有改动，URI 需保持一致。
- Dockerfile 去掉了 `--frozen`；若主代理要求可复现锁定构建，需在合并前重新生成与 `pyproject.toml` 一致的 `uv.lock`。

## 5. 主代理必须阻断发布的剩余风险

1. **Docker GPU Runner 真机验收未完成**：适配器与 `wait()`/回收已有单测，但未在有 GPU 的服务器上跑真实容器训练（无 Docker/GPU 环境）。合并前需在服务器执行 `RUN_EXECUTOR_BACKEND=docker` 的端到端。
2. **真实外部服务联合不健康时不会误启**：检查脚本已能检出"生产 backend 为 fake"，但真实 S3/Celery/MLflow/MySQL 的连通性仍需在有服务的服务器上用 `scripts/verify_da0_e2e.py` + Spike 命令验证。
3. **`uv.lock` 陈旧**：`uv sync --frozen` 会失败；当前 Dockerfile 改为 `--frozen` 已移除（不传），但生产可复现构建仍建议由有 `uv` 的机器重新生成 `.lock` 并提交。