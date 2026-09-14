# 子工程二：前端真实联调、质量收口与用户流程验收

## 目标

把当前能构建但仍混有旧 Demo、静态占位和未接通操作的前端，收口为一套可沿真实 FastAPI 契约工作的研究平台界面。重点是用户从登录、选择资产、创建实验、提交 Run、观察日志/事件、采集结果、绘图/导出/对比到分享/权限管理的完整路径可用、可解释、可恢复。

## 当前基线与已确认问题

以下结论来自 2026-09-13 的仓库检查：

- `cd apps/web && npm run build`：通过。
- `cd apps/web && npm run lint`：失败，9 个 error、5 个 warning。
- `apps/web/src/App.tsx` 中 `Assets`、`ExperimentList`、`BasinDiagnostic`、`AdvancedExperimentForm` 等组件定义但未使用；同时仍有未使用的状态/变量。
- `apps/web/src/components/ui/button.tsx` 触发 `react-refresh/only-export-components`。
- `apps/web/src/lib/api.ts` 的 `withSessionRetry` 在 401 时只清理 Token，不调用 `/auth/refresh`，也不重试；README 对“自动重新登录并重试一次”的描述与实现不一致。
- 前端已使用 `/runs`、Run 详情、SSE、结果和实验正式接口，但 `scripts/verify-integration.sh` 仍检查旧的 `/dev-demo/workspace`，验证路径与当前代码不一致。
- `ApiCatalogPage` 的实验创建逻辑通过寻找已有 `SUBMITTED` draft 来复用数据集/环境，没有让用户明确选择冻结输入；这会导致空库、多个草稿或权限变化时创建流程不可预测。
- 运行环境页的“创建环境/管理”、权限与分享页的内容仍有静态占位或没有点击行为；资源详情、部分实验/Checkpoint 视图仍保留原型数据。
- 运行中心的 GPU 抽屉目前把运行中的 Run 按数组序号映射为 GPU，不能把真实 lease/gpu_index 作为事实来源；没有资源采样时部分错误被静默吞掉。
- SSE/加载失败路径大量使用空 `catch`，用户看不到错误；401、断线、Run 终态和重复订阅需要更明确的状态管理。

## 工作范围

### P0：质量门禁与 API 客户端

1. 清理 `npm run lint` 的 9 个 error 和 5 个 warning；移除死代码或把确实需要的组件接入真实页面，不能通过关闭规则掩盖问题。修正 `button.tsx` 的 Fast Refresh 导出问题。
2. 修正 API client 的会话生命周期：access token 401 时只允许一次 refresh + 原请求重试；refresh 失败才清理 session 并回到登录页；并发请求不能无限刷新或互相覆盖 Token；204、错误体、网络断开都要有稳定错误语义。
3. 更新 API 类型以覆盖 `PREPARING`、`FAILED` 等真实状态，避免用宽泛 `string` 或错误的旧 Demo 类型掩盖状态机问题。
4. 修正 SSE：断线重连保留 `Last-Event-ID`，收到终态后停止或降级轮询，Abort 时清理重连计时器；非 2xx、解析错误、权限失效要显示可操作提示。

### P1：真实用户流程

1. 以正式 API 为唯一数据源，移除用户可见页面中的静态实验、结果、Checkpoint、数据和分享内容；如果后端接口暂未支持，显示明确的“暂未接入”状态并禁用操作，不能伪装成真实数据。
2. 完成数据流程：数据集列表、创建、导入任务、上传/映射/确认、版本列表和错误重试；`fake-upload` 只保留开发联调用途，并在界面上明确标注。
3. 完成代码/模板流程：代码仓库、ZIP/Git/目录导入、CodeVersion、TemplateVersion 和参数 Schema；创建实验时必须由用户明确选择 dataset version、code version、template version、environment version 和参数，而不是从“某个已提交 draft”猜测。
4. 完成实验/Run 流程：创建 Draft → 编辑 → 提交幂等 → 进入队列 → start/cancel/await → Run 详情。Run 详情要显示阶段、状态、日志、事件、资源采样、配置和错误；按钮状态必须遵守后端状态机。
5. 完成结果流程：结果索引、指标读取、结果详情、2–5 个同数据版本结果对比、绘图、导出和结果采集。加载中、无数据、权限不足、后端错误都要有对应 UI。
6. 完成环境、权限和分享页面的真实读取和写操作，至少覆盖列表、创建/撤销/复制链接或明确的不可用原因；不允许保留无 handler 的“创建/管理/查看版本”按钮。
7. GPU 抽屉使用后端资源样本和 lease/event 中的真实 GPU index，不要按数组序号猜测；没有采样时显示“暂无采样”，不要显示虚假的利用率/显存。

### P1：联调与可访问性

1. 更新 `scripts/verify-integration.sh` 到当前正式接口：默认端口、登录、seed、资源列表、`/runs`、Run 详情、未认证 401、关键写操作和错误边界都要检查；删除或单独标记旧 `/dev-demo/workspace` 检查。
2. 统一 README/AGENTS/脚本中的端口、启动方式和“Fake/InMemory/真实 Runner”描述。
3. 所有异步操作提供 loading/disabled 状态，失败提示不能被空 catch 吞掉；对 modal/drawer、表格按钮和表单补齐可访问名称、键盘关闭和焦点基本行为。
4. 不必引入大型新 UI 框架；保持现有视觉规范和组件风格，优先拆分 `App.tsx` 中职责明显的页面/组件，降低后续维护成本。

## 不要做的事

- 不要修改后端领域逻辑或为了前端通过而改 API 语义；发现后端阻塞时记录精确接口契约问题。
- 不要保留“看起来可点击但没有行为”的按钮，也不要用随机/硬编码业务数据作为成功回退。
- 不要删除用户当前工作树中与本子工程无关的修改。
- 不要用 `eslint-disable`、`any` 或关闭 Hook 规则来隐藏真实问题。

## 验收标准

- `cd apps/web && npm run lint` 0 error、0 warning。
- `cd apps/web && npm run build` 通过。
- 启动 API 与 Vite 后，`scripts/verify-integration.sh` 通过，且检查的是当前正式接口。
- 浏览器人工或自动 smoke 覆盖：登录/刷新、资源列表、创建数据集、创建并提交实验、打开 Run 详情、SSE 断线重连、取消 Run、结果指标/绘图/导出/对比、退出登录。
- 任何后端重启、401、空列表、慢请求、失败请求、无资源采样都显示明确状态，不出现白屏、死转圈或伪造成功。
- 变更摘要列出已移除的旧 Demo/静态路径、真实接口映射、测试命令和仍依赖后端子工程的契约问题。

## 可直接交给代理的提示词

```text
你负责 HydroLab 的“前端真实联调、质量收口与用户流程验收”子工程。工作目录是当前仓库，先阅读 apps/web/AGENTS.md、apps/web/README.md、apps/web/src/lib/api.ts、apps/web/src/App.tsx、plans/01-prototype-interaction-spec.md、plans/04-prototype-backend-traceability.md，以及本文件。当前工作树有用户未提交改动，必须保留无关改动，不要 reset/checkout/reset --hard。你只修改 apps/web、前端联调脚本和相关前端文档，不修改 apps/api 的业务实现。

目标：把当前“build 通过但 lint 失败、正式 API 与旧 Demo/静态占位并存”的界面收口为可真实联调的研究平台。重点检查并修复：App.tsx 未使用组件/状态；button.tsx Fast Refresh lint；401 只清 Token 不 refresh/retry；ApiRunStatus 缺少真实状态；SSE 重连与 Abort；verify-integration.sh 仍检查 /dev-demo/workspace；实验创建从已提交 draft 猜数据/环境；运行环境/权限分享/资源详情存在静态占位或无 handler 按钮；GPU 按数组序号而不是后端 gpu_index 展示；空 catch 吞掉加载错误。

执行要求：
1. 先运行 git status、npm run lint、npm run build，记录失败项；不要覆盖用户现有修改。
2. 以 apps/api 的正式 REST/SSE 契约为唯一真实来源，先读 routes 和 schemas 再改类型与调用。不要为了界面通过修改后端。
3. 修复 API client 的 access-token refresh + 单次重试、错误体解析、204、网络异常和并发刷新；修正 SSE 的 Last-Event-ID、重连、终态、Abort 和错误提示。
4. 清理或接入所有未使用组件，修复 lint/Hooks，不准用 eslint-disable、any 或空 catch 掩盖问题。保持现有视觉规范，必要时把巨大的 App.tsx 拆成职责清楚的文件。
5. 把用户可见的静态业务数据替换为真实 API 数据，完善 loading/empty/error/disabled 状态。实验表单必须明确选择数据版本、代码版本、模板版本、环境版本和参数，不能从旧 draft 猜测。对没有后端支持的功能显示明确未接入状态，不能假装成功。
6. 更新联调脚本和 README，使它验证当前 /runs、Run 详情、事件/日志、结果等正式路径，并覆盖未认证 401。若能使用浏览器自动化，启动 API/Vite 做一次端到端 smoke；否则至少提供可重复的脚本验证。
7. 最后运行 npm run lint、npm run build、联调脚本；逐项记录结果，并列出仍需后端代理解决的精确接口问题。

交付：前端代码、类型/API client、联调脚本/文档、必要的测试或 smoke 证据，以及一份变更摘要。变更摘要必须包含已完成项、已删除的旧 Demo/静态路径、每条验收命令及其结果、未完成项和后端契约依赖。
```
