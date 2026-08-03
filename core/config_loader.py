#!/usr/bin/env python3
"""
配置加载模块

职责边界（一个值只有一个家）：
- 环境变量（core.settings）：密钥、连接、开关、调度参数
- config.json：业务清单 projects/subscriptions/email，支持 ${VAR} 占位符
- 数据库动态配置：生产的业务清单，需 ENABLE_DYNAMIC_CONFIG，有数据时覆盖文件同名段落
"""
import copy
import hashlib
import json
import logging
import os
import re
from threading import Lock
from typing import Any, Dict, Optional

from dotenv import load_dotenv

from core.logger import get_logger
from core.settings import get_settings

logger = get_logger('config_loader')

DEFAULT_REFRESH_INTERVAL_SECONDS = 3600

_DB_META_FIELDS = {'id', 'created_at', 'updated_at'}


def load_env_file(env_file: str = '.env') -> None:
    """加载 .env 文件"""
    if os.path.exists(env_file):
        load_dotenv(env_file, override=True)
        logger.info(f"[Config] 已加载环境变量文件: {env_file}")


def get_default_config_path() -> str:
    return get_settings().config_path


def make_project_id(provider_name: str, project_name: str) -> str:
    return hashlib.md5(f"{provider_name}:{project_name}".encode()).hexdigest()


def make_subscription_id(name: str) -> str:
    return hashlib.md5(f"subscription:{name}".encode()).hexdigest()


def get_refresh_interval() -> int:
    """刷新间隔：环境变量 BALANCE_REFRESH_INTERVAL_SECONDS，未设置或非正数时用默认值。"""
    interval = get_settings().balance_refresh_interval_seconds
    if interval is None or interval <= 0:
        return DEFAULT_REFRESH_INTERVAL_SECONDS
    return interval


# 全局配置缓存和锁
_config_cache: Dict[str, Dict[str, Any]] = {}
_config_lock = Lock()


def clear_config_cache(config_file: Optional[str] = None) -> None:
    """清除配置缓存"""
    with _config_lock:
        if config_file:
            _config_cache.pop(config_file, None)
        else:
            _config_cache.clear()
        logger.debug("[Config] 配置缓存已清除")


def _ensure_base_shape(config: Dict[str, Any]) -> Dict[str, Any]:
    config.setdefault('projects', [])
    config.setdefault('subscriptions', [])
    config.setdefault('email', [])
    return config


def _substitute_env_placeholders(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _substitute_env_placeholders(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_substitute_env_placeholders(v) for v in value]
    if isinstance(value, str):
        pattern = r'\$\{([^}]+)\}'

        def replace_env(match):
            var_name = match.group(1)
            return os.environ.get(var_name, match.group(0))

        return re.sub(pattern, replace_env, value)
    return value


def load_config_with_env_vars(config_file: str = 'config.json') -> Dict[str, Any]:
    """加载配置文件并替换环境变量占位符

    Raises:
        ValueError: 配置文件不是合法 JSON 时
    """
    # 首先加载 .env 文件（只在首次调用时加载）
    if not getattr(load_config_with_env_vars, '_env_loaded', False):
        load_env_file()
        load_config_with_env_vars._env_loaded = True

    config: Dict[str, Any] = {}

    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config = _substitute_env_placeholders(json.load(f))
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件格式错误: {e}")
    else:
        logger.warning(f"[Config] 配置文件不存在: {config_file}，仅使用数据库与默认值")

    config = _ensure_base_shape(config)

    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(f"配置加载完成: {json.dumps(mask_sensitive_data(config), ensure_ascii=False)}")

    return config


def get_config(config_file: str = 'config.json', use_cache: bool = True) -> Dict[str, Any]:
    """获取文件配置（含环境变量覆盖），带缓存"""
    if use_cache:
        with _config_lock:
            cached = _config_cache.get(config_file)
            if cached is not None:
                return cached

    config = load_config_with_env_vars(config_file)
    with _config_lock:
        _config_cache[config_file] = config

    return config


def _strip_meta_fields(items):
    return [{k: v for k, v in item.items() if k not in _DB_META_FIELDS} for item in items]


def load_config(config_file: Optional[str] = None, use_cache: bool = True) -> Dict[str, Any]:
    """加载最终配置：文件配置（含 env 覆盖）+ 数据库动态配置。

    返回独立副本，调用方可安全修改。
    """
    config_file = config_file or get_default_config_path()
    config = copy.deepcopy(get_config(config_file, use_cache=use_cache))

    if not get_settings().enable_dynamic_config:
        return config

    try:
        from database.repository import ConfigRepository
        db_projects = ConfigRepository.get_all_projects()
        db_subscriptions = ConfigRepository.get_all_subscriptions()
        db_emails = ConfigRepository.get_all_emails()
    except Exception as e:
        logger.warning(f"[Config] 读取数据库动态配置失败，回退到文件配置: {e}")
        return config

    if db_projects:
        config['projects'] = _strip_meta_fields(db_projects)
    if db_subscriptions:
        config['subscriptions'] = _strip_meta_fields(db_subscriptions)
    if db_emails:
        config['email'] = _strip_meta_fields(db_emails)

    return config


def mask_sensitive_data(config: Dict[str, Any]) -> Dict[str, Any]:
    """脱敏处理，用于日志输出"""
    masked = copy.deepcopy(config)

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
