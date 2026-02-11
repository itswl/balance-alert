#!/usr/bin/env python3
"""
配置加载模块
支持从环境变量读取敏感配置，优先于配置文件
"""
import os
import json
import re
from typing import Dict, Any, Optional


def load_env_file(env_file: str = '.env') -> None:
    """加载 .env 文件到环境变量"""
    if not os.path.exists(env_file):
        return
    
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key, value)


def get_env(key: str, default: Any = None) -> Any:
    """获取环境变量，支持类型转换"""
    value = os.environ.get(key, default)
    if value is None:
        return default
    
    # 布尔值转换
    if isinstance(default, bool):
        return value.lower() in ('true', '1', 'yes', 'on')
    
    # 整数转换
    if isinstance(default, int):
        try:
            return int(value)
        except ValueError:
            return default
    
    # 浮点数转换
    if isinstance(default, float):
        try:
            return float(value)
        except ValueError:
            return default
    
    return value


def get_api_key_from_env(project_name: str) -> Optional[str]:
    """从环境变量获取 API Key
    
    环境变量命名规则: API_KEY_<项目名称大写>
    特殊字符替换: - -> _, 空格 -> _, . -> _
    
    示例:
        项目 "OpenRouter" -> API_KEY_OPENROUTER
        项目 "Volc-火山引擎" -> API_KEY_VOLC_火山引擎
    """
    # 转换项目名称
    env_name = re.sub(r'[^a-zA-Z0-9]', '_', project_name).upper()
    env_key = f"API_KEY_{env_name}"
    return os.environ.get(env_key)


def get_email_password_from_env(email_name: str) -> Optional[str]:
    """从环境变量获取邮箱密码
    
    环境变量命名规则: EMAIL_PASSWORD_<邮箱名称大写>
    特殊字符替换: @ -> _, . -> _, - -> _
    
    示例:
        邮箱 "dexxxv@xxx.ai" -> EMAIL_PASSWORD_DEXXXV_XXX_AI
    """
    # 转换邮箱名称
    env_name = re.sub(r'[^a-zA-Z0-9]', '_', email_name).upper()
    env_key = f"EMAIL_PASSWORD_{env_name}"
    return os.environ.get(env_key)


def get_webhook_from_env() -> Optional[Dict[str, str]]:
    """从环境变量获取 Webhook 配置"""
    url = os.environ.get('WEBHOOK_URL')
    if not url:
        return None
    
    return {
        'url': url,
        'type': os.environ.get('WEBHOOK_TYPE', 'feishu'),
        'source': os.environ.get('WEBHOOK_SOURCE', 'credit-monitor')
    }


def load_config(config_file: str = 'config.json') -> Dict[str, Any]:
    """加载配置，环境变量优先于配置文件"""
    # 首先加载 .env 文件
    load_env_file()
    
    # 读取配置文件
    with open(config_file, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    # 环境变量覆盖 webhook 配置
    webhook_env = get_webhook_from_env()
    if webhook_env:
        config['webhook'] = webhook_env
    
    # 环境变量覆盖邮箱密码
    if 'email' in config:
        for email in config['email']:
            email_name = email.get('name', '')
            env_password = get_email_password_from_env(email_name)
            if env_password:
                email['password'] = env_password
    
    # 环境变量覆盖 API Key
    if 'projects' in config:
        for project in config['projects']:
            project_name = project.get('name', '')
            env_api_key = get_api_key_from_env(project_name)
            if env_api_key:
                project['api_key'] = env_api_key
    
    # 环境变量覆盖刷新间隔
    refresh_interval = get_env('BALANCE_REFRESH_INTERVAL', None)
    if refresh_interval is not None:
        if 'settings' not in config:
            config['settings'] = {}
        config['settings']['balance_refresh_interval_seconds'] = refresh_interval
    
    return config


def mask_sensitive_data(config: Dict[str, Any]) -> Dict[str, Any]:
    """脱敏处理，用于日志输出"""
    import copy
    masked = copy.deepcopy(config)
    
    # 脱敏 webhook URL
    if 'webhook' in masked and 'url' in masked['webhook']:
        url = masked['webhook']['url']
        if 'hook/' in url:
            masked['webhook']['url'] = url[:url.rfind('hook/') + 5] + '***'
    
    # 脱敏邮箱密码
    if 'email' in masked:
        for email in masked['email']:
            if 'password' in email:
                email['password'] = '***'
    
    # 脱敏 API Key
    if 'projects' in masked:
        for project in masked['projects']:
            if 'api_key' in project:
                api_key = project['api_key']
                if len(api_key) > 8:
                    project['api_key'] = api_key[:4] + '***' + api_key[-4:]
                else:
                    project['api_key'] = '***'
    
    return masked


# 全局配置缓存
_config_cache: Optional[Dict[str, Any]] = None


def get_config(config_file: str = 'config.json', use_cache: bool = True) -> Dict[str, Any]:
    """获取配置，带缓存"""
    global _config_cache
    
    if use_cache and _config_cache is not None:
        return _config_cache
    
    _config_cache = load_config(config_file)
    return _config_cache


def clear_config_cache() -> None:
    """清除配置缓存"""
    global _config_cache
    _config_cache = None
