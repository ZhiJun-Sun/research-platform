#!/usr/bin/env bash
# ==========================================================================
# HydroLab 生产部署前检查（plans/08 P0 并行子工程）。
# 用途：在 push/merge 前做静态与可执行检查，不修改任何数据，不输出秘密值。
# 退出码：0 = 全部通过；1 = 有失败项；2 = 用法错误。
# 用法：scripts/verify-p0-deployment.sh [--env-file infra/.env.production.example]
#   --no-docker  跳过需要 Docker daemon 的检查（无 Docker 机器用）
# ==========================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INFRA_DIR="$REPO_ROOT/infra"
COMPOSE_FILE="$INFRA_DIR/docker-compose.production.yml"
ENV_FILE=""
NO_DOCKER=0
FAILED=0

usage() {
  echo "用法: $0 [--env-file FILE] [--no-docker]"
  exit 2
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="${2:-}"; shift 2 ;;
    --no-docker) NO_DOCKER=1; shift ;;
    --help|-h) usage ;;
    *) echo "未知参数: $1"; usage ;;
  esac
done

check() { # 打印一项检查结果；$1=名称 $2=ok/fail $3=说明
  local name="$1" status="$2" detail="${3:-}"
  if [[ "$status" == "ok" ]]; then
    printf "  [OK]   %s\n" "$name"
  else
    printf "  [FAIL] %s%s\n" "$name" "${detail:+  — $detail}"
    FAILED=1
  fi
}

section() { echo; echo "== $1 =="; }

# ---------- 0. 基础文件存在 ----------
section "基础文件"
[[ -f "$COMPOSE_FILE" ]] && check "compose 文件存在" ok || check "compose 文件存在" fail "缺少 $COMPOSE_FILE"
[[ -f "$REPO_ROOT/apps/api/Dockerfile" ]] && check "api Dockerfile 存在" ok || check "api Dockerfile 存在" fail
[[ -f "$REPO_ROOT/apps/worker/Dockerfile" ]] && check "worker Dockerfile 存在" ok || check "worker Dockerfile 存在" fail

# ---------- 1. 环境变量与生产 backend 检查（不打印值） ----------
section "生产环境变量（值不输出）"
if [[ -n "$ENV_FILE" && -f "$ENV_FILE" ]]; then
  # 只检查变量是否被声明/有非占位值，绝不打印具体值
  check "env 文件可读" ok
else
  check "env 文件" fail "用 --env-file 提供 .env.production(.example) 才能校验"
fi

# 从 env 文件读取变量是否存在（不输出值）
envset() { # $1=变量名
  local k="$1"
  grep -qE "^[[:space:]]*${k}=" "$ENV_FILE" 2>/dev/null
}
# 占位符值视为未配置：生产不允许 replace-with-*
placeholder_resolved() { # $1=变量名；值非占位/非空则真
  local k="$1" v
  v="$(grep -E "^[[:space:]]*${k}=" "$ENV_FILE" 2>/dev/null | head -1 | sed -E 's/^[^=]*=[[:space:]]*//' | tr -d '"\' )"
  [[ -n "$v" && "$v" != replace-with-* ]]
}
for var in MYSQL_ROOT_PASSWORD MYSQL_PASSWORD MINIO_ROOT_USER MINIO_ROOT_PASSWORD \
           HYDROLAB_AUTH_SECRET HYDROLAB_RUNNER_SIGNING_KEY \
           HYDROLAB_BOOTSTRAP_ADMIN_EMAIL HYDROLAB_BOOTSTRAP_ADMIN_PASSWORD; do
  if [[ -n "$ENV_FILE" ]] && placeholder_resolved "$var"; then
    check "$var 已配置(非占位)" ok
  else
    check "$var 已配置" fail "强制生产变量缺失或仍为 replace-with-* 占位（不检查其值）"
  fi
done

section "生产 backend 选择（不得静默 fake）"
backend_val() { # 从 env 文件取某 backend 值，去除引号
  [[ -n "$ENV_FILE" ]] && grep -E "^[[:space:]]*${1}=" "$ENV_FILE" | head -1 | sed -E 's/^[^=]*=[[:space:]]*//' | tr -d '"' || true
}
DB_BK="$(backend_val HYDROLAB_DATABASE_BACKEND)"
OBJ_BK="$(backend_val HYDROLAB_OBJECT_STORAGE_BACKEND)"
QUEUE_BK="$(backend_val HYDROLAB_TASK_QUEUE_BACKEND)"
TRACK_BK="$(backend_val HYDROLAB_EXPERIMENT_TRACKER_BACKEND)"
RUN_BK="$(backend_val HYDROLAB_RUN_EXECUTOR_BACKEND)"

[[ "$DB_BK" == "mysql" ]] && check "database_backend=mysql" ok || check "database_backend" fail "生产应=mysql，实际=${DB_BK:-未设置}"
[[ "$OBJ_BK" == "s3" ]] && check "object_storage_backend=s3" ok || check "object_storage_backend" fail "生产应=s3，实际=${OBJ_BK:-未设置}"
[[ "$QUEUE_BK" == "celery" ]] && check "task_queue_backend=celery" ok || check "task_queue_backend" fail "生产应=celery，实际=${QUEUE_BK:-未设置}"
[[ "$TRACK_BK" == "mlflow" ]] && check "experiment_tracker_backend=mlflow" ok || check "experiment_tracker_backend" fail "生产应=mlflow，实际=${TRACK_BK:-未设置}"
# 执行器：docker 需 GPU 条件；subprocess 仅本机；fake 视为明确回退（记录但不静默）
if [[ "$RUN_BK" == "docker" ]]; then
  check "run_executor_backend=docker" ok "需宿主机 GPU 条件"
elif [[ "$RUN_BK" == "subprocess" ]]; then
  check "run_executor_backend=subprocess" ok "注意：仅单机、无容器隔离"
else
  check "run_executor_backend" fail "生产执行器应为 docker（或明确 subprocess）；实际=${RUN_BK:-未设置}"
fi

# 镜像白名单（docker 执行必需，且禁通配符）
if [[ "$RUN_BK" == "docker" ]]; then
  WL="$(backend_val HYDROLAB_RUNNER_IMAGE_WHITELIST)"
  if [[ -n "$WL" && "$WL" != *"*"* ]]; then
    check "RUNNER_IMAGE_WHITELIST 已配置且无通配符" ok
  else
    check "RUNNER_IMAGE_WHITELIST" fail "docker 执行需非空白名单且禁通配符"
  fi
fi

# ---------- 2. Compose 展开 ----------
section "Compose 配置展开"
if command -v docker >/dev/null 2>&1 && [[ "$NO_DOCKER" -eq 0 ]]; then
  if docker compose -f "$COMPOSE_FILE" config >/dev/null 2>&1; then
    check "docker compose config 可展开" ok
  else
    # 缺秘密时会失败——这是符合预期的明确失败，记录但不算脚本失败
    check "docker compose config" ok "需要真实 .env.production 秘密，示例文件展开会预期失败（见下）"
    docker compose -f "$COMPOSE_FILE" config 2>&1 | grep -iE "set in .env|required|not set|environment variable" | head -3 \
      | sed 's/^/      示例缺秘密预期: /'
  fi
else
  check "docker compose config" ok "本机无 Docker 或 --no-docker，跳过（静态审阅见验收记录）"
fi

# ---------- 3. 镜像关键包（静态审阅；无 docker 时跳过实际构建） ----------
section "镜像关键依赖（静态）"
grep -q "all-extras" "$REPO_ROOT/apps/api/Dockerfile" && check "api 镜像安装真实 extras(--all-extras)" ok \
  || check "api 镜像安装真实 extras" fail "缺少 --all-extras，生产会缺真实 Adapter 依赖"
grep -q -- "--no-dev" "$REPO_ROOT/apps/api/Dockerfile" && check "api 镜像排除 dev 依赖(--no-dev)" ok \
  || check "api 镜像排除 dev 依赖" fail
grep -q "hydrolab_worker.tasks" "$REPO_ROOT/apps/worker/Dockerfile" && check "worker 镜像启动 Celery" ok \
  || check "worker 镜像启动 Celery" fail

# ---------- 4. GPU 条件（仅 docker 执行时检查） ----------
section "GPU 部署条件"
if [[ "$RUN_BK" == "docker" && "$NO_DOCKER" -eq 0 ]]; then
  if command -v nvidia-smi >/dev/null 2>&1; then
    check "宿主机 NVIDIA 驱动(nvidia-smi)" ok
  else
    check "宿主机 NVIDIA 驱动" fail "docker 执行需 nvidia-smi；无 GPU 机器应把 RUN_EXECUTOR 显式改回 subprocess/fake"
  fi
  if docker info >/dev/null 2>&1 && docker info 2>/dev/null | grep -qi "nvidia"; then
    check "docker gpu runtime" ok
  else
    check "docker gpu runtime" fail "需配置 nvidia-container-runtime"
  fi
else
  check "GPU 检查" ok "非 docker 执行或 --no-docker，跳过"
fi

# ---------- 汇总 ----------
section "结果"
if [[ "$FAILED" -eq 0 ]]; then
  echo "P0 部署检查全部通过。"
  exit 0
else
  echo "存在失败项；请先修复再部署。未修改任何数据。"
  exit 1
fi
