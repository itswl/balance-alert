#!/bin/bash
# MySQL 快速配置脚本

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"
NAMESPACE="balance-alert"
SECRET_NAME="balance-alert-secret"

echo "🔧 MySQL 配置向导"
echo "=========================="
echo ""

# 检查是否已安装 pymysql
echo "📦 检查 MySQL 驱动..."
if python3 -c "import pymysql" 2>/dev/null; then
    echo "✅ pymysql 已安装"
else
    echo "❌ pymysql 未安装"
    read -p "是否现在安装? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        pip install pymysql cryptography
        echo "✅ pymysql 和 cryptography 安装完成"
    else
        echo "⚠️  请手动安装: pip install pymysql cryptography"
        exit 1
    fi
fi

echo ""
echo "📝 请输入 MySQL 连接信息："
echo ""

# 读取用户输入
read -p "数据库主机 [localhost]: " DB_HOST
DB_HOST=${DB_HOST:-localhost}

read -p "数据库端口 [3306]: " DB_PORT
DB_PORT=${DB_PORT:-3306}

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

read -p "使用 SSL 连接? (y/n) [n]: " USE_SSL
USE_SSL=${USE_SSL:-n}

read -p "字符集 [utf8mb4]: " CHARSET
CHARSET=${CHARSET:-utf8mb4}

# 构建连接字符串
DATABASE_URL="mysql+pymysql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}?charset=${CHARSET}"
if [[ $USE_SSL =~ ^[Yy]$ ]]; then
    DATABASE_URL="${DATABASE_URL}&ssl=true"
fi

echo ""
echo "🧪 测试数据库连接..."

# 测试连接
python3 << EOF
import sys
import pymysql
from pymysql.err import OperationalError

try:
    conn = pymysql.connect(
        host='${DB_HOST}',
        port=${DB_PORT},
        user='${DB_USER}',
        password='${DB_PASS}',
        database='${DB_NAME}',
        charset='${CHARSET}'
    )

    # 测试查询
    cursor = conn.cursor()
    cursor.execute("SELECT VERSION();")
    version = cursor.fetchone()
    print(f'✅ 数据库连接成功!')
    print(f'   MySQL 版本: {version[0]}')

    cursor.close()
    conn.close()
    sys.exit(0)

except OperationalError as e:
    print(f'❌ 数据库连接失败: {e}')
    print()
    print('💡 可能的原因:')
    print('  1. 数据库服务未启动')
    print('  2. 用户名或密码错误')
    print('  3. 数据库不存在')
    print('  4. 权限不足')
    print()
    print('🔧 创建数据库的 SQL 命令:')
    print(f'  CREATE DATABASE ${DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;')
    print(f'  CREATE USER \'${DB_USER}\'@\'%\' IDENTIFIED BY \'your_password\';')
    print(f'  GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO \'${DB_USER}\'@\'%\';')
    print(f'  FLUSH PRIVILEGES;')
    sys.exit(1)
EOF

if [ $? -eq 0 ]; then
    echo ""
    echo "📝 更新 .env 配置文件..."

    # 备份原配置
    if [ -f "$ENV_FILE" ]; then
        cp "$ENV_FILE" "$ENV_FILE.backup.$(date +%Y%m%d_%H%M%S)"
        echo "✅ 已备份原配置到 .env.backup.*"
    fi

    # 更新或添加 DATABASE_URL
    if grep -q "^DATABASE_URL=" "$ENV_FILE" 2>/dev/null; then
        # macOS 兼容的 sed 语法
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|^DATABASE_URL=.*|DATABASE_URL=${DATABASE_URL}|" "$ENV_FILE"
        else
            sed -i "s|^DATABASE_URL=.*|DATABASE_URL=${DATABASE_URL}|" "$ENV_FILE"
        fi
        echo "✅ 已更新 DATABASE_URL"
    else
        echo "" >> "$ENV_FILE"
        echo "DATABASE_URL=${DATABASE_URL}" >> "$ENV_FILE"
        echo "✅ 已添加 DATABASE_URL"
    fi

    # 确保启用数据库
    if grep -q "^ENABLE_DATABASE=" "$ENV_FILE" 2>/dev/null; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|^ENABLE_DATABASE=.*|ENABLE_DATABASE=true|" "$ENV_FILE"
        else
            sed -i "s|^ENABLE_DATABASE=.*|ENABLE_DATABASE=true|" "$ENV_FILE"
        fi
    else
        echo "ENABLE_DATABASE=true" >> "$ENV_FILE"
    fi

    echo ""
    echo "🎉 MySQL 配置完成!"
    echo ""
    echo "连接信息:"
    echo "  主机: ${DB_HOST}"
    echo "  端口: ${DB_PORT}"
    echo "  数据库: ${DB_NAME}"
    echo "  用户: ${DB_USER}"
    echo "  字符集: ${CHARSET}"
    echo "  SSL: ${USE_SSL}"
    echo ""
    echo "📋 下一步："
    echo "  1. 运行 python3 scripts/test_database.py 测试数据库"
    echo "  2. 运行 python3 web_server_modular.py 启动服务"
    echo "  3. 系统会自动创建所需的数据库表"
    echo ""
    echo "📖 详细文档: docs/MYSQL_SETUP.md"
    echo ""
    echo "💡 性能优化提示："
    echo "  - 确保数据库使用 utf8mb4 字符集"
    echo "  - 在 balance_history 表上创建索引"
    echo "  - 调整 MySQL 的 innodb_buffer_pool_size"
else
    echo ""
    echo "❌ 配置失败，请检查数据库连接信息"
    echo ""
    echo "📖 故障排查文档: docs/MYSQL_SETUP.md"
    exit 1
fi
