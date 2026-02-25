#!/bin/bash
# Docker 容器启动入口脚本
# 初始化配置文件和目录

set -e

echo "🚀 Balance Alert - Docker 容器启动"
echo "=================================="
echo ""

# 1. 创建必要的目录
echo "📁 创建必要目录..."
mkdir -p /app/logs /app/data

# 2. 初始化 config.json（如果不存在或为空）
if [ ! -s /app/config.json ]; then
    echo "📝 创建默认配置文件..."
    cat > /app/config.json << 'EOF'
{
  "settings": {
    "balance_refresh_interval_seconds": 3600,
    "max_concurrent_checks": 5,
    "min_refresh_interval_seconds": 60,
    "enable_smart_refresh": false,
    "smart_refresh_threshold_percent": 5
  },
  "webhook": {
    "url": "",
    "source": "credit-monitor",
    "type": "feishu"
  },
  "email": [],
  "subscriptions": [],
  "projects": []
}
EOF
    echo "✅ 默认配置文件已创建"
fi

# 3. 确保文件权限正确
echo "🔐 设置文件权限..."
chmod 644 /app/config.json
chmod 755 /app/logs /app/data

# 4. 显示配置信息
echo ""
echo "📋 配置信息:"
echo "  - 配置文件: /app/config.json ($(stat -c%s /app/config.json 2>/dev/null || stat -f%z /app/config.json) bytes)"
echo "  - 日志目录: /app/logs"
echo "  - 数据目录: /app/data"
echo "  - 用户: $(whoami)"
echo ""

# 5. 检查环境变量
if [ -n "$ENABLE_DATABASE" ]; then
    echo "💾 数据库: $ENABLE_DATABASE"
    if [ -n "$DATABASE_URL" ]; then
        # 隐藏密码
        SAFE_URL=$(echo "$DATABASE_URL" | sed 's/:\/\/[^:]*:[^@]*@/:\/\/***:***@/')
        echo "  - URL: $SAFE_URL"
    fi
fi

echo ""
echo "✅ 初始化完成，启动服务..."
echo ""

# 6. 执行原始启动脚本
exec /app/start.sh
