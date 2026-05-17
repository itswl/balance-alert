#!/usr/bin/env python3
"""
配置加载模块
支持从环境变量读取敏感配置，优先于配置文件
"""
import os
import json
import re
import hashlib
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path
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


def get_webhook_from_env() -> Optional[Dict[str, Any]]:
    """从环境变量获取 webhook 配置"""
    webhook_url = get_env('WEBHOOK_URL')
    if not webhook_url:
        return None
    
    return {
        'enabled': get_env('WEBHOOK_ENABLED', 'true').lower() == 'true',
        'url': webhook_url,
        'secret': get_env('WEBHOOK_SECRET', ''),
        'platform': get_env('WEBHOOK_PLATFORM', 'feishu')
    }


def get_email_password_from_env(email_name: str) -> Optional[str]:
    """从环境变量获取邮箱密码"""
    # 尝试特定邮箱的环境变量
    specific_key = f'EMAIL_{email_name.upper().replace(" ", "_").replace("-", "_")}_PASSWORD'
    password = get_env(specific_key)
    if password:
        return password

    # 尝试通用环境变量
    return get_env('EMAIL_PASSWORD')


def _env_token(value: str) -> str:
    """将项目名转换为环境变量安全片段。"""
    return re.sub(r'[^A-Z0-9]+', '_', value.upper()).strip('_')


def get_api_key_from_env(project_name: str) -> Optional[str]:
    """从环境变量获取 API Key"""
    project_token = _env_token(project_name)
    candidates = [
        f'{project_token}_API_KEY',
        f'API_KEY_{project_token}',
    ]

    for key in candidates:
        api_key = get_env(key)
        if api_key:
            return api_key

    # 项目密钥的通用 fallback 使用 PROJECT_API_KEY，避免与 Web 认证 API_KEY 混用。
    generic_key = get_env('PROJECT_API_KEY') or get_env('DEFAULT_PROJECT_API_KEY')
    if generic_key:
        return generic_key

    # 兼容旧部署：显式打开后才允许 API_KEY 作为项目通用密钥。
    if get_env('ALLOW_LEGACY_PROJECT_API_KEY', 'false').lower() == 'true':
        return get_env('API_KEY')

    return None


def load_emails_from_env() -> List[Dict[str, Any]]:
    """从环境变量加载邮箱配置（支持 EMAIL_1_*, EMAIL_2_* 格式）"""
    emails = []
    idx = 1

    while True:
        prefix = f'EMAIL_{idx}_'
        username = get_env(f'{prefix}USERNAME')

        # 如果没有找到 username，说明没有更多邮箱配置
        if not username:
            break

        email_config = {
            'name': get_env(f'{prefix}NAME', f'Email {idx}'),
            'host': get_env(f'{prefix}HOST', 'imap.gmail.com'),
            'port': int(get_env(f'{prefix}PORT', '993')),
            'username': username,
            'password': get_env(f'{prefix}PASSWORD', ''),
            'use_ssl': get_env(f'{prefix}USE_SSL', 'true').lower() == 'true',
            'enabled': get_env(f'{prefix}ENABLED', 'true').lower() == 'true',
        }

        emails.append(email_config)
        idx += 1

    return emails


def load_projects_from_env() -> List[Dict[str, Any]]:
    """从环境变量加载项目配置（支持 PROJECT_1_*, PROJECT_2_* 格式）"""
    projects = []
    idx = 1

    while True:
        prefix = f'PROJECT_{idx}_'
        name = get_env(f'{prefix}NAME')

        # 如果没有找到 name，说明没有更多项目配置
        if not name:
            break

        project_config = {
            'name': name,
            'owner_project': get_env(f'{prefix}OWNER_PROJECT') or get_env(f'{prefix}PROJECT') or None,
            'provider': get_env(f'{prefix}PROVIDER', 'openrouter'),
            'api_key': get_env(f'{prefix}API_KEY', ''),
            'threshold': float(get_env(f'{prefix}THRESHOLD', '100.0')),
            'type': get_env(f'{prefix}TYPE', 'credits'),
            'enabled': get_env(f'{prefix}ENABLED', 'true').lower() == 'true',
        }

        projects.append(project_config)
        idx += 1

    return projects


def load_subscriptions_from_env() -> List[Dict[str, Any]]:
    """从环境变量加载订阅配置（支持 SUBSCRIPTION_1_*, SUBSCRIPTION_2_* 格式）"""
    subscriptions = []
    idx = 1

    while True:
        prefix = f'SUBSCRIPTION_{idx}_'
        name = get_env(f'{prefix}NAME')

        # 如果没有找到 name，说明没有更多订阅配置
        if not name:
            break

        sub_config = {
            'name': name,
            'owner_project': get_env(f'{prefix}OWNER_PROJECT') or get_env(f'{prefix}PROJECT') or None,
            'cycle_type': get_env(f'{prefix}CYCLE_TYPE', 'monthly'),
            'renewal_day': int(get_env(f'{prefix}RENEWAL_DAY', '1')),
            'alert_days_before': int(get_env(f'{prefix}ALERT_DAYS_BEFORE', '3')),
            'amount': float(get_env(f'{prefix}AMOUNT', '0')),
            'enabled': get_env(f'{prefix}ENABLED', 'true').lower() == 'true',
        }

        # 可选字段
        last_renewed = get_env(f'{prefix}LAST_RENEWED_DATE')
        if last_renewed:
            sub_config['last_renewed_date'] = last_renewed

        subscriptions.append(sub_config)
        idx += 1

    return subscriptions


# 全局配置缓存和锁
_config_cache: Optional[Dict[str, Any]] = None
_config_lock = Lock()
def start_config_watcher(config_file: str = 'config.json', callback: Optional[Callable] = None) -> None:
    if callback:
        logger.warning("[Config] 配置监听已简化，不再支持文件变更回调")
    logger.info(f"[Config] 配置监听已禁用: {Path(config_file)}")


def stop_config_watcher() -> None:
    return None


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


def _load_json_with_env_substitution(config_file: str) -> Dict[str, Any]:
    with open(config_file, 'r', encoding='utf-8') as f:
        content = f.read()

    pattern = r'\$\{([^}]+)\}'

    def replace_env(match):
        var_name = match.group(1)
        return os.environ.get(var_name, match.group(0))

    content = re.sub(pattern, replace_env, content)
    return json.loads(content)


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


def _overlay_webhook_from_env(webhook: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    webhook_url = get_env('WEBHOOK_URL')
    if not webhook_url:
        return webhook

    if webhook is None:
        webhook = {}

    webhook['url'] = webhook_url
    webhook['source'] = get_env('WEBHOOK_SOURCE', webhook.get('source', 'credit-monitor'))
    webhook_type = get_env('WEBHOOK_TYPE') or get_env('WEBHOOK_PLATFORM')
    if webhook_type:
        webhook['type'] = webhook_type
    else:
        webhook['type'] = webhook.get('type', 'feishu')

    return webhook


def _overlay_sensitive_from_env(config: Dict[str, Any]) -> Dict[str, Any]:
    env_emails = load_emails_from_env()
    if env_emails:
        config['email'] = env_emails
    else:
        for email in config.get('email', []) or []:
            email_name = email.get('name', '')
            env_password = get_email_password_from_env(email_name)
            if env_password:
                email['password'] = env_password

    env_projects = load_projects_from_env()
    if env_projects:
        config['projects'] = env_projects
    else:
        for project in config.get('projects', []) or []:
            project_name = project.get('name', '')
            env_api_key = get_api_key_from_env(project_name)
            if env_api_key:
                project['api_key'] = env_api_key

    env_subscriptions = load_subscriptions_from_env()
    if env_subscriptions and not (config.get('subscriptions') or []):
        config['subscriptions'] = env_subscriptions
        logger.info(f"[Config] 从环境变量加载 {len(env_subscriptions)} 个订阅")

    return config


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

    use_env_config = get_env('USE_ENV_CONFIG', 'false').lower() == 'true'
    config: Dict[str, Any] = {}

    if not use_env_config and os.path.exists(config_file):
        try:
            config = _load_json_with_env_substitution(config_file)
        except json.JSONDecodeError as e:
            raise ValueError(f"配置文件格式错误: {e}")
    else:
        if use_env_config:
            logger.info("[Config] USE_ENV_CONFIG=true：忽略配置文件，仅使用环境变量与数据库")
        else:
            logger.warning(f"[Config] 配置文件不存在: {config_file}，仅使用环境变量与数据库")

    config = _ensure_base_shape(config)
    config['settings'] = _overlay_settings_from_env(config.get('settings', {}) or {})
    config['webhook'] = _overlay_webhook_from_env(config.get('webhook'))
    config = _overlay_sensitive_from_env(config)
    config = _load_dynamic_from_db(config)
    config['webhook'] = _overlay_webhook_from_env(config.get('webhook'))
    config = _overlay_sensitive_from_env(config)

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
