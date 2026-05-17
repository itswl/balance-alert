#!/usr/bin/env python3
from typing import Any, Dict, List, Optional

from core.logger import get_logger

logger = get_logger('history_service')

try:
    from database.repository import BalanceRepository, AlertRepository
    DB_AVAILABLE = True
except Exception:
    DB_AVAILABLE = False


def get_balance_history(project_id: Optional[str] = None, provider: Optional[str] = None, days: int = 7, limit: int = 100) -> List[Dict[str, Any]]:
    if not DB_AVAILABLE:
        raise RuntimeError("数据库功能未启用")
    return BalanceRepository.get_balance_history(project_id=project_id, provider=provider, days=days, limit=limit)


def get_balance_trend(project_id: str, days: int = 30) -> Dict[str, Any]:
    if not DB_AVAILABLE:
        raise RuntimeError("数据库功能未启用")
    return BalanceRepository.get_balance_trend(project_id, days)


def get_recent_alerts(project_id: Optional[str] = None, alert_type: Optional[str] = None, days: int = 7, limit: int = 50) -> List[Dict[str, Any]]:
    if not DB_AVAILABLE:
        raise RuntimeError("数据库功能未启用")
    return AlertRepository.get_recent_alerts(project_id=project_id, alert_type=alert_type, days=days, limit=limit)


def get_alert_statistics(days: int = 30) -> Dict[str, Any]:
    if not DB_AVAILABLE:
        raise RuntimeError("数据库功能未启用")
    return AlertRepository.get_alert_statistics(days)


def get_all_projects_summary() -> List[Dict[str, Any]]:
    if not DB_AVAILABLE:
        raise RuntimeError("数据库功能未启用")
    return BalanceRepository.get_all_projects_summary()

