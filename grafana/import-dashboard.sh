#!/bin/bash
# 把 dashboards/balance-alert-dashboard.json 导入（或覆盖）到已有的 Grafana，需要 jq
# 用法: ./import-dashboard.sh [grafana-url] [username] [password]
#       密码也可用环境变量 GRAFANA_ADMIN_PASSWORD 提供
set -euo pipefail
cd "$(dirname "$0")"

URL="${1:-http://localhost:3000}"
USER="${2:-${GRAFANA_ADMIN_USER:-admin}}"
PASS="${3:-${GRAFANA_ADMIN_PASSWORD:-}}"
[ -n "$PASS" ] || { echo "缺少 Grafana 密码：第 3 个参数或 GRAFANA_ADMIN_PASSWORD" >&2; exit 1; }
command -v jq >/dev/null || { echo "需要安装 jq" >&2; exit 1; }

DS_UID=$(curl -sf -u "$USER:$PASS" "$URL/api/datasources/name/Prometheus" | jq -r '.uid // empty')
[ -n "$DS_UID" ] || { echo "Grafana 里没有名为 Prometheus 的数据源，请先添加" >&2; exit 1; }

jq --arg uid "$DS_UID" \
   'walk(if type == "object" and .uid == "${DS_PROMETHEUS}" then .uid = $uid else . end)
    | {dashboard: ., overwrite: true, folderUid: ""}' \
   dashboards/balance-alert-dashboard.json \
| curl -sf -u "$USER:$PASS" -H "Content-Type: application/json" -d @- "$URL/api/dashboards/db" \
| jq -r --arg url "$URL" '"已导入: " + $url + .url'
