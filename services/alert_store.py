#!/usr/bin/env python3
"""
告警去重与留痕

余额、订阅、邮件三类告警共用同一套「冷却判断 + 历史留痕」逻辑，差别只在
冷却时长取哪个环境变量。数据库未启用时全部降级为「不冷却、不留痕」，
不影响告警本身发送。

数据库层的异常兜底由 database.repository 的 @db_op 负责，这里只处理
「连 repository 都导不进来」（未安装 sqlalchemy）的情况。
"""
from typing import Optional

from core.logger import get_logger
from core.settings import get_settings

logger = get_logger('alert_store')

DEFAULT_COOLDOWN_SECONDS = 86400

try:
    from database.repository import AlertRepository, BalanceRepository, EmailRepository
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False
    logger.warning("数据库模块不可用，告警冷却与历史记录将跳过")


def cooldown_seconds(kind: str = 'balance') -> int:
    """告警冷却时长（秒），默认 24 小时。

    订阅提醒优先读 SUBSCRIPTION_ALERT_COOLDOWN_SECONDS，未设置时回退到 ALERT_COOLDOWN_SECONDS。
    """
    settings = get_settings()
    value = settings.subscription_alert_cooldown_seconds if kind == 'subscription' else None
    if value is None:
        value = settings.alert_cooldown_seconds
    return max(0, value) if value is not None else DEFAULT_COOLDOWN_SECONDS


def in_cooldown(alert_id: str, alert_type: str, seconds: int) -> bool:
    """该告警是否仍在冷却窗口内；数据库不可用时一律放行"""
    if not DB_AVAILABLE:
        return False
    return AlertRepository.has_recent_alert(alert_id, alert_type, seconds)


def record_alert(alert_id: str, name: str, alert_type: str, message: str,
                 value: Optional[float] = None, threshold: Optional[float] = None) -> None:
    """记录已发出的告警，作为下次冷却判断的依据"""
    if not DB_AVAILABLE:
        return None
    AlertRepository.save_alert_record(
        project_id=alert_id,
        project_name=name,
        alert_type=alert_type,
        message=message,
        balance_value=value,
        threshold_value=threshold,
        status='sent',
    )


def record_balance(project_id: str, project_name: str, provider: str, balance: float,
                   threshold: Optional[float], balance_type: str, need_alarm: bool) -> None:
    """记录一次余额检查结果，供历史查询与趋势分析"""
    if not DB_AVAILABLE:
        return None
    BalanceRepository.save_balance_record(
        project_id=project_id,
        project_name=project_name,
        provider=provider,
        balance=balance,
        threshold=threshold,
        balance_type=balance_type,
        need_alarm=need_alarm,
    )


def email_alert_sent_recently(mailbox: str, sender: str, subject: str, date: str, days: int) -> bool:
    """同一封告警邮件近期是否已经通知过"""
    if not DB_AVAILABLE:
        return False
    return EmailRepository.has_recent_email_alert(
        mailbox=mailbox, sender=sender, subject=subject, date=date, days=days
    )


def record_email_alert(mailbox: str, sender: str, subject: str, date: str,
                       service_name: Optional[str] = None, amount: Optional[float] = None,
                       matched_keywords: Optional[list] = None, alert_sent: bool = False) -> None:
    """记录扫描到的告警邮件，作为下次去重依据"""
    if not DB_AVAILABLE:
        return None
    EmailRepository.save_email_alert(
        mailbox=mailbox,
        sender=sender,
        subject=subject,
        date=date,
        service_name=service_name,
        amount=amount,
        matched_keywords=matched_keywords,
        alert_sent=alert_sent,
    )
