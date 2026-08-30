# HydroLab 后端领域与 API 实施计划

> 状态：Confirmed  
> 架构：FastAPI + PostgreSQL + Redis/Celery + S3-compatible storage + MLflow + Docker Runner  
> 原则：契约由定版原型倒推，API 层不直接执行训练命令；业务服务仅依赖 `05` 定义的领域端口。

## 1. 服务边界

首版采用模块化单体 API，避免过早拆微服务；Runner、Worker 和环境构建器为独立进程。

```text
React Web
   │ REST + SSE
FastAPI
   ├── PostgreSQL：身份、权限、资源版本、任务、索引和血缘
   ├── TaskQueue Port：Fake → Celery/Redis Adapter
   ├── ObjectStorage Port：Fake/Local → S3 Adapter（MinIO 或兼容服务）
   ├── ExperimentTracker Port：Fake/Noop → MLflow Adapter
   └── Transactional Outbox
          └── Worker → RunExecutor Port → Docker GPU Runner
```

FastAPI 不持有 Docker Socket；Runner Controller 位于受控服务器侧，仅消费经过校验的 RunSpec。

## 2. 建议后端目录

```text
apps/api/
├── pyproject.toml
├── alembic.ini
├── src/hydrolab/
│   ├── main.py
│   ├── core/          # settings, security, errors, logging, idempotency
│   ├── db/            # session, base, migrations helpers
│   ├── auth/
│   ├── users/
│   ├── access/
│   ├── folders/
│   ├── datasets/
│   ├── code_assets/
│   ├── environments/
│   ├── experiments/
│   ├── runs/
│   ├── checkpoints/
│   ├── results/
│   ├── sharing/
│   ├── storage/
│   ├── events/
│   └── outbox/
└── tests/

apps/worker/            # 导入、解析、绘图、导出、同步 MLflow
apps/runner/            # RunSpec 校验、GPU 租约、容器生命周期
infra/                  # compose、反向代理、初始化和观测
packages/contracts/     # OpenAPI 快照、JSON Schema、事件 Schema
examples/minimal-lstm/  # 第一条端到端受控样例
```

领域模块内部使用 `router.py / schemas.py / models.py / repository.py / service.py / policies.py`，路由不直接访问 ORM。基础设施实现放入 `adapters/`，至少包含 `fake`、`local` 和真实实现；领域层禁止直接 import boto3、celery、mlflow、neuralhydrology、darts 或 optuna。端口和准入门禁以 `05-open-source-reuse-and-adapter-plan.md` 为准。

### 2.1 首批端口

```text
ObjectStorage       → FakeObjectStorage / LocalFilesystemObjectStorage / S3ObjectStorageAdapter
TaskQueue           → FakeTaskQueue / CeleryTaskQueueAdapter
ExperimentTracker   → FakeExperimentTracker / NoopExperimentTracker / MlflowTrackingAdapter
RunExecutor         → FakeRunExecutor / DockerGpuRunExecutor
ModelFrameworkAdapter → CommandTemplateAdapter / NeuralHydrologyAdapter
OptimizationAdapter → OptunaAdapter（MVP 后）
```

每个真实 Adapter 与 Fake 必须运行同一组 contract tests；Fake 需要支持失败、重复、超时和部分成功注入。

## 3. 身份、邀请和授权

### 3.1 身份模型

- `users`：id、email、display_name、status、is_admin、created_at。
- `invitations`：token_hash、email、expires_at、accepted_at、inviter_id。
- `sessions` 或短期 access token + 可撤销 refresh token。

无公开注册。首个管理员通过一次性 bootstrap 命令创建；之后仅管理员邀请。

### 3.2 授权模型

- `resource_grants`：resource_type、resource_id、subject_type、subject_id、role、expires_at。
- 首版角色仅 `OWNER`、`VIEWER`；未来需要协作编辑时再扩展。
- 业务查询先过 Policy，再访问资源；禁止只依赖前端隐藏按钮。
- 跨资源操作同时校验所有输入资源，例如创建 Run 必须有代码、数据、环境和 Checkpoint 的读取权。

### 3.3 只读链接

`share_links` 保存 token_hash、锁定 resource_version、允许 artifact 范围、expires_at、revoked_at、访问计数和最后访问时间。原始 token 仅创建时返回，不明文入库。

## 4. 核心领域模型

所有主键推荐 UUIDv7；所有表包含 `created_at`，可变元数据包含 `updated_at`，乐观并发字段使用 `version_no`。

### 4.1 文件夹与数据

- `asset_folders`：owner_id、parent_id、name、path_key；同父目录名称唯一，防循环移动。
- `datasets`：逻辑资产、owner、folder。
- `dataset_versions`：dataset_id、version_no、source_type、status、object_prefix、manifest、content_hash、parent_version_id、frozen_at。
- `dataset_import_jobs`：upload/url/derive、阶段、进度、错误、幂等键。
- `field_mappings` / `field_mapping_items`：原字段、语义、标准名、单位、顺序、置信度、用户修正。

版本进入 READY 后禁止更新内容字段；修正映射产生新版本。

### 4.2 代码、模板和环境

- `code_repositories`、`code_versions`：source_type、commit_sha、object_prefix、content_hash、scan_status。
- `experiment_templates`、`template_versions`：任务类型、命令模板、参数 Schema、输出契约、进度协议。
- `runtime_environments`、`runtime_environment_versions`：spec、status、image_ref、image_digest、build_log_artifact_id。
- `parameter_presets`：template_version_id、name、values、owner_id。

### 4.3 实验与 Run

- `experiments`：逻辑定义、name、owner、current_version_id。
- `experiment_versions`：code_version_id、template_version_id、dataset_version_id、environment_version_id、mode、default_parameters、output_spec、content_hash。
- `runs`：experiment_version_id、status、stage、resolved_parameters、seed、priority、initial_checkpoint_id、requested_resources、timestamps、retry_of_run_id、resume_from_stage。
- `run_stage_records`：阶段状态、输入/输出哈希、开始结束时间、错误和可重入标记。
- `run_events`：递增 event_seq、type、payload、created_at；用于 SSE 恢复和审计。
- `metric_points`：run_id、name、step_type、step、split、basin_id、value、timestamp。
- `resource_samples`：GPU/CPU/内存/显存采样，可采用分区表并设置保留期。
- `gpu_leases`：gpu_id、run_id、lease_until、heartbeat_at，唯一约束保证同卡单租约。

ExperimentVersion 不因 Run 参数覆盖而改变；Run 保存完整 resolved config。

### 4.4 Checkpoint、结果与血缘

- `checkpoints`：run_id、artifact_id、epoch、kind、architecture_signature、io_signature、scaler_artifact_id、optimizer_state、scheduler_state、metrics、digest。
- `checkpoint_compatibility_checks`：checkpoint_id、target context、status、issues、repair_plan、validated_at。
- `results`：run_id、status、summary_metrics、metric_schema_version、time_range、basin_set_hash。
- `artifacts`：owner、resource reference、kind、object_key、media_type、size、sha256、status。
- `lineage_edges`：from_type/id、to_type/id、relation、metadata。
- `plot_jobs` / `plot_specs`：结构化绘图计划、状态和产物。
- `export_jobs`：所选 artifact、manifest、状态、过期时间。

## 5. 统一 API 约定

### 5.1 路径和版本

所有业务接口位于 `/api/v1`。健康检查分为：

- `GET /health/live`：进程存活，不探测外部依赖。
- `GET /health/ready`：按部署配置探测启用的关键 Adapter；Fake/Noop 模式不假装真实服务已连接。

### 5.2 列表响应

```json
{
  "items": [],
  "next_cursor": null,
  "total": 0
}
```

查询统一使用 `cursor`、`limit`、`q`、`sort`、领域筛选。`limit` 有上限；排序必须包含唯一键保证稳定。

### 5.3 错误响应

```json
{
  "error": {
    "code": "CHECKPOINT_MAPPING_REQUIRED",
    "message": "Checkpoint 与目标配置不兼容",
    "details": {},
    "request_id": "..."
  }
}
```

基础错误码：`VALIDATION_ERROR`、`UNAUTHENTICATED`、`FORBIDDEN`、`NOT_FOUND`、`CONFLICT`、`RATE_LIMITED`、`DEPENDENCY_UNAVAILABLE`、`IMPORT_FAILED`、`RUN_STATE_CONFLICT`、`CHECKPOINT_MAPPING_REQUIRED`、`STORAGE_QUOTA_EXCEEDED`。

### 5.4 幂等与并发

创建导入、Run、分享、绘图和导出支持 `Idempotency-Key`。停止/撤销为天然幂等命令。更新可变元数据使用 ETag/`If-Match`；不可变版本不提供内容 PATCH。

### 5.5 时间、单位和数值

时间均为 UTC RFC3339，前端本地化显示。指标使用 JSON number；NaN/Infinity 转为 null 并附质量标记。单位使用标准字符串并在 DatasetVersion 中冻结。

## 6. API 分组

### 6.1 认证和用户

```text
POST   /auth/login
POST   /auth/refresh
POST   /auth/logout
GET    /me
GET    /me/preferences
PATCH  /me/preferences
POST   /admin/invitations
POST   /invitations/{token}/accept
```

### 6.2 运行中心

```text
GET /dashboard/summary
GET /compute/gpus
GET /runs?status=...
GET /activity
GET /events/dashboard          # SSE，可选；也可聚合各 Run 事件
```

### 6.3 文件夹与数据

```text
GET/POST   /folders
PATCH/DELETE /folders/{id}
GET/POST   /datasets
GET        /datasets/{id}
GET        /datasets/{id}/versions
POST       /dataset-imports                 # 创建 upload/url/derive job
POST       /dataset-imports/{id}/parts      # 分片签名/登记
POST       /dataset-imports/{id}/complete
GET        /dataset-imports/{id}
POST       /dataset-imports/{id}/confirm-mapping
POST       /dataset-imports/{id}/retry
POST       /dataset-imports/{id}/cancel
```

浏览器通过短期预签名 URL 直传 S3-compatible storage；服务端完成后验证大小、摘要和 manifest。签名必须在 HydroLab Policy 通过后生成。

### 6.4 代码、模板和环境

```text
GET/POST /code-repositories
POST     /code-imports                       # zip/git
GET      /code-imports/{id}
GET      /code-versions/{id}
GET/POST /code-versions/{id}/templates
GET/PATCH /template-versions/{id}
GET/POST /runtime-environments
POST     /runtime-environments/{id}/versions
GET      /environment-versions/{id}
GET      /environment-versions/{id}/build-events  # SSE
```

Git 认证使用一次性凭证引用，不接受命令行字符串。

### 6.5 实验、草稿和 Run

```text
POST      /experiment-drafts
GET/PATCH /experiment-drafts/{id}
POST      /experiment-drafts/{id}/validate
POST      /experiments
GET       /experiments
GET       /experiments/{id}
GET       /experiments/{id}/versions
POST      /experiments/{id}/versions
GET       /experiments/{id}/runs
POST      /experiment-versions/{id}/runs
GET       /runs/{id}
POST      /runs/{id}/cancel
POST      /runs/{id}/rerun
POST      /runs/{id}/retry-stage
GET       /runs/{id}/events                 # SSE
GET       /runs/{id}/logs?cursor=...
GET       /runs/{id}/metrics
```

`validate` 返回字段错误、兼容性问题、配额、预计资源和可提交标记，不产生 Run。

### 6.6 Checkpoint

```text
GET  /checkpoints
GET  /checkpoints/{id}
POST /checkpoints/{id}/compatibility-checks
POST /checkpoints/{id}/reuse
GET  /checkpoints/{id}/derived-runs
```

`reuse` 请求包含用途、目标数据/环境/模板、参数覆盖和已确认 repair_plan；服务端重新检查后创建 Run。

### 6.7 结果、诊断、绘图和导出

```text
GET  /results
GET  /results/{run_id}
GET  /results/{run_id}/metrics
GET  /results/{run_id}/basins
GET  /results/{run_id}/basins/{basin_id}/diagnostics
GET  /results/{run_id}/basins/{basin_id}/events
GET  /results/{run_id}/artifacts
POST /result-comparisons/validate
POST /result-comparisons/query
POST /plot-plans/parse
POST /plot-jobs
GET  /plot-jobs/{id}
POST /export-jobs
GET  /export-jobs/{id}
GET  /artifacts/{id}/download-url
```

`query` 接受 2–5 个 Run 和 baseline_run_id，返回四区 ViewModel 所需数据；不默认持久化。

### 6.8 分享

```text
POST   /share-links
GET    /share-links
POST   /share-links/{id}/revoke
GET    /shared/{token}
GET    /shared/{token}/artifacts/{id}/download-url
```

公开 token 接口限流、防枚举、只返回白名单字段，并校验过期/撤销/锁定版本。

## 7. SSE 事件契约

事件拥有 `id`、`type`、`occurred_at`、`run_id`、`payload`。核心类型：

```text
run.status.changed
run.stage.changed
run.progress.updated
run.metric.reported
run.log.available
run.resource.sampled
run.artifact.created
run.failed
run.completed
```

`run.progress.updated` 包含 stage、epoch/batch current/total、percent、ETA。SSE 仅传日志游标/尾部片段，不持续推送完整日志。服务端保留可恢复事件；超过保留窗口返回快照并从最新位置继续。

## 8. 异步任务与一致性

### 8.1 Transactional Outbox

创建 Run、导入、构建、绘图和导出时，业务记录与 Outbox 同事务写入。发布器将 Outbox 投递 Celery，避免“数据库已提交但任务未投递”。消费者按 job_id 幂等。

### 8.2 对象上传两阶段提交

Artifact 先为 `PENDING_UPLOAD`，上传完成后校验 sha256/size，再进入 `READY`；失败对象隔离并按生命周期清理。数据库不保存未经验证的对象为可下载状态。

### 8.3 MLflow

PostgreSQL 是业务真相源；MLflow 是 `ExperimentTracker` 的可替换实现。Run 保存 `mlflow_run_id`，同步失败可重试，不让 MLflow 状态反向覆盖业务状态。Adapter 禁用时使用 Fake/Noop，核心 Run 链路仍可执行。

### 8.4 Celery 与消息投递

Celery 是 `TaskQueue` 的实现，不是 Run 状态机。消息只携带稳定 ID 和版本化 envelope；消费者重新读取数据库并按 job_id/attempt 幂等。Celery task ID 仅作关联，revoke 只发出取消信号，最终终态由 HydroLab 与 Runner 确认。

### 8.5 S3 对象存储

S3 Adapter 负责 multipart、预签名、HEAD、range、copy 和删除；Artifact READY、sha256、manifest、权限与血缘仍由 HydroLab 管理。MinIO 是可替换部署产品，而不是业务 API。

## 9. Runner 安全契约

API 生成规范化 `RunSpec`，只能引用服务端解析的资源 ID：

- 镜像必须在 digest 白名单。
- 代码、数据、初始权重只读挂载；输出独立可写。
- 非 root、无 privileged、无 host network、无 Docker Socket、drop capabilities。
- 默认禁网，CPU/内存/PID/GPU/磁盘/时长限制。
- 命令来自已审核模板，参数按 Schema 编码；禁止 shell 拼接用户输入。
- 每个 Run 唯一工作目录；结束后计算产物哈希再上传。
- GPU 租约、Runner 心跳和终止回收需可审计。

## 10. 数据库迁移与索引

迁移按领域分批，禁止启动时自动 `create_all`。关键索引：

- 所有 owner/status/created_at 列表组合。
- 资源版本 `(resource_id, version_no)` 唯一。
- Dataset/Code content_hash 用于去重提示，不跨用户自动共享权限。
- `run_events(run_id, event_seq)` 唯一。
- `metric_points(run_id, name, split, basin_id, step)`。
- `gpu_leases(gpu_id)` 活跃唯一。
- 分享 token_hash 唯一，expires/revoked 索引。

Run events、metrics、resource samples 按时间或 run 哈希分区并制定保留策略；业务元数据长期保留。

## 11. 安全与审计

- 密码/Token/凭证只保存安全哈希或 Secret 引用。
- ZIP 防路径穿越、符号链接逃逸和压缩炸弹；限制文件数、展开大小与单文件大小。
- URL 下载限制 scheme、DNS 重绑定、内网地址、重定向次数和总大小，防 SSRF。
- Git URL 白名单协议，凭证脱敏。
- 审计管理员、授权、分享、下载、Run 控制、环境构建和删除动作。
- 日志脱敏，不记录分享 token、Git token、Cookie 和完整环境 Secret。
- CORS 仅允许部署域名；Cookie 使用 HttpOnly/Secure/SameSite。

## 12. OpenAPI 与前端类型

FastAPI OpenAPI 是 REST Schema 唯一来源。CI 导出 `packages/contracts/openapi.json` 并检查破坏性变更；前端生成客户端或使用严格封装。事件 JSON Schema 独立版本化。原型中文文案不写入稳定枚举。
