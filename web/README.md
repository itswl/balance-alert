# Web 模块化架构

本目录包含 Flask Web 服务器代码（Dashboard + REST API）。

## 架构概览

```
web/
├── __init__.py              # 模块入口
├── app.py                   # Flask 应用工厂
├── middleware.py            # 中间件（请求验证）
├── utils.py                 # 工具函数
├── routes/                  # 路由蓝图
│   ├── __init__.py
│   ├── core.py              # 核心 API（健康检查、余额查询、刷新）
│   ├── subscription.py      # 订阅管理 API
│   ├── history.py           # 历史数据 API（可选）
│   ├── project.py           # 项目配置 API（可选）
│   ├── email.py             # 邮箱配置 API（可选）
│   └── ...（未来扩展）
├── handlers/                # 业务逻辑处理器
│   ├── __init__.py
│   ├── monitor_handler.py   # 监控逻辑
│   ├── subscription_handler.py  # 订阅逻辑
│   └── ...（未来扩展）
└── README.md                # 本文档
```

## 设计原则

### 1. 关注点分离

- **routes/**：处理 HTTP 请求/响应，路由定义
- **handlers/**：业务逻辑处理，与框架解耦
- **middleware.py**：横切关注点（请求验证）
- **utils.py**：工具函数，可复用

### 2. Flask Blueprint

每个功能模块使用独立的 Blueprint：

- `create_core_bp(state_manager)` - 核心功能（/, /health, /ready, /live, /api/features, /api/credits, /api/refresh）
- `create_subscription_bp(state_manager)` - 订阅管理（/api/subscription/*）
- `history_bp` - 历史数据（/api/history/*，可选）
 - `project_bp/email_bp` - 动态配置 API（/api/config/*，可选）

优势：
- 模块化组织代码
- 独立测试每个 Blueprint
- 便于功能开关和版本化

### 3. 依赖注入

使用“蓝图工厂（Blueprint Factory）”通过闭包注入依赖（如 StateManager），避免模块级全局变量：

```python
# 在 app.py 中
from .routes import create_core_bp

app.register_blueprint(create_core_bp(state_manager))
```

优势：
- 方便单元测试（Mock 依赖）
- 解耦模块间依赖

### 4. 应用工厂模式

`create_app()` 函数创建和配置 Flask 应用：

```python
from web import create_app

app = create_app(state_manager)
```

优势：
- 支持多实例（测试、生产）
- 配置灵活（环境变量、参数）

## 使用方法

### 方式1：使用模块化启动器

```bash
python main.py
```

这是推荐的启动方式。

### 方式2：在代码中使用

```python
from web import create_app
from core.state_manager import StateManager

# 创建应用
state_mgr = StateManager()
app = create_app(state_mgr)

# 运行
app.run(host='0.0.0.0', port=8080)
```

## 模块说明

### app.py - Flask 应用工厂

**create_app(state_manager)**

创建并配置 Flask 应用实例。

**参数**：
- `state_manager` (StateManager): 状态管理器实例

**返回**：
- Flask 应用实例

**功能**：
- 配置 Flask（CORS、JSON、请求大小限制）
- 注册所有 Blueprint
- 注册错误处理器

### middleware.py - 中间件

**protect_api_endpoints(app)**

统一保护 `/api/*` 接口，请求必须携带 `X-API-Key` 或 `Authorization: Bearer <key>`，服务端使用环境变量 `WEB_API_KEY` 校验。

**@validate_request(model_class)**

请求验证装饰器，使用 Pydantic 模型验证请求体。

示例：
```python
@validate_request(AddSubscriptionRequest)
def add_subscription(validated_data: AddSubscriptionRequest):
    # validated_data 是已验证的 Pydantic 实例
    pass
```

### utils.py - 工具函数

常用工具函数：

- `get_enable_web_alarm()` - 获取 Web 告警是否启用
- `get_refresh_interval()` - 获取刷新间隔配置
- `load_config_safe()` - 安全加载配置文件
- `make_etag_response()` - 创建带 ETag 的响应
- `audit_log()` - 记录审计日志

### handlers/ - 业务逻辑处理器

**monitor_handler.py**

- `update_balance_cache(results, state_mgr)` - 更新余额缓存
- `refresh_credits(config_path, project_name, dry_run)` - 执行余额刷新

**subscription_handler.py**

- `update_subscription_cache(results, state_mgr)` - 更新订阅缓存
- `refresh_subscription_cache(config_path, state_mgr)` - 刷新订阅缓存
- `calculate_next_renewal_date()` - 计算下次续费日期

### routes/ - 路由蓝图

**core.py - 核心 API**

| 路由 | 方法 | 说明 |
|------|------|------|
| / | GET | 首页（Dashboard）|
| /health | GET | 就绪检查 |
| /ready | GET | 就绪检查 |
| /live | GET | 存活检查 |
| /api/features | GET | 查询功能开关 |
| /api/credits | GET | 获取余额 |
| /api/refresh | GET/POST | 刷新余额（30 秒冷却） |

**subscription.py - 订阅管理 API**

| 路由 | 方法 | 说明 |
|------|------|------|
| /api/subscriptions | GET | 获取订阅状态 |
| /api/subscription/add | POST | 添加订阅 |
| /api/config/subscriptions | GET | 获取订阅配置（不含状态） |
| /api/config/subscription | POST | 更新订阅配置 |
| /api/subscription/delete | POST/DELETE | 删除订阅 |
| /api/subscription/mark_renewed | POST | 标记已续费 |
| /api/subscription/clear_renewed | POST | 清除续费标记 |

**history.py - 历史数据 API（可选）**

| 路由 | 方法 | 说明 |
|------|------|------|
| /api/history/balance | GET | 余额历史 |
| /api/history/trend/<project_id> | GET | 余额趋势 |
| /api/history/alerts | GET | 告警历史 |
| /api/history/stats | GET | 告警统计 |
| /api/history/projects | GET | 项目摘要 |

**project.py / email.py - 动态配置 API（可选）**

| 路由 | 方法 | 说明 |
|------|------|------|
| /api/config/projects | GET | 获取项目配置 |
| /api/config/threshold | POST | 更新项目阈值 |
| /api/config/emails | GET | 获取邮箱配置 |
| /api/config/email | POST | 添加/更新邮箱配置 |
| /api/config/email/delete | POST | 删除邮箱配置 |

## 测试

### 单元测试

每个模块可独立测试：

```python
# 测试 handlers
from web.handlers import refresh_credits

result = refresh_credits('config.json', dry_run=True)
assert result['success'] is True

# 测试 Blueprint
from web import create_app
from core.state_manager import StateManager

state_mgr = StateManager()
app = create_app(state_mgr)
client = app.test_client()

response = client.get('/health')
assert response.status_code == 200
```

### 集成测试

```python
import pytest
from web import create_app

@pytest.fixture
def client():
    app = create_app()
    app.config['TESTING'] = True
    return app.test_client()

def test_get_credits(client):
    response = client.get('/api/credits')
    assert response.status_code in [200, 503]
```

## 扩展指南

### 添加新的 Blueprint

1. 创建新文件 `web/routes/new_module.py`：

```python
from flask import Blueprint

new_bp = Blueprint('new_module', __name__, url_prefix='/api/new')

@new_bp.route('/endpoint')
def new_endpoint():
    return {'status': 'success'}
```

2. 在 `web/routes/__init__.py` 中导出：

```python
from .new_module import new_bp
__all__ = [..., 'new_bp']
```

3. 在 `web/app.py` 中注册：

```python
def _register_blueprints(app, state_manager):
    # ... 现有代码
    from .routes import new_bp
    app.register_blueprint(new_bp)
```

### 添加新的 Handler

1. 创建 `web/handlers/new_handler.py`：

```python
def handle_new_logic(*args, **kwargs):
    # 业务逻辑
    pass
```

2. 在 Blueprint 中使用：

```python
from ..handlers.new_handler import handle_new_logic

@new_bp.route('/action')
def action():
    result = handle_new_logic()
    return jsonify(result)
```

---

**最后更新**: 2026-05-17
