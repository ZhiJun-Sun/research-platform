# P0 并行子工程：生产部署封装与验收工具

## 目标

在不改动实验执行核心逻辑的前提下，把当前平台整理到可以进行真实服务器部署验收的状态：生产镜像、Worker 服务、Compose 配置、环境变量模板、部署前检查脚本，以及与主代理改动的集成验收记录。

本任务完成后，主代理将负责验收并决定是否合并；不要自行执行生产部署、推送镜像、修改服务器或写入真实密钥。

## 与主代理的边界

主代理正在处理以下核心代码，请不要修改这些文件或其中的领域行为：

- `apps/api/src/hydrolab/execution/service.py`
- `apps/api/src/hydrolab/db/repositories/experiments.py`
- `apps/api/src/hydrolab/db/repositories/execution.py`
- `apps/api/src/hydrolab/adapters/docker/*`
- `apps/api/src/hydrolab/experiments/repositories.py`
- `apps/api/src/hydrolab/experiments/dto.py`
- `apps/api/src/hydrolab/experiments/service.py`

如果发现上述模块的接口需要配合，请在结果中记录兼容性建议，不要直接改动。可以修改部署文件、镜像文件、脚本、部署文档和 Worker 的启动封装；若必须修改 Worker 业务语义，先停下来报告冲突。

## 工作项

### 1. 生产镜像与 Worker 启动

- 检查 `apps/api/Dockerfile` 与 `apps/api/pyproject.toml`，确保生产镜像安装真实运行所需的可选依赖（Docker、Celery/Redis、S3、MLflow 等），并且不会把开发依赖带入生产镜像。
- 为 `apps/worker` 增加可构建的生产 Dockerfile 或等价镜像构建方式。
- 为 Worker 提供明确、可审计的启动入口；如果现有 `configure_runtime(handler)` 仍需要外部注入，请不要伪造“已可生产运行”的 handler，应明确暴露检查失败原因。
- 镜像构建命令必须可复现，避免依赖本机路径或未声明的全局包。

### 2. Compose 与生产配置

- 更新 `infra/docker-compose.production.yml`，加入真正的 Worker 服务、健康检查、依赖关系和必要的资源限制。
- 更新 `infra/.env.production.example`（或实际存在的模板文件），明确列出真实部署所需的 backend 开关：数据库、对象存储、任务队列、实验追踪、Run Executor；生产示例不得默认静默落到 fake 后端。
- 确保 API、Worker、MySQL、Redis、MinIO/S3、MLflow 的环境变量名称与当前代码一致。
- 保留安全默认值：不提交真实密码、Token、云端密钥；对强制生产变量给出清晰的启动失败提示。
- 清理或标记不可用的 placeholder runner/profile，不能让默认 Compose 看起来已支持 GPU 但实际启动的是占位镜像。

### 3. 部署前检查脚本

新增一个不泄露密钥的检查脚本，例如 `scripts/verify-p0-deployment.sh` 或同等 Python 脚本，至少检查：

- Compose 配置可以展开（例如 `docker compose config`）。
- API/Worker 镜像中的关键 Python 包可导入。
- MySQL、Redis、对象存储、MLflow 的 endpoint/凭据变量是否齐全；不得打印秘密值。
- GPU 部署时 Docker GPU runtime、宿主机 NVIDIA 驱动和可见 GPU 配置是否满足要求；无 GPU 时应明确报告而不是误判成功。
- 生产 backend 配置没有悄悄使用 fake 实现。
- 检查脚本在服务未启动时能给出可读的失败原因和下一步，不要修改数据。

### 4. 文档与验收记录

- 更新 `infra/README.md`，把“已实现”“需要服务器条件”“仍未完成”分开，删除与代码现状矛盾的描述。
- 写明从零部署、启动、健康检查、提交一次小型训练、查看结果、停止任务的命令；命令中的秘密使用占位符。
- 增加一份简短验收记录，至少包含：修改文件、执行命令、通过/失败结果、仍需主代理确认的接口。

## 验收标准

1. `docker compose -f infra/docker-compose.production.yml --env-file infra/.env.production.example config` 能成功展开，或在示例文件刻意缺少秘密时给出明确且预期的失败说明。
2. API 与 Worker 镜像构建文件可静态审阅，真实后端依赖不会因 optional dependency 未安装而在启动时才失败。
3. Compose 中存在独立 Worker，且不会与 API 重复执行任务。
4. 生产配置显式选择真实 backend；fake 只能作为本地开发 profile 或明确的回退模式。
5. 检查脚本不输出密码/token，退出码能区分通过与失败。
6. 不修改主代理负责的核心执行、Outbox、GPU lease、Docker adapter 代码；如存在必要联动，结果中清楚列出。

## 建议验证命令

```bash
docker compose -f infra/docker-compose.production.yml --env-file infra/.env.production.example config
docker build -f apps/api/Dockerfile apps/api
docker build -f apps/worker/Dockerfile apps/worker
./scripts/verify-p0-deployment.sh --help
```

如果当前机器没有 Docker daemon，请至少完成静态检查、Dockerfile 语法/依赖审阅，并在验收记录中明确标注未执行的容器级验证。

## 交付格式

完成后请返回：

1. 修改文件清单；
2. 执行过的命令和结果；
3. 无法完成的项及原因；
4. 与主代理核心改动可能发生的接口冲突；
5. 你认为主代理必须阻断发布的剩余风险。

