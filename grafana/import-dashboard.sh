#!/bin/bash

# Grafana Dashboard 自动导入脚本
# 用法: ./import-dashboard.sh [grafana-url] [username] [password]

set -e

# 配置
GRAFANA_URL="${1:-http://localhost:3000}"
GRAFANA_USER="${2:-admin}"
GRAFANA_PASS="${3:-admin123}"
DASHBOARD_FILE="dashboards/balance-alert-dashboard.json"
DATASOURCE_NAME="Prometheus"

echo "========================================="
echo "Grafana Dashboard 自动导入工具"
echo "========================================="
echo ""
echo "配置信息:"
echo "  Grafana URL: $GRAFANA_URL"
echo "  用户名: $GRAFANA_USER"
echo "  Dashboard: $DASHBOARD_FILE"
echo ""

# 检查 Dashboard 文件是否存在
if [ ! -f "$DASHBOARD_FILE" ]; then
    echo "❌ 错误: Dashboard 文件不存在: $DASHBOARD_FILE"
    exit 1
fi

# 检查 jq 工具
if ! command -v jq &> /dev/null; then
    echo "⚠️  警告: 未安装 jq 工具，尝试使用备用方法"
    USE_JQ=false
else
    USE_JQ=true
fi

# 测试 Grafana 连接
echo "1. 测试 Grafana 连接..."
if ! curl -s -u "$GRAFANA_USER:$GRAFANA_PASS" "$GRAFANA_URL/api/health" > /dev/null; then
    echo "❌ 错误: 无法连接到 Grafana: $GRAFANA_URL"
    echo "   请检查 URL、用户名和密码是否正确"
    exit 1
fi
echo "✅ Grafana 连接成功"
echo ""

# 获取数据源 UID
echo "2. 查找 Prometheus 数据源..."
if [ "$USE_JQ" = true ]; then
    DATASOURCE_UID=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASS" \
        "$GRAFANA_URL/api/datasources/name/$DATASOURCE_NAME" | jq -r '.uid')
else
    # 备用方法：使用 grep 和 sed
    DATASOURCE_UID=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASS" \
        "$GRAFANA_URL/api/datasources/name/$DATASOURCE_NAME" | \
        grep -o '"uid":"[^"]*"' | sed 's/"uid":"//;s/"//')
fi

if [ -z "$DATASOURCE_UID" ] || [ "$DATASOURCE_UID" = "null" ]; then
    echo "❌ 错误: 未找到 Prometheus 数据源"
    echo "   请先在 Grafana 中添加 Prometheus 数据源"
    exit 1
fi
echo "✅ 找到数据源 UID: $DATASOURCE_UID"
echo ""

# 准备 Dashboard JSON
echo "3. 准备 Dashboard..."
TEMP_FILE=$(mktemp)

if [ "$USE_JQ" = true ]; then
    # 使用 jq 替换数据源 UID
    jq --arg uid "$DATASOURCE_UID" \
       '(.dashboard // .) |
        walk(if type == "object" and .uid == "${DS_PROMETHEUS}" then .uid = $uid else . end) |
        {dashboard: ., overwrite: true, folderUid: ""}' \
       "$DASHBOARD_FILE" > "$TEMP_FILE"
else
    # 备用方法：使用 sed 替换
    sed "s/\${DS_PROMETHEUS}/$DATASOURCE_UID/g" "$DASHBOARD_FILE" | \
        sed '1s/^/{"dashboard": /' | \
        sed '$s/$/,"overwrite": true, "folderUid": ""}/' > "$TEMP_FILE"
fi

echo "✅ Dashboard 准备完成"
echo ""

# 导入 Dashboard
echo "4. 导入 Dashboard 到 Grafana..."
RESPONSE=$(curl -s -X POST \
    -H "Content-Type: application/json" \
    -u "$GRAFANA_USER:$GRAFANA_PASS" \
    -d @"$TEMP_FILE" \
    "$GRAFANA_URL/api/dashboards/db")

# 清理临时文件
rm -f "$TEMP_FILE"

# 检查导入结果
if echo "$RESPONSE" | grep -q '"status":"success"'; then
    echo "✅ Dashboard 导入成功！"
    echo ""

    # 提取 Dashboard URL
    if [ "$USE_JQ" = true ]; then
        DASHBOARD_URL=$(echo "$RESPONSE" | jq -r '.url')
    else
        DASHBOARD_URL=$(echo "$RESPONSE" | grep -o '"url":"[^"]*"' | sed 's/"url":"//;s/"//')
    fi

    echo "========================================="
    echo "🎉 完成！"
    echo "========================================="
    echo ""
    echo "Dashboard 访问地址:"
    echo "  $GRAFANA_URL$DASHBOARD_URL"
    echo ""
    echo "推荐操作:"
    echo "  1. 打开浏览器访问上述地址"
    echo "  2. 检查数据源配置是否正确"
    echo "  3. 调整时间范围和刷新间隔"
    echo "  4. 保存 Dashboard（如有修改）"
    echo ""
else
    echo "❌ Dashboard 导入失败"
    echo ""
    echo "错误详情:"
    echo "$RESPONSE"
    echo ""
    exit 1
fi
