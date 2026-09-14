# 第 3、4 项实现与后续 Agent 交接清单

日期：2026-09-14。范围：自动 Outbox 发布；Docker 训练移至独立 Worker。

## 1. 本轮已实现

### 1.1 自动 Outbox Publisher

- `apps/api/src/hydrolab/execution/publisher.py`：API lifespan 内启动、关闭后台发布循环，每秒领取一条事件；队列异常不会终止循环，关闭时取消后台任务。
- `main.py`：仅 Celery 后端启用 Publisher；Docker 模式不再启动 API 内 FIFO 调度器，subprocess 本地模式保持原调度行为。
- `execution/service.py`：每次投递使用 Outbox event.id 作为 job_id；重试不生成新 ID；发布调用超时 30 秒；成功后写回数据库，异常归还 PENDING。
- SQL 和内存仓储：只领取 `run.requested` / `run.cancel_requested`；SQL 使用 FOR UPDATE SKIP LOCKED；PUBLISHING 超过 300 秒可重领。确认/归还必须匹配领取时间，防止旧发布者覆盖新领取。
- 复用 published_at 记录 PUBLISHING 的领取时间，PUBLISHED 时改为实际发布时间；SQL 领取时间按现有 MySQL DATETIME 秒精度写入。后续如改字段，必须同步迁移与仓储。
- 投递语义为至少一次；消息已发出而确认写库失败时可重投，消费端必须幂等。没有宣称 exactly-once。

### 1.2 API 与训练 Worker 分离

- `adapters/remote_executor.py`：API 的 Docker 配置装配为远程执行标记，不创建 Docker 客户端；API start 只返回已提交的 QUEUED Run，实际启动依赖提交时创建的 Outbox。
- API cancel 写入持久化 `run.cancel_requested`；确认终态只能由 Worker 执行。start/cancel/complete 增加所有者或管理员校验，手动 dispatch 限管理员。
- `apps/worker/src/hydrolab_worker/runtime.py`：独立装配 MySQL 仓储、S3、MLflow、Docker 和 RunControlService，不启动 FastAPI lifespan、不执行迁移。
- Worker 使用 MySQL `GET_LOCK(hydrolab:run:<UUID>, 0)` 持有单个 Run 的执行权；每轮确认锁仍归当前连接所有。连接使用 NullPool，避免 Celery 每次 asyncio.run 跨事件循环复用连接池。
- QUEUED 启动、RUNNING 轮询、终态持久化；已终态重复消息不重新启动。竞争执行权或 GPU 资源不足通过 Celery retry 重试。
- Worker 每秒检查持久化取消事件、更新 GPU 心跳，并非阻塞地读取 Docker 状态；任务超过 execution.timeout_seconds 后清理容器并记 FAILED。
- Worker 重启后的 PREPARING/RUNNING 会按固定容器名重新关联；RUNNING 对应容器不存在时失败，不自动重跑训练；PREPARING 未发现容器时可重新准备。
- 修复 Run 状态只修改领域对象的问题：新增 RunStore.save，并在真实启动/失败/完成/取消时写回 SQL。
- GPU 心跳到期不会直接释放租约。过期不等于容器已停止，清理由确认终止或后续对账流程负责。

### 1.3 队列和 Docker 契约

- `run.execute` → `hydrolab` 队列；`run.cancel` → `hydrolab-control` 队列。
- Celery kwargs 仅为 job_id、resource_id、attempt，与消费者签名一致。
- 训练 Worker concurrency=2；控制 Worker concurrency=1。当前运行时单 Run 申请一张卡，GPU 总数仍固定为 2。
- 取消事实保存在 Outbox；正在执行的 Worker 直接查库处理。控制队列消费者确认请求，不持有 Docker socket。
- Docker 容器名 `hydrolab-<完整 UUID hex>`，附 run_id label；训练以 `65534:65534` 运行，移除 capabilities、禁止提权，默认禁网。
- 代码和数据只读挂载 `/workspace/code`；输出读写挂载 `/workspace/output`，通过 HYDROLAB_OUTPUT_DIR 告知训练脚本。Worker 为新输出目录设置 UID/GID 65534。
- DeviceIDs 使用 GPU 租约索引，不再同时设置非零 Count；容器内 CUDA_VISIBLE_DEVICES 使用本地序号 0..N-1。
- Docker wait(timeout=0) 只轮询，不阻塞、不删除容器；先采集/落库，再 cleanup。取消无法连接 Docker 时不会虚报 CANCELLED。
- S3 冻结内容读取改用 open_range；补上同步采集器调用的 S3 put_bytes，运行于采集线程。

### 1.4 部署

- Compose：API 无 socket/工作区挂载；仅训练 Worker 挂载 `/var/run/docker.sock` 和同路径的工作区。
- `HYDROLAB_RUNNER_WORKSPACE_ROOT` 默认 `/srv/hydrolab/runs`，必须是 Docker 宿主机与 Worker 内一致的绝对路径。本实现面向一台 Linux GPU 主机，未实现多主机 GPU 命名空间。
- socket 授予训练 Worker 宿主机 Docker 控制权；Worker 是可信基础设施，训练容器不挂载该 socket。当前没有实现 socket proxy 或 rootless Docker。
- API/Worker 均注入 MinIO S3 凭据；API 镜像补入 Alembic 文件，避免启动迁移找不到脚本。
- Compose 服务 env_file 支持 HYDROLAB_ENV_FILE，允许用示例文件做离线展开，不创建生产配置。

## 2. 本地验收结果与边界

- API 全量：159 passed，9 skipped。新增覆盖：发布失败自动恢复、稳定 ID、旧领取不能覆盖新领取、未知 topic 不阻塞、控制队列参数、API 无 Docker 执行能力、Docker 零超时轮询、取消失败不虚报成功、Worker 锁竞争、终态消息不重复启动。
- Worker 执行权测试使用模拟数据库连接，不能替代 MySQL 并发验收。
- Compose 可用示例配置完整展开，并断言 API/控制 Worker 无 socket、训练 Worker 同路径工作区挂载。
- 内网数据库验证按照用户要求记为 TODO；本轮没有连接内网 MySQL，也没有升级业务库。
- Docker 镜像构建和真实 GPU 执行仍未验收；上轮本地 Docker daemon 未运行。
- 本地测试成功不代表以下待完成项已解决。

离线检查命令（仓库根目录）：

```bash
apps/api/.venv/bin/python -m pytest -q apps/api/tests --disable-warnings
HYDROLAB_ENV_FILE=.env.production.example docker compose --env-file infra/.env.production.example -f infra/docker-compose.production.yml config --quiet
```

## 3. 可直接交给 Agent A：数据库事务、恢复与内网验证（P0）

目标：验证并补齐跨进程状态一致性，任何中断都不能重复训练、丢任务或把仍运行的 GPU 重新分配。

负责文件：`apps/api/src/hydrolab/db/`、`apps/api/alembic/`、`apps/api/src/hydrolab/experiments/service.py`、`apps/worker/src/hydrolab_worker/runtime.py`、相关 tests/db。与 Agent B 协调 Worker 接口修改。

实施清单：

1. **真实 MySQL 重跑**：使用独立测试库，配置 HYDROLAB_TEST_DATABASE_URL 后执行 tests/db。先核验目标库身份，不对业务 hydrolab 执行测试迁移。交付服务器、时间、脱敏命令、迁移 revision、测试结果。
2. **修正旧库 collation 升级**：当前 b32a91f9c7d4 只有外键/唯一约束创建；dataset_versions 的 collation 指定出现在初始迁移中。已处于旧 revision、collation 不一致的库不能靠修改初始脚本修好。补独立升级路径/前置核查，验证从旧库状态升级以及全新库升级。不得用手工 stamp 掩盖失败。
3. **提交事务**：当前 Experiment/Version/Run/Stages/Outbox 多个仓储分别 commit。引入共享事务或 UnitOfWork，使一次提交要么全部成功，要么全部回滚；批量提交明确逐项/全批事务语义。
4. **并发幂等**：两个连接同 owner+key 同时提交，只返回同一个 Run，禁止 500 和残留多余 Experiment/Version；同实验 version_no 并发分配需唯一约束/锁。
5. **发布者并发**：两个实例同时领取、broker 不可用、发出后写库失败、发布者重启、领取过期、旧领取迟到确认。断言事件可恢复且 job_id 不变；禁止只测试内存对象。
6. **Worker 故障窗口**：启动容器前后分别 kill Worker；GET_LOCK 连接断开；写 execution 前失败；终态写库/采集失败。验证固定容器名可关联、状态可恢复、不重复 launch。
7. **恢复调度器**：目前恢复依赖消息重投，没有独立扫描器。增加扫描 PREPARING/RUNNING/过期租约与 Docker label 的对账流程；处理消息已确认但失败的孤儿任务、终态后遗留容器、无容器的租约。确认容器结束后才释放 GPU。
8. **租约并发/死锁**：MySQL 行锁与 unique gpu_index 的竞争需要实际双连接测试；处理 OperationalError 死锁重试。现有 acquire 只处理 IntegrityError。
9. **状态原子性**：当前 RunStore.save 是按 ID 写入，未实现状态 CAS；补期望状态与原子迁移，终态不得被迟到写入覆盖。保证取消/完成/重试的竞争收敛。

验收：真实 MySQL 中完成全链路状态迁移；故障注入后最终无孤儿容器/占用；一 Run 最多一个活跃容器；完整测试结果与剩余风险写入独立验收记录。

## 4. 可直接交给 Agent B：环境、产物与运行时收口（P0）

目标：用户从网页创建环境、选择真实数据提交实验后，Worker 能训练并把结果显示回网页。

负责文件：code_assets、S3/MLflow adapters、execution/collector.py、results、相关 API 与前端联调；Docker adapter/Worker runtime 如需修改先与 Agent A 协调。

实施清单：

1. **环境 image_digest**：create_environment_version 目前只写 base_image、依赖内容和配置 hash，没有写实际 image_digest；Docker _build_spec 要求该字段。实现从已构建并校验的训练镜像登记 digest 的路径；不能把依赖 hash 当镜像、不能把声明依赖误称为已安装。补 API schema、权限、SQL 回读与测试。
2. **镜像白名单严格校验**：限制真实不可变 digest 格式，拒绝 tag、占位串、空数组；确认镜像中 Python 与训练依赖实际存在。训练镜像需要 UID 65534 能读取代码和写输出。
3. **训练输出契约**：脚本须写 HYDROLAB_OUTPUT_DIR，现有脚本如果直接写 code/experiments 会因代码只读而失败；增加受控 argv 参数映射或修改示例训练脚本，不能把整个代码挂载改回可写。
4. **S3 上传闭环**：本轮补了执行读取与采集 put_bytes；数据/代码导入的其他路径仍需逐个验证 S3，不能依赖 `.objects` 或 `._root` 私有本地实现。验证 presigned upload、complete、hash、bundle 文件物化与缺对象失败。
5. **Result 持久化**：当前 collection_report 存在 Worker 进程内，API 无法读取，且 finalize 没有自动登记完整 Result。把 report 和产物/指标/Checkpoint 写入可持久查询的位置，完成 ResultService ingest 的幂等串联。API 不应读取 Worker 本地目录或进程内字典。
6. **日志链路**：Docker stdout/stderr 尚未持续写入 RunLog，补流式/增量采集、日志截断与重启续读。大日志不能无限积累在内存。
7. **MLflow 恢复**：tracking refs 当前进程内保存；保存 external_run_id，重启后继续同一条 MLflow run；失败补偿与重试不可创建重复 run。
8. **多用户权限**：本轮只收紧启动/取消/完成/dispatch。检查 logs/events/resources/collection/await 和 internal progress/metrics 等接口的资源权限及内部认证，增加跨用户反例测试。
9. **GPU 配置**：当前单 Run=1 GPU、总数=2；如需支持动态设备列表/多卡，冻结资源请求，贯通 API、队列、Worker、租约和 DeviceIDs；不要只改变 UI 或 concurrency。

验收：通过网页或 API 提交一次小训练，无手工 dispatch/start/ingest；日志、状态、指标、checkpoint/下载均可见；API/Worker 重启后结果仍可查询；错误数据/镜像给出可追踪失败。

## 5. 可直接交给 Agent C：构建、生产门禁与服务器验收（P0/P1）

负责文件：Dockerfiles、uv.lock、infra、scripts、CI、运维文档。不要修改 Agent A/B 的业务逻辑；发现接口缺失请记录。

实施清单：

1. **构建复现**：更新与 pyproject 匹配的 uv.lock，恢复 --locked 或等价锁定构建；实际构建 API/Worker/Web 镜像，验证 Python/Celery/迁移文件和所需依赖；记录镜像 digest。
2. **预检脚本**：修复 verify-p0-deployment.sh 的 Compose 失败仍 OK、忽略 --env-file、跳过仍报全部通过、白名单占位串可通过等问题。使用本轮 HYDROLAB_ENV_FILE 支持，区分 PASS/FAIL/SKIP，失败必须非零。不得输出真实密钥。
3. **服务初始化**：建立 MinIO bucket 与应用最小权限凭据；当前使用 root 凭据是部署联通配置，正式上线换为专用账户；核对 MLflow 镜像是否包含 pymysql，以及 MLflow 与 HydroLab 共库/迁移版本表冲突风险，必要时独立库。
4. **Readiness**：API ready 加数据库，失败返回 503；增加 Worker 消费心跳、Docker 与 GPU 可用性。当前 API remote executor 的 healthcheck 仅表示装配成功，不能证明 Worker 健康。不要给 API 加 socket 来实现探活。
5. **宿主机目录**：设置 Linux 主机 HYDROLAB_RUNNER_WORKSPACE_ROOT 绝对路径，同路径挂到 Worker；确认输出 UID/GID 65534 权限。API、Web、控制 Worker 和训练容器均不能挂载 socket。
6. **Docker 资源限制**：补训练 CPU/内存/PID/shm 限额、磁盘配额、日志轮转；评估可信 Worker 的 Docker 权限收敛。当前实现不是面向不可信多租户的完整沙箱。
7. **服务器矩阵**：成功训练、非法镜像、错误 argv、缺数据、OOM、手动取消、超时、两卡并发第三个排队、Worker 重启、Redis 短暂不可用、MySQL 中断、S3 上传失败。
8. **前端 E2E 与运维**：TLS/域名/CORS、登录、真实数据上传、实验提交、日志/结果/下载；备份与恢复演练。修复过时的 infra/README 与 ACCEPTANCE，不保留未经复现的通过结论。
9. **质量门禁**：全量 Ruff/Mypy 与浏览器 E2E；现有 Mypy 第三方 stubs/Python 版本不一致、历史 lint 问题需独立收口。本轮 targeted Ruff 不代表全仓全绿。

构建示例（根目录；实际服务操作由有权限的服务器 Agent 执行）：

```bash
docker build -f apps/worker/Dockerfile -t hydrolab-worker:acceptance apps
docker run --rm --network none hydrolab-worker:acceptance celery --version
docker compose -f infra/docker-compose.production.yml --env-file infra/.env.production build api worker worker-control web
```

禁止在未核验的业务库直接跑测试升级/降级；数据库身份和生产写操作须遵守用户授权。

## 6. 通用交付提示词

请先完整阅读 plans/09-worker-outbox-handoff.md，执行分配给你的 Agent A/B/C 工作包。保留当前工作区所有其他人的修改；开始前核对实际代码，文档中的现状以代码为准。每项修复必须提供相应测试证据，内网或硬件不可用项明确记录 TODO，不能用 mock 通过代替真机通过。不要自行发布生产或修改业务数据库。交付修改文件、关键设计与接口、执行过的命令和结果、未完成事项及风险；跨包接口变更先说明，再协调修改。主代理将依据该文档验收。
