#!/usr/bin/env bash
# 前后端联调验证：通过 Vite 代理走真实 HTTP 链路，全部请求带超时，避免死等。
# 用法：scripts/verify-integration.sh [web_base]   默认 http://127.0.0.1:5175
set -uo pipefail

BASE="${1:-http://127.0.0.1:5175}"
CURL="curl -sS -m 8"
fail=0

echo "== HydroLab 前后端联调验证 =="
echo "web base: $BASE"

code=$($CURL -o /dev/null -w '%{http_code}' "$BASE/" || echo 000)
[ "$code" = "200" ] && echo "PASS 前端页面 $code" || { echo "FAIL 前端页面 $code"; exit 1; }

token=$($CURL -X POST "$BASE/api/v1/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"admin@hydrolab.cn","password":"admin123456"}' \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["tokens"]["access_token"])' 2>/dev/null)
[ -n "${token:-}" ] && echo "PASS 登录获取 Token" || { echo "FAIL 登录"; exit 1; }

AUTH=(-H "Authorization: Bearer $token")

seed=$($CURL -X POST "$BASE/api/v1/dev-demo/seed" "${AUTH[@]}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' 2>/dev/null)
[ "$seed" = "seeded" ] || [ "$seed" = "already_seeded" ] && echo "PASS 领域资产初始化 ($seed)" || { echo "FAIL 初始化"; fail=1; }

check() { # path label
  n=$($CURL "$BASE$1" "${AUTH[@]}" | python3 -c 'import json,sys
d=json.load(sys.stdin)
print(len(d if isinstance(d,list) else d.get("items",[])))' 2>/dev/null)
  if [ -n "${n:-}" ] && [ "$n" -gt 0 ] 2>/dev/null; then
    echo "PASS $2 ($n)"
  else
    echo "FAIL $2 (${n:-error})"; fail=1
  fi
}

check /api/v1/datasets           "数据 · GET /datasets"
check /api/v1/code-repositories  "代码 · GET /code-repositories"
check /api/v1/templates          "模板 · GET /templates"
check /api/v1/environments       "环境 · GET /environments"
check /api/v1/experiments        "实验 · GET /experiments"
check /api/v1/checkpoints        "Checkpoint · GET /checkpoints"
check /api/v1/results            "结果 · GET /results"

runs=$($CURL "$BASE/api/v1/runs" "${AUTH[@]}" | python3 -c 'import json,sys; print(len(json.load(sys.stdin)))' 2>/dev/null)
if [ -n "${runs:-}" ] && [ "$runs" -gt 0 ] 2>/dev/null; then
  echo "PASS 运行中心 · GET /runs ($runs)"
  run_id=$($CURL "$BASE/api/v1/runs" "${AUTH[@]}" | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["id"])' 2>/dev/null)
  run_code=$($CURL -o /dev/null -w '%{http_code}' "$BASE/api/v1/runs/$run_id" "${AUTH[@]}" || echo 000)
  [ "$run_code" = "200" ] && echo "PASS Run 详情 · GET /runs/$run_id ($run_code)" || { echo "FAIL Run 详情"; fail=1; }
else
  echo "FAIL 运行中心 · GET /runs（${runs:-error}）"; fail=1
fi

unauth=$($CURL -o /dev/null -w '%{http_code}' "$BASE/api/v1/results" || echo 000)
[ "$unauth" = "401" ] && echo "PASS 未认证访问被拒绝 401" || { echo "FAIL 鉴权边界 $unauth"; fail=1; }

[ "$fail" = "0" ] && echo "== 全部联调检查通过 ==" || echo "== 存在失败项 =="
exit "$fail"