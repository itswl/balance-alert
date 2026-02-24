#!/bin/bash
# 从 .env 文件创建 Kubernetes Secret

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_ROOT/.env"
NAMESPACE="balance-alert"
SECRET_NAME="balance-alert-secret"

echo "🔐 从 .env 创建 Kubernetes Secret"
echo "=================================="
echo ""

# 检查 .env 文件
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ 错误: .env 文件不存在"
    echo "路径: $ENV_FILE"
    echo ""
    echo "请先创建 .env 文件："
    echo "  cp .env.example .env"
    echo "  # 然后编辑 .env 填入真实配置"
    exit 1
fi

echo "📝 .env 文件: $ENV_FILE"
echo "📦 命名空间: $NAMESPACE"
echo "🔑 Secret 名称: $SECRET_NAME"
echo ""

# 确认操作
read -p "是否继续? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "已取消"
    exit 0
fi

# 创建命名空间（如果不存在）
if ! kubectl get namespace "$NAMESPACE" &>/dev/null; then
    echo "📂 创建命名空间: $NAMESPACE"
    kubectl create namespace "$NAMESPACE"
fi

# 删除旧的 Secret（如果存在）
if kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" &>/dev/null; then
    echo "🗑️  删除旧的 Secret"
    kubectl delete secret "$SECRET_NAME" -n "$NAMESPACE"
fi

# 创建 Secret
echo "✨ 创建 Secret..."
kubectl create secret generic "$SECRET_NAME" \
    --from-env-file="$ENV_FILE" \
    -n "$NAMESPACE"

echo ""
echo "✅ Secret 创建成功!"
echo ""
echo "🔍 查看 Secret:"
echo "  kubectl get secret $SECRET_NAME -n $NAMESPACE"
echo ""
echo "📋 查看 Secret 内容（base64 编码）:"
echo "  kubectl get secret $SECRET_NAME -n $NAMESPACE -o yaml"
echo ""
echo "🔓 查看解码后的内容:"
echo "  kubectl get secret $SECRET_NAME -n $NAMESPACE -o jsonpath='{.data}' | jq 'map_values(@base64d)'"
echo ""
echo "⚠️  安全提示："
echo "  - Secret 包含敏感信息，请勿分享或提交到 Git"
echo "  - 考虑使用 Sealed Secrets 或 External Secrets 加密存储"
echo "  - 定期轮换密钥和密码"
