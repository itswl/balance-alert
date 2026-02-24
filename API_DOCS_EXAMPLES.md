# API 文档示例

## 如何为端点添加 Swagger 文档

在 Flask 路由函数的 docstring 中添加 YAML 格式的文档：

```python
@app.route('/api/credits', methods=['GET'])
@require_auth
def get_credits():
    """
    获取所有项目余额和积分
    ---
    tags:
      - 余额监控
    security:
      - Bearer: []
      - ApiKey: []
    responses:
      200:
        description: 成功返回余额数据
        schema:
          type: object
          properties:
            last_update:
              type: string
              format: date-time
              example: "2026-02-24 10:30:00"
              description: 最后更新时间
            projects:
              type: array
              description: 项目列表
              items:
                type: object
                properties:
                  name:
                    type: string
                    example: "OpenRouter"
                  provider:
                    type: string
                    example: "openrouter"
                  balance:
                    type: number
                    example: 125.50
                  threshold:
                    type: number
                    example: 100.0
                  type:
                    type: string
                    enum: [balance, credits]
                    example: "credits"
                  need_alarm:
                    type: boolean
                    example: false
            summary:
              type: object
              properties:
                total_projects:
                  type: integer
                  example: 10
                need_alarm_count:
                  type: integer
                  example: 2
      503:
        description: 服务不可用，数据未初始化
    """
    return state_manager.get_balance_state()
```

## 主要 API 端点列表

### 余额监控
- `GET /api/credits` - 获取所有项目余额
- `POST /api/refresh` - 手动刷新余额

### 订阅管理
- `GET /api/subscriptions` - 获取所有订阅
- `POST /api/subscription/add` - 添加新订阅
- `POST /api/subscription/update` - 更新订阅
- `DELETE /api/subscription/delete` - 删除订阅

### 系统
- `GET /health` - 健康检查
- `GET /metrics` - Prometheus 指标
- `GET /api/docs` - API 文档（Swagger UI）

### 认证
- `POST /api/token` - 获取 JWT 令牌

## 访问 API 文档

启动服务后访问：
- Swagger UI: http://localhost:8080/api/docs
- OpenAPI Spec: http://localhost:8080/apispec.json
