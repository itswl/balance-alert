#!/usr/bin/env python3
"""
状态管理器
封装 Web 看板展示的余额/订阅/邮箱扫描状态与定时任务运行情况，提供线程安全的访问接口
"""
import copy
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.logger import get_logger
from core.timeutil import to_utc_iso

logger = get_logger('state_manager')


def _empty_balance_state() -> Dict[str, Any]:
    return {'last_update': None, 'projects': [], 'summary': {}}


def _empty_subscription_state() -> Dict[str, Any]:
    return {'last_update': None, 'subscriptions': [], 'summary': {}}


def _empty_email_state() -> Dict[str, Any]:
    return {'last_update': None, 'days': None, 'dry_run': None, 'mailboxes': [], 'alerts': [], 'summary': {}}


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
        self._email = _empty_email_state()
        self._jobs: Dict[str, Dict[str, Any]] = {}

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

    def remove_balance_project(self, name: str) -> None:
        """项目被删除后从看板状态里摘掉，不必等下一轮检查"""
        with self._lock:
            kept = [p for p in self._balance['projects'] if p.get('project') != name]
            if len(kept) != len(self._balance['projects']):
                self._set_balance(kept)

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

    def update_email_state(self, scan_result: Optional[Dict[str, Any]]) -> None:
        """更新邮箱扫描状态（线程安全），入参为 EmailScanner.scan_emails 的返回值"""
        scan_result = scan_result or {}
        mailboxes = list(scan_result.get('mailboxes') or [])
        alerts = list(scan_result.get('results') or [])
        with self._lock:
            self._email = {
                'last_update': self._now_iso(),
                'days': scan_result.get('days'),
                'dry_run': scan_result.get('dry_run'),
                'mailboxes': mailboxes,
                'alerts': alerts,
                'summary': {
                    'total_mailboxes': len(mailboxes),
                    'failed_mailboxes': sum(1 for m in mailboxes if m.get('error')),
                    'total_emails': sum(int(m.get('total_emails') or 0) for m in mailboxes),
                    'total_alerts': len(alerts),
                    'alerts_sent': sum(1 for a in alerts if a.get('alert_sent', False)),
                },
            }
            logger.info(f"邮箱扫描状态已更新: {self._email['summary']}")

    def get_balance_state(self) -> Dict[str, Any]:
        """获取余额状态（线程安全，返回独立副本）"""
        with self._lock:
            return copy.deepcopy(self._balance)

    def get_subscription_state(self) -> Dict[str, Any]:
        """获取订阅状态（线程安全，返回独立副本）"""
        with self._lock:
            return copy.deepcopy(self._subscriptions)

    def get_email_state(self) -> Dict[str, Any]:
        """获取邮箱扫描状态（线程安全，返回独立副本）"""
        with self._lock:
            return copy.deepcopy(self._email)

    # ---------- 定时任务 ----------

    @staticmethod
    def _empty_job(name: str) -> Dict[str, Any]:
        return {
            'name': name, 'description': '', 'schedule': '', 'enabled': True,
            'next_run': None, 'last_run': None, 'last_success': None, 'last_error': None,
            'last_duration_seconds': None, 'last_detail': None, 'runs': 0, 'failures': 0,
        }

    def register_job(self, name: str, *, description: str = '', schedule: str = '',
                     enabled: bool = True, next_run=None) -> None:
        """登记一个定时任务的静态信息，运行记录由 record_job_run 补充"""
        with self._lock:
            job = self._jobs.setdefault(name, self._empty_job(name))
            job.update({
                'description': description,
                'schedule': schedule,
                'enabled': enabled,
                'next_run': to_utc_iso(next_run) if enabled else None,
            })

    def record_job_run(self, name: str, *, success: bool, started_at, duration_seconds: float,
                       error: Optional[str] = None, detail: Any = None, next_run=None) -> None:
        """记录一次任务运行（线程安全）"""
        with self._lock:
            job = self._jobs.setdefault(name, self._empty_job(name))
            job['last_run'] = to_utc_iso(started_at)
            job['last_duration_seconds'] = round(float(duration_seconds), 3)
            job['next_run'] = to_utc_iso(next_run) if job.get('enabled', True) else None
            job['runs'] += 1
            if success:
                job['last_success'] = job['last_run']
                job['last_error'] = None
                job['last_detail'] = detail
            else:
                job['failures'] += 1
                job['last_error'] = error or '未知错误'
            level = logger.info if success else logger.warning
            level(f"任务 {name} {'成功' if success else '失败'}，耗时 {job['last_duration_seconds']} 秒"
                  + ('' if success else f"：{job['last_error']}"))

    def _jobs_healthy_locked(self) -> bool:
        return all(not job.get('last_error') for job in self._jobs.values() if job.get('enabled', True))

    def get_job_state(self) -> Dict[str, Any]:
        """定时任务运行情况（线程安全，返回独立副本）。healthy = 所有启用任务的上次运行都成功。"""
        with self._lock:
            return {
                'healthy': self._jobs_healthy_locked(),
                'jobs': copy.deepcopy(list(self._jobs.values())),
            }
