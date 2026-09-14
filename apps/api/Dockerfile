# HydroLab API 生产镜像。
# 说明：
#  - uv.lock 若与 pyproject 不一致（新增了真实 Adapter 可选依赖），--frozen 会失败；
#    这里不传 --frozen，让 uv 在构建时按 pyproject 解析，确保真实运行依赖装入镜像。
#  - 必须用 --all-extras 安装真实 Adapter 的可选依赖（S3/Celery/MLflow/Docker），
#    否则相应 backend 会在运行时才报缺少模块。
#  - --no-dev 排除开发依赖（pytest/moto/fakeredis 等），保持生产镜像精简。
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --all-extras --no-install-project
COPY src ./src
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
EXPOSE 8000
CMD ["uvicorn", "hydrolab.main:app", "--host", "0.0.0.0", "--port", "8000"]
