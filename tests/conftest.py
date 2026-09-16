import os

import pytest

# 会影响配置加载的环境变量前缀
_CLEARED_PREFIXES = ('PROJECT_', 'WEBHOOK_', 'SUBSCRIPTION_', 'EMAIL_', 'BALANCE_', 'MAX_', 'MIN_', 'WEB_')
# Provider 密钥与阈值：留着会让「环境变量自动发现项目」把开发机 .env 里的真实账号带进测试
_CLEARED_SUFFIXES = ('_API_KEY', '_THRESHOLD', '_OWNER_PROJECT')


@pytest.fixture(autouse=True)
def clean_env():
    """清除测试环境变量污染，保证测试结果不受开发机 .env 影响"""
    keys_to_remove = [
        k for k in os.environ
        if k.startswith(_CLEARED_PREFIXES) or k.endswith(_CLEARED_SUFFIXES)
    ]

    saved_env = {k: os.environ.pop(k) for k in keys_to_remove}
    yield
    os.environ.update(saved_env)
