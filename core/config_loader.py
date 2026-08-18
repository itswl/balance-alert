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


# ============ 配置规范化 ============
# 目标：config.json 只写必要字段，其余按约定推导，文件/数据库/API 三条来路统一在此处理。

# provider 的默认余额类型（仅影响展示与告警文案）
_PROVIDER_DEFAULT_TYPE = {
    'openrouter': 'credits',
    'uniapi': 'credits',
    'wxrank': 'credits',
    'tikhub': 'balance',
    'volc': 'balance',
    'aliyun': 'balance',
}

_PLACEHOLDER_PATTERN = re.compile(r'\$\{[^}]+\}')


def is_unresolved_placeholder(value: Any) -> bool:
    """``${VAR}`` 没被环境变量替换时视为未配置，避免把字面量当密钥发出去。"""
    return isinstance(value, str) and bool(_PLACEHOLDER_PATTERN.search(value))


def provider_key_env_names(provider: str, ordinal: int = 1) -> list:
    """项目省略 api_key 时，按约定推导候选环境变量名。

    单实例：``OPENROUTER_API_KEY``（也接受 ``OPENROUTER_1_API_KEY``）
    同一 provider 的第 n 个项目：``VOLC_2_API_KEY``
    """
    upper = (provider or '').upper()
    if not upper:
        return []
    if ordinal <= 1:
        return [f'{upper}_API_KEY', f'{upper}_1_API_KEY']
    return [f'{upper}_{ordinal}_API_KEY']


def resolve_api_key(project: Dict[str, Any], provider: str, ordinal: int) -> tuple:
    """返回 (api_key, 来源说明)。显式 api_key 优先，其次按环境变量约定推导。"""
    api_key = project.get('api_key')
    if api_key and not is_unresolved_placeholder(api_key):
        return str(api_key), 'api_key 字段'

    for name in provider_key_env_names(provider, ordinal):
        value = os.environ.get(name)
        if value:
            return value, f'环境变量 {name}'

    return '', None


def split_mmdd(renewal_day: Any) -> Optional[tuple]:
    """把年付的 MMDD 整数（如 315）拆成 (月, 日)；不是合法 MMDD 时返回 None。

    小于等于 31 的值属于旧配置的"只写了日"，不是 MMDD，同样返回 None。
    """
    try:
        value = int(renewal_day)
    except (TypeError, ValueError):
        return None
    if value <= 31:
        return None
    month, day = value // 100, value % 100
    if 1 <= month <= 12 and 1 <= day <= 31:
        return month, day
    return None


def coerce_renewal_day(value: Any, cycle_type: str) -> Any:
    """续费日归一化。

    年付支持直观的 ``"03-15"`` / ``"3-15"`` 写法，内部统一存 MMDD 整数（315）；
    周付/月付接受数字或数字字符串。无法解析时原样返回，交由下游兜底。
    """
    if isinstance(value, str):
        text = value.strip()
        matched = re.fullmatch(r'(\d{1,2})\s*[-/月]\s*(\d{1,2})\s*日?', text)
        if matched:
            month, day = int(matched.group(1)), int(matched.group(2))
            return month * 100 + day if cycle_type == 'yearly' else day
        if text.isdigit():
            return int(text)
    return value


def normalize_projects(projects: list) -> list:
    """补齐项目的省略字段：provider 小写、name/type 默认值、api_key 按约定推导。"""
    ordinals: Dict[str, int] = {}
    for project in projects:
        if not isinstance(project, dict):
            continue
        provider = str(project.get('provider') or '').strip().lower()
        project['provider'] = provider
        if not project.get('name'):
            project['name'] = provider or 'unknown'
        if not project.get('type'):
            project['type'] = _PROVIDER_DEFAULT_TYPE.get(provider, 'balance')

        ordinals[provider] = ordinals.get(provider, 0) + 1
        project['api_key'] = resolve_api_key(project, provider, ordinals[provider])[0]
    return projects


def normalize_subscriptions(subscriptions: list) -> list:
    """补齐订阅的省略字段：周期默认按月，续费日支持 MM-DD 写法。"""
    for sub in subscriptions:
        if not isinstance(sub, dict):
            continue
        cycle_type = str(sub.get('cycle_type') or 'monthly').strip().lower()
        sub['cycle_type'] = cycle_type
        if sub.get('renewal_day') is not None:
            sub['renewal_day'] = coerce_renewal_day(sub['renewal_day'], cycle_type)
    return subscriptions


def normalize_emails(emails: list) -> list:
    """补齐邮箱的省略字段：端口与 SSL 用 IMAP 常规默认，name 缺省取账号。"""
    for email_config in emails:
        if not isinstance(email_config, dict):
            continue
        if not email_config.get('port'):
            email_config['port'] = 993
        if email_config.get('use_ssl') is None:
            email_config['use_ssl'] = True
        if not email_config.get('name'):
            email_config['name'] = email_config.get('username') or 'mailbox'
        if is_unresolved_placeholder(email_config.get('password')):
            email_config['password'] = ''
    return emails


def owner_project_of(item: Dict[str, Any]) -> Optional[str]:
    """归属项目，兼容早期配置里写作 project 的情况"""
    return item.get('owner_project') or item.get('project')


def filter_enabled(items: list) -> list:
    """只保留启用的条目（缺省视为启用）"""
    return [item for item in items if item.get('enabled', True)]


def normalize_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """对三类业务清单统一做规范化，使下游只面对补齐后的完整字段。"""
    normalize_projects(config.get('projects') or [])
    normalize_subscriptions(config.get('subscriptions') or [])
    normalize_emails(config.get('email') or [])
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
        return normalize_config(config)

    try:
        from database.repository import ConfigRepository
        db_projects = ConfigRepository.get_all_projects()
        db_subscriptions = ConfigRepository.get_all_subscriptions()
        db_emails = ConfigRepository.get_all_emails()
    except Exception as e:
        logger.warning(f"[Config] 读取数据库动态配置失败，回退到文件配置: {e}")
        return normalize_config(config)

    if db_projects:
        config['projects'] = _strip_meta_fields(db_projects)
    if db_subscriptions:
        config['subscriptions'] = _strip_meta_fields(db_subscriptions)
    if db_emails:
        config['email'] = _strip_meta_fields(db_emails)

    return normalize_config(config)


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
