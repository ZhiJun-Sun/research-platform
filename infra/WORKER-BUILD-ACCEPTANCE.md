# Worker 构建修复验收（2026-09-14）

本记录仅覆盖第一步 Worker 镜像封装；不代表生产任务消费链路已经完成。

## 已修改

- Compose 的 Worker 构建上下文改为 `../apps`，与 `worker/Dockerfile` 和其 COPY 路径一致。
- 依赖层使用 `uv sync --no-dev --all-extras --no-install-project`，避免在复制源码前安装 API 项目；运行时通过 PYTHONPATH 加载 API 与 Worker 源码。
- PATH 加入 `/app/api/.venv/bin`，确保 `celery`、`python` 使用镜像内虚拟环境。
- 包含 API 的 Alembic 配置与迁移脚本。
- Dockerfile 增加依赖导入与 `celery --version` 构建检查。
- Dockerfile 专用 ignore 文件只允许需要的源码和配置进入构建上下文。

## 实际验证

- 解析当前 Compose：Worker Dockerfile 与全部 COPY 源路径存在，通过。
- 使用本机 API 虚拟环境与 Worker 源码导入运行依赖，通过；此结果不等于镜像内验证。
- 本次相关文件空白检查通过。
- 实际执行 `docker build -f apps/worker/Dockerfile -t hydrolab-worker:p0-check apps`：失败，Docker daemon 未运行，当前 context 为 desktop-linux，socket 不存在。尚未执行依赖解析或镜像层构建。
- Compose 配置展开仍被缺失 `infra/.env.production` 阻断；CLI 的 `--env-file` 只提供插值变量，不能替代服务声明的 env_file。未创建生产配置或填入真实凭据。

## 下一次验收

Docker daemon 启动后，在项目根目录运行：

```bash
docker build -f apps/worker/Dockerfile -t hydrolab-worker:p0-check apps
docker run --rm --network none hydrolab-worker:p0-check celery --version
```

生产环境文件准备完成后，再执行：

```bash
docker compose -f infra/docker-compose.production.yml --env-file infra/.env.production build worker
```

当前沿用依赖重新解析方式，uv.lock 同步与锁定构建仍待处理。Worker 的数据库 handler、消息契约与队列消费属于后续步骤，未在本次实现。
