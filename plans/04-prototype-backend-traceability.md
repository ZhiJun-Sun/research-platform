# HydroLab 原型—后端追踪矩阵

> 状态：Confirmed  
> 用途：保证每个原型交互都有真实后端归属，并指导逐页替换 Mock。

## 1. 运行中心

| 原型区域/操作 | 后端真相源 | API / 事件 | 异步任务 | 关键验收 |
|---|---|---|---|---|
| 当前训练任务 | Run、ExperimentVersion、MetricPoint | `GET /runs`、Run SSE | Runner | 状态/阶段/指标一致，刷新可恢复 |
| GPU 摘要与抽屉 | GpuLease、ResourceSample | `GET /compute/gpus`、resource event | Runner heartbeat | 不显示过期租约，双卡不重复分配 |
| 等待队列与 ETA | Run priority、队列快照 | `GET /dashboard/summary` | Scheduler | 排序稳定，ETA 标记为估算 |
| 最近活动 | AuditLog、领域事件 | `GET /activity` | event projector | 仅返回用户有权资源 |
| 新手清单 | UserPreference + 资源存在性 | `GET/PATCH /me/preferences` | 无 | 可隐藏/恢复，完成态由真实资源计算 |
| 创建实验 | ExperimentDraft | Draft API | 无 | 向导/高级模式共享草稿 |

## 2. 数据

| 原型区域/操作 | 后端实体 | API | 异步任务/事件 | 关键验收 |
|---|---|---|---|---|
| 文件夹树 | AssetFolder | `/folders` | 无 | 防循环，移动不改变资源授权 |
| 全局搜索 | Dataset、DatasetVersion | `GET /datasets?q=` | 可选索引器 | 分页、权限过滤、稳定排序 |
| 本地上传 | ImportJob、Artifact | `/dataset-imports`、parts、complete | 校验/解析 Worker | 直传、摘要、失败不产生 READY 版本 |
| URL 下载 | ImportJob | `/dataset-imports` | Download Worker | SSRF 防护、大小限制、取消/重试 |
| 版本派生 | DatasetVersion parent | `/dataset-imports` | Derive Worker | 新版本、完整血缘、旧版本不变 |
| 自动字段识别 | FieldMapping draft | `GET /dataset-imports/{id}` | Probe Worker | 返回置信度和待确认项 |
| 编辑并确认映射 | FieldMapping、DatasetVersion | `POST .../confirm-mapping` | Finalize Worker | 后端校验唯一时间/目标规则 |
| 详情/版本/血缘/使用 | DatasetVersion、LineageEdge | dataset detail APIs | 无 | 精确版本和内容 hash 可追溯 |
| 分享资源 | ShareLink | `/share-links` | 无 | 版本锁定、只读、过期/撤销 |

## 3. 模型代码与运行环境

| 原型区域/操作 | 后端实体 | API | 异步任务 | 关键验收 |
|---|---|---|---|---|
| ZIP/Git 导入 | CodeRepository、CodeVersion、ImportJob | `/code-imports` | Scan Worker | 防穿越/泄露，锁定 commit/hash |
| 代码详情 | CodeVersion | `/code-versions/{id}` | 无 | 只读快照、环境/模板关系正确 |
| 训练/评估/预测/绘图模板 | TemplateVersion | `/code-versions/{id}/templates` | Discovery Worker | task_type 清晰，命令不接受 shell 拼接 |
| 编辑命令与参数 | ParameterSchema | `PATCH /template-versions/{id}` | Validation Worker | 创建新模板版本，不覆写冻结版本 |
| 动态参数/预设 | ParameterPreset | parameter preset API（B3 细化） | 无 | 类型、范围、映射均服务端验证 |
| 环境列表 | EnvironmentVersion | `/runtime-environments` | 无 | 精确 digest 和构建状态 |
| 创建环境 | EnvironmentVersion | `POST .../versions` | Build Worker | API 无 Docker 权限，日志可追踪 |

## 4. 实验与 Run

| 原型区域/操作 | 后端实体 | API / 事件 | 异步任务 | 关键验收 |
|---|---|---|---|---|
| 实验列表 | Experiment、current Version | `GET /experiments` | 无 | 不将 Run 当 Experiment |
| 实验详情配置摘要 | ExperimentVersion | `GET /experiments/{id}` | 无 | 锁定 code/data/template/environment |
| Run 历史与参数差异 | Run.resolved_parameters | `GET /experiments/{id}/runs` | 无 | 返回相对默认配置 diff |
| 创建实验草稿 | ExperimentDraft | Draft CRUD/validate | 无 | 模式切换/刷新不丢数据 |
| 创建并进入队列 | ExperimentVersion、Run、Outbox | `POST /experiments` 或 `/.../runs` | Scheduler | 幂等、事务性投递、越权预检 |
| 失败 Run 提示 | RunStage、Error | `GET /runs/{id}` | Runner | 保留失败阶段、错误、日志和产物 |
| 从失败阶段重试 | 新 Run + retry link | `POST /runs/{id}/retry-stage` | Runner | 不可安全重试时服务端拒绝 |
| 复制/重新运行 | 新 Run | `POST /runs/{id}/rerun` | Runner | 旧 Run 不变，resolved config 可审计 |

## 5. Run 详情

| 原型卡片/操作 | 后端数据 | API / SSE | 关键验收 |
|---|---|---|---|
| 阶段条 | Run.status/stage、RunStage | REST 快照 + `run.stage.changed` | 终态不可回退 |
| Epoch/Batch/ETA | RunEvent | `run.progress.updated` | 断线续接，不重复 |
| Loss/NSE/KGE/RMSE | MetricPoint | metrics API + `run.metric.reported` | step/split/basin 语义明确 |
| 实时日志 | Log Artifact、cursor | logs API + `run.log.available` | 不把完整日志塞 SSE |
| GPU 资源 | ResourceSample、Lease | resource event | 只显示实际容器采样 |
| 参数和数据血缘 | resolved config、LineageEdge | Run detail | 可追溯所有精确版本 |
| 停止 | Run command | `POST /runs/{id}/cancel` | 幂等，释放资源 |
| 拖拽布局 | UserPreference/localStorage | 后续 preferences API | 不影响 Run 业务真相 |

## 6. Checkpoint

| 原型区域/操作 | 后端实体 | API | 异步任务 | 关键验收 |
|---|---|---|---|---|
| 权重详情 | Checkpoint、Artifact、Scaler | `GET /checkpoints/{id}` | Metadata extractor | digest、架构、IO、优化器齐全 |
| 派生运行 | LineageEdge / Run | `/derived-runs` | 无 | resume/finetune/evaluate/predict 可区分 |
| 复用模式 | CompatibilityCheck | `POST /compatibility-checks` | 可选检查 Worker | 使用目标版本重新计算兼容性 |
| 显式修复 | RepairPlan | `POST /checkpoints/{id}/reuse` | Runner | 未修复不可提交；方案进入 provenance |

## 7. 结果与对比

| 原型区域/操作 | 后端实体 | API | 异步任务 | 关键验收 |
|---|---|---|---|---|
| 结果索引 | Result、Run | `GET /results` | Result indexer | 服务端筛选/排序/分页 |
| 总览指标 | Result.summary_metrics | `GET /results/{run_id}` | Evaluator | 指标版本和数据范围明确 |
| 标准图 | Artifact、PlotSpec | results detail | Plot Worker | 图/数据/配置/脚本/哈希齐全 |
| 逐流域表 | BasinMetric | `/basins` | Evaluator | 分页排序，异常值质量标记 |
| 综合诊断 | Diagnostic evidence | `/diagnostics` | Diagnostic Worker | 只陈述证据，不输出因果 |
| 洪水事件 | EventMetric | `/events` | Event Evaluator | 洪峰/峰现/洪量定义版本化 |
| 添加图表结构化模式 | PlotSpec | `POST /plot-jobs` | Plot Worker | 先 validate 后执行 |
| 自然语言绘图 | PlotPlan | `POST /plot-plans/parse` | 可插拔 Parser | 必须人工确认结构化计划 |
| 结果资产下载 | Artifact | download-url | 无 | 短期 URL、逐文件授权 |
| 选择性导出 | ExportJob | `/export-jobs` | Export Worker | manifest/hash/过期清理 |
| 勾选 2–5 Run | Comparison request | `/result-comparisons/validate` | 无 | task/metric/time/basin 兼容检查 |
| 四区对比 | 聚合查询 | `/result-comparisons/query` | 可选缓存 | baseline 明确，差异计算可复现 |

## 8. 权限与分享

| 原型操作 | 后端实体/API | 关键验收 |
|---|---|---|
| 集中查看分享 | `ShareLink`、`GET /share-links` | 只列当前用户有权管理的链接 |
| 创建链接 | `POST /share-links` | token 仅返回一次，数据库存 hash |
| 复制链接 | 前端剪贴板 | 不需要后端；不在日志记录 token |
| 提前撤销 | `POST /share-links/{id}/revoke` | 幂等且立即生效 |
| 共享访问 | `GET /shared/{token}` | 限流、防枚举、版本锁定、字段白名单 |

## 9. 运行环境管理

| 原型操作 | 后端实体/API | 关键验收 |
|---|---|---|
| 环境版本列表 | `GET /runtime-environments` | 状态、CUDA/框架、digest 和使用数 |
| 创建环境 | `POST /runtime-environments/{id}/versions` | 版本化且独立构建 |
| 构建状态/日志 | build SSE、Artifact | 失败可重试，不污染旧版本 |
| 设为模板默认 | 新 TemplateVersion 或可变草稿 | 不回写历史 ExperimentVersion |

## 10. 原型 Mock 替换顺序

真实开源 Adapter 还需通过 `05-open-source-reuse-and-adapter-plan.md` 的对应 Spike；未通过时使用 Fake/Local 实现验证领域和前端契约。

| 顺序 | 前端区域 | 后端阶段 | Adapter / Spike | Mock 移除条件 |
|---|---|---|---|---|
| 1 | 服务健康、当前用户、分享 | B0–B1 | Fake ports；无外部服务前置 | 鉴权/错误/空态 E2E 通过 |
| 2 | 数据列表、详情、创建 | B2 | `ObjectStorage`；S3-01 | upload/derive 通过，URL 有安全测试，真实上传前 S3-01 通过 |
| 3 | 代码、模板、环境 | B3 | `ModelFrameworkAdapter`、`RunExecutor` 契约 | ZIP/Git/模板状态可用；真实构建按 Runner 门禁 |
| 4 | 实验、草稿、Run 历史 | B4 | `FakeTaskQueue` → Outbox contract | Draft、validate、幂等提交通过 |
| 5 | 运行中心、GPU、Run 基本状态 | B5 | `CeleryTaskQueueAdapter`、`DockerGpuRunExecutor`；QUEUE-01 | minimal-lstm 完整运行 |
| 6 | Run 实时详情 | B6 | `MlflowTrackingAdapter`；TRACK-01；可选 NH-01 | SSE 断线恢复、日志和指标通过 |
| 7 | Checkpoint 与失败恢复 | B7 | `NeuralHydrologyAdapter` collector；NH-01 | 服务端兼容阻断和派生 Run 通过 |
| 8 | 结果、绘图、导出、对比 | B8 | Darts/Optuna/DVC 默认不启用 | 科研闭环 E2E 通过 |

## 11. 当前发现的前端接入准备项

这些是后端编码阶段需要处理的结构问题，不在本次计划任务中修改：

1. 当前页面和 Mock 数据主要集中于 `apps/web/src/App.tsx`，需要按 feature 拆分。
2. 当前使用本地 `View` 状态而非真实 URL 路由，后端接入前应建立资源 ID 路由和深链。
3. React Router/Zustand 已安装但原型尚未真正使用，不应把 README 中模板描述当成现状。
4. `@codeflicker/appwrite` 属于脚手架遗留，与已确认 FastAPI 认证方案冲突；B0/B1 前决定移除或明确仅用于公司 SSO 网关，禁止同时维护两套业务后端。
5. 新手清单和 Run 卡片布局目前仅本地状态；分别接资源完成度和用户偏好。
6. Mock 中使用显示名称定位资源；真实接口必须使用稳定 ID，名称仅展示。
7. 前端需要统一 API client、错误映射、请求取消、缓存失效和 SSE 重连模块。
8. 前端不得直接调用 S3、MLflow、Celery、NeuralHydrology 或其他第三方服务；预签名 URL 也必须先从 HydroLab API 获得。

## 12. 开源 Adapter 追踪

| 原型能力 | HydroLab 端口 | 首选实现 | 真相源边界 | 准入门禁 |
|---|---|---|---|---|
| 上传、下载、Artifact | ObjectStorage | S3ObjectStorageAdapter | Artifact/权限/manifest 在 MySQL | S3-01 |
| 导入、构建、执行、绘图队列 | TaskQueue | CeleryTaskQueueAdapter | Job/Run 状态在 MySQL | QUEUE-01 |
| 训练参数与指标跟踪 | ExperimentTracker | MlflowTrackingAdapter | Run/权限/结果索引在 MySQL | TRACK-01 |
| 水文训练与评估 | ModelFrameworkAdapter | NeuralHydrologyAdapter | GPU lease/状态/兼容性由 HydroLab 管理 | NH-01 |
| 通用时序模型 | ModelFrameworkAdapter | DartsAdapter | MVP 不启用 | DARTS-01 |
| 超参数搜索 | OptimizationAdapter | OptunaAdapter | Optuna 不创建或调度 Run | OPT-01 |
| 外部数据版本桥 | ImportSourceAdapter | DVC CLI bridge | DatasetVersion 不委托 DVC | DVC-01 |
| 双 GPU 调度 | RunExecutor + GpuLease | MySQL lease + Docker Runner | 不采用 Ray/ClearML/Kubeflow 状态 | Runner Spike |

ClearML 仅参考 Agent/Queue 设计；Kubeflow 当前拒绝；Ray 在多节点前延后。任何决策变化先更新 `05`。

## 13. 追踪矩阵完成定义

每个原型操作只有满足以下条件才可标记“真实接入完成”：

- 使用真实稳定资源 ID 与后端 Schema。
- loading/empty/error/disabled/success 均有真实接口验证。
- Policy 和越权测试通过。
- 异步任务可取消/重试且状态可恢复。
- 关键操作写审计和 request_id。
- 浏览器桌面与 416px 回归通过，无控制台错误。
- Mock adapter 在生产构建中不可达。
