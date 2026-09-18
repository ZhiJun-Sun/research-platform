# Agent B 验收记录：环境、产物与运行时收口

日期：2026-09-14

## 已完成

### 环境镜像 digest（B-01/B-02）

- `EnvironmentVersion` 已在服务创建时登记 `image_digest`，当前使用经过严格校验的不可变 `base_image` 引用。
- 新增严格校验：必须是 `<name>@sha256:<64 位小写十六进制>`，拒绝 tag-only、空值、首尾空白、控制字符、占位串和短 digest。
- API 的 `EnvironmentVersionView` 暴露 `image_digest`；已有 SQL model/repository 字段继续用于持久化和回读。
- 实验配置已有 `environment_image_digest`，Docker Runner 可据此执行白名单校验。
- 更新 dev seed 和测试 fixture 使用格式有效的 digest。

### 训练输出契约（B-03）

- `RunControlService` 增加受控 `{OUTPUT_DIR}` argv 占位符。
- subprocess 映射到宿主机工作区 `output`，Docker 映射到容器内 `/workspace/output`。
- Docker/local executor 继续通过 `HYDROLAB_OUTPUT_DIR` 暴露可写输出目录；代码目录保持只读挂载。
- 新增 argv 渲染单测，覆盖 subprocess、Docker 和输出路径映射。

### MLflow 重放幂等（B-07）

- `MlflowTrackingAdapter.start_run` 在创建前按 `hydrolab.run_id` tag 查询已有 MLflow Run。
- Worker 重启导致进程内 `_started` 映射丢失时，会复用已有外部 Run，不创建重复 Run。
- 新增 fake-client 回归测试覆盖重启/重放场景。

### Result 自动持久化（B-05）

- 真实 Runner 成功采集后，在标记 Run `SUCCEEDED` 前把 Result、MetricPoint 与 ResultArtifact 幂等写入领域仓储。
- 生产 Worker 装配同一 `ResultService`；MySQL 后端因此不再依赖 Worker 进程内 `_reports`。
- `/runs/{id}/collection` 在内存报告不存在时从持久结果、指标和产物回读；`/result/ingest` 保留为幂等确认接口。
- 本地真实 subprocess 从网页提交小训练已验证：7 行日志、4 条指标、5 个产物自动登记，结果页直接可见。

### 资源权限（B-08）

- Run 的 await、collection、events、logs、resources、SSE stream 全部增加 Run 所有者/管理员校验。
- `/internal/*` 的 dispatch、complete、progress、metrics、resource 上报改为管理员依赖；真实 Worker 走数据库/队列，不依赖这些浏览器接口。
- 新增跨用户负例测试，覆盖观测、控制、内部上报和 dispatch。

## 验证结果

```text
apps/api/.venv/bin/python -m pytest -q tests/test_code_assets.py tests/test_experiments.py
9 passed

apps/api/.venv/bin/python -m pytest -q tests/test_run_permissions.py tests/test_execution.py
7 passed

apps/api/.venv/bin/python -m pytest -q tests/adapters/test_mlflow_tracker.py
4 passed

apps/api/.venv/bin/python -m pytest -q tests/test_execution_service.py
3 passed

apps/api/.venv/bin/python -m pytest -q tests --disable-warnings
162 passed, 13 skipped
```

## 未完成项与精确依赖

### B-04：S3 上传闭环

代码导入和数据导入已经调用受控 `put_bytes`，S3 adapter 已有 create/complete/head/open_range 逻辑；但本轮没有可用的 MinIO/S3 服务，因此没有宣称 presigned PUT、multipart complete、hash、bundle 物化和缺对象失败已通过真实验收。

TODO：在独立 MinIO bucket 中逐条验证 ZIP/数据上传、complete 后 HEAD、内容 hash、下载/范围读取、导出 bundle 和缺对象错误；同时检查所有导入路径不得依赖 Fake/Local 实现的 `.objects` 或 `._root` 私有字段。

### B-05 剩余验收：真实 MySQL 重启

代码路径已改为 Worker 自动写入 SQL store，并有新建 `ResultService` 后仍可回读的回归测试。由于本轮按用户要求不执行 A2 容器部署，真实 MySQL + API/Worker 重启验收仍需在 8 个服务启动后执行；不把本地 memory 后端宣称为真机重启通过。Checkpoint 独立领域对象的自动创建仍需补充模型签名等元数据；当前 checkpoint 文件已作为持久 ResultArtifact 可查。

### B-06：Docker 日志链路

当前 Docker executor 负责容器启动、轮询、取消和终态，但没有持续将容器 stdout/stderr 增量写入 `RunLog`，也没有重启续读 cursor 和日志截断策略。

TODO：在 Worker 中使用非阻塞 Docker log stream，按 RunLog cursor 增量写入，设置单行/单 Run 上限与归档策略；Worker 重启后从 Docker 日志 cursor 继续读取，不能无限积累内存。需要真实 Docker daemon 验证。

### B-09：动态 GPU 配置

当前契约仍为单 Run 默认 1 GPU、总数 2；GPU lease 的 `gpu_index` 已作为执行事实来源，Docker DeviceIDs 和 CUDA 本地序号已有实现。

TODO：如需动态设备列表或多卡，需冻结 resource request 并贯通 API、队列、Worker、lease、DeviceIDs、恢复和前端；不能只调整 UI 或 concurrency。需要具备 GPU 的 Linux 主机验收。

### 内部认证说明

本轮将 HTTP `/internal/*` 收紧为管理员依赖，满足当前本地 Fake/HTTP 调用的最小权限边界。生产 Worker 实际通过持久化仓储和 Celery/Outbox 工作，不调用这些 HTTP endpoint。若未来需要 Worker 经 HTTP 上报，应由 Agent A/B 协调增加专用 service token/mTLS，不应复用普通用户 Bearer token。
