#!/usr/bin/env python3
"""
状态管理器
封装全局状态，提供线程安全的访问接口
支持状态持久化和通知机制
"""
import threading
import time
import json
import os
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, asdict
from logger import get_logger

logger = get_logger('state_manager')


@dataclass
class BalanceState:
    """余额状态数据类"""
    last_update: Optional[str] = None
    projects: List[Dict[str, Any]] = None
    summary: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.projects is None:
            self.projects = []
        if self.summary is None:
            self.summary = {}


@dataclass
class SubscriptionState:
    """订阅状态数据类"""
    last_update: Optional[str] = None
    subscriptions: List[Dict[str, Any]] = None
    summary: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.subscriptions is None:
            self.subscriptions = []
        if self.summary is None:
            self.summary = {}


class StateManager:
    """状态管理器类"""
    
    def __init__(self):
        self._balance_state = BalanceState()
        self._subscription_state = SubscriptionState()
        self._lock = threading.RLock()
        self._callbacks = []
        self._cache_file = os.environ.get('CACHE_FILE_PATH', '/tmp/balance_cache.json')
    
    def register_callback(self, callback: Callable[[str, Any], None]):
        """注册状态变更回调函数"""
        with self._lock:
            self._callbacks.append(callback)
    
    def unregister_callback(self, callback: Callable[[str, Any], None]):
        """注销状态变更回调函数"""
        with self._lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)
    
    def _notify_callbacks(self, state_type: str, state_data: Any):
        """通知所有注册的回调函数"""
        for callback in self._callbacks[:]:  # 复制列表避免在迭代时修改
            try:
                callback(state_type, state_data)
            except Exception as e:
                logger.error(f"回调函数执行失败: {e}")
    
    def update_balance_state(self, projects: List[Dict[str, Any]]) -> None:
        """更新余额状态（线程安全）"""
        with self._lock:
            self._balance_state.last_update = time.strftime('%Y-%m-%d %H:%M:%S')
            self._balance_state.projects = projects.copy()
            self._balance_state.summary = {
                'total': len(projects),
                'success': sum(1 for r in projects if r['success']),
                'failed': sum(1 for r in projects if not r['success']),
                'need_alarm': sum(1 for r in projects if r.get('need_alarm', False)),
            }
            
            # 通知回调
            self._notify_callbacks('balance', self._balance_state)
            
            logger.info(f"余额状态已更新: {self._balance_state.summary}")
    
    def update_subscription_state(self, subscriptions: List[Dict[str, Any]]) -> None:
        """更新订阅状态（线程安全）"""
        with self._lock:
            self._subscription_state.last_update = time.strftime('%Y-%m-%d %H:%M:%S')
            self._subscription_state.subscriptions = subscriptions.copy()
            self._subscription_state.summary = {
                'total': len(subscriptions),
                'need_alert': sum(1 for r in subscriptions if r.get('need_alert', False)),
            }
            
            # 通知回调
            self._notify_callbacks('subscription', self._subscription_state)
            
            logger.info(f"订阅状态已更新: {self._subscription_state.summary}")
    
    def get_balance_state(self) -> Dict[str, Any]:
        """获取余额状态（线程安全）"""
        with self._lock:
            return asdict(self._balance_state)
    
    def get_subscription_state(self) -> Dict[str, Any]:
        """获取订阅状态（线程安全）"""
        with self._lock:
            return asdict(self._subscription_state)
    
    def has_data(self) -> bool:
        """检查是否有数据（线程安全）"""
        with self._lock:
            return self._balance_state.last_update is not None
    
    def save_to_cache(self) -> bool:
        """保存状态到缓存文件"""
        try:
            cache_data = {
                'projects': self._balance_state.projects,
                'subscriptions': self._subscription_state.subscriptions,
                'metadata': {
                    'balance_last_update': self._balance_state.last_update,
                    'subscription_last_update': self._subscription_state.last_update,
                    'saved_at': time.strftime('%Y-%m-%d %H:%M:%S')
                }
            }
            
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"状态已保存到缓存文件: {self._cache_file}")
            return True
            
        except (OSError, IOError, json.JSONEncodeError) as e:
            logger.error(f"保存缓存文件失败: {e}")
            return False
    
    def load_from_cache(self) -> bool:
        """从缓存文件加载状态"""
        try:
            if not os.path.exists(self._cache_file):
                logger.info(f"缓存文件不存在: {self._cache_file}")
                return False
            
            with open(self._cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            with self._lock:
                self._balance_state.projects = cache_data.get('projects', [])
                self._subscription_state.subscriptions = cache_data.get('subscriptions', [])
                
                metadata = cache_data.get('metadata', {})
                self._balance_state.last_update = metadata.get('balance_last_update')
                self._subscription_state.last_update = metadata.get('subscription_last_update')
                
                # 重建摘要信息
                self._rebuild_summaries()
            
            logger.info(f"状态已从缓存文件加载: {self._cache_file}")
            return True
            
        except (OSError, IOError, json.JSONDecodeError) as e:
            logger.error(f"加载缓存文件失败: {e}")
            return False
    
    def _rebuild_summaries(self):
        """重建状态摘要信息"""
        # 重建余额摘要
        projects = self._balance_state.projects
        self._balance_state.summary = {
            'total': len(projects),
            'success': sum(1 for r in projects if r['success']),
            'failed': sum(1 for r in projects if not r['success']),
            'need_alarm': sum(1 for r in projects if r.get('need_alarm', False)),
        }
        
        # 重建订阅摘要
        subscriptions = self._subscription_state.subscriptions
        self._subscription_state.summary = {
            'total': len(subscriptions),
            'need_alert': sum(1 for r in subscriptions if r.get('need_alert', False)),
        }
    
    def clear_state(self):
        """清空所有状态"""
        with self._lock:
            self._balance_state = BalanceState()
            self._subscription_state = SubscriptionState()
            logger.info("状态已清空")


# 全局状态管理器实例
state_manager = StateManager()