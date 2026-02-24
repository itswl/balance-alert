# 贡献指南

感谢你对 Balance Alert 项目的关注！

## 开发环境搭建

```bash
# 1. 克隆仓库
git clone https://github.com/your-org/balance-alert.git
cd balance-alert

# 2. 安装依赖
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
vim .env

# 4. 运行测试
pytest tests/ -v

# 5. 启动开发服务器
python web_server.py
```

## 代码规范

### Python 代码风格

遵循 PEP 8 规范：

```bash
# 代码格式化
black --line-length 120 .

# 代码检查
flake8 --max-line-length 120 .

# 类型检查
mypy --ignore-missing-imports .
```

### 命名约定

- **文件名**：小写 + 下划线 (`config_loader.py`)
- **类名**：大驼峰 (`CreditMonitor`)
- **函数/变量**：小写 + 下划线 (`get_credits`)
- **常量**：大写 + 下划线 (`MAX_RETRIES`)

### 文档字符串

使用 Google 风格：

```python
def get_credits(self) -> Dict[str, Any]:
    """
    获取余额信息

    Returns:
        dict: {
            'success': bool,
            'credits': float,
            'currency': str
        }

    Example:
        >>> provider.get_credits()
        {'success': True, 'credits': 150.0}
    """
```

## 提交规范

### Commit Message 格式

```bash
# 使用 emoji 前缀（可选）
🚀 feat(providers): 添加 Google Vertex AI 支持
🐛 fix(monitor): 修复并发检查线程安全问题
📝 docs(api): 更新 API 文档示例
⚡ perf(cache): 优化缓存命中率
```

**Emoji 前缀**：
- 🚀 `feat` - 新功能
- 🐛 `fix` - Bug修复
- 📝 `docs` - 文档
- ⚡ `perf` - 性能优化
- ♻️ `refactor` - 重构
- ✅ `test` - 测试
- 🔧 `chore` - 配置/工具

## 测试要求

### 测试覆盖率

- 最低要求：> 70%
- 核心模块：> 90%（monitor, providers）

### 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行单个测试
pytest tests/test_monitor.py::test_check_project -v

# 查看覆盖率
pytest tests/ --cov=. --cov-report=html
```

### Mock 示例

```python
from unittest.mock import patch

@patch('requests.get')
def test_provider(mock_get):
    mock_get.return_value.json.return_value = {'data': {...}}
    # 测试逻辑
```

## PR 流程

### 1. Fork 并创建分支

```bash
git clone https://github.com/YOUR_USERNAME/balance-alert.git
git checkout -b feat/add-new-feature
```

### 2. 开发与测试

```bash
# 开发代码
vim providers/google.py

# 运行测试
pytest tests/ -v

# 代码格式化
black .
```

### 3. 提交代码

```bash
git add .
git commit -m "🚀 feat(providers): 添加 Google Provider"
git push origin feat/add-new-feature
```

### 4. 创建 Pull Request

填写 PR 描述，包括：
- 变更说明
- 测试清单
- 相关 Issue

## 添加新 Provider

### 步骤

1. **创建 Provider 文件**

```python
# providers/google.py
from .base import BaseProvider

class GoogleProvider(BaseProvider):
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.base_url = "https://api.google.com"

    def get_credits(self) -> Dict[str, Any]:
        try:
            response = self.session.get(
                f"{self.base_url}/billing",
                headers={'Authorization': f'Bearer {self.api_key}'}
            )
            data = response.json()
            return {
                'success': True,
                'credits': data['balance'],
                'currency': 'USD'
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}
```

2. **注册 Provider**

```python
# providers/__init__.py
from .google import GoogleProvider

PROVIDER_MAP = {
    'google': GoogleProvider,
    # ... 其他 Providers
}
```

3. **添加测试**

```python
# tests/test_providers_google.py
def test_google_provider_success():
    with patch('requests.Session.get') as mock_get:
        mock_get.return_value.json.return_value = {'balance': 250.0}
        provider = GoogleProvider('test-key')
        result = provider.get_credits()
        assert result['success'] is True
```

4. **更新文档**

在 `README.md` 中添加 Google Provider 配置示例。

## 常见问题

### Q: 如何调试 API 调用？

```bash
# 启用详细日志
export LOG_LEVEL=DEBUG
python web_server.py
```

### Q: 测试时如何避免真实 API 调用？

使用 Mock：
```python
@patch('providers.openrouter.OpenRouterProvider.get_credits')
def test_monitor(mock_get):
    mock_get.return_value = {'success': True, 'credits': 100.0}
```

### Q: 依赖冲突怎么办？

```bash
# 清理并重装
pip uninstall -r requirements.txt -y
pip install -r requirements.txt
```

## 开发工具推荐

### VS Code 插件

- Python
- Pylance
- Python Test Explorer
- GitLens

### VS Code 配置

```json
{
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true,
  "python.testing.pytestEnabled": true
}
```

## 联系方式

- **Issues**: https://github.com/your-org/balance-alert/issues
- **Email**: dev@example.com

---

**最后更新**: 2024-02-24
