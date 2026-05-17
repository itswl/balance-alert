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
    read -sp "邮箱密码: " email_pass
    echo ""
    echo "EMAIL_PASSWORD=$email_pass" >> .env
else
    echo "# EMAIL_PASSWORD=your-password" >> .env
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

echo ""
echo "火山引擎 API Key 格式：AK-xxx:SK-xxx"
read -p "OpenRouter API Key（留空跳过）: " openrouter_key
if [ -n "$openrouter_key" ]; then
    echo "OPENROUTER_API_KEY=$openrouter_key" >> .env
else
    echo "# OPENROUTER_API_KEY=sk-or-v1-your-key" >> .env
fi

read -p "UniAPI API Key（留空跳过）: " uniapi_key
if [ -n "$uniapi_key" ]; then
    echo "UNIAPI_API_KEY=$uniapi_key" >> .env
else
    echo "# UNIAPI_API_KEY=uniapi-your-key" >> .env
fi

read -p "WxRank API Key（留空跳过）: " wxrank_key
if [ -n "$wxrank_key" ]; then
    echo "WXRANK_API_KEY=$wxrank_key" >> .env
else
    echo "# WXRANK_API_KEY=wxrank-your-key" >> .env
fi

read -p "火山引擎-1 (AK:SK格式，留空跳过): " volc1_key
if [ -n "$volc1_key" ]; then
    echo "VOLC_1_API_KEY=$volc1_key" >> .env
else
    echo "# VOLC_1_API_KEY=AK-xxx:SK-xxx" >> .env
fi

read -p "火山引擎-2 (AK:SK格式，留空跳过): " volc2_key
if [ -n "$volc2_key" ]; then
    echo "VOLC_2_API_KEY=$volc2_key" >> .env
else
    echo "# VOLC_2_API_KEY=AK-xxx:SK-xxx" >> .env
fi

echo ""
echo "阿里云 API Key 格式：AccessKeyId:AccessKeySecret"
read -p "阿里云-1 (KeyId:Secret格式，留空跳过): " aliyun1_key
if [ -n "$aliyun1_key" ]; then
    echo "ALIYUN_1_API_KEY=$aliyun1_key" >> .env
else
    echo "# ALIYUN_1_API_KEY=LTAI-xxx:secret-xxx" >> .env
fi

read -p "阿里云-2 (KeyId:Secret格式，留空跳过): " aliyun2_key
if [ -n "$aliyun2_key" ]; then
    echo "ALIYUN_2_API_KEY=$aliyun2_key" >> .env
else
    echo "# ALIYUN_2_API_KEY=LTAI-xxx:secret-xxx" >> .env
fi

echo ""
read -p "TikHub API Key（留空跳过）: " tikhub_key
if [ -n "$tikhub_key" ]; then
    echo "TIKHUB_API_KEY=$tikhub_key" >> .env
else
    echo "# TIKHUB_API_KEY=tikhub-your-key" >> .env
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
