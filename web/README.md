# Web 模块化架构

本目录包含重构后的 Flask Web 服务器模块化代码。

## 架构概览

```
web/
├── __init__.py              # 模块入口
├── app.py                   # Flask 应用工厂
├── middleware.py            # 中间件（认证、验证）
├── utils.py                 # 工具函数
├── routes/                  # 路由蓝图
│   ├── __init__.py
│   ├── core.py              # 核心 API（健康检查、余额查询、刷新）
│   ├── subscription.py      # 订阅管理 API
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
- **middleware.py**：横切关注点（认证、验证）
- **utils.py**：工具函数，可复用

### 2. Flask Blueprint

每个功能模块使用独立的 Blueprint：

- `core_bp` - 核心功能（/, /health, /api/credits, /api/refresh）
- `subscription_bp` - 订阅管理（/api/subscription/*）

优势：
- 模块化组织代码
- 独立测试每个 Blueprint
- 便于功能开关和版本化

### 3. 依赖注入

使用 `init_*_routes()` 函数注入依赖（如 StateManager）：

```python
# 在 app.py 中
from .routes import core_bp, init_core_routes

init_core_routes(state_manager)  # 注入依赖
app.register_blueprint(core_bp)   # 注册蓝图
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
python web_server_modular.py
```

这是推荐的方式，使用新的模块化架构。

### 方式2：在代码中使用

```python
from web import create_app
from state_manager import StateManager

# 创建应用
state_mgr = StateManager()
app = create_app(state_mgr)

# 运行
app.run(host='0.0.0.0', port=8080)
```

### 方式3：兼容旧版

原有的 `web_server.py` 仍然可用，保持向后兼容：

```bash
python web_server.py
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
- 注册额外路由（历史数据、配置）
- 注册错误处理器

### middleware.py - 中间件

**@require_api_key**

API 认证装饰器，支持两种方式：
1. Header: `Authorization: Bearer <key>`
2. Query: `?api_key=<key>`

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
- `write_config()` - 写入配置文件（带文件锁）
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
| /health | GET | 健康检查 |
| /api/credits | GET | 获取余额 |
| /api/refresh | POST | 刷新余额 |

**subscription.py - 订阅管理 API**

| 路由 | 方法 | 说明 |
|------|------|------|
| /api/subscriptions | GET | 获取订阅状态 |
| /api/subscription/add | POST | 添加订阅 |
| /api/config/subscription | POST | 更新订阅 |
| /api/subscription/delete | POST/DELETE | 删除订阅 |
| /api/subscription/mark_renewed | POST | 标记已续费 |

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
from state_manager import StateManager

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

## 迁移计划

当前状态：

- ✅ 核心功能已模块化（core、subscription）
- ✅ 中间件和工具函数已提取
- ✅ 应用工厂模式已实现
- ⏸️ 历史数据API暂时保留在 app.py（未来可拆分为 history_bp）
- ⏸️ 配置API暂时保留在 app.py（未来可拆分为 config_bp）

下一步：

1. 完整测试模块化版本
2. 逐步迁移历史数据和配置 API 到独立 Blueprint
3. 废弃旧版 `web_server.py`（在下一个大版本）

## 性能对比

模块化版本 vs 单体版本：

| 指标 | 单体版本 | 模块化版本 |
|------|----------|------------|
| 文件数 | 1 (1200+ 行) | 10+ 文件 |
| 代码组织 | 混合在一起 | 按功能分离 |
| 可测试性 | 困难 | 容易 |
| 维护性 | 中等 | 良好 |
| 性能 | 基准 | 基本一致 |

## 常见问题

### Q: 为什么不一次性重构所有代码？

A: 为了保持稳定性和向后兼容，采用渐进式重构策略。当前版本已经包含核心功能，剩余部分可以在后续版本中迁移。

### Q: 如何切换回旧版？

A: 运行 `python web_server.py` 即可使用旧版，配置和数据完全兼容。

### Q: 性能会受影响吗？

A: 模块化主要影响代码组织，运行时开销可忽略（< 1ms）。实际测试显示性能基本一致。

### Q: 如何调试新版本？

A: 使用相同的方法：

```bash
# 设置日志级别
export LOG_LEVEL=DEBUG

# 运行
python web_server_modular.py
```

---

**维护者**: 项目团队
最后更新**: 2024-02-24
