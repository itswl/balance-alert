# Web 模块

Flask Web 看板和 API。

## 结构

```text
web/
├── app.py           # 应用工厂 create_app()：CORS、认证、蓝图注册、错误处理
├── middleware.py    # protect_api_endpoints（/api/* 的 API Key 认证）、validate_request（pydantic 请求校验）
├── schemas.py       # 订阅相关请求的 pydantic 校验模型
├── utils.py         # json_error/json_success、load_config_safe、config_db_write、ETag、审计日志、脱敏
└── routes/
    ├── core.py          # / /health /live /api/features /api/credits /api/subscriptions /api/refresh
    ├── subscription.py  # 订阅增删改查（未启用时蓝图统一返回 503）
    ├── project.py       # /api/config/projects /api/config/threshold（需 ENABLE_DYNAMIC_CONFIG）
    ├── email.py         # 邮箱配置 CRUD（需 ENABLE_DYNAMIC_CONFIG）
    └── history.py       # 历史数据查询（需 ENABLE_HISTORY_API）
```

## 设计要点

- 路由直接调用 `services/` 与 `database/repository.py`，没有中间转发层。
- `core` 与 `subscription` 蓝图始终注册；订阅功能未启用时由 `subscription` 蓝图的
  `before_request` 统一返回 503，`GET /api/subscriptions` 在 `core` 中提供、始终可用。
- `project` / `email` / `history` 蓝图按 `ENABLE_DYNAMIC_CONFIG` / `ENABLE_HISTORY_API` 注册。
- 认证：`middleware.protect_api_endpoints` 对所有 `/api/*` 请求校验 `X-API-Key`
  （或 `Authorization: Bearer`），密钥来自 `WEB_API_KEY`。
- 状态数据来自 `core.state_manager.StateManager`，由 `main.py` 的后台线程周期刷新。

各端点的请求/响应格式见 `docs/API.md`。
