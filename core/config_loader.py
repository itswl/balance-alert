#!/usr/bin/env python3
"""
配置加载模块
支持从环境变量读取敏感配置，优先于配置文件
"""
import os
import json
import re
from typing import Dict, Any, Optional
from threading import Lock
from dotenv import load_dotenv
from core.config_validator import AppConfig
from core.logger import get_logger

logger = get_logger('config_loader')

def load_env_file(env_file: str = '.env') -> None:
    """加载 .env 文件"""
    if os.path.exists(env_file):
        load_dotenv(env_file, override=True)
        logger.info(f"[Config] 已加载环境变量文件: {env_file}")


def get_env(key: str, default=None) -> Optional[str]:
    """获取环境变量"""
    return os.environ.get(key, default)


# 全局配置缓存和锁
_config_cache: Optional[Dict[str, Any]] = None
_config_lock = Lock()


def clear_config_cache() -> None:
    """清除配置缓存"""
    global _config_cache
    with _config_lock:
        _config_cache = None
        logger.debug("[Config] 配置缓存已清除")


def _ensure_base_shape(config: Dict[str, Any]) -> Dict[str, Any]:
    if config.get('settings') is None:
        config['settings'] = {}
    config.setdefault('settings', {})
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


def _load_json_with_env_substitution(config_file: str) -> Dict[str, Any]:
    with open(config_file, 'r', encoding='utf-8') as f:
        content = f.read()

    return _substitute_env_placeholders(json.loads(content))


def _overlay_settings_from_env(settings: Dict[str, Any]) -> Dict[str, Any]:
    refresh_interval = get_env('BALANCE_REFRESH_INTERVAL_SECONDS')
    if refresh_interval:
        try:
            settings['balance_refresh_interval_seconds'] = int(refresh_interval)
        except (ValueError, TypeError):
            logger.warning(f"BALANCE_REFRESH_INTERVAL_SECONDS 值无效: {refresh_interval}，忽略")

    max_concurrent = get_env('MAX_CONCURRENT_CHECKS')
    if max_concurrent:
        try:
            settings['max_concurrent_checks'] = int(max_concurrent)
        except (ValueError, TypeError):
            logger.warning(f"MAX_CONCURRENT_CHECKS 值无效: {max_concurrent}，忽略")

    min_refresh = get_env('MIN_REFRESH_INTERVAL_SECONDS')
    if min_refresh:
        try:
            settings['min_refresh_interval_seconds'] = int(min_refresh)
        except (ValueError, TypeError):
            logger.warning(f"MIN_REFRESH_INTERVAL_SECONDS 值无效: {min_refresh}，忽略")

    enable_smart = get_env('ENABLE_SMART_REFRESH')
    if enable_smart is not None:
        settings['enable_smart_refresh'] = str(enable_smart).lower() == 'true'

    smart_threshold = get_env('SMART_REFRESH_THRESHOLD_PERCENT')
    if smart_threshold:
        try:
            settings['smart_refresh_threshold_percent'] = int(float(smart_threshold))
        except (ValueError, TypeError):
            logger.warning(f"SMART_REFRESH_THRESHOLD_PERCENT 值无效: {smart_threshold}，忽略")

    return settings


def _load_dynamic_from_db(config: Dict[str, Any]) -> Dict[str, Any]:
    try:
        from database.repository import ConfigRepository

        db_projects = ConfigRepository.get_all_projects()
        db_subscriptions = ConfigRepository.get_all_subscriptions()
        db_emails = ConfigRepository.get_all_emails()

        if db_projects:
            config['projects'] = [
                {k: v for k, v in p.items() if k not in ['id', 'created_at', 'updated_at']}
                for p in db_projects
            ]
        if db_subscriptions:
            config['subscriptions'] = [
                {k: v for k, v in s.items() if k not in ['id', 'created_at', 'updated_at']}
                for s in db_subscriptions
            ]
        if db_emails:
            config['email'] = [
                {k: v for k, v in e.items() if k not in ['id', 'created_at', 'updated_at']}
                for e in db_emails
            ]
    except Exception as e:
        logger.warning(f"从数据库读取配置失败: {e}")

    return config


def load_config_with_env_vars(config_file: str = 'config.json', validate: bool = True) -> Dict[str, Any]:
    """加载配置文件并替换环境变量占位符

    Args:
        config_file: 配置文件路径
        validate: 是否验证配置（默认 True）

    Returns:
        Dict[str, Any]: 配置字典

    Raises:
        ValueError: 当配置验证失败时
    """
    # 首先加载 .env 文件（只在首次调用时加载）
    if not getattr(load_config_with_env_vars, '_env_loaded', False):
        load_env_file()
        load_config_with_env_vars._env_loaded = True

    config: Dict[str, Any] = {}

    if os.path.exists(config_file):
        try:
            config = _load_json_with_env_substitution(config_file)
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件格式错误: {e}")
    else:
        logger.warning(f"[Config] 配置文件不存在: {config_file}，仅使用数据库与默认值")

    config = _ensure_base_shape(config)
    config['settings'] = _overlay_settings_from_env(config.get('settings', {}) or {})
    config = _load_dynamic_from_db(config)
    config = _substitute_env_placeholders(config)

    # 打印配置版本号
    config_version = config.get('version')
    if config_version:
        logger.info(f"[Config] 配置版本: {config_version}")

    if validate:
        app_config = AppConfig.from_dict(config)
        errors = app_config.validate()
        if errors:
            error_messages = []
            for section, section_errors in errors.items():
                error_messages.append(f"  {section}:")
                for err in section_errors:
                    error_messages.append(f"    - {err}")
            logger.warning(f"配置验证发现以下问题:\n" + "\n".join(error_messages))

    # 调试日志：输出脱敏配置
    logger.debug(f"配置加载完成: {json.dumps(mask_sensitive_data(config), ensure_ascii=False)}")

    return config


def load_config(config_file: str = 'config.json') -> Dict[str, Any]:
    """加载配置，环境变量优先于配置文件（兼容旧接口）"""
    return load_config_with_env_vars(config_file)


def get_config(config_file: str = 'config.json', use_cache: bool = True) -> Dict[str, Any]:
    """获取配置，带缓存和自动重载"""
    global _config_cache
    
    # 如果使用缓存且缓存存在，直接返回
    if use_cache:
        with _config_lock:
            if _config_cache is not None:
                return _config_cache
    
    # 加载新配置
    config = load_config_with_env_vars(config_file)
    
    # 更新缓存
    with _config_lock:
        _config_cache = config
    
    return config


def mask_sensitive_data(config: Dict[str, Any]) -> Dict[str, Any]:
    """脱敏处理，用于日志输出"""
    import copy
    masked = copy.deepcopy(config)
    
    # 脱敏 webhook URL
    webhook = masked.get('webhook')
    if isinstance(webhook, dict) and 'url' in webhook:
        url = webhook.get('url') or ''
        if 'hook/' in url:
            webhook['url'] = url[:url.rfind('hook/') + 5] + '***'
    
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
