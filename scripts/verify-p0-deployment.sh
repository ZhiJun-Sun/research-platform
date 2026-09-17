#!/usr/bin/env bash
# ==========================================================================
# HydroLab 生产部署前检查（plans/08 P0 并行子工程；v2 增加资源/端口/GPU 冒烟）。
# 用途：部署前做静态与可执行检查，不修改任何数据，不输出秘密值。
# 退出码：0 = 全部通过；1 = 有失败项；2 = 用法错误。
# 用法：scripts/verify-p0-deployment.sh [--env-file infra/.env.production]
#   --no-docker       跳过需要 Docker daemon 的检查（无 Docker 机器用）
#   --skip-gpu-smoke  跳过 CUDA 容器冒烟测试（离线机器；其余 GPU 检查保留）
# ==========================================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INFRA_DIR="$REPO_ROOT/infra"
COMPOSE_FILE="$INFRA_DIR/docker-compose.production.yml"
ENV_FILE=""
NO_DOCKER=0
SKIP_GPU_SMOKE=0
FAILED=0

usage() {
  echo "用法: $0 [--env-file FILE] [--no-docker] [--skip-gpu-smoke]"
  exit 2
}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="${2:-}"; shift 2 ;;
    --no-docker) NO_DOCKER=1; shift ;;
    --skip-gpu-smoke) SKIP_GPU_SMOKE=1; shift ;;
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
warn() { printf "  [WARN] %s%s\n" "$1" "${2:+  — $2}"; }
section() { echo; echo "== $1 =="; }

# ---------- 0. 基础文件存在 ----------
section "基础文件"
[[ -f "$COMPOSE_FILE" ]] && check "compose 文件存在" ok || check "compose 文件存在" fail "缺少 $COMPOSE_FILE"
[[ -f "$REPO_ROOT/apps/api/Dockerfile" ]] && check "api Dockerfile 存在" ok || check "api Dockerfile 存在" fail
[[ -f "$REPO_ROOT/apps/worker/Dockerfile" ]] && check "worker Dockerfile 存在" ok || check "worker Dockerfile 存在" fail
[[ -f "$REPO_ROOT/apps/web/Dockerfile" ]] && check "web Dockerfile 存在" ok || check "web Dockerfile 存在" fail

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
env_val() { # 取变量值（去引号）；env 文件缺失时输出空
  [[ -n "$ENV_FILE" && -f "$ENV_FILE" ]] || { printf ""; return; }
  grep -E "^[[:space:]]*${1}=" "$ENV_FILE" 2>/dev/null | head -1 | sed -E 's/^[^=]*=[[:space:]]*//' | tr -d '"'"'"''
}
# 占位符值视为未配置：生产不允许 replace-with-*
placeholder_resolved() { # $1=变量名；值非占位/非空则真
  local k="$1" v
  v="$(env_val "$k")"
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
DB_BK="$(env_val HYDROLAB_DATABASE_BACKEND)"
OBJ_BK="$(env_val HYDROLAB_OBJECT_STORAGE_BACKEND)"
QUEUE_BK="$(env_val HYDROLAB_TASK_QUEUE_BACKEND)"
TRACK_BK="$(env_val HYDROLAB_EXPERIMENT_TRACKER_BACKEND)"
RUN_BK="$(env_val HYDROLAB_RUN_EXECUTOR_BACKEND)"

[[ "$DB_BK" == "mysql" ]] && check "database_backend=mysql" ok || check "database_backend" fail "生产应=mysql，实际=${DB_BK:-未设置}"
[[ "$OBJ_BK" == "s3" ]] && check "object_storage_backend=s3" ok || check "object_storage_backend" fail "生产应=s3，实际=${OBJ_BK:-未设置}"
[[ "$QUEUE_BK" == "celery" ]] && check "task_queue_backend=celery" ok || check "task_queue_backend" fail "生产应=celery，实际=${QUEUE_BK:-未设置}"
[[ "$TRACK_BK" == "mlflow" ]] && check "experiment_tracker_backend=mlflow" ok || check "experiment_tracker_backend" fail "生产应=mlflow，实际=${TRACK_BK:-未设置}"
# 执行器：docker 需 GPU 条件；subprocess 仅本机；fake 视为明确回退（记录但不静默）
if [[ "$RUN_BK" == "docker" ]]; then
  check "run_executor_backend=docker" ok "需宿主机 GPU 条件（见下）"
elif [[ "$RUN_BK" == "subprocess" ]]; then
  check "run_executor_backend=subprocess" ok "注意：仅单机、无容器隔离"
else
  check "run_executor_backend" fail "生产执行器应为 docker（或明确 subprocess）；实际=${RUN_BK:-未设置}"
fi

# 镜像白名单（docker 执行必需，禁通配符，且不得保留占位 digest）
if [[ "$RUN_BK" == "docker" ]]; then
  WL="$(env_val HYDROLAB_RUNNER_IMAGE_WHITELIST)"
  if [[ -z "$WL" ]]; then
    check "RUNNER_IMAGE_WHITELIST" fail "docker 执行需非空白名单"
  elif [[ "$WL" == *"*"* ]]; then
    check "RUNNER_IMAGE_WHITELIST" fail "白名单禁用通配符"
  elif [[ "$WL" == *REPLACE* ]]; then
    check "RUNNER_IMAGE_WHITELIST" fail "仍是 replace/REPLACE 占位 digest，须换成真实训练镜像"
  else
    check "RUNNER_IMAGE_WHITELIST 已配置且无通配符" ok
  fi
fi

# ---------- 2. 宿主机端口占用（值取自 env 文件，默认 8080/9001） ----------
section "宿主机端口占用（新栈只应占用 Web 与 MinIO 控制台两个号）"
if command -v ss >/dev/null 2>&1; then
  LISTEN_TOOL="ss -ltn"
elif command -v netstat >/dev/null 2>&1; then
  LISTEN_TOOL="netstat -ltn"
else
  LISTEN_TOOL=""
fi
port_in_use() { # $1=端口号；在监听表第 4 列匹配 :端口 结尾
  [[ -n "$LISTEN_TOOL" ]] || return 1
  $LISTEN_TOOL 2>/dev/null | awk '{print $4}' | grep -E ":${1}$" >/dev/null
}
if [[ -z "$LISTEN_TOOL" ]]; then
  warn "端口检查" "本机无 ss/netstat，跳过"
else
  while read -r BIND_VAR PORT_VAR LABEL; do
    BIND="$(env_val "$BIND_VAR")"; BIND="${BIND:-127.0.0.1}"
    PORT="$(env_val "$PORT_VAR")"; PORT="${PORT:-8080}"
    if port_in_use "$PORT"; then
      check "$LABEL 端口 $PORT 空闲" fail "宿主机已被占用；在 env 文件把 $PORT_VAR 改成空闲端口（容器内部端口不受影响）"
    else
      check "$LABEL 端口 $PORT 空闲" ok "将绑定 ${BIND}:${PORT}"
    fi
    if [[ "$BIND" == "0.0.0.0" || "$BIND" == "*" || "$BIND" == "::" ]]; then
      warn "$LABEL 对外暴露" "绑定 0.0.0.0 为 HTTP 明文；公网正式使用建议外层加 TLS 反代"
    fi
  done <<< $'HYDROLAB_WEB_BIND HYDROLAB_WEB_PORT Web\nHYDROLAB_MINIO_CONSOLE_BIND HYDROLAB_MINIO_CONSOLE_PORT MinIO控制台'
fi

# ---------- 3. 宿主机资源 ----------
section "宿主机资源"
if [[ -r /proc/meminfo ]]; then
  MEM_KB="$(awk '/^MemTotal:/{print $2}' /proc/meminfo)"
  MEM_GIB=$(( MEM_KB / 1024 / 1024 ))
  if (( MEM_GIB >= 4 )); then
    check "内存 ≥ 4 GiB" ok "共 ${MEM_GIB} GiB"
  else
    check "内存 ≥ 4 GiB" fail "仅 ${MEM_GIB} GiB；整套栈（MySQL/Redis/MinIO/MLflow/API/Worker×2/Web）至少 4 GiB，建议 8 GiB"
  fi
else
  warn "内存检查" "非 Linux，跳过（部署目标为 Linux 服务器）"
fi
disk_avail_kb() { df -Pk "$1" 2>/dev/null | awk 'NR==2{print $4}'; }
WS_ROOT="$(env_val HYDROLAB_RUNNER_WORKSPACE_ROOT)"; WS_ROOT="${WS_ROOT:-/srv/hydrolab/runs}"
for target in "$REPO_ROOT" "$WS_ROOT"; do
  KB="$(disk_avail_kb "$target")"
  if [[ -z "$KB" ]]; then
    warn "磁盘可用空间(${target})" "路径不存在或无法读取 df"
    continue
  fi
  GB=$(( KB / 1024 / 1024 ))
  if (( GB < 10 )); then
    check "磁盘可用空间(${target})" fail "仅 ${GB} GB；镜像+MySQL/MinIO 数据建议 ≥ 20 GB"
  elif (( GB < 20 )); then
    warn "磁盘可用空间(${target})" "剩 ${GB} GB，建议 ≥ 20 GB"
  else
    check "磁盘可用空间(${target})" ok "剩 ${GB} GB"
  fi
done

# ---------- 4. Compose 展开 ----------
section "Compose 配置展开"
if command -v docker >/dev/null 2>&1 && [[ "$NO_DOCKER" -eq 0 ]]; then
  # env_file 相对 compose 文件目录解析：提供 env 文件时把 HYDROLAB_ENV_FILE 指到 infra/ 下的同名文件
  ENV_BASE="$(basename "$ENV_FILE")"
  if [[ -n "$ENV_FILE" && -f "$ENV_FILE" ]] \
     && HYDROLAB_ENV_FILE="$ENV_BASE" docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config >/dev/null 2>&1; then
    check "docker compose config 可展开" ok
  else
    # 缺秘密时会失败——这是符合预期的明确失败，记录但不算脚本失败
    check "docker compose config" ok "需要真实 .env.production 秘密，示例文件展开会预期失败（见下）"
    HYDROLAB_ENV_FILE="$ENV_BASE" docker compose --env-file "${ENV_FILE:-$INFRA_DIR/.env.production.example}" -f "$COMPOSE_FILE" config 2>&1 \
      | grep -iE "set in .env|required|not set|environment variable|env file" | head -3 \
      | sed 's/^/      示例缺秘密预期: /'
  fi
else
  check "docker compose config" ok "本机无 Docker 或 --no-docker，跳过（静态审阅见验收记录）"
fi

# ---------- 5. 镜像关键包（静态审阅；无 docker 时跳过实际构建） ----------
section "镜像关键依赖（静态）"
grep -q "all-extras" "$REPO_ROOT/apps/api/Dockerfile" && check "api 镜像安装真实 extras(--all-extras)" ok \
  || check "api 镜像安装真实 extras" fail "缺少 --all-extras，生产会缺真实 Adapter 依赖"
grep -q -- "--no-dev" "$REPO_ROOT/apps/api/Dockerfile" && check "api 镜像排除 dev 依赖(--no-dev)" ok \
  || check "api 镜像排除 dev 依赖" fail
grep -q "hydrolab_worker.tasks" "$REPO_ROOT/apps/worker/Dockerfile" && check "worker 镜像启动 Celery" ok \
  || check "worker 镜像启动 Celery" fail

# ---------- 6. GPU 条件（docker 执行器：驱动/数量/工具链/CUDA 冒烟） ----------
section "GPU 部署条件"
if [[ "$RUN_BK" != "docker" ]]; then
  check "GPU 检查" ok "执行器=${RUN_BK:-未设置}，非 docker 不需要 GPU"
elif [[ "$NO_DOCKER" -eq 1 ]]; then
  check "GPU 检查" ok "--no-docker，跳过"
else
  if command -v nvidia-smi >/dev/null 2>&1; then
    check "宿主机 NVIDIA 驱动(nvidia-smi)" ok
    GPU_COUNT="$(nvidia-smi -L 2>/dev/null | grep -c '^GPU' || true)"
    GPU_DESC="$(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null | sort -u | tr '\n' '；')"
    if (( GPU_COUNT >= 2 )); then
      check "GPU 数量=${GPU_COUNT}" ok "满足双卡并行设计（每卡同时一个 Run）：${GPU_DESC}"
    elif (( GPU_COUNT == 1 )); then
      check "GPU 数量=1" ok "可运行，但一次只能训练一个（双卡并行需 2 张）：${GPU_DESC}"
    else
      check "GPU 数量" fail "nvidia-smi 存在但未枚举到 GPU；检查驱动与容器冲突"
    fi
  else
    check "宿主机 NVIDIA 驱动" fail "docker 执行需 nvidia-smi；无 GPU 机器应把 RUN_EXECUTOR 显式改回 fake"
    GPU_COUNT=0
  fi
  if docker info >/dev/null 2>&1 && docker info 2>/dev/null | grep -qi "nvidia"; then
    check "docker gpu runtime 已注册" ok
  else
    warn "docker gpu runtime" "docker info 未见 nvidia runtime；CDI 模式属正常，以冒烟测试为准"
  fi
  if (( GPU_COUNT >= 1 )); then
    if command -v nvidia-ctk >/dev/null 2>&1; then
      check "nvidia-container-toolkit(nvidia-ctk)" ok
    else
      warn "nvidia-container-toolkit" "未找到 nvidia-ctk；冒烟测试失败时需安装后 systemctl restart docker"
    fi
    if [[ "$SKIP_GPU_SMOKE" -eq 1 ]]; then
      check "CUDA 容器冒烟测试" ok "--skip-gpu-smoke 跳过"
    else
      # 探针镜像优先用 env 白名单里的训练镜像（本地已有、最贴近真实训练、不依赖网络）；
      # 白名单未就绪时回退官方 CUDA 探针（可能需要联网拉取）。
      PROBE_IMG="$(env_val HYDROLAB_RUNNER_IMAGE_WHITELIST | tr -d '[]"' | cut -d, -f1 | xargs)"
      if [[ -n "$PROBE_IMG" && "$PROBE_IMG" != *REPLACE* && "$PROBE_IMG" == *@sha256:* ]]; then
        docker pull -q "$PROBE_IMG" >/dev/null 2>&1 || true   # 本地已有时立即返回；离线不阻塞
        if docker run --rm --gpus all "$PROBE_IMG" python -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" >/dev/null 2>&1; then
          check "CUDA 容器冒烟测试(--gpus all, 训练镜像)" ok "torch.cuda 可用；保持 HYDROLAB_RUNNER_GPU_MODE=device_requests"
        elif docker run --rm --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all "$PROBE_IMG" python -c "import torch,sys; sys.exit(0 if torch.cuda.is_available() else 1)" >/dev/null 2>&1; then
          check "CUDA 容器冒烟测试(--runtime=nvidia/CDI, 训练镜像)" ok "torch.cuda 可用"
          warn "GPU 注入模式" "此宿主机为 CDI 模式：在 .env.production 设 HYDROLAB_RUNNER_GPU_MODE=nvidia_runtime"
        else
          check "CUDA 容器冒烟测试" fail "训练镜像内 torch.cuda 不可用：镜像 CUDA 版本与驱动不匹配，或两种注入方式均未生效"
        fi
      else
        docker pull -q nvidia/cuda:12.4.1-base-ubuntu22.04 >/dev/null 2>&1 || true
        if docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
          check "CUDA 容器冒烟测试(--gpus all)" ok "容器内可见 GPU；保持 HYDROLAB_RUNNER_GPU_MODE=device_requests"
        elif docker run --rm --runtime=nvidia -e NVIDIA_VISIBLE_DEVICES=all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi >/dev/null 2>&1; then
          check "CUDA 容器冒烟测试(--runtime=nvidia/CDI)" ok "容器内可见 GPU"
          warn "GPU 注入模式" "此宿主机为 CDI 模式：在 .env.production 设 HYDROLAB_RUNNER_GPU_MODE=nvidia_runtime"
        elif ! docker image inspect nvidia/cuda:12.4.1-base-ubuntu22.04 >/dev/null 2>&1; then
          check "CUDA 容器冒烟测试" fail "探针镜像拉取失败（离线/网络受限）；先在 env 填好真实镜像白名单，冒烟会改用你的训练镜像"
        else
          check "CUDA 容器冒烟测试" fail "两种注入方式都失败：确认 nvidia-container-toolkit 安装、CDI spec 已生成（nvidia-ctk cdi generate）后 systemctl restart docker"
        fi
      fi
    fi
  fi
fi

# ---------- 7. 执行器运行条件（工作区/socket/训练解释器） ----------
section "执行器运行条件"
if [[ "$RUN_BK" == "docker" && "$NO_DOCKER" -eq 0 ]]; then
  if [[ -S /var/run/docker.sock ]]; then
    check "docker socket 存在（Worker 挂载）" ok
  else
    check "docker socket" fail "/var/run/docker.sock 不存在；docker 执行器需要它启动训练容器"
  fi
  if [[ -e "$WS_ROOT" ]]; then
    if [[ -w "$WS_ROOT" ]]; then
      check "训练工作区可写" ok "$WS_ROOT（宿主机与 Worker 内须同路径）"
    else
      warn "训练工作区" "$WS_ROOT 存在但当前用户不可写；API/Worker 容器以 root 运行通常可用"
    fi
  else
    warn "训练工作区" "$WS_ROOT 不存在；部署前执行 sudo mkdir -p '$WS_ROOT'"
  fi
elif [[ "$RUN_BK" == "subprocess" ]]; then
  PY="$(env_val HYDROLAB_RUNNER_PYTHON_EXECUTABLE)"; PY="${PY:-python3}"
  if command -v "$PY" >/dev/null 2>&1 || [[ -x "$PY" ]]; then
    if "$PY" -c "import torch" >/dev/null 2>&1; then
      check "训练解释器含 torch" ok "$PY"
    else
      check "训练解释器含 torch" fail "$PY 缺 torch，subprocess 训练无法执行"
    fi
  else
    check "训练解释器" fail "$PY 不存在（检查 HYDROLAB_RUNNER_PYTHON_EXECUTABLE）"
  fi
else
  check "执行器运行条件" ok "fake 执行器无额外要求"
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
