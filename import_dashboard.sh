#!/bin/bash
# Grafana Dashboard 导入脚本

GRAFANA_URL="http://localhost:3000"
GRAFANA_USER="admin"
GRAFANA_PASS="admin123"

echo "📋 正在导入 Grafana Dashboard..."

# 等待 Grafana 启动
echo "⏳ 等待 Grafana 启动..."
for i in {1..30}; do
    if curl -s "$GRAFANA_URL/api/health" > /dev/null 2>&1; then
        echo "✅ Grafana 已启动"
        break
    fi
    sleep 2
done

# 获取 Prometheus 数据源 UID
echo "🔍 获取 Prometheus 数据源..."
DATASOURCE_UID=$(curl -s -u "$GRAFANA_USER:$GRAFANA_PASS" "$GRAFANA_URL/api/datasources/name/Prometheus" | jq -r '.uid')

if [ -z "$DATASOURCE_UID" ] || [ "$DATASOURCE_UID" == "null" ]; then
    echo "❌ 未找到 Prometheus 数据源"
    exit 1
fi

echo "✅ 找到数据源 UID: $DATASOURCE_UID"

# 替换 Dashboard 中的数据源 UID
echo "🔧 更新 Dashboard 配置..."
sed "s/\"uid\": \"prometheus\"/\"uid\": \"$DATASOURCE_UID\"/g" grafana/dashboards/balance-alert-dashboard.json > /tmp/dashboard_fixed.json

# 导入 Dashboard
echo "📥 导入 Dashboard..."
cat /tmp/dashboard_fixed.json | jq '{dashboard: ., overwrite: true}' > /tmp/dashboard_import.json

RESPONSE=$(curl -s -X POST \
  -H "Content-Type: application/json" \
  -u "$GRAFANA_USER:$GRAFANA_PASS" \
  -d @/tmp/dashboard_import.json \
  "$GRAFANA_URL/api/dashboards/db")

if echo "$RESPONSE" | grep -q '"status":"success"'; then
  DASHBOARD_URL=$(echo "$RESPONSE" | jq -r '.url')
  echo ""
  echo "✅ Dashboard 导入成功！"
  echo "🎉 所有配置完成！"
  echo ""
  echo "🔗 Dashboard 地址: $GRAFANA_URL$DASHBOARD_URL"
  echo "🌐 访问 Grafana: $GRAFANA_URL"
  echo "👤 用户名: $GRAFANA_USER"
  echo "🔑 密码: $GRAFANA_PASS"
else
  echo ""
  echo "❌ Dashboard 导入失败"
  echo "错误信息: $RESPONSE"
  exit 1
fi
