# HydroLab 规划文档索引

> 状态：Confirmed  
> 最后更新：2026-08-29  
> 适用根目录：`/Users/sunzhijun/Downloads/last_design`

## 1. 目录职责

`plans/` 是本项目唯一的规划文档目录，用于保存产品交互、领域模型、API 契约、实施路线、验收方案与原型追踪关系。

`docs/` 只保存已经落地的设计记录、开发说明、运维手册和用户文档，不再新增实施计划。

## 2. 文档清单

| 编号 | 文档 | 状态 | 用途 |
|---|---|---|---|
| 01 | `01-prototype-interaction-spec.md` | Confirmed | 固化前端原型的信息架构、页面流程和状态语义 |
| 02 | `02-backend-domain-and-api-plan.md` | Confirmed | 定义领域模型、数据库边界、REST/SSE 契约和权限规则 |
| 03 | `03-backend-implementation-roadmap.md` | Confirmed | 指导后端目录、依赖、实施批次、测试与上线 |
| 04 | `04-prototype-backend-traceability.md` | Confirmed | 将原型页面逐项映射到后端实体、接口和异步事件 |
| 05 | `05-open-source-reuse-and-adapter-plan.md` | Confirmed | 定义开源准入决策、领域端口、Adapter、Spike 与回退策略 |

## 3. 状态规则

规划文档使用以下状态：

```text
Draft → Confirmed → In Progress → Completed
                    └────────────→ Superseded
```

- `Draft`：仍需确认，不可作为编码依据。
- `Confirmed`：需求和边界已确认，可进入实施。
- `In Progress`：相关实现正在进行。
- `Completed`：代码、迁移、测试和文档均达到验收条件。
- `Superseded`：已被其他文档替代，必须注明替代文档。

## 4. 更新规则

1. 产品交互变化先更新 `01`，再同步 `02` 与 `04`。
2. 实体、接口、状态机或错误码变化必须更新 `02` 和 `04`。
3. 实施顺序、依赖、部署或验收变化必须更新 `03`。
4. 所有接口实现都必须能在 `04` 中找到对应的原型入口和验收路径。
5. 开源组件、SDK、协议、版本或 Adapter 变化必须先更新 `05`，再同步 `02`、`03` 与 `04`。
6. 不允许只改前端 Mock 而不更新追踪矩阵。
7. 不允许接口直接依赖前端展示文案；前后端通过稳定枚举和 Schema 交互。
8. 每个阶段完成后同步更新项目 `README.md`、`AGENTS.md` 和迁移/回滚说明。

## 5. 当前基线

- 前端原型：`apps/web/src/App.tsx`
- 全局样式：`apps/web/src/index.css`
- 原型设计记录：`docs/prototype-design-record.md`
- 总体实施计划：线程计划 `水文时序实验平台实施计划_hazlfi/plan.md`
- 当前业务数据：全部为 Mock，不代表后端已接入。

## 6. 后端实施原则

- FastAPI 只负责业务 API、鉴权、校验和任务编排，不直接执行用户训练命令。
- 所有训练、评估、预测、绘图命令由队列投递至隔离 Runner。
- PostgreSQL 保存业务元数据与不可变引用；S3-compatible object storage 保存大文件；MLflow 保存训练跟踪；Redis/Celery 负责任务投递。
- 业务代码只依赖 `05` 定义的领域端口；先实现 Fake/Local Adapter，再由 Spike 准入真实服务。
- 外部组件状态和 ID 只用于关联与观测，不得成为 HydroLab 业务真相源。
- Experiment 是可复用配置定义，Run 是一次实际执行。
- 数据、代码、模板、环境、Checkpoint 和结果采用不可变版本。
- 首版分享为有期限只读链接。
- 所有列表接口必须支持分页，筛选和排序由服务端执行。
- 所有写操作需要幂等键或明确的重复提交保护。
