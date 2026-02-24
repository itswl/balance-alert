#!/bin/bash
# 快速修复 .env 文件中的占位符

set -e

echo "=========================================="
echo "修复 .env 文件中的占位符"
echo "=========================================="
echo ""

if [ ! -f ".env" ]; then
    echo "❌ 错误：.env 文件不存在"
    echo "请先运行：./setup-env.sh"
    exit 1
fi

# 备份原文件
cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
echo "✅ 已备份原文件到 .env.backup.*"
echo ""

# 检查是否有占位符
if grep -q '\${' .env; then
    echo "检测到以下占位符需要替换："
    grep '\${' .env | grep -v '^#' | head -10
    echo ""
    echo "请选择处理方式："
    echo "1. 注释掉所有包含占位符的行（推荐）"
    echo "2. 删除所有包含占位符的行"
    echo "3. 手动编辑"
    read -p "请选择 (1/2/3): " choice

    case $choice in
        1)
            # 注释掉包含占位符的行
            sed -i.tmp '/\${/s/^/# /' .env
            rm -f .env.tmp
            echo "✅ 已注释掉所有包含占位符的行"
            ;;
        2)
            # 删除包含占位符的行
            sed -i.tmp '/\${/d' .env
            rm -f .env.tmp
            echo "✅ 已删除所有包含占位符的行"
            ;;
        3)
            echo "请手动编辑 .env 文件"
            echo "使用命令：vim .env 或 nano .env"
            exit 0
            ;;
        *)
            echo "❌ 无效选择"
            exit 1
            ;;
    esac

    echo ""
    echo "=========================================="
    echo "✅ 修复完成！"
    echo "=========================================="
    echo ""
    echo "现在 .env 文件中不再有未解析的占位符。"
    echo ""
    echo "下一步："
    echo "1. 编辑 .env 添加真实的 API Key："
    echo "   vim .env"
    echo ""
    echo "2. 或者重新运行配置向导："
    echo "   ./setup-env.sh"
    echo ""
    echo "3. 重启容器："
    echo "   docker-compose down && docker-compose up -d"
else
    echo "✅ .env 文件中没有发现占位符"
    echo ""
    echo "如果仍有问题，请检查变量值是否填写正确。"
fi
