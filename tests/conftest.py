import os
import pytest

@pytest.fixture(autouse=True)
def clean_env():
    """清除测试环境变量污染"""
    keys_to_remove = []
    for k in os.environ:
        if k.startswith(('PROJECT_', 'WEBHOOK_', 'SUBSCRIPTION_', 'EMAIL_', 'BALANCE_', 'MAX_', 'MIN_', 'WEB_')):
            keys_to_remove.append(k)
    
    saved_env = {}
    for k in keys_to_remove:
        saved_env[k] = os.environ[k]
        del os.environ[k]
        
    yield
    
    for k, v in saved_env.items():
        os.environ[k] = v
