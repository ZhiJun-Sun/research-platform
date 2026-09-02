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
HYDROLAB_RUNNER_DATA_ROOT=/srv/hydrolab/datasets     # 可选：未选定数据版本时的兼容兜底
HYDROLAB_CODE_IMPORT_ROOTS=["/srv/projects"]         # 目录导入白名单
```

#### 数据如何进入训练进程

数据有两条互斥路径，**前者优先**：

| 路径 | 触发条件 | 可追溯性 |
| --- | --- | --- |
| 冻结数据版本物化 | Run 所属实验版本含 `dataset_version_id` | ✅ 跑的是哪份数据完全确定 |
| 全局目录软链接 | 未选定数据版本且配了 `DATA_ROOT` | ❌ 仅兼容早期联调 |

选定数据版本时，平台从对象存储取回该版本全部文件、按包内原始相对路径写入
`<workspace>/<run_id>/code/datasets/`，使训练代码原生的 `datasets/<流域>.xlsx`
相对路径直接命中；同时会摧除可能残留的全局软链接，避免写入穿透到共享只读目录。

数据集支持的格式：`CSV` / `PARQUET` / `NETCDF` / `XLSX` / `BUNDLE`。
其中 `BUNDLE`（zip）用于一个版本内含多文件与子目录的场景（水文数据常见：
多流域时序表 + 静态属性 + 子目录），导入时会清点内容并拒绝路径穿越与解压炸弹。

#### 双 4090 自动调度

`subprocess` Runner 启用时，API 生命周期会启动单机 FIFO 调度器：每秒扫描一次队列，
默认将最早创建的两个 `QUEUED` Run 分别启动在 GPU 0 / GPU 1 上；其余 Run 保持排队。
任一任务结束后，调度器采集产物、释放对应 GPU 租约，并在下一轮自动启动队首任务。

- 每张 GPU 默认只跑一个 Run，避免训练显存互相挤占；
- 分配的租约会注入子进程环境：`CUDA_VISIBLE_DEVICES=0` 或 `=1`，同时写入
  `HYDROLAB_GPU_INDICES`，因此不是“逻辑上分卡、实际都跑 GPU0”；
- `POST /runs/{id}/start` 仍保留，便于单条手动调试；正常批量场景不必逐条调用；
- Fake Runner 不启用自动调度，维持显式 `start/complete` 的测试与调试语义；
- 当前队列/租约是进程内状态：**API 重启会丢失排队信息**，因此单机可用但尚非容错队列；
  生产化前必须完成 Postgres 持久化与 Celery/Redis 队列适配。

链路语义：

1. `POST /code-import-previews` 只读扫描目录，排除 `.venv`/缓存/数据/既有产物；
2. `POST /code-repositories/{id}/directory-imports` 把目录固化为**确定性 ZIP** 并写入对象存储，得到不可变 CodeVersion；
3. 实验提交后冻结 ExperimentVersion（含 argv 与参数）；
4. `POST /runs/{id}/start` 在 `<workspace>/<run_id>/{code,output}` 中物化代码**与选定的数据版本**，并以进程组方式真实执行 argv（从不经过 shell）；
5. stdout 逐行回流到 Run 日志；`POST /runs/{id}/await` 等待结束；
6. 结束后自动采集 metrics/checkpoint/predictions/plot，`Infinity`/`NaN` 被消毒为空值；
7. `POST /runs/{id}/result/ingest` 一次性登记 Result + Metrics + Artifacts，前端即可绘图、对比、导出。

### 端到端验收

```bash
cd apps/api
uv run python ../../scripts/verify_da0_e2e.py --source /srv/projects/da0 --epochs 1
```

脚本会真实训练并逐项校验代码导入、数据包冻结、执行、日志、产物采集、结果登记与落盘，全部通过时退出码为 0。
它会把 `da0/datasets` 顶层数据文件打成 BUNDLE 上传并冻结为真实数据版本，
因此即使不配 `HYDROLAB_RUNNER_DATA_ROOT` 也能跑通——这正是“选数据集就能跑”生效的证据。

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
