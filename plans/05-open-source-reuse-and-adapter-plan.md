# HydroLab 开源复用与 Adapter 准入方案

> 状态：Confirmed  
> 最后更新：2026-08-29  
> 适用范围：后端领域端口、基础设施适配器、模型执行器与后续扩展准入  
> 核心原则：成熟底层能力尽量复用，HydroLab 业务语义必须自有。

<!-- anchor:decision-summary -->
## 1. 决策摘要

| 候选 | 决策 | HydroLab 用途 | 首次准入阶段 |
|---|---|---|---|
| S3 协议 + boto3 | ADOPT + WRAP | 数据、代码、日志、Checkpoint、结果、导出对象 | B0 Fake，B2 真实 Spike |
| Celery + Redis | WRAP | Outbox 后的异步任务投递 | B0 Fake，B4/B5 真实 Spike |
| MLflow Tracking | WRAP | 参数、指标、模型与技术 Artifact 跟踪 | B0 Fake，B6 真实 Spike |
| NeuralHydrology | WRAP | 水文模型训练、评估、配置和产物解析 | B3 契约，B6/B7 Spike |
| Darts | DEFER | 通用时序基线、概率预测、回测 | B8 后按需求 Spike |
| Optuna | DEFER → WRAP | 超参数建议、剪枝和 Study 管理 | MVP 后 |
| DVC | REFERENCE / DEFER | 外部 DVC 仓库导入导出桥接 | MVP 后 |
| ClearML | REFERENCE | 借鉴 Agent、队列、远程执行设计 | 不接入运行时 |
| Kubeflow | REJECT（当前）/ REFERENCE（未来） | 借鉴 Job、Pipeline、元数据分层 | 多节点 Kubernetes 前不启用 |
| Ray | DEFER / REFERENCE | 多节点逻辑资源调度 | 单机双 GPU 阶段不启用 |

`ADOPT` 表示采用稳定协议或服务；`WRAP` 表示只能通过 HydroLab 端口接入；`REFERENCE` 表示只借鉴设计；`DEFER` 表示延后；`REJECT` 表示当前架构不使用。

<!-- anchor:ownership-boundary -->
## 2. 不可外包的业务边界

以下能力必须由 HydroLab PostgreSQL、领域服务和 Policy 维护，任何开源组件都不得成为业务真相源：

- User、Invitation、Session、ResourceGrant、ShareLink 与审计。
- DatasetVersion、CodeVersion、TemplateVersion、EnvironmentVersion 的不可变语义。
- Experiment、ExperimentVersion、Run 与 Run 状态机。
- Transactional Outbox、幂等键和跨资源权限检查。
- `GpuLease`、业务优先级、取消语义与孤儿 Run 收敛。
- Checkpoint 架构/输入输出/Scaler 兼容性及显式 repair plan。
- Result 索引、多 Run 对比、PlotSpec、Export manifest 与科研血缘。

外部 ID 只能作为关联字段：

```text
HydroLab Run.id          ↔ mlflow_run_id
HydroLab Outbox/job.id   ↔ celery_task_id
HydroLab Artifact.id     ↔ s3 bucket/object_key/version_id
HydroLab Run.id          ↔ framework native run directory
HydroLab OptimizationRun ↔ optuna trial number
```

外部系统状态可作为观测信号，不能直接覆盖 HydroLab 状态。

<!-- anchor:ports -->
## 3. 统一端口与 Fake-first 结构

```python
class ObjectStorage(Protocol):
    def create_upload(self, request: UploadRequest) -> UploadSession: ...
    def complete_upload(self, session_id: str, parts: list[UploadedPart]) -> ObjectInfo: ...
    def head(self, ref: ObjectRef) -> ObjectInfo: ...
    def open_range(self, ref: ObjectRef, start: int, end: int | None) -> BinaryIO: ...
    def copy(self, source: ObjectRef, target: ObjectRef) -> ObjectInfo: ...
    def create_download_url(self, ref: ObjectRef, expires_in: int) -> str: ...
    def delete_quarantined(self, ref: ObjectRef) -> None: ...

class TaskQueue(Protocol):
    def enqueue(self, envelope: TaskEnvelope) -> EnqueueReceipt: ...
    def revoke(self, external_task_id: str) -> None: ...

class ExperimentTracker(Protocol):
    def start_run(self, context: TrackingContext) -> ExternalRunRef: ...
    def log_parameters(self, run: ExternalRunRef, values: dict) -> None: ...
    def log_metrics(self, run: ExternalRunRef, points: list[MetricRecord]) -> None: ...
    def log_artifact_reference(self, run: ExternalRunRef, artifact: ArtifactReference) -> None: ...
    def finish_run(self, run: ExternalRunRef, status: str) -> None: ...

class ModelFrameworkAdapter(Protocol):
    def validate(self, request: FrameworkRunRequest) -> ValidationReport: ...
    def materialize(self, request: FrameworkRunRequest, workdir: Path) -> MaterializedRun: ...
    def command(self, run: MaterializedRun) -> list[str]: ...
    def parse_event(self, line: str) -> list[NormalizedRunEvent]: ...
    def collect_outputs(self, workdir: Path) -> FrameworkOutputs: ...

class OptimizationAdapter(Protocol):
    def ask(self, study_id: str) -> TrialSuggestion: ...
    def report(self, trial_id: str, metric: MetricRecord) -> PruneDecision: ...
    def tell(self, trial_id: str, outcome: TrialOutcome) -> None: ...
```

首批实现顺序：

```text
FakeObjectStorage / LocalFilesystemObjectStorage
FakeTaskQueue
FakeExperimentTracker
FakeRunExecutor
→ 领域与 API 单元/契约测试
→ S3ObjectStorageAdapter
→ CeleryTaskQueueAdapter
→ MlflowTrackingAdapter
→ DockerGpuRunExecutor
→ NeuralHydrologyAdapter
```

Fake 必须模拟失败、重复投递、超时、断线和部分成功，而不只是 happy path。

<!-- anchor:s3 -->
## 4. S3 协议与 MinIO 部署产品

### 4.1 决策

- 协议：`ADOPT` S3 API。
- 客户端：`WRAP` boto3/botocore 为 `S3ObjectStorageAdapter`。
- 部署：生产可使用 MinIO 或其他 S3-compatible 服务，不让业务代码绑定某个厂商。
- SDK 选择：首选 boto3；只有经 Spike 证明存在不可替代能力时才增加 MinIO Python SDK。

AWS 官方文档确认 boto3 支持有时效的预签名下载和预签名上传，适合浏览器绕过 API 直传/直下。<kreference link="https://docs.aws.amazon.com/boto3/latest/guide/s3-presigned-urls.html" index="1">[^1]</kreference>

### 4.2 可复用能力

- multipart upload、预签名上传/下载。
- `HEAD`、range GET、server-side copy、对象 metadata。
- bucket/object versioning（若部署产品支持且开启）。
- 生命周期清理和服务端加密。

### 4.3 不委托能力

- 资源授权不能等同 bucket policy；先过 HydroLab Policy 才能签名。
- `DatasetVersion`、Artifact READY 状态、sha256、manifest 和血缘仍在 PostgreSQL。
- 分享链接不能直接暴露永久对象 URL。

### 4.4 Spike S3-01

验证：5 GB 以上 multipart、失败续传、完成后二次 `HEAD`、sha256/size 校验、range 下载、服务端 copy、短期 URL 过期、非法 key、删除隔离区、MinIO 与至少一个标准 S3 模拟环境的契约一致性。

准入标准：同一套 `ObjectStorage` contract tests 对 Fake、LocalFilesystem、S3 全部通过；失败上传不会生成 READY Artifact；凭证不进入日志。

回退：本地开发使用 `LocalFilesystemObjectStorage`；生产若 MinIO 产品/许可不满足要求，可切换任一通过 S3 Spike 的对象存储。

许可与版本：boto3 使用 Apache-2.0；MinIO Server 的部署许可及社区版功能必须在选定镜像时单独复核，计划不把未核实的 MinIO 版本写死。

<!-- anchor:celery -->
## 5. Celery + Redis

### 5.1 决策

`WRAP` 为 `CeleryTaskQueueAdapter`，只承担消息投递和 Worker 唤醒。Celery 官方说明任务可能重投，`acks_late` 要求任务幂等；worker 子进程丢失时若要重投还需评估 `task_reject_on_worker_lost`。<kreference link="https://docs.celeryq.dev/en/stable/userguide/tasks.html" index="2">[^2]</kreference>

### 5.2 消息契约

```json
{
  "schema_version": 1,
  "job_id": "uuid",
  "job_type": "run.execute",
  "resource_id": "uuid",
  "attempt": 1,
  "correlation_id": "uuid",
  "not_before": "RFC3339"
}
```

消息只传稳定 ID，不传 ORM 对象、Secret、大文件或完整配置；Worker 启动后重新读取数据库并校验当前状态。

### 5.3 可靠性规则

- Outbox 发布至少一次；消费者以 `job_id + attempt` 幂等。
- Celery 状态与 result backend 不作为 Run 真相源。
- 只对临时依赖错误指数退避；配置错误、权限错误、模型错误不自动重试。
- 长训练任务不在 Celery 子进程内直接执行；Celery 调应用服务，由 Runner 管理外部容器。
- revoke 只是取消信号，最终取消结果由 HydroLab 状态机、Runner 心跳与容器退出共同确认。
- 训练任务使用低 prefetch 的独立队列；短导入/绘图任务与长任务隔离。

### 5.4 Spike QUEUE-01

覆盖发布后崩溃、消费前崩溃、执行中 worker kill、重复消息、Redis 短时不可用、visibility timeout、revoke、API/Worker 重启和 Outbox 重扫。

准入标准：不丢业务 Job；重复投递最多启动一个有效 Runner；终态可收敛；Celery task ID 变化不改变 Run ID。

回退：`FakeTaskQueue` 用于测试；单机受控部署可临时使用数据库轮询 Worker，但接口不变。

许可与版本：Celery 为 BSD-3-Clause；当前稳定文档为 5.6 系列，patch 版本和 Redis transport 参数在 Spike 后锁定。

<!-- anchor:mlflow -->
## 6. MLflow Tracking

### 6.1 决策

`WRAP` 为 `MlflowTrackingAdapter`。MLflow Tracking 提供 Run、参数、指标、数据集和 Artifact/模型跟踪，适合作为技术跟踪子系统。<kreference link="https://mlflow.org/docs/latest/ml/tracking/" index="3">[^3]</kreference>

MLflow 仓库许可证为 Apache-2.0。<kreference link="https://raw.githubusercontent.com/mlflow/mlflow/master/LICENSE.txt" index="4">[^4]</kreference>

### 6.2 映射

```text
HydroLab ExperimentVersion → MLflow experiment tags
HydroLab Run               → MLflow run
resolved parameters        → MLflow params（扁平化且限制长度）
MetricPoint                → MLflow metrics
Artifact                   → 优先记录 HydroLab Artifact URI/hash；避免无规则双写大文件
Checkpoint                 → MLflow model/checkpoint metadata + HydroLab checkpoint_id tag
```

### 6.3 边界

- PostgreSQL 是 Run、权限、版本和 Artifact 索引真相源。
- MLflow 故障不得把已成功训练改成 FAILED；同步记录独立状态并可重放。
- Web 前端不直接调用 MLflow；所有查询通过 HydroLab API 和 Policy。
- 不把 MLflow Experiment 等同 HydroLab Experiment。

### 6.4 Spike TRACK-01

验证创建/恢复 Run、批量指标、重复写、多个 Checkpoint、S3 Artifact URI、MLflow 重启、网络失败后重放、搜索和删除策略。

准入标准：适配器失败可重试且不阻塞业务事件持久化；重放不产生第二个 MLflow Run；可由 HydroLab Run 定位 MLflow Run，反向亦可。

回退：`FakeExperimentTracker` 或 `NoopExperimentTracker`；核心平台仍可运行，待服务恢复后补同步。

版本：采用独立依赖组和单独服务镜像；Python/数据库/S3 兼容矩阵在 TRACK-01 后固定，不在计划阶段猜测 patch 版本。

<!-- anchor:neuralhydrology -->
## 7. NeuralHydrology

### 7.1 决策

`WRAP` 为 `NeuralHydrologyAdapter`，作为首个水文领域模型执行适配器。官方快速入门提供配置驱动的 `nh-run train/evaluate`、多配置调度和结果集成能力。<kreference link="https://neuralhydrology.readthedocs.io/en/latest/usage/quickstart.html" index="5">[^5]</kreference>

仓库许可证为 BSD-3-Clause。<kreference link="https://raw.githubusercontent.com/neuralhydrology/neuralhydrology/master/LICENSE" index="6">[^6]</kreference>

### 7.2 包装流程

```text
ExperimentVersion + DatasetVersion + resolved config
→ 校验字段/频率/流域/时期
→ 生成只读 config.yml
→ argv: nh-run train/evaluate ...
→ 解析 stdout、run directory、metrics、predictions
→ 标准化 RunEvent/Checkpoint/Scaler/Result/Artifact
```

### 7.3 边界

- 不使用 `nh-schedule-runs` 替代 HydroLab `GpuLease` 和队列。
- 不让框架目录结构成为平台 Artifact Schema；通过 collector 归一化。
- 不静默加载形状不一致的权重。
- 数据集下载、用户权限、环境构建、Run 状态仍由平台管理。

### 7.4 Spike NH-01

使用小型公开/合成流域数据完成训练、评估、断点恢复、跨数据微调、预测和产物抽取；验证 NSE/KGE/RMSE 映射、Scaler、epoch checkpoint、失败日志和 CPU fallback。

准入标准：同一 RunSpec 可重放；配置完全归档；平台能识别 checkpoint 与预测；进度无法结构化时至少降级到阶段/进程级；不依赖框架内 GPU scheduler。

回退：继续支持通用 `CommandTemplateAdapter + JSONL Progress v1`，NeuralHydrology 只是可选模板能力。

版本：单独运行环境镜像固定 NeuralHydrology、PyTorch、CUDA 和 Python；由 NH-01 在目标 4090 镜像上产出兼容矩阵和 digest。

<!-- anchor:darts -->
## 8. Darts

### 8.1 决策

`DEFER`，MVP 后按通用时序需求实现 `DartsAdapter`。Darts 提供统一 fit/predict、协变量、概率预测、回测、集成和深度模型能力。<kreference link="https://unit8co.github.io/darts/" index="7">[^7]</kreference>

仓库许可证为 Apache-2.0。<kreference link="https://raw.githubusercontent.com/unit8co/darts/master/LICENSE" index="8">[^8]</kreference>

### 8.2 未来复用

- 朴素、统计和机器学习基线。
- 多序列/global model、past/future/static covariates。
- backtesting 与 probabilistic forecast。

不把 Darts `TimeSeries` 作为平台持久化模型；Adapter 负责 DatasetVersion 与 TimeSeries 的显式转换、频率/缺失/时区校验和预测 Artifact 归一化。

Spike DARTS-01：在相同 DatasetVersion 上跑 naive、统计、深度三类模型，验证协变量、概率分位数、回测和 GPU 环境体积。

启用门槛：用户需要通用基线或概率预测，且额外镜像与依赖成本可接受。回退为通用命令模板。

<!-- anchor:optuna -->
## 9. Optuna

### 9.1 决策

`DEFER → WRAP` 为 `OptunaAdapter`。采用 Ask-and-Tell，而不是让 Optuna 包裹并直接执行训练。官方文档确认 `Study.ask()`/`tell()` 可嵌入已有训练流程并支持中间值和剪枝。<kreference link="https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/009_ask_and_tell.html" index="9">[^9]</kreference>

仓库许可证为 MIT。<kreference link="https://raw.githubusercontent.com/optuna/optuna/master/LICENSE" index="10">[^10]</kreference>

### 9.2 未来流程

```text
OptimizationStudy
→ adapter.ask()
→ 创建标准 HydroLab Run
→ MetricPoint → adapter.report()/should_prune()
→ 平台取消 Runner 或等待终态
→ adapter.tell(COMPLETE/FAIL/PRUNED)
```

Optuna 不拥有 Run、GPU、权限、Artifact 或取消。Study 与 Trial 映射必须存入 HydroLab 数据库，外部 storage 只是优化器状态。

Spike OPT-01：PostgreSQL 持久化、多 worker ask/tell、worker 丢失、heartbeat、重复 tell、剪枝竞态、Study 恢复和参数 Schema 映射。

回退：平台继续支持用户手动创建多 Run 对比；不影响 MVP。

<!-- anchor:dvc -->
## 10. DVC

### 10.1 决策

`REFERENCE / DEFER`，只考虑外部同步桥，不作为内部版本系统。DVC remote 可连接 S3/MinIO 等存储并同步大文件/目录。<kreference link="https://dvc.org/doc/user-guide/data-management/remote-storage" index="11">[^11]</kreference>

### 10.2 可选桥接

- 从指定 Git commit + `.dvc`/`dvc.lock` 导入，转换为 HydroLab DatasetVersion/CodeVersion。
- 导出 manifest，供已有 DVC 工作流消费。
- 凭证仅通过 Secret 引用注入隔离 Import Worker。

禁止：让 DVC cache/hash 直接充当 HydroLab 授权、浏览器上传、Artifact 索引或 DatasetVersion 真相源。

Spike DVC-01 只有出现真实用户需求才启动；CLI 隔离优先于不稳定的内部 Python API。回退为标准 ZIP/Git/URL/S3 导入。

<!-- anchor:clearml -->
## 11. ClearML

### 11.1 决策

`REFERENCE`，不引入 ClearML Server/Agent 作为运行时依赖。

可借鉴：Agent 拉取任务、队列分类、远程执行、环境捕获、实验/Artifact 联动。不得复用其完整 UI、权限模型、Task 状态或队列作为 HydroLab 业务层，否则会与既定原型和领域模型形成双重真相。

许可证与组件边界必须在任何代码复用前按具体仓库和版本重新核验；本次未获得稳定的官方架构页面，因此不作未验证断言。仅阅读其公开设计不构成运行时依赖。

未来触发条件：若自研 Runner Controller 的运维成本经实测不可接受，再做 CLEARML-01 对比 Spike；对比项为权限、离线/断网恢复、双 GPU 租约、容器隔离、定制 UI 和迁移成本。

<!-- anchor:kubeflow -->
## 12. Kubeflow

### 12.1 决策

当前 `REJECT`，未来多节点 Kubernetes 阶段 `REFERENCE`。Kubeflow 官方架构明确建立在 Kubernetes 之上，并由多个训练、流水线、调优、Notebook 等子项目组成。<kreference link="https://www.kubeflow.org/docs/started/architecture/" index="12">[^12]</kreference>

对于单 Ubuntu 服务器和两张固定 RTX 4090，引入 Kubernetes、CRD、控制器和整套平台会显著增加部署、备份、升级和故障面，且重复现有 HydroLab UI/权限/Run 语义。

可借鉴：声明式 Job、阶段化 Pipeline、控制面/执行面隔离、元数据与 Artifact 分离。

重评门槛：多 GPU 节点、分布式训练、弹性扩缩、租户隔离已成为刚需。届时另建 K8s Spike，不在现有 Runner 端口中泄露 Kubernetes 类型。

<!-- anchor:ray -->
## 13. Ray

### 13.1 决策

单机双 GPU 阶段 `DEFER / REFERENCE`。Ray 支持逻辑 CPU/GPU/custom resources，并可为 GPU task/actor 设置可见设备；官方同时说明这些是逻辑资源而非物理隔离。<kreference link="https://docs.ray.io/en/latest/ray-core/scheduling/resources.html" index="13">[^13]</kreference>

因此 Ray 不能替代：

- Docker 非 root、挂载和网络隔离。
- HydroLab `GpuLease`、权限、优先级和取消审计。
- Run 状态、Outbox 与 Artifact 一致性。

当前采用 PostgreSQL `GpuLease` + Runner Controller 更简单。重评条件为多节点、分布式训练、Actor 服务或动态集群调度。Spike RAY-01 必须与现有 Runner 在故障恢复、显存隔离、容器集成和运维复杂度上量化对比。

<!-- anchor:compatibility -->
## 14. 许可、维护与版本治理

### 14.1 准入清单

每个真实 Adapter 合并前必须保存：

- 官方仓库、文档、LICENSE/NOTICE 链接。
- 固定版本、发布日期、最后维护活动和已知安全公告。
- Python、操作系统、数据库、PyTorch、CUDA、NVIDIA Driver 兼容矩阵。
- 锁文件、容器 digest、SBOM 和许可证扫描结果。
- 升级/降级测试与数据迁移说明。

### 14.2 固定策略

- 应用依赖固定到已验证 minor/patch；容器固定 digest，不使用 `latest`。
- ML 框架依赖按 RuntimeEnvironmentVersion 隔离，避免 API 进程安装 PyTorch/CUDA。
- Adapter 对外只暴露 HydroLab DTO；第三方类型不得穿透领域层。
- 每季度或安全公告触发升级评估；升级先跑 contract tests 和对应 Spike 回归。
- 未能验证的兼容范围统一标记为“版本在 Spike 后固定”，不能写成已支持。

<!-- anchor:spike-gates -->
## 15. Spike 门禁与实施顺序

| 门禁 | 阶段前置 | 必须通过的 Spike |
|---|---|---|
| G0 纯代码基线 | B0 | Fake adapters、状态机、错误、OpenAPI；不要求外部服务 |
| G1 对象存储 | B2 真实上传 | S3-01 |
| G2 队列/Runner | B5 真实执行 | QUEUE-01 + Runner 安全 Spike |
| G3 跟踪 | B6 MLflow | TRACK-01 |
| G4 水文适配 | 对外提供 NeuralHydrology 模板 | NH-01 |
| G5 扩展能力 | MVP 后 | DARTS-01 / OPT-01 / DVC-01 按需 |
| G6 集群化 | 多节点前 | RAY-01 或独立 Kubeflow/K8s Spike |

执行顺序：

```text
领域端口与 DTO
→ Fake/Local adapters
→ 单元与 contract tests
→ API/业务纵向切片
→ 对应 Spike
→ 真实 Adapter
→ staging/cloud 验收
```

外部服务不可用只阻塞相应真实 Adapter 的准入，不阻塞领域代码、Fake 集成、OpenAPI、迁移和前端契约开发。

<!-- anchor:acceptance -->
## 16. 总体验收条件

- 所有业务服务仅依赖端口，不直接 import boto3、celery、mlflow、optuna、darts 或 neuralhydrology。
- 每个 WRAP 项都有 Fake、contract tests、故障注入和禁用开关。
- 第三方服务不可用时，错误被映射为稳定 HydroLab 错误码，不泄露内部异常。
- 外部 ID、版本和同步状态可审计。
- 没有组件绕过 Policy 获取对象或启动 Runner。
- 没有第三方状态反向覆盖业务真相。
- 所有真实版本均在 Spike 后写入锁文件和镜像 digest。

## 17. 官方来源

[^1]: https://docs.aws.amazon.com/boto3/latest/guide/s3-presigned-urls.html
[^2]: https://docs.celeryq.dev/en/stable/userguide/tasks.html
[^3]: https://mlflow.org/docs/latest/ml/tracking/
[^4]: https://raw.githubusercontent.com/mlflow/mlflow/master/LICENSE.txt
[^5]: https://neuralhydrology.readthedocs.io/en/latest/usage/quickstart.html
[^6]: https://raw.githubusercontent.com/neuralhydrology/neuralhydrology/master/LICENSE
[^7]: https://unit8co.github.io/darts/
[^8]: https://raw.githubusercontent.com/unit8co/darts/master/LICENSE
[^9]: https://optuna.readthedocs.io/en/stable/tutorial/20_recipes/009_ask_and_tell.html
[^10]: https://raw.githubusercontent.com/optuna/optuna/master/LICENSE
[^11]: https://dvc.org/doc/user-guide/data-management/remote-storage
[^12]: https://www.kubeflow.org/docs/started/architecture/
[^13]: https://docs.ray.io/en/latest/ray-core/scheduling/resources.html
