# HydroLab API

水文时序实验平台后端（FastAPI，模块化单体）。契约见 `plans/02`，开源准入见 `plans/05`。

## 设计原则

- **代码优先**：默认全 Fake 适配器，无需 PostgreSQL/Redis/S3/MLflow/GPU 即可开发与测试；
- **端口隔离**：领域服务只依赖 `hydrolab.ports` 的 Protocol，第三方 SDK 只能出现在 `hydrolab.adapters`；
- **业务真相自有**：Run 状态机、权限、不可变版本、GPU 租约由本平台维护，外部系统状态不得反向覆盖。

## 目录

```text
src/hydrolab/
├── core/       # settings / errors / logging / middleware
├── ports/      # ObjectStorage、TaskQueue、ExperimentTracker、RunExecutor、DTO
├── adapters/
│   ├── fake/   # 内存实现 + 故障/重复注入（测试与本地开发基线）
│   └── local/  # 本地文件系统对象存储
├── api/        # deps 装配 + 路由（B0/B1/B2）
├── datasets/   # 文件夹、数据集、导入、字段映射、不可变版本
├── repositories/ # B1 身份/授权 InMemory 仓储
└── main.py     # create_app()
tests/
├── contracts/  # 端口契约测试：Fake/Local/未来真实实现共用
└── ...         # HTTP 层与错误模型测试
alembic/        # 迁移骨架（真实 PostgreSQL 接入后启用）
```

## 快速开始

```bash
cd apps/api
uv sync                 # 自动管理 Python ≥3.11 与依赖
uv run pytest           # 全部契约/单元测试
uv run ruff check src tests
uv run mypy src
uv run uvicorn hydrolab.main:app --reload
```

端点：

- `GET /health/live` — 进程存活；
- `GET /health/ready` — 按启用的后端逐组件报告（Fake 模式如实标注 backend=fake）；
- `GET /openapi.json` — REST 契约唯一来源。

## B1 已实现：身份、邀请、授权与分享

数据存储为 **InMemory Repository**（进程重启即清空，专供无数据库联调）；
部署时仅替换 `hydrolab/api/container.py` 中的构造实现为 SQL 版本，服务与路由不变。

本地联调账号（首次启动自动 bootstrap）：`admin@hydrolab.cn` / `admin123456`。

```text
POST /api/v1/auth/login|refresh|logout      会话（access 30min / refresh 14d，存储哈希）
GET|PATCH /api/v1/me[/preferences]          当前用户与偏好（Run 卡片布局等）
POST /api/v1/admin/invitations              管理员邀请（token 仅返回一次）
GET  /api/v1/admin/invitations              邀请列表（不含 token）
POST /api/v1/admin/invitations/{id}/revoke  撤销邀请
POST /api/v1/invitations/{token}/accept     接受邀请（唯一注册入口）
GET|POST /api/v1/resources/{type}/{id}/grants    资源授权（OWNER/VIEWER）
DELETE /api/v1/resources/{type}/{id}/grants/{id} 撤销授权
POST /api/v1/share-links                    创建只读链接（版本锁定 + Idempotency-Key）
GET  /api/v1/share-links                    我的分享（含访问计数）
POST /api/v1/share-links/{id}/revoke        撤销（幂等，立即生效）
GET  /api/v1/shared/{token}                 公开访问（字段白名单 + 限流防枚举）
```

安全语义（均有测试覆盖）：无公开注册；过期/已用/撤销邀请拒绝；用户 A 不可见用户 B 资源；
VIEWER 不能管理授权和分享；分享过期/撤销返回 410；审计不记录凭证；token 只存 HMAC 哈希。

## B2 已实现：文件夹、数据导入与不可变版本

B2 继续使用进程内仓储和既有 `FakeObjectStorage` / 可选 `LocalFilesystemObjectStorage`，使前端可在无数据库、无 MinIO 的情况下联调数据导入闭环：

```text
创建文件夹 / 移动文件夹（禁止循环移动）
→ 创建 Dataset（自动创建 OWNER 授权）
→ 创建 UPLOAD 导入任务（支持 Idempotency-Key）
→ 开发联调 fake-upload
→ CSV 表头探测与字段映射草稿
→ 用户确认唯一时间字段
→ 创建带 sha256 / manifest 的 READY DatasetVersion
```

```text
GET|POST  /api/v1/folders
PATCH     /api/v1/folders/{folder_id}
GET|POST  /api/v1/datasets
GET       /api/v1/datasets/{dataset_id}
GET       /api/v1/datasets/{dataset_id}/versions
POST      /api/v1/dataset-imports
GET       /api/v1/dataset-imports/{job_id}[/mapping]
POST      /api/v1/dataset-imports/{job_id}/fake-upload
POST      /api/v1/dataset-imports/{job_id}/confirm-mapping|cancel|retry
```

`READY` 版本的 manifest、内容哈希、映射和版本号不会被修改；修正映射必须以新的导入任务形成新版本。当前 `fake-upload` 是开发联调专用端点，生产 S3 预签名 multipart 上传、SSRF 安全 URL 下载、Parquet/NetCDF 内容探测与持久化仓储仍受 S3-01/真实环境门禁约束。

## B3 已实现：代码、模板与运行环境资产

B3 将训练所需的代码、入口约定、参数 Schema 和依赖环境纳入独立的不可变版本。当前 ZIP 导入只进行安全检查、清单识别和对象快照，**不会执行归档内的代码**：

```text
POST /api/v1/code-repositories
POST /api/v1/code-repositories/{id}/zip-imports
POST /api/v1/code-repositories/{id}/git-imports
GET  /api/v1/code-repositories/{id}/versions

POST /api/v1/templates
POST /api/v1/templates/{id}/versions
GET  /api/v1/templates/{id}/versions
POST /api/v1/environments
POST /api/v1/environments/{id}/versions
POST /api/v1/parameter-presets
```

安全与可复现约束：ZIP 拒绝路径穿越、符号链接、文件/解压大小超限与压缩炸弹；Git 只登记无凭证 HTTPS 引用并保持 `PENDING`，未来由隔离 Worker clone；模板仅保存 argv 参数数组，拒绝 Shell 控制符；运行环境要求不可变镜像 digest；ParameterPreset 必须符合 TemplateVersion 的参数 Schema。

## B4 已实现：实验草稿、冻结配置与 QUEUED Run

B4 将已完成的数据、代码、模板、环境和参数资产组合为可保存的 Draft，并在服务端验证后冻结为 `ExperimentVersion`。提交仅创建可追踪的 `QUEUED` Run 和 `run.requested` Fake Outbox 事件，**不会启动 Docker、队列或 GPU**：

```text
GET|POST  /api/v1/experiment-drafts
PATCH     /api/v1/experiment-drafts/{id}
POST      /api/v1/experiment-drafts/{id}/submit   # 支持 Idempotency-Key
GET       /api/v1/experiments
GET       /api/v1/experiments/{id}[/versions|/runs]
GET       /api/v1/runs/{id}/stages
```

提交时服务端校验全部输入版本为 `READY`、模板与代码版本关联一致、参数符合 Template Schema、资源授权有效；随后保存含输入 hash、argv、环境 hash 和最终参数的 `resolved_config` / `config_hash`。同一幂等键只创建一个 Run；提交后的 Draft 不可修改。

## B5/B6 已实现：Fake Runner、双 GPU 租约与实时观测基线

B5/B6 将 B4 创建的 `run.requested` 事件接入本地 Fake 控制面。它不会执行用户代码或启动 Docker，但已验证完整的运行控制与前端实时读取协议：

```text
Fake Outbox → FakeTaskQueue → GPU Lease（2 卡） → FakeRunExecutor
→ QUEUED / PREPARING / RUNNING / SUCCEEDED | FAILED | CANCELLED
→ Run Event / 日志 / 指标 / 资源采样 → REST / SSE
```

```text
POST /api/v1/internal/outbox/dispatch
POST /api/v1/runs/{id}/start|cancel
POST /api/v1/internal/runs/{id}/complete|progress|metrics|resources
GET  /api/v1/runs/{id}/events?after_id=N
GET  /api/v1/runs/{id}/events/stream     # Last-Event-ID 恢复
GET  /api/v1/runs/{id}/logs?after_id=N
GET  /api/v1/runs/{id}/resources
```

GPU lease 在 Run 成功、失败或取消时释放；资源不足时拒绝启动，避免重复占用。事件流使用已有 `run-event-v1` 协议，SSE 支持 `Last-Event-ID` 游标恢复。当前内存实现仅用于无基础设施联调；B5/B6 的真实接入仍需要 Celery/Redis、Docker/NVIDIA、MLflow 和持久化事件存储。

## B7 已实现：Checkpoint 元数据、兼容性校验与修复计划

成功 Run 可以创建不可变 Checkpoint 元数据，并将来源 `ExperimentVersion.resolved_config` 固定为追溯依据：

```text
POST /api/v1/checkpoints
GET  /api/v1/checkpoints
POST /api/v1/checkpoints/{id}/compatibility
```

兼容性校验支持 `RESUME`、`FINETUNE`、`EVALUATE`、`PREDICT` 模式。`RESUME` 强制要求数据、代码、模板、环境来源版本完全一致且 Checkpoint 含 Optimizer；特征、模型签名或 Scaler 不匹配将得到结构化 `repair_plan`，例如 `FEATURE_MAPPING`、`MODEL_KEY_MAPPING`、`REFIT_SCALER`。当前仅管理元数据和规则，不加载或执行不可信权重文件；真实权重/Scaler artifact 解析将在真实对象存储与 Runner 接入后替换实现。

## 切换到真实服务

按 `plans/05` 的 Spike 门禁逐个启用（见 `infra/README.md` 与 `.env.example`）。
选择未实现的真实后端会得到明确的 `DEPENDENCY_UNAVAILABLE`，不会静默降级。
