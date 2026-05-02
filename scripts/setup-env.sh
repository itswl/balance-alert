#!/bin/bash
# 快速设置环境变量脚本

set -e

echo "=========================================="
echo "Balance Alert - 环境变量配置向导"
echo "=========================================="
echo ""
echo "⚠️  重要提示："
echo "1. 火山引擎 API Key 格式：AK-xxx:SK-xxx （用冒号分隔）"
echo "2. 阿里云 API Key 格式：AccessKeyId:AccessKeySecret （用冒号分隔）"
echo "3. 按 Ctrl+C 可以随时退出"
echo ""

# 检查是否已存在 .env
if [ -f ".env" ]; then
    echo "📄 检测到已存在 .env 文件"
    read -p "是否备份并重新创建？(y/n): " confirm
    if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
        cp .env .env.backup.$(date +%Y%m%d_%H%M%S)
        echo "✅ 已备份到 .env.backup.*"
    else
        echo "❌ 已取消"
        exit 0
    fi
fi

# 创建 .env 文件
cat > .env << 'EOF'
# ========================================
# 余额告警系统 - 环境变量配置
# ========================================
# ⚠️ 警告：此文件包含敏感信息，请勿提交到 Git！

# ========================================
# 系统设置
# ========================================
BALANCE_REFRESH_INTERVAL_SECONDS=3600
MAX_CONCURRENT_CHECKS=5
MIN_REFRESH_INTERVAL_SECONDS=60
ENABLE_SMART_REFRESH=false
SMART_REFRESH_THRESHOLD_PERCENT=5

# ========================================
# 数据库配置
# ========================================
ENABLE_DATABASE=true
DATABASE_URL=sqlite:///./data/balance_alert.db

EOF

# Webhook URL
echo ""
echo "=========================================="
echo "1. Webhook 配置"
echo "=========================================="
read -p "请输入飞书 Webhook URL（留空跳过）: " webhook_url
if [ -n "$webhook_url" ]; then
    echo "WEBHOOK_URL=$webhook_url" >> .env
    echo "WEBHOOK_TYPE=feishu" >> .env
    echo "WEBHOOK_SOURCE=credit-monitor" >> .env
else
    echo "# WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/YOUR_TOKEN" >> .env
    echo "# WEBHOOK_TYPE=feishu" >> .env
    echo "# WEBHOOK_SOURCE=credit-monitor" >> .env
fi

# 邮箱配置
echo "" >> .env
echo "# ========================================" >> .env
echo "# 邮箱配置" >> .env
echo "# ========================================" >> .env
echo ""
echo "=========================================="
echo "2. 邮箱配置（可选）"
echo "=========================================="
read -p "是否配置邮箱？(y/n): " config_email
if [ "$config_email" = "y" ] || [ "$config_email" = "Y" ]; then
    read -p "邮箱地址: " email_addr
    read -sp "邮箱密码: " email_pass
    echo ""
    echo "EMAIL_1_NAME=邮箱1" >> .env
    echo "EMAIL_1_HOST=imap.feishu.cn" >> .env
    echo "EMAIL_1_PORT=993" >> .env
    echo "EMAIL_1_USERNAME=$email_addr" >> .env
    echo "EMAIL_1_PASSWORD=$email_pass" >> .env
    echo "EMAIL_1_USE_SSL=true" >> .env
    echo "EMAIL_1_ENABLED=true" >> .env
else
    echo "# EMAIL_1_USERNAME=your-email@example.com" >> .env
    echo "# EMAIL_1_PASSWORD=your-password" >> .env
fi

# 项目 API Key
echo "" >> .env
echo "# ========================================" >> .env
echo "# 项目 API Key" >> .env
echo "# ========================================" >> .env
echo ""
echo "=========================================="
echo "3. 配置项目 API Key"
echo "=========================================="

# 项目1 - OpenRouter
read -p "OpenRouter API Key（留空跳过）: " project1_key
if [ -n "$project1_key" ]; then
    echo "PROJECT_1_API_KEY=$project1_key" >> .env
else
    echo "# PROJECT_1_API_KEY=sk-or-v1-your-key" >> .env
fi

# 项目2 - WxRank
read -p "WxRank API Key（留空跳过）: " project2_key
if [ -n "$project2_key" ]; then
    echo "PROJECT_2_API_KEY=$project2_key" >> .env
else
    echo "# PROJECT_2_API_KEY=wxrank-your-key" >> .env
fi

# 项目3 - 火山引擎1
echo ""
echo "火山引擎 API Key 格式：AK-xxx:SK-xxx"
read -p "火山引擎-自然选择 (AK:SK格式，留空跳过): " project3_key
if [ -n "$project3_key" ]; then
    echo "PROJECT_3_API_KEY=$project3_key" >> .env
else
    echo "# PROJECT_3_API_KEY=AK-xxx:SK-xxx" >> .env
fi

# 项目4 - 火山引擎2
read -p "火山引擎-陌玉 (AK:SK格式，留空跳过): " project4_key
if [ -n "$project4_key" ]; then
    echo "PROJECT_4_API_KEY=$project4_key" >> .env
else
    echo "# PROJECT_4_API_KEY=AK-xxx:SK-xxx" >> .env
fi

# 项目5 - 阿里云1
echo ""
echo "阿里云 API Key 格式：AccessKeyId:AccessKeySecret"
read -p "阿里云-1 (KeyId:Secret格式，留空跳过): " project5_key
if [ -n "$project5_key" ]; then
    echo "PROJECT_5_API_KEY=$project5_key" >> .env
else
    echo "# PROJECT_5_API_KEY=LTAI-xxx:secret-xxx" >> .env
fi

# 项目6 - 阿里云2
read -p "阿里云-2 (KeyId:Secret格式，留空跳过): " project6_key
if [ -n "$project6_key" ]; then
    echo "PROJECT_6_API_KEY=$project6_key" >> .env
else
    echo "# PROJECT_6_API_KEY=LTAI-xxx:secret-xxx" >> .env
fi

# 项目7 - TikHub
echo ""
read -p "TikHub API Key（留空跳过）: " project7_key
if [ -n "$project7_key" ]; then
    echo "PROJECT_7_API_KEY=$project7_key" >> .env
else
    echo "# PROJECT_7_API_KEY=tikhub-your-key" >> .env
fi

echo ""
echo "=========================================="
echo "✅ .env 文件已创建！"
echo "=========================================="
echo ""
echo "文件位置: $(pwd)/.env"
echo ""
echo "下一步："
echo "1. 检查 .env 文件内容：cat .env"
echo "2. 重启容器：docker-compose down && docker-compose up -d"
echo "3. 查看日志：docker-compose logs -f"
echo ""
echo "⚠️  注意：请勿将 .env 文件提交到 Git！"
