#!/bin/bash
# Docker 容器启动入口脚本
# 初始化配置文件和目录

set -e

echo "🚀 Balance Alert - Docker 容器启动"
echo "=================================="
echo ""

# 1. 创建必要的目录（如果不存在）
if [ ! -d /app/logs ]; then
    echo "📁 创建日志目录..."
    mkdir -p /app/logs
fi

if [ ! -d /app/data ]; then
    echo "📁 创建数据目录..."
    mkdir -p /app/data
fi

# 2. 初始化 config.json（如果不存在或为空）
if [ ! -s /app/config.json ]; then
    echo "📝 创建默认配置文件..."
    cat > /app/config.json << 'EOF'
{
  "settings": {
    "balance_refresh_interval_seconds": 3600,
    "max_concurrent_checks": 5
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

# 3. 权限已在 Dockerfile 中设置，跳过 chmod

# 4. 显示配置信息
echo ""
echo "📋 环境信息:"
CONFIG_SIZE=$(stat -c%s /app/config.json 2>/dev/null || stat -f%z /app/config.json 2>/dev/null || echo "unknown")
echo "  - 配置文件: /app/config.json (${CONFIG_SIZE} bytes)"
echo "  - 日志目录: /app/logs"
echo "  - 数据目录: /app/data"
echo "  - 运行用户: $(whoami)"
echo "  - 工作目录: $(pwd)"
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
