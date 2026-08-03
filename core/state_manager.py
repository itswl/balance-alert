#!/usr/bin/env python3
"""
状态管理器
封装 Web 看板展示的余额/订阅状态，提供线程安全的访问接口
"""
import copy
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.logger import get_logger

logger = get_logger('state_manager')


def _empty_balance_state() -> Dict[str, Any]:
    return {'last_update': None, 'projects': [], 'summary': {}}


def _empty_subscription_state() -> Dict[str, Any]:
    return {'last_update': None, 'subscriptions': [], 'summary': {}}


def _balance_summary(projects: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        'total': len(projects),
        'success': sum(1 for r in projects if r['success']),
        'failed': sum(1 for r in projects if not r['success']),
        'need_alarm': sum(1 for r in projects if r.get('need_alarm', False)),
    }


class StateManager:
    """状态管理器类

    写线程（后台刷新）与读线程（waitress worker）真实并发，读写都在锁内；
    get_* 返回深拷贝，调用方可任意修改而不影响内部状态。
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._start_time = time.time()
        self._balance = _empty_balance_state()
        self._subscriptions = _empty_subscription_state()

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')

    def uptime_seconds(self) -> float:
        return time.time() - self._start_time

    def _set_balance(self, projects: List[Dict[str, Any]]) -> None:
        self._balance = {
            'last_update': self._now_iso(),
            'projects': projects,
            'summary': _balance_summary(projects),
        }
        logger.info(f"余额状态已更新: {self._balance['summary']}")

    def update_balance_state(self, projects: List[Dict[str, Any]]) -> None:
        """全量更新余额状态（线程安全）"""
        with self._lock:
            self._set_balance(list(projects or []))

    def merge_balance_state(self, projects: List[Dict[str, Any]]) -> None:
        """按项目名合并部分刷新结果（线程安全）"""
        with self._lock:
            proj_map = {p.get('project'): p for p in self._balance['projects'] if p.get('project') is not None}
            for r in projects or []:
                proj_key = r.get('project')
                if proj_key is not None:
                    proj_map[proj_key] = r
            self._set_balance(list(proj_map.values()))

    def update_subscription_state(self, subscriptions: Optional[List[Dict[str, Any]]]) -> None:
        """更新订阅状态（线程安全）"""
        with self._lock:
            subscriptions = list(subscriptions or [])
            self._subscriptions = {
                'last_update': self._now_iso(),
                'subscriptions': subscriptions,
                'summary': {
                    'total': len(subscriptions),
                    'need_alert': sum(1 for r in subscriptions if r.get('need_alert', False)),
                },
            }
            logger.info(f"订阅状态已更新: {self._subscriptions['summary']}")

    def get_balance_state(self) -> Dict[str, Any]:
        """获取余额状态（线程安全，返回独立副本）"""
        with self._lock:
            return copy.deepcopy(self._balance)

    def get_subscription_state(self) -> Dict[str, Any]:
        """获取订阅状态（线程安全，返回独立副本）"""
        with self._lock:
            return copy.deepcopy(self._subscriptions)
