# Kubernetes 部署

本目录只有一个部署清单：`common-prod.yaml`，包含 balance-alert 的 Deployment、Service 和 Ingress，全部部署在 `common-prod` 命名空间。

## 部署步骤

### 1. 创建 Secret

敏感配置通过 Secret 注入容器（`envFrom`），直接用本地 `.env` 文件生成：

```bash
kubectl create secret generic balance-alert-secret \
  --from-env-file=.env \
  -n common-prod \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 2. 部署

```bash
kubectl apply -f k8s/common-prod.yaml
```

### 3. 验证

```bash
kubectl get pods -n common-prod -l app=balance-alert
kubectl logs -f deployment/balance-alert -n common-prod
```

## 关键环境变量

`.env`（即 Secret）中至少需要提供：

| 变量 | 说明 |
|------|------|
| `WEB_API_KEY` | Web/API 访问密钥（必填，Secret 中缺失时 Pod 无法启动） |
| `DATABASE_URL` | 数据库连接串（生产环境建议 PostgreSQL） |
| 各 provider 密钥 | 如 `OPENROUTER_API_KEY`、`VOLC_1_API_KEY`、`ALIYUN_1_API_KEY` 等，按实际监控的项目配置 |

其余非敏感参数（刷新间隔、功能开关等）已在 `common-prod.yaml` 的 `env` 中直接设置，按需修改。

## 更新配置

修改 `.env` 后重新执行第 1 步的命令更新 Secret，然后重启使其生效：

```bash
kubectl rollout restart deployment/balance-alert -n common-prod
```
