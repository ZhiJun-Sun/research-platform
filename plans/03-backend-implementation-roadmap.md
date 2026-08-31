# HydroLab 后端实施路线与验收计划

> 状态：Confirmed  
> 状态：B0–B8 后端 Fake-first 基线已完成（B8 结果/绘图规格/导出清单/同数据版本 Run 对比，90 项源码检查通过、87 项测试通过）；运行中心已完成 FastAPI 本地联调和浏览器操作验证。B9 部署骨架已交付，真实 Adapter、Docker、Ubuntu 双 RTX 4090 验收待云端环境。
> 目标：按定版交互原型建立可部署、可迁移、可测试的真实后端。

## 1. 实施前检查清单

编码前先记录实际检查结果，不把假设写成“已通过”：

- [x] 项目 Git 根目录：`/Users/sunzhijun/Downloads/last_design`，2026-08-29 初始化 main 分支。
- [x] Python 与包管理：系统 Python 3.9 不满足要求，使用 uv 自动管理 Python ≥3.11；依赖已在 `apps/api/pyproject.toml` 声明并通过 `uv sync` 锁定。
- [x] 项目已在无 Docker、数据库、Redis、对象存储、MLflow 和 GPU 的环境运行 Fake/Local 单元与契约测试（43 项通过，ruff/mypy 全绿）。
- [ ] Docker Engine、Compose v2、磁盘和可用端口仅作为后续真实 Adapter/部署验收项，不阻塞 B1。
- [ ] PostgreSQL、Redis、S3-compatible storage、MLflow 版本兼容性在对应 Spike 后记录。
- [ ] Ubuntu 服务器 NVIDIA Driver、两张 RTX 4090、NVIDIA Container Toolkit、CUDA 镜像标记为云端验收项。
- [x] 当前无 GPU/基础设施，真实集成标记为待验收，不阻塞 API、领域和 Fake Adapter 开发。
- [ ] 备份目录、对象存储容量和低水位阈值。
- [ ] 外部访问域名、TLS、反向代理和邮件/邀请发送方式。
- [ ] 原型 Mock 字段与 `04` 追踪矩阵一致。

## 2. 技术基线

建议锁定而非使用 latest：

- API 核心：FastAPI、Pydantic v2、SQLAlchemy 2 async、Alembic；Python 精确版本由首批依赖 Spike 后固定。
- 生产目标：PostgreSQL 16、Redis 7、Celery 5.6 系列、S3-compatible storage、MLflow 3 系列；均须通过 `05` 对应 Spike，不能因当前不可访问而阻塞编码。
- 首批可执行基线：Fake/Local adapters、pytest、pytest-asyncio、httpx、ruff、mypy/pyright。
- 真实集成测试阶段再加入 testcontainers、Docker、boto3、Celery、MLflow client。
- structlog 或标准 JSON logging；OpenTelemetry + Prometheus 指标。

具体 patch 版本在阶段 B0 环境检查后写入 `pyproject.toml` 和镜像，不在计划中假称已验证。

## 3. 配置与环境

配置采用环境变量 + Secret 文件，至少区分 local/test/staging/production：

```text
DATABASE_URL
REDIS_URL
S3_ENDPOINT / S3_REGION / S3_BUCKET
S3_ACCESS_KEY / S3_SECRET_KEY / S3_ADDRESSING_STYLE
MLFLOW_TRACKING_URI
OBJECT_STORAGE_BACKEND=fake|local|s3
TASK_QUEUE_BACKEND=fake|celery
EXPERIMENT_TRACKER_BACKEND=fake|noop|mlflow
RUN_EXECUTOR_BACKEND=fake|docker
AUTH_SECRET / COOKIE_DOMAIN
PUBLIC_BASE_URL
CORS_ORIGINS
RUNNER_SIGNING_KEY
STORAGE_QUOTA_BYTES / STORAGE_LOW_WATERMARK_BYTES
```

提交 `.env.example`，禁止提交真实 Secret。设置启动时强校验，生产环境不允许默认密钥。

## 4. 分阶段纵向切片

每个批次都必须同时包含：迁移、模型、服务、路由、Policy、测试、OpenAPI、前端接入和回滚说明。

### B0：工程、契约与 Fake 基线

**实现**

- 建立 `apps/api`、`apps/worker`、`apps/runner`、`infra`、`packages/contracts`。
- FastAPI 生命周期、配置、JSON 日志、request_id、统一错误模型。
- 定义 ObjectStorage、TaskQueue、ExperimentTracker、RunExecutor、ModelFrameworkAdapter 端口及 DTO。
- 实现 Fake/Noop/Local adapters、故障注入和共享 contract tests；不要求启动 PostgreSQL、Redis、S3、MLflow 或 GPU。
- `/health/live`、按启用 Adapter 计算的 `/health/ready`。
- Alembic 基线和空数据库升级/降级测试；无 PostgreSQL 时先完成迁移静态检查与 Repository 单测。
- CI：lint、typecheck、unit、contract、migration、OpenAPI diff。

**验收**

- 无外部服务环境可启动 API 测试配置并完成核心测试。
- Fake 可模拟重复投递、对象上传失败、Tracker 不可用和 Runner 超时。
- 外部 SDK 类型不穿透领域层。
- 有服务的测试环境中，依赖故障时 live 仍存活、ready 明确失败。
- 不修改前端业务流程。

### B1：身份、邀请、资源授权与分享基础

> 状态：已完成（InMemory 基线，66 项测试通过；SQL Repository 与 Alembic 迁移随首个真实数据库环境接入）

**实现**

- User、Invitation、Session/Token、ResourceGrant、ShareLink、AuditLog。
- 管理员 bootstrap 和邀请接受；无公开注册。
- 所有者/只读 Policy；分享 token 哈希、有效期与撤销。
- 前端接入 `/me`、权限与分享列表、资源详情分享弹窗。

**验收**

- 未邀请用户不能注册；过期/已用邀请不可复用。
- 用户 A 不能读取用户 B 私有资源。
- 分享链接锁定版本、过期和撤销立即生效。
- Token/Secret 不出现在数据库明文和日志。

### B2：文件夹、数据导入与不可变版本

> 状态：已完成（InMemory + Fake/Local ObjectStorage 基线，71 项测试通过；S3 直传、URL SSRF 安全下载、Parquet/NetCDF 深度探测与 SQL Repository 随对应 Spike/真实环境接入）

**实现**

- Folder、Dataset、DatasetVersion、ImportJob、FieldMapping、Artifact。
- 先以 Local/Fake ObjectStorage 跑通两阶段提交；S3-01 通过后接入 multipart 直传、URL 下载、版本派生、格式探测和映射确认。
- CSV/Parquet 首批完成；NetCDF 在同一接口下作为后续适配器，不阻塞核心链路。
- 内容 manifest、sha256、配额、取消/重试与清理任务。
- 前端数据列表/详情/创建流程从 Mock 切换真实 API。

**验收**

- 上传中断可续传或安全重试。
- URL 下载阻止 SSRF、超大文件和危险重定向。
- READY 版本不可改写；修正映射会生成新版本。
- 文件夹移动不改变版本或权限。
- 跨用户无法下载、搜索或通过对象 key 猜测资源。

### B3：代码、模板与环境资产

> 状态：已完成（InMemory + Fake/Local ObjectStorage 基线，75 项测试通过；Git clone、异步镜像构建、代码安全扫描与 SQL Repository 随隔离 Worker/真实环境接入）

**实现**

- ZIP/Git 导入、CodeVersion 快照和安全扫描。
- `hydro-experiment.yaml` v1 Schema；无清单的发现任务只产生待确认模板。
- TemplateVersion、动态参数 Schema、ParameterPreset。
- EnvironmentVersion、环境构建队列、镜像 digest 和日志。
- 前端模型代码及运行环境页面接入。

**验收**

- ZIP 穿越、符号链接逃逸和压缩炸弹被拒绝。
- Git 凭证不进入日志/快照。
- 模板参数错误返回字段级错误。
- 环境构建在独立构建器中执行，API 容器没有 Docker 权限。
- 实验可引用精确 code/template/environment 版本。

### B4：Experiment、草稿与 Run 元数据

> 状态：已完成（InMemory + Fake Outbox 基线，78 项测试通过；SQL 事务性 Outbox、Celery 投递与真实 Runner 在 B5/真实基础设施阶段接入）

**实现**

- ExperimentDraft、Experiment/Version、Run、RunStage、Outbox。
- 分步/高级表单共享 Draft API。
- 服务端 validate：参数、版本访问权、任务模式、Checkpoint 初步兼容、配额。
- 原子创建 Run + Outbox；幂等键。
- 实验列表/详情/Run 历史接入。

**验收**

- 模式切换和刷新不丢草稿。
- Experiment 与 Run 在 API 和数据库层明确分离。
- 重复提交不会创建多个 Run。
- Run 保存完整 resolved config 和所有精确版本 ID。
- 无权资源不能通过构造 ID 创建 Run。

### B5：最小 Runner、队列和双 GPU 租约

> 状态：Fake-first 基线已完成（B6 观测能力一并完成，81 项测试通过；Celery/Redis、Docker/NVIDIA Container Toolkit 与真实 GPU 安全验收待云端环境）

**实现**

- 仅允许仓库内 `examples/minimal-lstm` 首先跑通。
- 先用 FakeTaskQueue/FakeRunExecutor 验证状态机和重复消息；QUEUE-01 与 Runner 安全 Spike 通过后接入 Celery Outbox、RunSpec 签名、Runner 心跳和 GPU lease。
- 隔离容器、只读输入、可写输出、禁网、非 root、资源限制。
- 状态机、取消、超时、异常回收和孤儿任务恢复。
- GPU/队列抽屉接真实状态。

**验收**

- 两张 GPU 连续调度不会重复占用。
- API 进程与训练执行权限隔离。
- Worker/API 重启不丢 Run；重复消息不重复执行。
- 取消和失败均释放 GPU、容器和租约。
- 容器不能读取其他 Run 或宿主敏感目录。

### B6：进度、日志、指标与 MLflow

> 状态：Fake-first Run Event / 日志 / 资源采样 / SSE 基线已完成（MLflowTrackingAdapter、持久化事件与分布式恢复待真实基础设施阶段）

**实现**

- JSONL Schema v1 解析；SDK/Regex 接口预留。
- RunEvent、MetricPoint、ResourceSample、日志对象和 SSE。
- REST 快照 + SSE 增量；Last-Event-ID 恢复。
- 先以 Fake/Noop Tracker 完成业务链路；TRACK-01 通过后接入 MLflow 参数/指标/标签同步及失败重试。
- NH-01 通过后开放 NeuralHydrology 模板；其 GPU 调度不得替代平台租约。
- Run 详情的阶段、Epoch、曲线、日志、GPU 和 ETA 全部接入。

**验收**

- 页面刷新/短时断网后恢复状态和曲线，不重复事件。
- 高频日志不会阻塞 API；SSE 只发送游标/增量。
- MLflow 暂时不可用不导致业务 Run 状态错误。
- 指标 NaN/Infinity 有确定处理。
- 资源采样具有保留期，不无限增长。

### B7：Checkpoint、失败重试与兼容性

> 状态：Checkpoint 不可变元数据与兼容性/repair_plan 基线已完成（83 项测试通过；真实权重、Scaler、Optimizer/Scheduler artifact 解析与持久化存储待真实 Runner/对象存储接入）

**实现**

- Checkpoint/Scaler/Optimizer/Scheduler 元数据和对象。
- 兼容检查服务与 repair_plan Schema。
- resume/finetune/evaluate/predict 统一复用接口。
- 失败现场、阶段产物完整性和 retry-stage 策略。
- 前端 Checkpoint 详情、修复向导和失败 Run 操作接入。

**验收**

- 不兼容时服务端阻止提交，不能靠跳过前端绕过。
- 显式修复方案进入 resolved config 和血缘。
- 同一 Checkpoint 可派生多个独立 Run。
- 不满足幂等/产物条件时不提供阶段重试，只能 rerun。
- 旧 Run 始终可审计且不被覆盖。

### B8：结果、诊断、绘图、导出与对比

> 状态：后端 Fake-first 基线已完成（Result/Metric/Artifact/PlotSpec/ExportManifest、同冻结数据版本比较、87 项测试通过）；前端结果页仍为原型数据，待逐页迁移至 Results API。

**实现**

- Result、Artifact、全局/逐流域指标、事件指标。
- 标准图自动生成；PlotSpec、自然语言到结构化计划的可插拔解析器。
- 选择性导出、manifest 和短期下载 URL。
- 2–5 Run 对比兼容检查与四区查询。
- 结果索引、详情、诊断、绘图、导出和对比全部接入。

**验收**

- 列表筛选排序在服务端执行且分页稳定。
- 指标与图表能追溯到 Run、输入文件和哈希。
- 图表同时保留图、数据、配置和脚本。
- 导出包文件与 manifest 哈希一致。
- 不兼容 Run 无法进入对比；基线差异计算有测试。

### B9：生产加固与 Ubuntu 双 4090 部署

> 状态：Docker Compose、镜像定义、环境模板、反向代理与云端验收 Runbook 已交付；本机无 Docker CLI，真实 S3/Celery/MLflow/Docker Adapter 与 Ubuntu 双 4090 验收尚未执行。

**实现**

- TLS/反代、数据库/对象备份、恢复演练、配额和低水位保护。
- Prometheus/Grafana 或等价观测、告警、审计查询。
- 数据生命周期、临时目录清理、事件/采样分区维护。
- 数据库滚动迁移、发布与回滚手册。
- 安全扫描、故障注入和 24h 队列测试。

**验收**

- 干净环境可以从备份恢复元数据和对象。
- 磁盘低水位拒绝新任务但不破坏运行中任务。
- API/Worker/Runner 单点重启后系统可收敛。
- 两张 4090 连续 24h 无重复租约与孤儿容器。
- 完成跨用户、容器逃逸面和下载授权 E2E。

## 5. 前端逐页替换策略

不一次性删除 Mock。建立统一接口层：

1. 定义后端 OpenAPI 与前端 API client。
2. 为每个 feature 定义 ViewModel 映射。
3. 开发环境通过 `VITE_DATA_SOURCE=mock|api` 明确选择；生产只允许 api。
4. 按 B1→B8 的顺序逐页切换。
5. 每切换一页，保留 Mock 用于 Story/视觉回归，但禁止业务逻辑出现双重真相。
6. 接口错误映射为页面 loading/empty/error/ready 和命令 pending/success/failure。
7. 将当前 `App.tsx` 拆分为路由和 feature，使用真实 URL 支持刷新和深链。

## 6. 测试金字塔

### 单元测试

- 状态机、Policy、字段映射、参数解析、兼容检查、指标和对比计算。
- 命令模板只生成 argv/config，不生成 shell 字符串。

### 数据库与契约测试

- Repository、唯一约束、不可变触发规则、迁移升降级。
- OpenAPI 快照和事件 JSON Schema 兼容。

### 集成测试

先对 Fake/Local 实现运行共享 contract tests；获得服务环境后，再使用隔离 PostgreSQL/Redis/S3-compatible storage 覆盖导入两阶段提交、Outbox、分享、SSE 恢复和 Artifact 授权。真实 Adapter 不通过对应 Spike 不进入默认路径。

### Runner 安全测试

测试只读挂载、无网络、非 root、资源限制、取消、超时、错误退出、重复消息和心跳失联。

### E2E

至少覆盖：

```text
邀请登录
→ 导入数据并确认字段
→ 导入代码/确认模板/选择环境
→ 创建 Experiment 和 Run
→ 观察 SSE 进度
→ 生成 Checkpoint/结果
→ 微调/评估
→ 单次结果/多 Run 对比
→ 导出/只读分享
```

## 7. 可观测性

每个请求、job、Run 和容器使用关联 ID。核心指标：API 延迟/错误、队列长度、任务等待时长、GPU 租约、Runner 心跳、导入失败、对象存储错误、SSE 连接数、磁盘水位。日志为 JSON 且脱敏。

## 8. 迁移、备份与回滚

- 每个 schema 变化配 Alembic upgrade/downgrade；破坏性迁移采用 expand/migrate/contract。
- 发布前备份 PostgreSQL 和 MinIO manifest；数据库备份与对象快照使用一致时间点标记。
- 回滚应用不自动回滚已写数据，使用兼容窗口和明确 runbook。
- Runtime Image、模板 Schema、Progress Event 和 PlotSpec 均显式版本化。

## 9. 性能与容量初始目标

面向小团队但保持边界：

- 列表默认 50、最大 200。
- SSE 每用户/每 Run 连接限制；资源采样 2–5 秒，指标按训练事件写入。
- 日志分块上传，API 不载入完整大日志。
- 大文件浏览器直传/直下对象存储。
- 对比最多 5 Run；超大逐流域数据采用分页/分块查询。
- 设置每用户对象配额、单导入上限、单 Run 输出上限和全局低水位。

具体数值在 B0/B2 压测后固化。

## 10. Definition of Done

一个批次只有同时满足以下条件才能标 Completed：

- 功能符合 `01` 交互语义和 `04` 追踪矩阵。
- 数据库迁移、回滚说明和索引齐全。
- Policy 覆盖且有越权测试。
- API/事件契约更新并通过兼容检查。
- 单元、集成和对应 E2E 通过。
- loading/empty/error/disabled 状态在真实接口下验证。
- 日志、指标、审计和错误 request_id 可用。
- README、AGENTS 和运维说明同步。
- 没有真实 Secret、未处理高危漏洞或静默失败路径。

## 11. 首次 Coding 会话范围

用户确认开始写代码后，第一轮执行 B0 的代码优先子集，不跳到业务功能：

1. 实际项目与 Git 检查并记录结果。
2. 建立 API/Worker/Runner/infra 目录骨架。
3. 定义设置、错误、日志、OpenAPI 和领域端口 DTO。
4. 实现 Fake/Noop/Local adapters 与共享 contract tests。
5. 建立 FastAPI `/health/live` 和配置感知的 `/health/ready`。
6. 建立 Alembic 基线；真实数据库验收可后补。
7. 最小 CI/测试与启动文档。

Compose、PostgreSQL、Redis、S3、MLflow、Docker GPU Runner 均不是首次 Coding 会话前置条件。需要真实接入时，按 `05` 的 S3-01、QUEUE-01、TRACK-01、NH-01 门禁逐项启用。

B0 代码基线验收后再进入 B1，避免同时引入认证、数据上传和 Runner 导致故障难定位。
