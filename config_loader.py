#!/usr/bin/env python3
"""
配置加载模块
支持从环境变量读取敏感配置，优先于配置文件
支持配置文件变化监听和自动重载
"""
import os
import json
import re
from typing import Dict, Any, Optional, Callable
from pathlib import Path
from threading import Lock, Thread
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


# 全局配置缓存和锁
_config_cache: Optional[Dict[str, Any]] = None
_config_lock = Lock()
_config_observer: Optional[Observer] = None
_config_callback: Optional[Callable] = None


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
            print(f"[Config] 检测到配置文件变化: {event_path}")
            self.callback()
    
    def on_created(self, event):
        """文件创建事件"""
        if event.is_directory:
            return
            
        event_path = Path(event.src_path).resolve()
        if event_path == self.config_file:
            print(f"[Config] 检测到配置文件创建: {event_path}")
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
    
    print(f"[Config] 开始监听配置文件: {config_path}")


def stop_config_watcher() -> None:
    """停止配置文件监听器"""
    global _config_observer
    
    if _config_observer is not None:
        _config_observer.stop()
        _config_observer.join()
        _config_observer = None
        print("[Config] 已停止配置文件监听")


def clear_config_cache() -> None:
    """清除配置缓存"""
    global _config_cache
    with _config_lock:
        _config_cache = None
        print("[Config] 配置缓存已清除")


def load_config_with_env_vars(config_file: str = 'config.json') -> Dict[str, Any]:
    """加载配置文件并替换环境变量占位符
    
    支持 ${VAR_NAME} 格式的环境变量替换
    """
    # 首先加载 .env 文件
    load_env_file()
    
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
