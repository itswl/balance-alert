#!/usr/bin/env python3
"""
配置加载模块
支持从环境变量读取敏感配置，优先于配置文件
支持配置文件变化监听和自动重载
"""
import os
import json
import re
import hashlib
from typing import Dict, Any, Optional, Callable, List
from pathlib import Path
from threading import Lock, Thread
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv
from config_validator import AppConfig
from logger import get_logger

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


def get_api_key_from_env(project_name: str) -> Optional[str]:
    """从环境变量获取 API Key"""
    # 尝试特定项目的环境变量
    specific_key = f'{project_name.upper().replace(" ", "_").replace("-", "_")}_API_KEY'
    api_key = get_env(specific_key)
    if api_key:
        return api_key

    # 尝试通用环境变量
    return get_env('API_KEY')


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
            'cycle_type': get_env(f'{prefix}CYCLE_TYPE', 'monthly'),
            'renewal_day': int(get_env(f'{prefix}RENEWAL_DAY', '1')),
            'alert_days_before': int(get_env(f'{prefix}ALERT_DAYS_BEFORE', '3')),
            'amount': float(get_env(f'{prefix}AMOUNT', '0')),
            'currency': get_env(f'{prefix}CURRENCY', 'CNY'),
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
_config_observer: Optional[Observer] = None
_config_callback: Optional[Callable] = None
_config_listeners: List[Callable[[Dict[str, Any]], None]] = []
_last_config_hash: Optional[str] = None


def register_config_listener(listener: Callable[[Dict[str, Any]], None]) -> None:
    """注册配置变更监听器"""
    global _config_listeners
    with _config_lock:
        if listener not in _config_listeners:
            _config_listeners.append(listener)
            logger.debug(f"[Config] 已注册配置监听器: {listener.__name__}")


def unregister_config_listener(listener: Callable[[Dict[str, Any]], None]) -> None:
    """注销配置变更监听器"""
    global _config_listeners
    with _config_lock:
        if listener in _config_listeners:
            _config_listeners.remove(listener)
            logger.debug(f"[Config] 已注销配置监听器: {listener.__name__}")


def _notify_config_listeners(config: Dict[str, Any]) -> None:
    """通知所有配置监听器（仅在配置实际变化时）"""
    global _last_config_hash
    config_str = json.dumps(config, sort_keys=True, ensure_ascii=False)
    config_hash = hashlib.md5(config_str.encode()).hexdigest()

    if config_hash == _last_config_hash:
        logger.debug("[Config] 配置未变化，跳过通知监听器")
        return

    _last_config_hash = config_hash
    listeners_copy = _config_listeners[:]  # 复制列表避免在迭代时修改
    for listener in listeners_copy:
        try:
            listener(config)
        except Exception as e:
            logger.error(f"[Config] 监听器 {listener.__name__} 执行失败: {e}")


class ConfigFileHandler(FileSystemEventHandler):
    """配置文件变化处理器"""
    
    def __init__(self, config_file: str, callback):
        self.config_file = Path(config_file).resolve()
        self.callback = callback
    
    def on_modified(self, event):
        """文件修改事件"""
        if event.is_directory:
            return

        event_path = Path(event.src_path).resolve()
        if event_path == self.config_file:
            logger.info(f"[Config] 检测到配置文件变化: {event_path}")
            self.callback()

    def on_created(self, event):
        """文件创建事件"""
        if event.is_directory:
            return

        event_path = Path(event.src_path).resolve()
        if event_path == self.config_file:
            logger.info(f"[Config] 检测到配置文件创建: {event_path}")
            self.callback()


def start_config_watcher(config_file: str = 'config.json', callback: Optional[Callable] = None) -> None:
    """启动配置文件监听器"""
    global _config_observer, _config_callback
    
    if _config_observer is not None:
        # 如果已经在运行，先停止
        stop_config_watcher()
    
    _config_callback = callback or clear_config_cache
    
    # 创建观察者
    _config_observer = Observer()
    handler = ConfigFileHandler(config_file, _config_callback)
    
    # 监听配置文件所在目录
    config_path = Path(config_file)
    watch_path = config_path.parent.resolve()
    
    _config_observer.schedule(handler, str(watch_path), recursive=False)
    _config_observer.start()

    logger.info(f"[Config] 开始监听配置文件: {config_path}")


def stop_config_watcher() -> None:
    """停止配置文件监听器"""
    global _config_observer

    if _config_observer is not None:
        _config_observer.stop()
        _config_observer.join()
        _config_observer = None
        logger.info("[Config] 已停止配置文件监听")


def clear_config_cache() -> None:
    """清除配置缓存"""
    global _config_cache, _last_config_hash
    with _config_lock:
        _config_cache = None
        _last_config_hash = None
        logger.debug("[Config] 配置缓存已清除")


def load_config_with_env_vars(config_file: str = 'config.json', validate: bool = True) -> Dict[str, Any]:
    """加载配置文件并替换环境变量占位符

    支持三种模式：
    1. 完全从环境变量加载（如果设置了 USE_ENV_CONFIG=true）
    2. 从配置文件加载，但使用环境变量覆盖敏感信息
    3. 支持 ${VAR_NAME} 格式的环境变量替换

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

    # 模式 1: 完全从环境变量加载（如果设置了 USE_ENV_CONFIG=true）
    use_env_config = get_env('USE_ENV_CONFIG', 'false').lower() == 'true'

    if use_env_config:
        logger.info("[Config] 使用完全环境变量配置模式")
        config = {
            'settings': {
                'balance_refresh_interval_seconds': int(get_env('BALANCE_REFRESH_INTERVAL_SECONDS', '3600')),
                'max_concurrent_checks': int(get_env('MAX_CONCURRENT_CHECKS', '5')),
                'min_refresh_interval_seconds': int(get_env('MIN_REFRESH_INTERVAL_SECONDS', '60')),
                'enable_smart_refresh': get_env('ENABLE_SMART_REFRESH', 'false').lower() == 'true',
                'smart_refresh_threshold_percent': int(get_env('SMART_REFRESH_THRESHOLD_PERCENT', '5')),
            },
            'webhook': {
                'url': get_env('WEBHOOK_URL', ''),
                'source': get_env('WEBHOOK_SOURCE', 'credit-monitor'),
                'type': get_env('WEBHOOK_TYPE', 'feishu'),
            },
            'email': load_emails_from_env(),
            'projects': load_projects_from_env(),
            'subscriptions': load_subscriptions_from_env(),
        }
    elif not os.path.exists(config_file):
        # 如果配置文件不存在，尝试从环境变量加载
        logger.warning(f"[Config] 配置文件不存在: {config_file}，尝试从环境变量加载")
        config = {
            'settings': {
                'balance_refresh_interval_seconds': int(get_env('BALANCE_REFRESH_INTERVAL_SECONDS', '3600')),
                'max_concurrent_checks': int(get_env('MAX_CONCURRENT_CHECKS', '5')),
                'min_refresh_interval_seconds': int(get_env('MIN_REFRESH_INTERVAL_SECONDS', '60')),
                'enable_smart_refresh': get_env('ENABLE_SMART_REFRESH', 'false').lower() == 'true',
                'smart_refresh_threshold_percent': int(get_env('SMART_REFRESH_THRESHOLD_PERCENT', '5')),
            },
            'webhook': {
                'url': get_env('WEBHOOK_URL', ''),
                'source': get_env('WEBHOOK_SOURCE', 'credit-monitor'),
                'type': get_env('WEBHOOK_TYPE', 'feishu'),
            },
            'email': load_emails_from_env(),
            'projects': load_projects_from_env(),
            'subscriptions': load_subscriptions_from_env(),
        }
    else:
        # 模式 2: 从配置文件加载，但使用环境变量覆盖
        # 读取配置文件内容
        with open(config_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 替换 ${VAR_NAME} 格式的环境变量
        pattern = r'\$\{([^}]+)\}'

        def replace_env(match):
            var_name = match.group(1)
            # 从环境变量读取，如果不存在则保持原样
            return os.environ.get(var_name, match.group(0))

        content = re.sub(pattern, replace_env, content)

        # 解析JSON
        config = json.loads(content)

        # 环境变量覆盖 webhook 配置
        webhook_url = get_env('WEBHOOK_URL')
        if webhook_url:
            if 'webhook' not in config:
                config['webhook'] = {}
            config['webhook']['url'] = webhook_url
            config['webhook']['source'] = get_env('WEBHOOK_SOURCE', config['webhook'].get('source', 'credit-monitor'))
            config['webhook']['type'] = get_env('WEBHOOK_TYPE', config['webhook'].get('type', 'feishu'))

        # 环境变量覆盖邮箱配置（支持两种方式）
        # 方式 1: 从环境变量完全加载邮箱（如果存在 EMAIL_1_USERNAME）
        env_emails = load_emails_from_env()
        if env_emails:
            config['email'] = env_emails
        # 方式 2: 覆盖配置文件中的邮箱密码
        elif 'email' in config:
            for email in config['email']:
                email_name = email.get('name', '')
                env_password = get_email_password_from_env(email_name)
                if env_password:
                    email['password'] = env_password

        # 环境变量覆盖项目配置（支持两种方式）
        # 方式 1: 从环境变量完全加载项目（如果存在 PROJECT_1_NAME）
        env_projects = load_projects_from_env()
        if env_projects:
            config['projects'] = env_projects
        # 方式 2: 覆盖配置文件中的 API Key
        elif 'projects' in config:
            for project in config['projects']:
                project_name = project.get('name', '')
                env_api_key = get_api_key_from_env(project_name)
                if env_api_key:
                    project['api_key'] = env_api_key

        # 环境变量覆盖订阅配置
        env_subscriptions = load_subscriptions_from_env()
        if env_subscriptions:
            config['subscriptions'] = env_subscriptions

        # 环境变量覆盖系统设置
        if 'settings' not in config:
            config['settings'] = {}

        refresh_interval = get_env('BALANCE_REFRESH_INTERVAL_SECONDS')
        if refresh_interval:
            try:
                config['settings']['balance_refresh_interval_seconds'] = int(refresh_interval)
            except (ValueError, TypeError):
                logger.warning(f"BALANCE_REFRESH_INTERVAL_SECONDS 值无效: {refresh_interval}，忽略")

        max_concurrent = get_env('MAX_CONCURRENT_CHECKS')
        if max_concurrent:
            try:
                config['settings']['max_concurrent_checks'] = int(max_concurrent)
            except (ValueError, TypeError):
                logger.warning(f"MAX_CONCURRENT_CHECKS 值无效: {max_concurrent}，忽略")

    # 打印配置版本号
    config_version = config.get('version')
    if config_version:
        logger.info(f"[Config] 配置版本: {config_version}")

    # 验证配置
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

    # 通知配置监听器
    _notify_config_listeners(config)

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
