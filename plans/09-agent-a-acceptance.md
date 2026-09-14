# plans/09 Agent A 验收记录

日期：2026-09-14

范围：数据库事务、恢复与内网验证（plans/09 §3）。未修改业务库 `hydrolab`，所有真库测试使用独立库 `hydrolab_agent_a_test`。

## 环境核验

只读核验目标 MySQL：

- Host/port：`10.196.83.122:3306`
- Server：MySQL `8.0.22`
- Server charset/collation：`utf8mb4` / `utf8mb4_0900_ai_ci`
- 业务库 `hydrolab`：未执行测试迁移、未执行测试写入
- 独立测试库：`hydrolab_agent_a_test`

内网连接经代理存在间歇性不可达。以下标注“真库通过”的项目是在连接可达窗口内实际执行的；之后连接持续在握手阶段报 `2013 Lost connection ... reading initial communication packet`，未用 mock 冒充真机通过。

## 已完成与证据

### A2：collation 独立升级路径

新增迁移链：

```text
0001_baseline
  -> 4e409406eb80
  -> c0a111a2f1  # 在外键迁移前归一化 dataset_versions
  -> b32a91f9c7d4
  -> c0a111a2f2  # 覆盖已处于 b32a91f9c7d4 的旧库
  -> c0a111a2f3  # experiment_versions version_no 唯一约束
```

新增 `hydrolab.db.collation_check` 只读前置核查：

- mismatch：退出码 `1`，列出 `dataset_versions.id/dataset_id` 与服务器 collation 的差异；
- consistent：退出码 `0`；
- 未配置 URL：退出码 `2`，不静默连接默认库。

真库验证：

1. 全新独立库 `upgrade head`：原迁移在 FK 创建处会报 MySQL 3780；加入 `c0a111a2f1` 后成功。
2. 库停在 `4e409406eb80` 且 `dataset_versions=utf8mb4_unicode_ci`：升级 head 后变为 `utf8mb4_0900_ai_ci`，`fk_dataset_versions_dataset_id_datasets` 成功创建。
3. 独立前置核查在升级前报告 mismatch，升级后报告 OK。

### A9：状态原子性 CAS

修改：

- `SqlRunStore.save(item, expected_status=...)`：单条条件 UPDATE，CAS 未命中抛 `StaleStateError`；终态不能被迟到状态覆盖；同终态重复写允许幂等收敛。
- `InMemoryRuns` 增加 persisted-status 快照，避免共享对象在 save 前就地修改导致 CAS 误判。
- `RunControlService.start/finalize/cancel` 使用期望状态或终态保护。

真库测试：`tests/db/test_mysql_state_cas.py` **4 passed**：

- 正常前向 CAS；
- 错误期望状态被拒绝；
- 终态不能被迟到取消覆盖；
- 同终态重复 finalize 幂等成功。

### A8：租约并发与死锁

修改：

- `SqlGpuLeases.acquire` 对 MySQL 1213 deadlock / 1205 lock wait timeout 做有限退避重试；
- 保留 unique `gpu_index` 作为最终竞争防线。

真库测试：`tests/db/test_mysql_lease_concurrency.py` **3 passed**：

- 两连接竞争单卡恰好一个成功；
- 1213/1205 错误识别；
- 模拟两次死锁后第三次成功。

### A3：提交事务 / UnitOfWork

新增 `hydrolab.db.unit_of_work.UnitOfWork`、`session_scope`、`commit_or_defer`：

- 未绑定 UoW 时保持原仓储逐方法提交语义；
- 绑定时 Experiment/Grant/Version/Run/Stages/Outbox/Draft 共用一个 session，UoW 统一提交或回滚；
- `ExperimentService.submit` 使用原子事务；`submit_batch` 采用逐项原子事务语义。

### A4：并发幂等与 version_no 防线

修改：

- `experiment_versions(experiment_id, version_no)` 唯一约束，迁移 `c0a111a2f3`；
- `ExperimentService.submit` 捕获唯一键竞态，事务已回滚后回读胜者 Run，不返回 500；
- 失败方的 Experiment/Version/Run/Stages/Outbox 不残留。

真库测试：`tests/db/test_mysql_submit_atomicity.py` **3 passed**：

- UoW 全量提交；
- duplicate key 整体回滚且无额外 Experiment/Version/Run；
- 两连接同 owner+key 只落一个 Run。

### A7：恢复对账器

新增 `hydrolab.execution.reconciler.RecoveryReconciler`：

- RUNNING + 容器确认不存在：FAILED，不自动重跑，确认结束后释放 GPU；
- PREPARING + 无容器：回 QUEUED，释放 GPU；
- 容器存在但执行记录缺失：重建执行记录；
- label 容器对应终态 Run：清理遗留容器；
- daemon 不可达等非 NotFound 异常不误判为容器结束。

新增 Docker `list_labeled_containers()`，按 `hydrolab.run_id` label 提供清理入口。

本地 fake executor 单测：`tests/test_reconciler.py` **4 passed**。

### A5：发布者并发测试

新增 `tests/db/test_mysql_outbox_concurrency.py`，覆盖：

- 两实例真实 DB `SKIP LOCKED` disjoint claim；
- PUBLISHING 超时重领；
- 旧 claimed_at 迟到确认被拒收，正确 claimed_at 才能确认。

真库执行：**3 passed**（内网恢复后补跑）。

## A1 真库测试汇总

内网可达后执行完整 DB 测试集：

```bash
HYDROLAB_TEST_DATABASE_URL='mysql+asyncmy://.../hydrolab_agent_a_test' \
python -m pytest -q apps/api/tests/db
```

结果：**22 passed**（原有 migration/repository + A9 CAS 4 + A8 租约 3 + A3/A4 原子性 3 + A5 outbox 3）。

## 本地回归

```bash
cd apps/api
.venv/bin/python -m pytest -q tests --disable-warnings
```

最终结果：**169 passed, 22 skipped**。

跨 worker 边界 import 冒烟：`ALL IMPORTS OK`（包含 `hydrolab_worker.runtime`、`hydrolab_worker.tasks`）。

## 未完成 / TODO / 风险

1. **A6 Worker 故障窗口真机验证**：本机 Docker daemon 不可用，无法真实 kill Worker、断开 GET_LOCK、启动/终止 GPU 容器、验证固定容器名不重复 launch。已由 CAS、reconciler 和 worker 现有锁逻辑覆盖库侧部分；真机项必须在 GPU Worker 服务器验收。
2. **A7 周期调度 wiring**：reconciler 模块和 Docker label 入口已完成并单测；周期触发应由生产 Worker/Celery beat 装配，不能在本机无 Docker 环境下宣称真机通过。
3. 测试独立库 `hydrolab_agent_a_test` 保留供后续重跑，未触碰业务库 `hydrolab`。

禁止事项均遵守：未发布生产、未修改业务库、未用手工 stamp 掩盖升级失败、未将 mock 通过冒充内网/Docker 真机通过。

---

## 部署就绪补充（内网/Redis/MinIO 可达后）

### 关键修复：collation 目标改为 datasets.id 基准（部署前必须）

只读核验业务库 `hydrolab` 时发现它处于**混合 collation** 状态：几乎全表
`utf8mb4_unicode_ci`，唯独 `dataset_versions` 是 `utf8mb4_0900_ai_ci`（其余表按
旧默认创建、dataset_versions 被重建后落到服务器默认）。原把 dataset_versions 对齐到
「服务器默认(0900)」会在该库里继续与 `datasets.id`(unicde_ci) 不兼容，外键仍会 3780。

修正：`c0a111a2f1/c0a111a2f2` 改为把 dataset_versions 对齐到 **被引用列
`datasets.id` 的 collation**；`collation_check` 增加跨表核验，退出码只由外键相关
一致性决定（避免整个 schema 合法统一为 unicode_ci 时误报）。

验证（真库）：
- 全新库升级 head 成功，tests/db **22 passed**；
- 忠实模拟业务库混合态（全表 unicode_ci + dataset_versions=0900）升级 head：**46 个外键全部建成**，此行此前必 3780；
- 预检：升级前对业务库报 MISMATCH (exit 1)，健康库报 OK (exit 0)。

业务库 `hydrolab` 当前：alembic_version=`4e409406eb80`（仍在初始 schema），collation 混合（待迁移）。
部署时先跑 `HYDROLAB_DATABASE_URL=业务库 python -m hydrolab.db.collation_check`，确认 MISMATCH 后，
用新迁移链 upgrade 到 `c0a111a2f3`（已验证在该状态下可建全外键）。未对业务库执行任何写/迁移。

### 离线 compose 校验（无需 docker daemon）
`HYDROLAB_ENV_FILE=.env.production.example docker compose --env-file ... config` 渲染成功。
不变量：api 无 docker.sock、worker(训练) 有、worker-control 无；api/worker/web/control 走 build 镜像。

### uv.lock 不同步（构建可复现风险）
`apps/api/uv.lock` 1695 行，**不含** celery/redis/mlflow/docker/aiobotocore/greenlet；
venv 已装有这些（说明实际安装未走锁）。Dockerfile 因此不加 `--frozen`（构建时按 pyproject 重解析）。
这破坏构建可复现性，属 Agent C 职责：安装 uv 后 `uv lock` 重新生成并恢复 `--locked`。

### 远程服务探活（只读，2026-09-14）
- Redis `10.196.83.122:6379`：PING=True；`CeleryTaskQueueAdapter.healthcheck` 对 db0/db15 均 True（真实 broker 接通）。
- MinIO `:9000`：`/minio/health/live` HTTP 200。
- MLflow `:5000`：`/health`、`/api/2.0/mlflow/experiments/search` 均 404 → **此端口非 MLflow**，真机 MLflow 集成仍不可做。

## 暂时做不了的部署项（列出，不作为跳过理由）
1. **Docker 镜像构建与运行**：本机无 docker daemon。
2. **真实 GPU 训练端到端**：需 GPU Worker 服务器。
3. **Worker 故障注入**（kill / GET_LOCK 断开 / 容器启停 / 固定容器名不重复 launch）：需 docker。
4. **MLflow 真机跟踪**：`5000` 非 MLflow；无可用 MLflow 服务。
5. **鉴权 S3 上传 / Celery 真发布**：工作区内无 MinIO root 凭证；且向共享 broker 发布真实 job 会触发训练执行，避免越权/破坏。
6. **服务器实际部署**：无 SSH/部署授权，须由有权限的服务器 Agent 执行。
7. **恢复 uv.lock 锁定**：需安装 uv 并跨网解析重生成，避免与 Agent C 撞车。

以上每一项都必须用真机通过（不允许 mock 冒充），等待 GPU 服务器 / 真网关 / 部署授权。
