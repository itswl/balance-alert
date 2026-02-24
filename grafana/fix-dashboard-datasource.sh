#!/bin/bash

# 修复 Grafana Dashboard 数据源引用脚本
# 自动将 Dashboard 中的数据源 UID 更新为实际的 UID

set -e

GRAFANA_URL="${1:-http://localhost:3000}"
GRAFANA_USER="${2:-admin}"
GRAFANA_PASS="${3:-admin123}"

echo "========================================="
echo "Grafana Dashboard 数据源修复工具"
echo "========================================="
echo ""

# 获取 Prometheus 数据源 UID
echo "1. 获取 Prometheus 数据源 UID..."
DATASOURCE_UID=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASS" \
    "$GRAFANA_URL/api/datasources" | \
    python3 -c "import sys, json; data = json.load(sys.stdin); print([d['uid'] for d in data if d['name'] == 'Prometheus'][0])" 2>/dev/null)

if [ -z "$DATASOURCE_UID" ]; then
    echo "❌ 错误: 未找到 Prometheus 数据源"
    exit 1
fi

echo "✅ Prometheus 数据源 UID: $DATASOURCE_UID"
echo ""

# 获取 Dashboard
echo "2. 获取 Dashboard 配置..."
DASHBOARD_JSON=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASS" \
    "$GRAFANA_URL/api/dashboards/uid/balance-alert")

if [ -z "$DASHBOARD_JSON" ]; then
    echo "❌ 错误: 未找到 Dashboard"
    exit 1
fi

echo "✅ Dashboard 获取成功"
echo ""

# 更新数据源 UID
echo "3. 更新数据源引用..."
UPDATED_DASHBOARD=$(echo "$DASHBOARD_JSON" | python3 -c "
import json, sys

data = json.load(sys.stdin)
dashboard = data['dashboard']

# 递归替换所有数据源 UID
def replace_datasource_uid(obj, new_uid='$DATASOURCE_UID'):
    if isinstance(obj, dict):
        if 'datasource' in obj and isinstance(obj['datasource'], dict):
            if 'uid' in obj['datasource']:
                obj['datasource']['uid'] = new_uid
        for value in obj.values():
            replace_datasource_uid(value, new_uid)
    elif isinstance(obj, list):
        for item in obj:
            replace_datasource_uid(item, new_uid)

replace_datasource_uid(dashboard)

# 准备更新请求
update_data = {
    'dashboard': dashboard,
    'overwrite': True,
    'message': 'Auto-fix datasource UID'
}

print(json.dumps(update_data))
")

# 保存更新
echo "4. 保存更新..."
RESULT=$(echo "$UPDATED_DASHBOARD" | curl -s -X POST \
    -u "$GRAFANA_USER:$GRAFANA_PASS" \
    -H "Content-Type: application/json" \
    -d @- \
    "$GRAFANA_URL/api/dashboards/db")

if echo "$RESULT" | grep -q '"status":"success"'; then
    echo "✅ Dashboard 更新成功！"
    echo ""

    DASHBOARD_URL=$(echo "$RESULT" | python3 -c "import sys, json; print(json.load(sys.stdin)['url'])" 2>/dev/null)

    echo "========================================="
    echo "🎉 完成！"
    echo "========================================="
    echo ""
    echo "Dashboard 地址:"
    echo "  $GRAFANA_URL$DASHBOARD_URL"
    echo ""
    echo "请刷新浏览器页面查看更新后的 Dashboard"
    echo ""
else
    echo "❌ 更新失败"
    echo ""
    echo "错误信息:"
    echo "$RESULT"
    exit 1
fi
