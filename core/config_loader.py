#!/usr/bin/env python3
"""
配置加载

只有两个来源，一个值只有一个家：

- 环境变量（core.settings 与本模块）：密钥、连接、开关、调度参数，以及由
  ``{PROVIDER}_API_KEY`` / ``EMAIL_HOST`` 自动发现出来的项目与邮箱
- 数据库动态配置：projects / subscriptions / email 三段业务清单，可在页面上增删改，
  需要 ENABLE_DATABASE + ENABLE_DYNAMIC_CONFIG

数据库里某一段有数据就用数据库的；环境变量发现的项目与邮箱追加在后面，
已经声明过的不会重复添加。没有配置文件这一层。
"""
import hashlib
import os
import re
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from core.logger import get_logger
from core.settings import get_settings

logger = get_logger('config_loader')

DEFAULT_REFRESH_INTERVAL_SECONDS = 3600

_DB_META_FIELDS = {'id', 'created_at', 'updated_at'}

# 自动发现时一个 provider / 一组邮箱变量最多认几个账号（后缀 _1 … _N）
MAX_ENV_ACCOUNTS = 10


def load_env_file(env_file: str = '.env') -> None:
    """把 .env 写进环境变量"""
    if os.path.exists(env_file):
        load_dotenv(env_file, override=True)
        logger.info(f"[Config] 已加载环境变量文件: {env_file}")


# 进程启动时加载一次，之后所有配置都直接读 os.environ
load_env_file()


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


# ============ 字段补齐 ============
# 目标：只写必要字段，其余按约定推导；数据库与环境变量两条来路统一在此处理。

# provider 的默认余额类型（仅影响展示与告警文案）
PROVIDER_DEFAULT_TYPE = {
    'openrouter': 'credits',
    'uniapi': 'credits',
    'wxrank': 'credits',
    'tikhub': 'balance',
    'volc': 'balance',
    'aliyun': 'balance',
    'deepseek': 'balance',
    'glm': 'quota',  # Coding Plan 剩余配额百分比
}


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
    if api_key:
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


def to_float(value: Any, default: float = 0.0) -> float:
    """把配置里的数字字段转成 float；空值或非数字用默认值。"""
    if value is None or value == '':
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_projects(projects: list) -> list:
    """补齐项目的省略字段：provider 小写、name/type 默认值、阈值转数字、api_key 按约定推导。"""
    ordinals: Dict[str, int] = {}
    for project in projects:
        if not isinstance(project, dict):
            continue
        provider = str(project.get('provider') or '').strip().lower()
        project['provider'] = provider
        if not project.get('name'):
            project['name'] = provider or 'unknown'
        if not project.get('type'):
            project['type'] = PROVIDER_DEFAULT_TYPE.get(provider, 'balance')
        # 没写阈值就是 0：永远不告警，自检会提示补上
        project['threshold'] = to_float(project.get('threshold'))

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


# ============ 环境变量自动发现 ============

def _env_float(*names: str) -> Optional[float]:
    """按顺序取第一个能解析成数字的环境变量"""
    for name in names:
        value = os.environ.get(name)
        if value:
            try:
                return float(value)
            except ValueError:
                logger.warning(f"[Config] {name}={value!r} 不是数字，已忽略")
    return None


def _env_bool(name: str) -> Optional[bool]:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return value.strip().lower() in ('1', 'true', 'yes', 'on')


def _env_variants(prefix: str, suffix: str, ordinal: int) -> List[str]:
    """序号 1 同时接受 ``PREFIX_SUFFIX`` 与 ``PREFIX_1_SUFFIX``，避免同一账号被认成两个"""
    if ordinal <= 1:
        return [f'{prefix}_{suffix}', f'{prefix}_1_{suffix}']
    return [f'{prefix}_{ordinal}_{suffix}']


def _env_first(prefix: str, suffix: str, ordinal: int) -> Optional[str]:
    return next((os.environ[n] for n in _env_variants(prefix, suffix, ordinal) if os.environ.get(n)), None)


def discover_env_projects(declared: list) -> list:
    """没在清单里声明过的 provider，只要设了 ``{PROVIDER}_API_KEY`` 就自动纳入监控。

    阈值取 ``{PROVIDER}_THRESHOLD``（多账号时也接受 ``{PROVIDER}_{序号}_THRESHOLD``），
    不填就不会告警，自检会提示。
    """
    from providers import PROVIDERS

    declared_providers = {
        str(p.get('provider') or '').strip().lower() for p in declared if isinstance(p, dict)
    }
    discovered = []
    for provider in sorted(PROVIDERS):
        if provider in declared_providers:
            continue
        upper = provider.upper()
        accounts = [
            (ordinal, key) for ordinal in range(1, MAX_ENV_ACCOUNTS + 1)
            for key in [_env_first(upper, 'API_KEY', ordinal)] if key
        ]
        for ordinal, api_key in accounts:
            suffix = f'-{ordinal}' if len(accounts) > 1 else ''
            numbered = f'{upper}_{ordinal}'
            discovered.append({
                'name': f'{provider}{suffix}',
                'provider': provider,
                'api_key': api_key,
                'threshold': _env_float(f'{numbered}_THRESHOLD', f'{upper}_THRESHOLD'),
                'owner_project': os.environ.get(f'{numbered}_OWNER_PROJECT') or os.environ.get(f'{upper}_OWNER_PROJECT'),
                'from_env': True,
            })
    if discovered:
        logger.info(f"[Config] 从环境变量发现 {len(discovered)} 个项目: " + ', '.join(p['name'] for p in discovered))
    return discovered


def discover_env_mailboxes(declared: list) -> list:
    """设了 ``EMAIL_HOST`` / ``EMAIL_USERNAME`` / ``EMAIL_PASSWORD`` 就自动纳入扫描。

    多个邮箱用 ``EMAIL_1_HOST`` / ``EMAIL_2_HOST``，名称取 ``EMAIL_{序号}_NAME``，缺省用账号。
    """
    # 名称和账号都算数：数据库里改过显示名的邮箱不该被再扫一遍
    declared_names = {str(m.get(k) or '') for m in declared if isinstance(m, dict) for k in ('name', 'username')}
    discovered = []
    for ordinal in range(1, MAX_ENV_ACCOUNTS + 1):
        host = _env_first('EMAIL', 'HOST', ordinal)
        username = _env_first('EMAIL', 'USERNAME', ordinal)
        password = _env_first('EMAIL', 'PASSWORD', ordinal)
        if not (host and username and password):
            continue
        name = _env_first('EMAIL', 'NAME', ordinal) or username
        if name in declared_names or username in declared_names:
            continue
        port = _env_float(*_env_variants('EMAIL', 'PORT', ordinal))
        use_ssl = next(
            (v for v in (_env_bool(n) for n in _env_variants('EMAIL', 'USE_SSL', ordinal)) if v is not None), None
        )
        discovered.append({
            'name': name,
            'host': host,
            'port': int(port) if port else 993,
            'username': username,
            'password': password,
            'use_ssl': True if use_ssl is None else use_ssl,
            'from_env': True,
        })
    if discovered:
        logger.info(f"[Config] 从环境变量发现 {len(discovered)} 个邮箱: " + ', '.join(m['name'] for m in discovered))
    return discovered


# ============ 最终配置 ============

def _db_sections() -> Dict[str, list]:
    """数据库里的三段业务清单；未启用动态配置或读取失败时返回空"""
    if not get_settings().enable_dynamic_config:
        return {}
    try:
        from database.repository import ConfigRepository
        return {section: ConfigRepository.get_all(section) for section in ConfigRepository.SECTIONS}
    except Exception as e:
        logger.warning(f"[Config] 读取数据库动态配置失败，仅使用环境变量: {e}")
        return {}


def _strip_meta_fields(items: list) -> list:
    return [{k: v for k, v in item.items() if k not in _DB_META_FIELDS} for item in items]


def load_config() -> Dict[str, Any]:
    """数据库动态配置 + 环境变量自动发现，返回补齐字段后的三段业务清单。

    每次返回新字典，调用方可安全修改。
    """
    db = _db_sections()
    config = {
        'projects': _strip_meta_fields(db.get('projects') or []),
        'subscriptions': _strip_meta_fields(db.get('subscriptions') or []),
        'email': _strip_meta_fields(db.get('email') or []),
    }
    config['projects'] += discover_env_projects(config['projects'])
    config['email'] += discover_env_mailboxes(config['email'])
    return normalize_config(config)
