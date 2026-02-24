#!/bin/bash

# Grafana Dashboard 测试脚本
# 验证 Dashboard 所需的 Prometheus 指标是否存在

set -e

# 配置
METRICS_URL="${1:-http://localhost:9100/metrics}"

echo "========================================="
echo "Grafana Dashboard 指标测试"
echo "========================================="
echo ""
echo "Metrics 端点: $METRICS_URL"
echo ""

# 测试连接
echo "1. 测试 Metrics 端点连接..."
if ! curl -s "$METRICS_URL" > /dev/null; then
    echo "❌ 错误: 无法连接到 Metrics 端点"
    echo "   请检查服务是否运行: docker-compose ps"
    exit 1
fi
echo "✅ Metrics 端点可访问"
echo ""

# 必需的指标列表
REQUIRED_METRICS=(
    "balance_alert_balance"
    "balance_alert_threshold"
    "balance_alert_ratio"
    "balance_alert_status"
    "balance_alert_subscription_days"
    "balance_alert_subscription_amount"
    "balance_alert_subscription_status"
    "balance_alert_last_check_timestamp"
)

# 检查每个指标
echo "2. 检查必需的 Prometheus 指标..."
MISSING_METRICS=()
FOUND_COUNT=0

for metric in "${REQUIRED_METRICS[@]}"; do
    if curl -s "$METRICS_URL" | grep -q "^$metric"; then
        echo "  ✅ $metric"
        FOUND_COUNT=$((FOUND_COUNT + 1))
    else
        echo "  ❌ $metric (缺失)"
        MISSING_METRICS+=("$metric")
    fi
done

echo ""
echo "指标统计: $FOUND_COUNT / ${#REQUIRED_METRICS[@]}"
echo ""

# 检查标签
echo "3. 检查指标标签..."
RESPONSE=$(curl -s "$METRICS_URL")

# 检查 project 标签
if echo "$RESPONSE" | grep -q 'project="'; then
    PROJECT_COUNT=$(echo "$RESPONSE" | grep 'balance_alert_balance{' | grep -o 'project="[^"]*"' | sort -u | wc -l)
    echo "  ✅ project 标签 (发现 $PROJECT_COUNT 个项目)"
    echo "$RESPONSE" | grep 'balance_alert_balance{' | grep -o 'project="[^"]*"' | sort -u | sed 's/^/     - /'
else
    echo "  ❌ project 标签缺失"
fi

echo ""

# 检查 name 标签（订阅）
if echo "$RESPONSE" | grep -q 'name="'; then
    SUBSCRIPTION_COUNT=$(echo "$RESPONSE" | grep 'balance_alert_subscription_days{' | grep -o 'name="[^"]*"' | sort -u | wc -l)
    echo "  ✅ name 标签 (发现 $SUBSCRIPTION_COUNT 个订阅)"
    echo "$RESPONSE" | grep 'balance_alert_subscription_days{' | grep -o 'name="[^"]*"' | sort -u | sed 's/^/     - /'
else
    echo "  ⚠️  name 标签缺失（如果没有配置订阅则正常）"
fi

echo ""

# 显示示例数据
echo "4. 示例数据预览..."
echo ""
echo "余额数据:"
echo "$RESPONSE" | grep '^balance_alert_balance{' | head -3
echo ""
echo "订阅数据:"
echo "$RESPONSE" | grep '^balance_alert_subscription' | head -3
echo ""

# 总结
echo "========================================="
if [ ${#MISSING_METRICS[@]} -eq 0 ]; then
    echo "✅ 测试通过！"
    echo "========================================="
    echo ""
    echo "所有必需的指标都存在，Dashboard 应该可以正常工作。"
    echo ""
    echo "下一步:"
    echo "  1. 确保 Prometheus 正在采集这些指标"
    echo "  2. 在 Grafana 中导入 Dashboard:"
    echo "     ./grafana/import-dashboard.sh"
    echo "  3. 访问 Grafana: http://localhost:3000"
    echo ""
else
    echo "⚠️  发现问题"
    echo "========================================="
    echo ""
    echo "缺失的指标 (${#MISSING_METRICS[@]}):"
    for metric in "${MISSING_METRICS[@]}"; do
        echo "  - $metric"
    done
    echo ""
    echo "可能的原因:"
    echo "  1. 服务刚启动，还未生成指标"
    echo "  2. 配置文件中没有项目或订阅"
    echo "  3. 监控代码未正确暴露指标"
    echo ""
    echo "建议操作:"
    echo "  1. 检查 config.json 配置"
    echo "  2. 手动刷新一次余额: curl http://localhost:8080/api/refresh"
    echo "  3. 等待几分钟后重新测试"
    echo ""
    exit 1
fi
