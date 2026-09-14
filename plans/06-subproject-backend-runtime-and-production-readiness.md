# 子工程一：后端运行时、持久化与真实执行链路

## 目标

把当前“Fake/InMemory 可联调”的后端推进到一个可安全切换真实基础设施、可恢复、可验收的运行时基线。重点不是重新设计领域模型，而是修复现有装配断点，确保 Settings 选择的 Adapter 真正贯穿执行链路，并让 Run 在真实执行器、队列和数据库场景下保持可追踪。

## 当前基线与已确认问题

以下结论来自 2026-09-13 的仓库检查：

- `apps/api/.venv/bin/python -m pytest -q`：131 passed，存在 72 条 warning。
- `apps/api/.venv/bin/python -m ruff check src tests`：21 个错误，主要集中在异步 timeout 参数、导入排序、结果渲染格式、未生效 noqa。
- `apps/api/.venv/bin/python -m mypy src`：6 个错误，包含 Celery/Docker/aiobotocore/openpyxl 缺少类型信息以及 Python 版本配置不一致。
- `apps/api/src/hydrolab/core/settings.py` 当前把 `database_backend` 默认设为 `mysql`，并在源码内包含远程 MySQL 连接信息；这与 README 所述的“默认 InMemory/Fake”冲突，也构成凭证泄露和误连接风险。
- `apps/api/src/hydrolab/main.py` 直接注入 `FakeTaskQueue()`，没有使用 `deps.get_task_queue()`；因此 `HYDROLAB_TASK_QUEUE_BACKEND=celery` 不会真正控制 Run dispatch。
- `ExperimentTracker` 目前只在 health check 装配，没有注入 `RunControlService` 的 start/metric/artifact/finish 链路；MLflow 开关不能产生完整跟踪记录。
- `RunControlService.is_real_executor()` 通过 `prepare_workspace` 判断真实执行器。Docker Adapter 没有这个工作区协议，因此 Docker 会走 Fake 的 `_build_spec` 分支；同时 Docker Adapter 没有 wait/真实状态回收/日志回流/工作区挂载闭环，不能作为可用 Runner。
- `apps/worker/src/hydrolab_worker/__init__.py` 仍是空壳；Celery 适配器已有单元测试，但没有真实 worker 消费、抢占、幂等、失败重试和恢复验收。
- S3 上传会话存于进程内；`complete_upload` 在远端完成前就移除本地 session，失败后无法可靠重试；`open_range` 一次性读完整响应；删除隔离对象时吞掉所有异常。
- MySQL/Alembic、GPU lease、outbox 和运行观测虽然已有 SQL 类，但尚未完成“应用重启后仍可恢复 queued/running/outbox”的集成验收。
- `apps/api/src/hydrolab/db/factory.py` 与 `api/container.py` 中的 `TYPE_CHECKING: pass`/空迁移函数属于结构性占位，不是本任务的重点；不要为了消除文本形式的 `pass` 破坏迁移语义。

## 工作范围

### P0：配置与装配正确性

1. 移除源码内的远程地址、账号和密码。开发默认必须是 `memory + fake` 或等价的完全本地配置；MySQL、S3、Celery、MLflow、Docker 均需由环境变量显式启用。
2. 修正 `.env.example`、API README、`infra/README.md` 和 Compose 中的配置说明，使默认值、实际启动行为和生产校验一致。
3. 确保 Alembic 使用同一份 Settings/DSN，支持 URL 中的特殊字符；应用启动不得因为默认配置而连接外部数据库。
4. `main.py` 必须从依赖装配取得 TaskQueue 和 ExperimentTracker，并通过 Protocol 类型传入执行服务；不能在核心服务中写死 Fake Adapter。
5. 加入配置装配测试：memory/fake、mysql、celery、mlflow、docker 分别验证选择了正确 Adapter，缺配置时返回明确错误且不泄露 Secret。

### P1：Run 执行与队列闭环

1. 重新定义并实现真实执行器需要的工作区/运行生命周期协议：准备代码和数据、生成签名或可验证的 RunSpec、启动、状态查询、日志/事件、等待终态、取消、超时、清理。
2. 统一 subprocess 与 Docker 的 RunSpec 语义。Docker 不能再落入 Fake 分支；必须能使用实验冻结的 `argv`、环境镜像 digest、数据版本和 GPU 租约。
3. Docker 安全门禁至少包括：非空 digest 白名单、禁止 shell、默认禁网、非 root、代码/数据只读、output 可写、GPU 映射、超时/取消后杀死容器、容器和临时目录清理、状态可回收。若沿用独立 Runner Controller 设计，请把 API 与 worker 的消息契约和责任边界落成代码与测试。
4. 完成 Celery worker 最小闭环：只携带稳定 ID；消费时重新读库；`job_id + attempt` 幂等；重复投递不重复启动 Run；失败可重试并进入可观测的死信/失败状态；取消是信号，业务终态仍由 HydroLab 状态机确认。
5. GPU lease 必须在成功、失败、取消、超时、进程/容器丢失和 API 重启恢复时释放或重新认领。并发启动测试不能分配同一张卡。
6. 将 MLflow tracker 接入 Run 生命周期；MLflow 失败不得覆盖 HydroLab 业务终态，但要保存同步失败状态并支持安全重放。`finish_run` 必须尊重传入终态语义，不得无条件写成同一种状态。

### P1：持久化、幂等与恢复

1. 用 MySQL 集成测试覆盖：迁移到 head、所有核心仓储可读写、外键/唯一约束、同一 owner 的幂等提交并发只生成一个 Run、分页/排序稳定。
2. 覆盖 outbox 发布前后、重复发布、发布失败重试和 API 重启后的恢复；不能依赖进程内列表作为业务事实。
3. 覆盖 Run events/logs/resources 的游标读取和 SSE 断点恢复；长日志/大对象不要一次性全部加载到内存。
4. 对 S3 Adapter 增加 multipart/单对象失败重试、session 过期、HEAD 校验、范围读取、内容 hash/大小校验和隔离对象清理测试；上传会话不能只依赖单进程内存，至少要明确其持久化边界并在生产路径满足恢复要求。

### P2：质量与文档

1. 清理 ruff 21 个错误；不要用扩大 noqa 范围的方式掩盖问题。异步等待统一采用项目支持的 Python 版本写法。
2. 让 mypy 在项目声明的 Python 3.11 环境下可重复执行；为真实 Adapter 增加必要的类型依赖或局部边界封装，不能把所有模块改成 `Any`。
3. 增补一条不依赖真实 GPU 的端到端测试：提交 Draft → Outbox → 队列 → Runner → 终态 → 结果登记；再增补一条 MySQL/Redis/S3/MLflow/Docker 的可选 Spike 验收命令。
4. 更新后端 README、infra 文档和 plans/05 的门禁状态，明确哪些 Adapter 已可启用、哪些仍是 Spike。

## 不要做的事

- 不要重写领域实体、API 路由或前端；如果发现契约问题，优先保持现有契约并在文档中说明。
- 不要提交任何真实密码、Token、远程内网地址或本地数据。
- 不要为了让测试通过而把真实后端静默降级为 Fake。
- 不要删除用户当前工作树中的无关改动；先阅读 `git status`，只修改本子工程负责的文件。

## 验收标准

- `cd apps/api && .venv/bin/python -m pytest -q` 通过，且新增测试覆盖本任务的 P0/P1 风险。
- `cd apps/api && .venv/bin/python -m ruff check src tests` 无错误。
- `cd apps/api && .venv/bin/python -m mypy src` 在项目声明的 Python 3.11 运行环境下无错误，或对无法由第三方库提供的 stub 给出最小、可审计的配置边界。
- 使用默认本地配置启动时不会连接任何外部 MySQL，也不会读取源码内的真实凭证。
- 显式配置 Celery/MLflow/Docker 时，health check、Run dispatch、Run lifecycle 和失败行为都能被测试证明没有绕回 Fake。
- API 重启、重复消息、取消和异常退出后，Run、outbox、GPU lease、日志/事件的状态仍可解释。
- 变更摘要列出：修改文件、迁移/回滚策略、配置变化、已验证命令、未完成的真实基础设施门禁。

## 可直接交给代理的提示词

```text
你负责 HydroLab 的“后端运行时、持久化与真实执行链路”子工程。工作目录是当前仓库，先阅读 apps/api/README.md、plans/02-backend-domain-and-api-plan.md、plans/03-backend-implementation-roadmap.md、plans/05-open-source-reuse-and-adapter-plan.md、infra/README.md，以及本文件。当前工作树有用户未提交改动，必须保留无关改动，不要 reset/checkout/reset --hard。

目标：把 Fake/InMemory 基线推进成可安全切换真实基础设施的运行时。优先修复配置安全和 Adapter 装配断点，再完成 Run/queue/SQL/Docker 的可验证闭环。特别检查并修复：Settings 中的远程默认数据库凭证；main.py 写死 FakeTaskQueue；ExperimentTracker 未接入 Run 生命周期；Docker executor 被 is_real_executor 判断挡回 Fake 分支；Docker 缺少真实 wait/状态回收/工作区挂载；Celery 没有 worker 消费；MySQL/outbox/GPU lease 的重启恢复未验收；S3 上传 session 和范围读取的可靠性问题。

执行要求：
1. 先运行 git status、现有 pytest，并列出你准备修改的文件和风险边界；不要修改 apps/web。
2. 用 Protocol/端口保持领域层隔离，不能在服务中写死 Fake Adapter，也不能用静默降级掩盖真实依赖缺失。
3. 删除源码中的真实连接信息和凭证，让本地默认配置安全且与 README 一致；Alembic、Settings、Compose 的 DSN 行为统一。
4. 让 task queue、experiment tracker、run executor 真正由 Settings 装配并贯穿业务生命周期。补齐 Docker/worker 的最小真实闭环；如果架构要求独立 Runner Controller，就把消息契约、状态回写、幂等和清理责任写成可测试实现。
5. 为配置、装配、重复消息、并发 GPU lease、取消/超时/异常退出、重启恢复、S3 multipart、MLflow 失败隔离补测试。真实外部服务不可用时使用 mock/容器化测试，但不要把它们伪装成已通过生产门禁。
6. 修复 ruff 和 mypy，不能扩大 noqa 或把代码泛化成 Any。保留已有 131 个通过测试。
7. 最后运行 pytest、ruff、mypy 和相关 e2e/Spike 命令，更新 README/infra/plans 的真实状态。

交付：代码、测试、必要迁移、配置说明和一份变更摘要。变更摘要必须包含已完成项、未完成项、每条验收命令及其结果、任何需要主工程代理接手的 API/配置契约。
```
