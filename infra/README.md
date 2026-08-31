# HydroLab 基础设施与 B9 部署基线

## 当前交付范围

B9 已提供可部署编排骨架：PostgreSQL 16、Redis 7、MinIO、MLflow、API、静态 Web 与同源 `/api` 反向代理。生产 Compose **默认仍使用 Fake Adapter**，因为 S3、Celery、MLflow 与 Docker GPU Runner 的业务 Adapter 尚未在应用代码中实现；不得仅通过修改环境变量把它们标记为已启用。

## Ubuntu 服务器前置条件

```bash
# Docker Engine / Compose plugin
sudo docker --version
sudo docker compose version

# GPU Runner profile 启用前必须确认
nvidia-smi
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi
```

第二条命令失败时，先安装/修复 NVIDIA Container Toolkit；不要启用 `gpu` profile。

## 启动基础服务

```bash
cd infra
cp .env.production.example .env.production
# 填写所有 replace-with-* 值，并修改 PUBLIC_BASE_URL/CORS 所需域名
sudo docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
sudo docker compose --env-file .env.production -f docker-compose.production.yml ps
```

Web 仅监听服务器回环地址 `127.0.0.1:8080`。生产应由 Caddy/Nginx/云负载均衡器在外层提供 TLS，再代理到该端口。

## 验收

```bash
curl -f http://127.0.0.1:8080/health
curl -f http://127.0.0.1:8080/api/v1/health
sudo docker compose --env-file .env.production -f docker-compose.production.yml logs --tail=100 api
```

> API 的生产设置会拒绝默认密钥和缺失的管理员账号。当前 Fake Adapter 基线可用于页面和业务流程验收，但不能执行真实训练。

## 后续真实 Adapter 切换门禁

| 组件 | 必须完成的实现与验收 | 才能切换 |
|---|---|---|
| S3 | `S3ObjectStorageAdapter`，上传/下载/签名 URL/权限 Spike | `OBJECT_STORAGE_BACKEND=s3` |
| Celery | Outbox publisher、幂等 worker、重试/死信/恢复 Spike | `TASK_QUEUE_BACKEND=celery` |
| MLflow | Tracking Adapter、Run/metric/artifact 关联 Spike | `EXPERIMENT_TRACKER_BACKEND=mlflow` |
| Docker GPU | 签名 RunSpec、只读挂载、网络/权限/超时/清理与双 4090 压测 | `RUN_EXECUTOR_BACKEND=docker` + `--profile gpu` |

在以上门禁通过前，`runner` 服务始终保持未启用状态。
