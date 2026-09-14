# HydroLab Worker 生产镜像（Celery 消费端）。
# Worker 的 run.execute 任务通过注入的 handler 重新读数据库并启动 Run，
# 因此必须同时包含 API 源码（hydrolab.*）与 Worker 源码（hydrolab_worker.*）。
#
# 依赖来源：直接复用 API 项目的 uv sync --all-extras（其 celery extra 已含 celery/redis，
# mysql/mlflow/s3/docker extras 覆盖 Worker 读库与回调所需），Worker 源码作为薄层暴露。
# 生产任务调用 runtime.execute_run，从数据库读取配置后交给 Docker 执行。
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
COPY api/pyproject.toml api/uv.lock ./api/
RUN cd api && uv sync --no-dev --all-extras --no-install-project
COPY api/src ./api/src
COPY api/alembic.ini ./api/alembic.ini
COPY api/alembic ./api/alembic
COPY worker/src ./worker/src
ENV PATH="/app/api/.venv/bin:$PATH"
ENV PYTHONPATH="/app/api/src:/app/worker/src"

# 构建时检查依赖和模块导入，不连接数据库或 broker。
RUN python -c "import hydrolab, hydrolab_worker, asyncmy, pymysql, alembic, celery, redis, aiobotocore, mlflow, docker" \
    && celery --version

# 启动 Celery worker；broker 由 HYDROLAB_REDIS_URL 提供（Compose 注入）。
CMD ["celery", "-A", "hydrolab_worker.tasks:celery_app", "worker", "--loglevel=info", "--concurrency=1"]
