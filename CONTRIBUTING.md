# 贡献指南

感谢你对 Balance Alert 项目的关注！本指南将帮助你快速开始贡献代码。

## 目录

- [开发环境搭建](#开发环境搭建)
- [代码规范](#代码规范)
- [提交规范](#提交规范)
- [测试要求](#测试要求)
- [PR 流程](#pr-流程)
- [添加新 Provider](#添加新-provider)
- [常见问题](#常见问题)

## 开发环境搭建

### 1. 克隆仓库

```bash
git clone https://github.com/your-org/balance-alert.git
cd balance-alert
```

### 2. 安装依赖

```bash
# 推荐使用虚拟环境
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 安装开发依赖
pip install pytest pytest-cov black flake8 mypy
```

### 3. 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env，填入测试用的 API Key
vim .env
```

### 4. 初始化数据库

```bash
# 自动创建 SQLite 数据库
python -c "from database import init_database; init_database()"
```

### 5. 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行单个测试文件
pytest tests/test_providers.py -v

# 查看测试覆盖率
pytest tests/ --cov=. --cov-report=html
open htmlcov/index.html  # 查看覆盖率报告
```

### 6. 启动开发服务器

```bash
# 方式1：直接运行
python web_server.py

# 方式2：使用 Flask 开发模式
export FLASK_APP=web_server.py
export FLASK_ENV=development
flask run --port 8080

# 访问 http://localhost:8080
```

## 代码规范

### Python 代码风格

我们遵循 PEP 8 规范，并使用以下工具检查：

```bash
# 代码格式化（自动修复）
black --line-length 120 .

# 代码风格检查
flake8 --max-line-length 120 --ignore E501,W503 .

# 类型检查
mypy --ignore-missing-imports .
```

### 命名约定

- **文件名**：小写 + 下划线（`config_loader.py`）
- **类名**：大驼峰（`CreditMonitor`, `OpenRouterProvider`）
- **函数/变量名**：小写 + 下划线（`get_credits`, `api_key`）
- **常量**：大写 + 下划线（`DEFAULT_TIMEOUT`, `MAX_RETRIES`）
- **私有成员**：单下划线前缀（`_cache`, `_load_config`）

### 文档字符串

使用 Google 风格的 docstring：

```python
def check_project(self, project_config: Dict[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    """
    检查单个项目的余额

    Args:
        project_config: 项目配置字典，包含 name, provider, api_key 等字段
        dry_run: 是否为测试模式（不发送告警），默认 False

    Returns:
        dict: 检查结果，包含以下字段：
            - success (bool): 是否成功
            - credits (float): 当前余额（成功时）
            - error (str): 错误信息（失败时）

    Raises:
        ValueError: 当 provider 不存在时

    Example:
        >>> config = {'name': 'Test', 'provider': 'openrouter', 'api_key': 'sk-xxx'}
        >>> monitor.check_project(config, dry_run=True)
        {'success': True, 'credits': 150.0}
    """
```

### 类型注解

所有公开函数都应添加类型注解：

```python
from typing import Dict, Any, List, Optional

def get_credits(self) -> Dict[str, Any]:
    """获取余额"""
    pass

def save_balance_record(
    project_id: str,
    balance: float,
    threshold: Optional[float] = None
) -> Optional[int]:
    """保存余额记录"""
    pass
```

### 错误处理

1. **优先使用特定异常**：

```python
# ❌ 不推荐
try:
    result = api_call()
except Exception:
    pass

# ✅ 推荐
try:
    result = api_call()
except requests.Timeout:
    logger.error("API 请求超时")
except requests.HTTPError as e:
    logger.error(f"API 返回错误: {e.response.status_code}")
```

2. **记录异常堆栈**：

```python
try:
    risky_operation()
except Exception as e:
    logger.error(f"操作失败: {e}", exc_info=True)  # 包含完整堆栈
```

3. **容错但不沉默**：

```python
# 数据库失败不应阻断主流程
try:
    BalanceRepository.save(...)
except Exception as e:
    logger.error(f"保存失败（不影响主流程）: {e}")
    # 继续执行后续逻辑
```

## 提交规范

### Commit Message 格式

使用 Conventional Commits 规范：

```
<类型>(<范围>): <简短描述>

<详细描述>（可选）

<Footer>（可选）
```

**类型（Type）**：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `style`: 代码格式（不影响功能）
- `refactor`: 重构（不是新功能也不是Bug修复）
- `perf`: 性能优化
- `test`: 测试相关
- `chore`: 构建/工具/依赖更新

**示例**：

```bash
# 好的提交信息
feat(providers): 添加 Google Vertex AI Provider 支持
fix(monitor): 修复并发检查时的线程安全问题
docs(api): 更新 Swagger API 文档示例
perf(cache): 优化响应缓存命中率

# 中文版（项目当前使用）
🚀 新增功能：Google Vertex AI Provider 支持
🐛 修复：并发检查线程安全问题
📝 文档：更新 API 文档示例
⚡ 性能：优化缓存命中率
```

### Emoji 前缀（可选）

| Emoji | 类型 | 说明 |
|-------|------|------|
| 🚀 | feat | 新功能 |
| 🐛 | fix | Bug修复 |
| 📝 | docs | 文档 |
| ⚡ | perf | 性能优化 |
| ♻️ | refactor | 重构 |
| ✅ | test | 测试 |
| 🔧 | chore | 配置/工具 |
| 🔒 | security | 安全修复 |

## 测试要求

### 测试覆盖率

- **最低要求**：新代码覆盖率 > 70%
- **推荐目标**：> 85%
- **核心模块**：> 90%（monitor, providers, database）

### 测试类型

1. **单元测试**（`tests/test_*.py`）

```python
def test_openrouter_provider_success(mock_requests):
    """测试 OpenRouter Provider 成功场景"""
    # Arrange
    mock_requests.get.return_value.json.return_value = {
        'data': {'credits': 150.0}
    }
    provider = OpenRouterProvider('sk-test-key')

    # Act
    result = provider.get_credits()

    # Assert
    assert result['success'] is True
    assert result['credits'] == 150.0
```

2. **集成测试**（`tests/test_integration.py`）

```python
def test_monitor_with_real_database(test_config):
    """测试监控器与数据库集成"""
    monitor = CreditMonitor(test_config)
    monitor.run(dry_run=True)

    # 验证数据已保存到数据库
    history = BalanceRepository.get_balance_history(days=1)
    assert len(history) > 0
```

3. **端到端测试**（`tests/test_e2e.py`）

```python
def test_full_monitoring_workflow(client):
    """测试完整监控工作流"""
    # 1. 刷新余额
    response = client.post('/api/refresh')
    assert response.status_code == 200

    # 2. 查询结果
    response = client.get('/api/credits')
    data = response.get_json()
    assert 'projects' in data
```

### Mock 最佳实践

```python
from unittest.mock import Mock, patch, MagicMock

# 1. Mock HTTP 请求
@patch('requests.get')
def test_with_mocked_http(mock_get):
    mock_get.return_value.json.return_value = {'data': {...}}
    # 测试逻辑

# 2. Mock 数据库
@patch('database.repository.BalanceRepository.save_balance_record')
def test_with_mocked_db(mock_save):
    mock_save.return_value = 123
    # 测试逻辑

# 3. Mock 环境变量
@patch.dict(os.environ, {'API_KEY': 'test-key'})
def test_with_mocked_env():
    # 测试逻辑
```

### 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 运行特定测试类
pytest tests/test_providers.py::TestOpenRouterProvider -v

# 运行单个测试
pytest tests/test_monitor.py::test_check_project_success -v

# 查看测试输出
pytest tests/ -v -s  # -s 显示 print 输出

# 并行测试（加速）
pytest tests/ -n auto  # 需要 pytest-xdist
```

## PR 流程

### 1. Fork 仓库并创建分支

```bash
# Fork 仓库到你的 GitHub 账号
# 然后克隆你的 Fork
git clone https://github.com/YOUR_USERNAME/balance-alert.git
cd balance-alert

# 添加上游仓库
git remote add upstream https://github.com/original/balance-alert.git

# 创建功能分支
git checkout -b feat/add-google-provider
```

### 2. 开发与测试

```bash
# 开发代码
vim providers/google.py

# 运行测试
pytest tests/test_providers.py -v

# 代码格式化
black providers/google.py

# 提交代码
git add providers/google.py tests/test_providers.py
git commit -m "feat(providers): 添加 Google Vertex AI Provider"
```

### 3. 保持分支同步

```bash
# 同步上游更新
git fetch upstream
git rebase upstream/main
```

### 4. 推送并创建 PR

```bash
# 推送到你的 Fork
git push origin feat/add-google-provider

# 在 GitHub 上创建 Pull Request
# 填写 PR 描述模板
```

### PR 描述模板

````markdown
## 变更说明

简要描述此 PR 的目的和改动内容。

## 变更类型

- [ ] 新功能 (feat)
- [ ] Bug 修复 (fix)
- [ ] 文档更新 (docs)
- [ ] 性能优化 (perf)
- [ ] 重构 (refactor)
- [ ] 测试相关 (test)

## 测试清单

- [ ] 所有测试通过 (`pytest tests/ -v`)
- [ ] 代码覆盖率 > 70% (`pytest --cov`)
- [ ] 代码格式化 (`black .`)
- [ ] 无 Lint 错误 (`flake8 .`)
- [ ] 手动测试通过

## 相关 Issue

关联 Issue #123（如果有）

## 截图（可选）

如果是 UI 改动，请提供截图。

## 附加说明

其他需要 Review 者注意的事项。
````

### Code Review 要点

Reviewer 会关注：

- [ ] 代码是否符合项目规范
- [ ] 是否有充分的测试覆盖
- [ ] 是否有潜在的性能问题
- [ ] 错误处理是否完善
- [ ] 日志记录是否合理
- [ ] 文档是否更新（如有必要）

## 添加新 Provider

### 步骤详解

#### 1. 创建 Provider 文件

在 `providers/` 目录下创建新文件：

```bash
touch providers/google.py
```

#### 2. 实现 Provider 类

```python
#!/usr/bin/env python3
"""
Google Vertex AI Provider

API 文档：https://cloud.google.com/vertex-ai/docs/reference
"""
import requests
from typing import Dict, Any
from .base import BaseProvider

class GoogleProvider(BaseProvider):
    """Google Vertex AI Provider 实现"""

    def __init__(self, api_key: str):
        """
        初始化 Provider

        Args:
            api_key: Google Cloud API Key 或 Service Account JSON
        """
        super().__init__(api_key)
        self.base_url = "https://compute.googleapis.com/compute/v1"

    def get_credits(self) -> Dict[str, Any]:
        """
        获取余额信息

        Returns:
            dict: {
                'success': bool,
                'credits': float,
                'currency': str,
                'error': str  # 仅失败时
            }
        """
        try:
            response = self.session.get(
                f"{self.base_url}/projects/your-project/billingInfo",
                headers={'Authorization': f'Bearer {self.api_key}'},
                timeout=10
            )
            response.raise_for_status()

            data = response.json()
            credits = data.get('creditBalance', 0.0)

            return {
                'success': True,
                'credits': credits,
                'currency': 'USD'
            }

        except requests.Timeout:
            return {
                'success': False,
                'error': '请求超时'
            }
        except requests.HTTPError as e:
            return {
                'success': False,
                'error': f'API 错误: {e.response.status_code}'
            }
        except Exception as e:
            return {
                'success': False,
                'error': str(e)
            }
```

#### 3. 注册 Provider

在 `providers/__init__.py` 中注册：

```python
from .google import GoogleProvider

PROVIDER_MAP = {
    # ... 现有 Providers
    'google': GoogleProvider,
    'vertex-ai': GoogleProvider,  # 别名
}
```

#### 4. 添加测试

创建 `tests/test_providers_google.py`：

```python
import pytest
from unittest.mock import Mock, patch
from providers.google import GoogleProvider

class TestGoogleProvider:
    """Google Provider 测试套件"""

    def test_get_credits_success(self):
        """测试成功获取余额"""
        with patch('requests.Session.get') as mock_get:
            # Mock API 响应
            mock_response = Mock()
            mock_response.json.return_value = {
                'creditBalance': 250.0
            }
            mock_response.status_code = 200
            mock_get.return_value = mock_response

            # 执行测试
            provider = GoogleProvider('test-key')
            result = provider.get_credits()

            # 断言
            assert result['success'] is True
            assert result['credits'] == 250.0

    def test_get_credits_api_error(self):
        """测试 API 错误处理"""
        with patch('requests.Session.get') as mock_get:
            mock_get.side_effect = requests.HTTPError(
                response=Mock(status_code=401)
            )

            provider = GoogleProvider('invalid-key')
            result = provider.get_credits()

            assert result['success'] is False
            assert 'API 错误' in result['error']
```

#### 5. 更新文档

在 `README.md` 中添加：

```markdown
### 支持的 Provider

- OpenRouter
- Anthropic (Claude)
- OpenAI
- Azure OpenAI
- **Google Vertex AI** ⬅️ 新增
...

### Google Vertex AI 配置

```json
{
  "name": "Google AI Project",
  "provider": "google",
  "api_key": "YOUR_GOOGLE_CLOUD_API_KEY",
  "threshold": 100.0,
  "enabled": true
}
```
```

#### 6. 提交 PR

```bash
git add providers/google.py tests/test_providers_google.py
git add providers/__init__.py README.md
git commit -m "feat(providers): 添加 Google Vertex AI Provider 支持"
git push origin feat/add-google-provider
```

## 常见问题

### Q: 如何调试 Provider API 调用？

A: 启用详细日志：

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# 或在 .env 中设置
LOG_LEVEL=DEBUG
```

### Q: 测试时如何避免真实 API 调用？

A: 使用 Mock：

```python
@patch('providers.openrouter.OpenRouterProvider.get_credits')
def test_monitor(mock_get_credits):
    mock_get_credits.return_value = {'success': True, 'credits': 100.0}
    # 测试逻辑
```

### Q: 如何测试配置热重载？

A: 使用临时文件：

```python
import tempfile
import json

def test_config_reload():
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as f:
        config = {'projects': [...]}
        json.dump(config, f)
        f.flush()

        # 加载配置
        loaded = load_config(f.name)
        assert len(loaded['projects']) == ...
```

### Q: 如何贡献文档？

A: 文档源文件在以下位置：

- `README.md` - 项目总览
- `ARCHITECTURE.md` - 架构设计
- `CONTRIBUTING.md` - 本文档
- `database/README.md` - 数据库文档
- `API_DOCS_EXAMPLES.md` - API 文档示例

直接编辑对应文件并提交 PR。

### Q: 遇到依赖冲突怎么办？

A: 尝试以下方法：

```bash
# 1. 清理环境
pip uninstall -r requirements.txt -y
pip cache purge

# 2. 重新安装
pip install -r requirements.txt

# 3. 如果还不行，使用 pip-tools
pip install pip-tools
pip-compile requirements.in  # 生成精确版本
pip-sync requirements.txt
```

### Q: 如何运行单个测试并查看详细输出？

```bash
# 运行单个测试，显示 print 输出
pytest tests/test_monitor.py::test_check_project -v -s

# 添加调试器断点
import pdb; pdb.set_trace()  # 在代码中添加
pytest tests/test_monitor.py --pdb  # 失败时自动进入调试器
```

## 开发工具推荐

### VS Code 插件

- **Python** - 官方 Python 支持
- **Pylance** - 类型检查和智能提示
- **Python Test Explorer** - 可视化测试运行
- **GitLens** - Git 增强
- **Code Spell Checker** - 拼写检查

### VS Code 配置 (`.vscode/settings.json`)

```json
{
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.linting.flake8Args": [
    "--max-line-length=120"
  ],
  "python.formatting.provider": "black",
  "python.formatting.blackArgs": [
    "--line-length=120"
  ],
  "editor.formatOnSave": true,
  "python.testing.pytestEnabled": true,
  "python.testing.unittestEnabled": false
}
```

## 联系方式

- **Issues**: https://github.com/your-org/balance-alert/issues
- **Discussions**: https://github.com/your-org/balance-alert/discussions
- **Email**: dev@example.com

## 致谢

感谢所有贡献者的付出！🎉

---

**最后更新**: 2024-02-24
