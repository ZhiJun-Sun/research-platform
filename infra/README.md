# HydroLab 基础设施与 B9 部署基线

## 2026-09-14 执行架构更新

当前 Docker 模式由独立 `worker` 执行训练；API 仅自动发布 Outbox 并处理业务请求，不持有 Docker socket。`worker-control` 消费控制队列；正在运行的训练 Worker 从 MySQL 读取取消请求。工作区必须在宿主机与 Worker 内使用相同绝对路径，默认 `/srv/hydrolab/runs`。

最新实现、验收边界和待办以 [交接清单](../plans/09-worker-outbox-handoff.md) 为准。下文旧的“API Docker adapter 执行训练”和“当前队列全为进程内状态”描述已被本次实现替代。数据库/真实 GPU 联合验收仍待服务器执行，已有 ACCEPTANCE 不能作为生产通过证明。

不含真实凭据的离线 Compose 验证（项目根目录）：

```bash
HYDROLAB_ENV_FILE=.env.production.example docker compose --env-file infra/.env.production.example -f infra/docker-compose.production.yml config --quiet
```

## 当前交付范围

B9 提供可部署编排骨架：MySQL 8、Redis 7、MinIO、MLflow、API、Worker（Celery）、静态 Web 与同源 `/api` 反向代理。

真实 Adapter（S3/MinIO、Celery/Redis、MLflow、Docker GPU Runner、MySQL 持久化）已实现并通过单测/契约测试。生产使用的是**显式选择真实后端**的配置模板（`.env.production.example` 默认指定 `mysql/s3/celery/mlflow/docker`），不再默认静默落到 fake；每个真实后端需在该服务器完成 Spike 验收后才算可用（见本章"状态分类"与 `apps/api/README.md`）。fake 仅作为本地开发 profile 或明确的回退模式。

## 状态分类

| 组件 | 状态 | 需要 |
|---|---|---|
| MySQL 持久化 | ✅ 已实现（SQL 仓储 + Alembic 迁移） | 服务器建库授权；`HYDROLAB_DATABASE_BACKEND=mysql` + URL |
| S3/MinIO 对象存储 | ✅ 已实现（S3 契约测试通过） | MinIO 实例 + S3 凭证 |
| Celery/Redis 队列 | ✅ 已实现（适配器 + Worker 幂等单测） | Redis 实例；启动 Worker 消费 |
| MLflow 跟踪 | ✅ 已实现（接入 Run 生命周期） | MLflow 实例 |
| Docker GPU Runner | 🟡 已实现适配器，需服务器真机验收 | Docker daemon + NVIDIA 驱动 + gpu runtime + 镜像白名单 |
| 真实端到端（MySQL/S3/Redis/MLflow/Docker 联合） | 🟡 未在无 Docker/内网不可达环境验证 | 在有上述服务的服务器上做 Spike 验收 |

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

> API 的生产设置会拒绝默认密钥和缺失的管理员账号。启用真实后端前，可用本地 `fake` profile 做页面与业务流程验收；真实训练需配置对应后端并运行 `scripts/verify-p0-deployment.sh` 检查。

## 真实执行链路（单机 subprocess Runner）

Docker GPU Runner 适配器已实现，但真机容器执行需宿主机 GPU 条件（本章后文单独说明）。在本机/受控内网可用 **subprocess Runner** 真实执行训练并采集产物，用于验证"数据 → 代码 → 实验 → 执行 → 结果"整条链路：

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
  生产化前必须完成 MySQL 持久化与 Celery/Redis 队列适配。

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

> **安全边界**：subprocess Runner 与 API 同主机同用户运行，**没有容器隔离**，因此 `validate_production()` 会在 `HYDROLAB_ENVIRONMENT=production` 时直接拒绝启动。它的定位是"Docker GPU Runner 真机验收前的可用实现"，只应在受控内网单机使用；对外多租户场景必须用 Docker GPU Runner。

## 真实 Adapter 门禁（已实现 / 待真机验收）

| 组件 | 现状 | 启用 |
|---|---|---|
| S3/MinIO | ✅ Adapter 与契约测试已实现 | `OBJECT_STORAGE_BACKEND=s3` + endpoint/凭证 |
| Celery | ✅ Adapter + Worker 幂等已实现 | `TASK_QUEUE_BACKEND=celery` + Redis；启动 Worker |
| MLflow | ✅ Adapter 已接入 Run 生命周期 | `EXPERIMENT_TRACKER_BACKEND=mlflow` + URI |
| Docker GPU | 🟡 Adapter 已实现，真机容器执行待验收 | `RUN_EXECUTOR_BACKEND=docker` + 镜像白名单 + GPU 条件 |

`docker-compose.production.yml` 不再提供指向占位镜像的 `runner` 服务；GPU 训练由 API 的 Docker adapter 承担。启用 GPU 需宿主机 NVIDIA 驱动与 gpu runtime（见部署前检查脚本）。

## 从零部署 / 启动 / 验收

```bash
# 1) 部署前检查（静态，不修改数据，不输出秘密）
./scripts/verify-p0-deployment.sh --env-file infra/.env.production.example --no-docker

# 2) 准备生产配置
cd infra
cp .env.production.example .env.production
# 填写所有 replace-with-* 占位符；替换真实域名与镜像 digest

# 3) 构建并启动（API + Worker + MySQL + Redis + MinIO + MLflow + Web）
sudo docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
sudo docker compose --env-file .env.production -f docker-compose.production.yml ps

# 4) 健康检查
curl -f http://127.0.0.1:8080/health/live
curl -f http://127.0.0.1:8080/api/v1/health/ready

# 5) 提交一次小型训练并查看结果
#    前端:  http://127.0.0.1:8080   （登录后走 数据集→代码→实验→提交→结果）
#    curl:  用 /api/v1/experiment-drafts 提交；随后观察 /runs/{id}/events、/result/ingest

# 6) 停止
sudo docker compose --env-file .env.production -f docker-compose.production.yml stop
```

> 命令中的秘密一律用 `replace-with-*` 占位符；不要提交真实密码/Token。
> 验收记录见 `infra/ACCEPTANCE.md`。
