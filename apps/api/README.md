# HydroLab API

水文时序实验平台后端（FastAPI，模块化单体）。契约见 `plans/02`，开源准入见 `plans/05`。

## 设计原则

- **代码优先**：默认全 Fake 适配器，无需 PostgreSQL/Redis/S3/MLflow/GPU 即可开发与测试；
- **端口隔离**：领域服务只依赖 `hydrolab.ports` 的 Protocol，第三方 SDK 只能出现在 `hydrolab.adapters`；
- **业务真相自有**：Run 状态机、权限、不可变版本、GPU 租约由本平台维护，外部系统状态不得反向覆盖。

## 目录

```text
src/hydrolab/
├── core/       # settings / errors / logging / middleware
├── ports/      # ObjectStorage、TaskQueue、ExperimentTracker、RunExecutor、DTO
├── adapters/
│   ├── fake/   # 内存实现 + 故障/重复注入（测试与本地开发基线）
│   └── local/  # 本地文件系统对象存储
├── api/        # deps 装配 + 路由（B0 仅健康检查）
└── main.py     # create_app()
tests/
├── contracts/  # 端口契约测试：Fake/Local/未来真实实现共用
└── ...         # HTTP 层与错误模型测试
alembic/        # 迁移骨架（真实 PostgreSQL 接入后启用）
```

## 快速开始

```bash
cd apps/api
uv sync                 # 自动管理 Python ≥3.11 与依赖
uv run pytest           # 全部契约/单元测试
uv run ruff check src tests
uv run mypy src
uv run uvicorn hydrolab.main:app --reload
```

端点：

- `GET /health/live` — 进程存活；
- `GET /health/ready` — 按启用的后端逐组件报告（Fake 模式如实标注 backend=fake）；
- `GET /openapi.json` — REST 契约唯一来源。

## B1 已实现：身份、邀请、授权与分享

数据存储为 **InMemory Repository**（进程重启即清空，专供无数据库联调）；
部署时仅替换 `hydrolab/api/container.py` 中的构造实现为 SQL 版本，服务与路由不变。

本地联调账号（首次启动自动 bootstrap）：`admin@hydrolab.cn` / `admin123456`。

```text
POST /api/v1/auth/login|refresh|logout      会话（access 30min / refresh 14d，存储哈希）
GET|PATCH /api/v1/me[/preferences]          当前用户与偏好（Run 卡片布局等）
POST /api/v1/admin/invitations              管理员邀请（token 仅返回一次）
GET  /api/v1/admin/invitations              邀请列表（不含 token）
POST /api/v1/admin/invitations/{id}/revoke  撤销邀请
POST /api/v1/invitations/{token}/accept     接受邀请（唯一注册入口）
GET|POST /api/v1/resources/{type}/{id}/grants    资源授权（OWNER/VIEWER）
DELETE /api/v1/resources/{type}/{id}/grants/{id} 撤销授权
POST /api/v1/share-links                    创建只读链接（版本锁定 + Idempotency-Key）
GET  /api/v1/share-links                    我的分享（含访问计数）
POST /api/v1/share-links/{id}/revoke        撤销（幂等，立即生效）
GET  /api/v1/shared/{token}                 公开访问（字段白名单 + 限流防枚举）
```

安全语义（均有测试覆盖）：无公开注册；过期/已用/撤销邀请拒绝；用户 A 不可见用户 B 资源；
VIEWER 不能管理授权和分享；分享过期/撤销返回 410；审计不记录凭证；token 只存 HMAC 哈希。

## 切换到真实服务

按 `plans/05` 的 Spike 门禁逐个启用（见 `infra/README.md` 与 `.env.example`）。
选择未实现的真实后端会得到明确的 `DEPENDENCY_UNAVAILABLE`，不会静默降级。
