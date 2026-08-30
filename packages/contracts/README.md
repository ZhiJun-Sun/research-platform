# HydroLab 契约包

存放跨进程共享的契约快照：

| 内容 | 状态 | 说明 |
|---|---|---|
| `events/run-event-v1.schema.json` | v1 | Run 事件（JSONL / SSE / run_events 表）统一 Schema |
| `openapi.json` | 待生成 | 由 CI 从 FastAPI 导出并做破坏性变更检查（plans/02 第 12 节） |

规则：

- 契约显式版本化；破坏性变更必须升版本并同步 `plans/02` 与 `plans/04`。
- 前端类型只能由 OpenAPI/Schema 生成或严格映射，禁止依赖中文展示文案。
- 事件 Schema 与 `apps/api/src/hydrolab/ports/dto.py` 中的 `NormalizedRunEvent` 保持一致。
