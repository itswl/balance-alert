#!/usr/bin/env python3
"""
数据访问层

提供数据库 CRUD 操作封装。所有方法用 @db_op 装饰：自动注入 session、
统一异常兜底（默认吞掉并返回兜底值，STRICT_DATABASE_ERRORS=true 时向上抛）。
"""
import json
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Dict, Iterator, List, Optional

from sqlalchemy import desc, func
from sqlalchemy.exc import DBAPIError, OperationalError

from core.logger import get_logger
from core.secret_crypto import decrypt_secret, encrypt_secret, encryption_enabled
from core.settings import get_settings
from .engine import ENABLE_DATABASE, get_session
from .models import (
    AlertHistory,
    BalanceHistory,
    EmailAlertHistory,
    EmailConfig,
    ProjectConfig,
    SubscriptionConfig,
)

logger = get_logger('repository')

DB_DISABLED_ERROR = {'error': '数据库未启用'}


@contextmanager
def session_scope(commit: bool = False) -> Iterator:
    session = None
    try:
        session = get_session()
        if session is None:
            yield None
            return
        yield session
        if commit:
            session.commit()
    except Exception:
        if session is not None and commit:
            session.rollback()
        raise
    finally:
        if session is not None:
            session.close()


def _should_reraise_db_exception(e: Exception) -> bool:
    if not get_settings().strict_database_errors:
        return False
    if isinstance(e, OperationalError):
        return False
    if isinstance(e, DBAPIError) and getattr(e, 'connection_invalidated', False):
        return False
    return True


def db_op(default: Any, error_message: str, *, commit: bool = False, exc_info: bool = False):
    """把方法体包装成一次数据库操作。

    被装饰的函数签名为 ``(session, *args)``，调用方按 ``(*args)`` 调用；
    数据库未启用或出错时返回 ``default``（可变默认值会拷贝，避免调用方互相污染）。
    """
    def fallback():
        return type(default)(default) if isinstance(default, (list, dict)) else default

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not ENABLE_DATABASE:
                return fallback()
            try:
                with session_scope(commit=commit) as session:
                    if session is None:
                        return fallback()
                    return func(session, *args, **kwargs)
            except Exception as e:
                logger.error(f"{error_message}: {e}", exc_info=exc_info)
                if _should_reraise_db_exception(e):
                    raise
                return fallback()
        return wrapper
    return decorator


def utcnow() -> datetime:
    """Return naive UTC datetime for existing database columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _decrypt_field(data: Dict[str, Any], field: str) -> Dict[str, Any]:
    if field in data:
        data[field] = decrypt_secret(data[field])
    return data


def _encrypt_model_field(model: Any, field: str) -> bool:
    current_value = getattr(model, field, None)
    encrypted_value = encrypt_secret(current_value)
    if encrypted_value != current_value:
        setattr(model, field, encrypted_value)
        return True
    return False


def _maybe_encrypt_models(session, models: List[Any], field: str) -> None:
    """把历史明文字段就地加密回写（AUTO_ENCRYPT_ON_READ）。"""
    if not get_settings().auto_encrypt_on_read or not encryption_enabled():
        return None

    changed = False
    for model in models:
        changed = _encrypt_model_field(model, field) or changed
    if changed:
        session.commit()


def _encrypt_data_field(data: Dict[str, Any], field: str) -> Dict[str, Any]:
    if field in data and data[field] != '***':
        data = data.copy()
        data[field] = encrypt_secret(data[field])
    return data


def _upsert(session, model_cls, data: Dict[str, Any], secret_field: Optional[str] = None) -> bool:
    """按 name 插入或更新一条配置；secret_field 为 '***' 时保留原值不覆盖。"""
    if secret_field:
        data = _encrypt_data_field(data, secret_field)
    row = session.query(model_cls).filter_by(name=data['name']).first()
    if row is None:
        session.add(model_cls(**data))
        return True
    for key, value in data.items():
        if key == secret_field and value == '***':
            continue
        setattr(row, key, value)
    return True


def _delete_by_name(session, model_cls, name: str) -> bool:
    row = session.query(model_cls).filter_by(name=name).first()
    if row:
        session.delete(row)
    return True


class ConfigRepository:
    """配置数据访问"""

    @staticmethod
    @db_op([], "获取邮箱配置失败")
    def get_all_emails(session) -> List[Dict[str, Any]]:
        """获取所有邮箱配置"""
        emails = session.query(EmailConfig).all()
        _maybe_encrypt_models(session, emails, 'password')
        return [_decrypt_field(e.to_dict(), 'password') for e in emails]

    @staticmethod
    @db_op(False, "保存邮箱配置失败", commit=True)
    def upsert_email(session, email_data: Dict[str, Any]) -> bool:
        """添加或更新邮箱"""
        return _upsert(session, EmailConfig, email_data, secret_field='password')

    @staticmethod
    @db_op(False, "删除邮箱失败", commit=True)
    def delete_email(session, name: str) -> bool:
        """删除邮箱"""
        return _delete_by_name(session, EmailConfig, name)

    @staticmethod
    @db_op([], "获取项目配置失败")
    def get_all_projects(session) -> List[Dict[str, Any]]:
        """获取所有项目配置（含未启用的）"""
        projects = session.query(ProjectConfig).all()
        _maybe_encrypt_models(session, projects, 'api_key')
        return [_decrypt_field(p.to_dict(), 'api_key') for p in projects]

    @staticmethod
    @db_op([], "获取订阅配置失败")
    def get_all_subscriptions(session) -> List[Dict[str, Any]]:
        """获取所有订阅配置（含未启用的）"""
        return [s.to_dict() for s in session.query(SubscriptionConfig).all()]

    @staticmethod
    @db_op(False, "保存项目配置失败", commit=True)
    def upsert_project(session, project_data: Dict[str, Any]) -> bool:
        """添加或更新项目"""
        return _upsert(session, ProjectConfig, project_data, secret_field='api_key')

    @staticmethod
    @db_op(False, "保存订阅配置失败", commit=True)
    def upsert_subscription(session, sub_data: Dict[str, Any]) -> bool:
        """添加或更新订阅"""
        return _upsert(session, SubscriptionConfig, sub_data)

    @staticmethod
    @db_op(False, "删除订阅失败", commit=True)
    def delete_subscription(session, name: str) -> bool:
        """删除订阅"""
        return _delete_by_name(session, SubscriptionConfig, name)


class EmailRepository:
    """邮件历史数据访问"""

    @staticmethod
    @db_op(None, "保存邮件告警记录失败", commit=True, exc_info=True)
    def save_email_alert(
        session,
        mailbox: str,
        sender: str,
        subject: str,
        date: str,
        service_name: Optional[str] = None,
        amount: Optional[float] = None,
        matched_keywords: List[str] = None,
        alert_sent: bool = False
    ) -> Optional[int]:
        """保存邮件告警记录"""
        record = EmailAlertHistory(
            mailbox=mailbox,
            sender=sender,
            subject=subject,
            date=date,
            service_name=service_name,
            amount=amount,
            matched_keywords=json.dumps(matched_keywords or [], ensure_ascii=False),
            alert_sent=alert_sent,
            timestamp=utcnow()
        )
        session.add(record)
        session.flush()
        logger.debug(f"保存邮件告警记录: {subject}")
        return record.id

    @staticmethod
    @db_op(False, "查询邮件告警去重记录失败", exc_info=True)
    def has_recent_email_alert(
        session,
        mailbox: str,
        sender: str,
        subject: str,
        date: str,
        days: int = 30
    ) -> bool:
        """检查近期是否已经成功发送过同一封告警邮件。"""
        since = utcnow() - timedelta(days=days)
        return session.query(EmailAlertHistory.id)\
            .filter(EmailAlertHistory.mailbox == mailbox)\
            .filter(EmailAlertHistory.sender == sender)\
            .filter(EmailAlertHistory.subject == subject)\
            .filter(EmailAlertHistory.date == date)\
            .filter(EmailAlertHistory.alert_sent.is_(True))\
            .filter(EmailAlertHistory.timestamp >= since)\
            .first() is not None


class BalanceRepository:
    """余额历史数据访问"""

    @staticmethod
    @db_op(None, "保存余额记录失败", commit=True, exc_info=True)
    def save_balance_record(
        session,
        project_id: str,
        project_name: str,
        provider: str,
        balance: float,
        threshold: Optional[float] = None,
        balance_type: str = 'credits',
        need_alarm: bool = False
    ) -> Optional[int]:
        """保存余额记录"""
        record = BalanceHistory(
            project_id=project_id,
            project_name=project_name,
            provider=provider,
            balance=balance,
            threshold=threshold,
            balance_type=balance_type,
            need_alarm=need_alarm,
            timestamp=utcnow()
        )
        session.add(record)
        session.flush()
        logger.debug(f"保存余额记录: {project_name} = {balance}")
        return record.id

    @staticmethod
    @db_op([], "查询余额历史失败", exc_info=True)
    def get_balance_history(
        session,
        project_id: Optional[str] = None,
        provider: Optional[str] = None,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取余额历史记录"""
        query = session.query(BalanceHistory)\
            .filter(BalanceHistory.timestamp >= utcnow() - timedelta(days=days))
        if project_id:
            query = query.filter(BalanceHistory.project_id == project_id)
        if provider:
            query = query.filter(BalanceHistory.provider == provider)
        records = query.order_by(desc(BalanceHistory.timestamp)).limit(limit).all()
        return [r.to_dict() for r in records]

    @staticmethod
    @db_op(DB_DISABLED_ERROR, "获取余额趋势失败", exc_info=True)
    def get_balance_trend(session, project_id: str, days: int = 30) -> Dict[str, Any]:
        """获取余额趋势分析"""
        records = session.query(BalanceHistory)\
            .filter(BalanceHistory.project_id == project_id)\
            .filter(BalanceHistory.timestamp >= utcnow() - timedelta(days=days))\
            .order_by(BalanceHistory.timestamp)\
            .all()

        if not records:
            return {'error': 'No data found'}

        balances = [r.balance for r in records]
        trend_data = {
            'project_id': project_id,
            'project_name': records[0].project_name,
            'days': days,
            'data_points': len(records),
            'current_balance': balances[-1],
            'min_balance': min(balances),
            'max_balance': max(balances),
            'avg_balance': sum(balances) / len(balances),
            'threshold': records[-1].threshold if records[-1].threshold is not None else 0,
            'first_timestamp': records[0].timestamp.isoformat(),
            'last_timestamp': records[-1].timestamp.isoformat(),
            'history': [
                {'timestamp': r.timestamp.isoformat(), 'balance': r.balance, 'need_alarm': r.need_alarm}
                for r in records
            ]
        }

        if len(balances) >= 2:
            trend_data['change'] = balances[-1] - balances[0]
            trend_data['change_percent'] = ((balances[-1] - balances[0]) / balances[0] * 100) if balances[0] != 0 else 0

        return trend_data


class AlertRepository:
    """告警历史数据访问"""

    @staticmethod
    @db_op(None, "保存告警记录失败", commit=True, exc_info=True)
    def save_alert_record(
        session,
        project_id: str,
        project_name: str,
        alert_type: str,
        message: str,
        balance_value: Optional[float] = None,
        threshold_value: Optional[float] = None,
        status: str = 'sent'
    ) -> Optional[int]:
        """保存告警记录"""
        record = AlertHistory(
            project_id=project_id,
            project_name=project_name,
            alert_type=alert_type,
            status=status,
            message=message,
            balance_value=balance_value,
            threshold_value=threshold_value,
            timestamp=utcnow()
        )
        session.add(record)
        session.flush()
        logger.debug(f"保存告警记录: {project_name} - {alert_type}")
        return record.id

    @staticmethod
    @db_op(False, "查询告警冷却记录失败", exc_info=True)
    def has_recent_alert(
        session,
        project_id: str,
        alert_type: str,
        within_seconds: int,
        status: str = 'sent'
    ) -> bool:
        """检查指定告警在冷却窗口内是否已经发送过。"""
        if within_seconds <= 0:
            return False
        query = session.query(AlertHistory.id)\
            .filter(AlertHistory.project_id == project_id)\
            .filter(AlertHistory.alert_type == alert_type)\
            .filter(AlertHistory.timestamp >= utcnow() - timedelta(seconds=within_seconds))
        if status:
            query = query.filter(AlertHistory.status == status)
        return query.first() is not None

    @staticmethod
    @db_op([], "查询告警历史失败", exc_info=True)
    def get_recent_alerts(
        session,
        project_id: Optional[str] = None,
        alert_type: Optional[str] = None,
        days: int = 7,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取最近的告警记录"""
        query = session.query(AlertHistory)\
            .filter(AlertHistory.timestamp >= utcnow() - timedelta(days=days))
        if project_id:
            query = query.filter(AlertHistory.project_id == project_id)
        if alert_type:
            query = query.filter(AlertHistory.alert_type == alert_type)
        records = query.order_by(desc(AlertHistory.timestamp)).limit(limit).all()
        return [r.to_dict() for r in records]

    @staticmethod
    @db_op(DB_DISABLED_ERROR, "获取告警统计失败", exc_info=True)
    def get_alert_statistics(session, days: int = 30) -> Dict[str, Any]:
        """获取告警统计信息"""
        since = utcnow() - timedelta(days=days)
        total_alerts = session.query(func.count(AlertHistory.id))\
            .filter(AlertHistory.timestamp >= since)\
            .scalar()

        alerts_by_type = session.query(
            AlertHistory.alert_type,
            func.count(AlertHistory.id).label('count')
        ).filter(AlertHistory.timestamp >= since)\
            .group_by(AlertHistory.alert_type)\
            .all()

        alerts_by_project = session.query(
            AlertHistory.project_name,
            func.count(AlertHistory.id).label('count')
        ).filter(AlertHistory.timestamp >= since)\
            .group_by(AlertHistory.project_name)\
            .order_by(desc('count'))\
            .limit(10)\
            .all()

        return {
            'days': days,
            'total_alerts': total_alerts,
            'by_type': {t: c for t, c in alerts_by_type},
            'top_projects': [{'project': p, 'count': c} for p, c in alerts_by_project],
        }
