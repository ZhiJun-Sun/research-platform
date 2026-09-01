# HydroLab 基础设施与 B9 部署基线

## 当前交付范围

B9 已提供可部署编排骨架：PostgreSQL 16、Redis 7、MinIO、MLflow、API、静态 Web 与同源 `/api` 反向代理。生产 Compose **默认仍使用 Fake Adapter**，因为 S3、Celery、MLflow 与 Docker GPU Runner 的业务 Adapter 尚未在应用代码中实现；不得仅通过修改环境变量把它们标记为已启用。

## Ubuntu 服务器前置条件

```bash
# Docker Engine / Compose plugin
sudo docker --version
sudo docker compose version

# GPU Runner profile 启用前必须确认
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

第二条命令失败时，先安装/修复 NVIDIA Container Toolkit；不要启用 `gpu` profile。

## 启动基础服务

```bash
cd infra
cp .env.production.example .env.production
# 填写所有 replace-with-* 值，并修改 PUBLIC_BASE_URL/CORS 所需域名
sudo docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
sudo docker compose --env-file .env.production -f docker-compose.production.yml ps
```

Web 仅监听服务器回环地址 `127.0.0.1:8080`。生产应由 Caddy/Nginx/云负载均衡器在外层提供 TLS，再代理到该端口。

## 验收

```bash
curl -f http://127.0.0.1:8080/health
curl -f http://127.0.0.1:8080/api/v1/health
sudo docker compose --env-file .env.production -f docker-compose.production.yml logs --tail=100 api
```

> API 的生产设置会拒绝默认密钥和缺失的管理员账号。当前 Fake Adapter 基线可用于页面和业务流程验收，但不能执行真实训练。

## 真实执行链路（单机 subprocess Runner）

Docker GPU Runner 尚未实现，但平台已提供**可真实执行训练并采集产物**的单机实现，用于在真实服务器上验证"数据 → 代码 → 实验 → 执行 → 结果"整条链路。

```bash
HYDROLAB_ENVIRONMENT=local                       # 生产环境会拒绝 subprocess
HYDROLAB_OBJECT_STORAGE_BACKEND=local
HYDROLAB_LOCAL_STORAGE_ROOT=/srv/hydrolab/objects
HYDROLAB_RUN_EXECUTOR_BACKEND=subprocess
HYDROLAB_RUNNER_WORKSPACE_ROOT=/srv/hydrolab/runs
HYDROLAB_RUNNER_PYTHON_EXECUTABLE=/usr/bin/python3   # 需含 torch 等训练依赖
HYDROLAB_RUNNER_DATA_ROOT=/srv/hydrolab/datasets     # 以 code/datasets 只读软链接暴露
HYDROLAB_CODE_IMPORT_ROOTS=["/srv/projects"]         # 目录导入白名单
```

链路语义：

1. `POST /code-import-previews` 只读扫描目录，排除 `.venv`/缓存/数据/既有产物；
2. `POST /code-repositories/{id}/directory-imports` 把目录固化为**确定性 ZIP** 并写入对象存储，得到不可变 CodeVersion；
3. 实验提交后冻结 ExperimentVersion（含 argv 与参数）；
4. `POST /runs/{id}/start` 在 `<workspace>/<run_id>/{code,output}` 中物化代码、软链数据，并以进程组方式真实执行 argv（从不经过 shell）；
5. stdout 逐行回流到 Run 日志；`POST /runs/{id}/await` 等待结束；
6. 结束后自动采集 metrics/checkpoint/predictions/plot，`Infinity`/`NaN` 被消毒为空值；
7. `POST /runs/{id}/result/ingest` 一次性登记 Result + Metrics + Artifacts，前端即可绘图、对比、导出。

### 端到端验收

```bash
cd apps/api
uv run python ../../scripts/verify_da0_e2e.py --source /srv/projects/da0 --epochs 1
```

脚本会真实训练并逐项校验代码导入、执行、日志、产物采集、结果登记与落盘，全部通过时退出码为 0。

> **安全边界**：subprocess Runner 与 API 同主机同用户运行，**没有容器隔离**，因此 `validate_production()` 会在 `HYDROLAB_ENVIRONMENT=production` 时直接拒绝启动。它的定位是"Docker GPU Runner 落地前的可用实现"，只应在受控内网单机使用；对外多租户场景必须等下表的 Docker GPU 门禁通过。

## 后续真实 Adapter 切换门禁

| 组件 | 必须完成的实现与验收 | 才能切换 |
|---|---|---|
| S3 | `S3ObjectStorageAdapter`，上传/下载/签名 URL/权限 Spike | `OBJECT_STORAGE_BACKEND=s3` |
| Celery | Outbox publisher、幂等 worker、重试/死信/恢复 Spike | `TASK_QUEUE_BACKEND=celery` |
| MLflow | Tracking Adapter、Run/metric/artifact 关联 Spike | `EXPERIMENT_TRACKER_BACKEND=mlflow` |
| Docker GPU | 签名 RunSpec、只读挂载、网络/权限/超时/清理与双 4090 压测 | `RUN_EXECUTOR_BACKEND=docker` + `--profile gpu` |

其中 Docker GPU 一行是**多租户/生产**的目标形态；单机受控场景可先用上文的 subprocess Runner 真实跑通链路。

在以上门禁通过前，`runner` 服务始终保持未启用状态。
