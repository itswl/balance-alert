#!/bin/bash
# PostgreSQL 快速配置脚本

set -e

echo "🔧 PostgreSQL 配置向导"
echo "========================"
echo ""

# 检查是否已安装 psycopg2
echo "📦 检查 PostgreSQL 驱动..."
if python3 -c "import psycopg2" 2>/dev/null; then
    echo "✅ psycopg2 已安装"
else
    echo "❌ psycopg2 未安装"
    read -p "是否现在安装? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pip install psycopg2-binary
        echo "✅ psycopg2-binary 安装完成"
    else
        echo "⚠️  请手动安装: pip install psycopg2-binary"
        exit 1
    fi
fi

echo ""
echo "📝 请输入 PostgreSQL 连接信息："
echo ""

# 读取用户输入
read -p "数据库主机 [localhost]: " DB_HOST
DB_HOST=${DB_HOST:-localhost}

read -p "数据库端口 [5432]: " DB_PORT
DB_PORT=${DB_PORT:-5432}

read -p "数据库名称 [balance_alert]: " DB_NAME
DB_NAME=${DB_NAME:-balance_alert}

read -p "数据库用户名: " DB_USER
if [ -z "$DB_USER" ]; then
    echo "❌ 用户名不能为空"
    exit 1
fi

read -s -p "数据库密码: " DB_PASS
echo
if [ -z "$DB_PASS" ]; then
    echo "❌ 密码不能为空"
    exit 1
fi

read -p "是否使用 SSL? (y/n) [n]: " USE_SSL
USE_SSL=${USE_SSL:-n}

# 构建连接字符串
DATABASE_URL="postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
if [[ $USE_SSL =~ ^[Yy]$ ]]; then
    DATABASE_URL="${DATABASE_URL}?sslmode=require"
fi

echo ""
echo "🧪 测试数据库连接..."

# 测试连接
python3 << EOF
import sys
import psycopg2
from psycopg2 import OperationalError

try:
    conn = psycopg2.connect(
        host='${DB_HOST}',
        port=${DB_PORT},
        database='${DB_NAME}',
        user='${DB_USER}',
        password='${DB_PASS}'
    )
    conn.close()
    print('✅ 数据库连接成功!')
    sys.exit(0)
except OperationalError as e:
    print(f'❌ 数据库连接失败: {e}')
    sys.exit(1)
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "📝 更新 .env 配置文件..."

    # 备份原配置
    if [ -f .env ]; then
        cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
        echo "✅ 已备份原配置到 .env.backup.*"
    fi

    # 更新或添加 DATABASE_URL
    if grep -q "^DATABASE_URL=" .env 2>/dev/null; then
        # macOS 兼容的 sed 语法
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|^DATABASE_URL=.*|DATABASE_URL=${DATABASE_URL}|" .env
        else
            sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${DATABASE_URL}|" .env
        fi
        echo "✅ 已更新 DATABASE_URL"
    else
        echo "" >> .env
        echo "DATABASE_URL=${DATABASE_URL}" >> .env
        echo "✅ 已添加 DATABASE_URL"
    fi

    # 确保启用数据库
    if grep -q "^ENABLE_DATABASE=" .env 2>/dev/null; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|^ENABLE_DATABASE=.*|ENABLE_DATABASE=true|" .env
        else
            sed -i "s|^ENABLE_DATABASE=.*|ENABLE_DATABASE=true|" .env
        fi
    else
        echo "ENABLE_DATABASE=true" >> .env
    fi

    echo ""
    echo "🎉 PostgreSQL 配置完成!"
    echo ""
    echo "连接信息:"
    echo "  主机: ${DB_HOST}"
    echo "  端口: ${DB_PORT}"
    echo "  数据库: ${DB_NAME}"
    echo "  用户: ${DB_USER}"
    echo "  SSL: ${USE_SSL}"
    echo ""
    echo "📋 下一步："
    echo "  1. 运行 python3 web_server_modular.py 启动服务"
    echo "  2. 系统会自动创建所需的数据库表"
    echo ""
    echo "📖 详细文档: docs/POSTGRESQL_SETUP.md"
else
    echo ""
    echo "❌ 配置失败，请检查数据库连接信息"
    echo "📖 参考文档: docs/POSTGRESQL_SETUP.md"
    exit 1
fi
