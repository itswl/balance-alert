#!/usr/bin/env python3
"""
数据访问层

提供数据库 CRUD 操作封装
"""
from typing import List, Optional, Dict, Any, Iterator
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
import os
from sqlalchemy import func, desc
from sqlalchemy.exc import DBAPIError, OperationalError
from core.logger import get_logger
from core.secret_crypto import decrypt_secret, encrypt_secret, encryption_enabled
from .models import BalanceHistory, AlertHistory, SubscriptionHistory, ProjectConfig, SubscriptionConfig, EmailConfig, EmailAlertHistory
import json
from .engine import get_session, ENABLE_DATABASE

logger = get_logger('repository')


def _strict_database_errors_enabled() -> bool:
    return os.environ.get('STRICT_DATABASE_ERRORS', 'false').lower() == 'true'


def _auto_encrypt_on_read_enabled() -> bool:
    return os.environ.get('AUTO_ENCRYPT_ON_READ', 'true').lower() == 'true'


def _should_reraise_db_exception(e: Exception) -> bool:
    if not _strict_database_errors_enabled():
        return False
    if isinstance(e, OperationalError):
        return False
    if isinstance(e, DBAPIError) and getattr(e, 'connection_invalidated', False):
        return False
    return True


def _db_read(default_value, error_message: str, op, *, exc_info: bool = False):
    if not ENABLE_DATABASE:
        return default_value
    try:
        with session_scope() as session:
            if session is None:
                return default_value
            return op(session)
    except Exception as e:
        logger.error(f"{error_message}: {e}", exc_info=exc_info)
        if _should_reraise_db_exception(e):
            raise
        return default_value


def _db_write(default_value, error_message: str, op, *, exc_info: bool = False):
    if not ENABLE_DATABASE:
        return default_value
    try:
        with session_scope(commit=True) as session:
            if session is None:
                return default_value
            return op(session)
    except Exception as e:
        logger.error(f"{error_message}: {e}", exc_info=exc_info)
        if _should_reraise_db_exception(e):
            raise
        return default_value


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
    if not _auto_encrypt_on_read_enabled():
        return None
    if not encryption_enabled():
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


def _project_to_dict(project: ProjectConfig) -> Dict[str, Any]:
    return _decrypt_field(project.to_dict(), 'api_key')


def _email_to_dict(email: EmailConfig) -> Dict[str, Any]:
    return _decrypt_field(email.to_dict(), 'password')


class ConfigRepository:
    """配置数据访问"""
    
    @staticmethod
    def get_all_emails() -> List[Dict[str, Any]]:
        """获取所有邮箱配置"""
        def op(session):
            emails = session.query(EmailConfig).all()
            _maybe_encrypt_models(session, emails, 'password')
            return [_email_to_dict(e) for e in emails]

        return _db_read([], "获取邮箱配置失败", op)

    @staticmethod
    def upsert_email(email_data: Dict[str, Any]) -> bool:
        """添加或更新邮箱"""
        def op(session):
            encrypted_data = _encrypt_data_field(email_data, 'password')
            email = session.query(EmailConfig).filter_by(name=encrypted_data['name']).first()
            if email:
                for k, v in encrypted_data.items():
                    if k == 'password' and v == '***':
                        continue
                    setattr(email, k, v)
            else:
                email = EmailConfig(**encrypted_data)
                session.add(email)
            return True

        return _db_write(False, "保存邮箱配置失败", op)
            
    @staticmethod
    def delete_email(name: str) -> bool:
        """删除邮箱"""
        def op(session):
            email = session.query(EmailConfig).filter_by(name=name).first()
            if email:
                session.delete(email)
            return True

        return _db_write(False, "删除邮箱失败", op)
            
    @staticmethod
    def get_all_projects() -> List[Dict[str, Any]]:
        """获取所有启用的项目配置"""
        def op(session):
            projects = session.query(ProjectConfig).all()
            _maybe_encrypt_models(session, projects, 'api_key')
            return [_project_to_dict(p) for p in projects]

        return _db_read([], "获取项目配置失败", op)

    @staticmethod
    def get_all_subscriptions() -> List[Dict[str, Any]]:
        """获取所有启用的订阅配置"""
        def op(session):
            subs = session.query(SubscriptionConfig).all()
            return [s.to_dict() for s in subs]

        return _db_read([], "获取订阅配置失败", op)

    @staticmethod
    def upsert_project(project_data: Dict[str, Any]) -> bool:
        """添加或更新项目"""
        def op(session):
            encrypted_data = _encrypt_data_field(project_data, 'api_key')
            project = session.query(ProjectConfig).filter_by(name=encrypted_data['name']).first()
            if project:
                for k, v in encrypted_data.items():
                    if k == 'api_key' and v == '***':
                        continue
                    setattr(project, k, v)
            else:
                project = ProjectConfig(**encrypted_data)
                session.add(project)
            return True

        return _db_write(False, "保存项目配置失败", op)

    @staticmethod
    def upsert_subscription(sub_data: Dict[str, Any]) -> bool:
        """添加或更新订阅"""
        def op(session):
            sub = session.query(SubscriptionConfig).filter_by(name=sub_data['name']).first()
            if sub:
                for k, v in sub_data.items():
                    setattr(sub, k, v)
            else:
                sub = SubscriptionConfig(**sub_data)
                session.add(sub)
            return True

        return _db_write(False, "保存订阅配置失败", op)
            
    @staticmethod
    def delete_subscription(name: str) -> bool:
        """删除订阅"""
        def op(session):
            sub = session.query(SubscriptionConfig).filter_by(name=name).first()
            if sub:
                session.delete(sub)
            return True

        return _db_write(False, "删除订阅失败", op)


class EmailRepository:
    """邮件历史数据访问"""

    @staticmethod
    def save_email_alert(
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
        def op(session):
            keywords_json = json.dumps(matched_keywords or [], ensure_ascii=False)
            record = EmailAlertHistory(
                mailbox=mailbox,
                sender=sender,
                subject=subject,
                date=date,
                service_name=service_name,
                amount=amount,
                matched_keywords=keywords_json,
                alert_sent=alert_sent,
                timestamp=utcnow()
            )
            session.add(record)
            session.flush()
            logger.debug(f"保存邮件告警记录: {subject}")
            return record.id

        return _db_write(None, "保存邮件告警记录失败", op, exc_info=True)

    @staticmethod
    def has_recent_email_alert(
        mailbox: str,
        sender: str,
        subject: str,
        date: str,
        days: int = 30
    ) -> bool:
        """检查近期是否已经成功发送过同一封告警邮件。"""
        def op(session):
            since = utcnow() - timedelta(days=days)
            return session.query(EmailAlertHistory.id)\
                .filter(EmailAlertHistory.mailbox == mailbox)\
                .filter(EmailAlertHistory.sender == sender)\
                .filter(EmailAlertHistory.subject == subject)\
                .filter(EmailAlertHistory.date == date)\
                .filter(EmailAlertHistory.alert_sent.is_(True))\
                .filter(EmailAlertHistory.timestamp >= since)\
                .first() is not None

        return _db_read(False, "查询邮件告警去重记录失败", op, exc_info=True)


class BalanceRepository:
    """余额历史数据访问"""

    @staticmethod
    def save_balance_record(
        project_id: str,
        project_name: str,
        provider: str,
        balance: float,
        threshold: Optional[float] = None,
        balance_type: str = 'credits',
        need_alarm: bool = False
    ) -> Optional[int]:
        """保存余额记录"""
        def op(session):
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

        return _db_write(None, "保存余额记录失败", op, exc_info=True)

    @staticmethod
    def get_latest_balance(project_id: str) -> Optional[Dict[str, Any]]:
        """获取项目最新余额记录"""
        def op(session):
            record = session.query(BalanceHistory)\
                .filter(BalanceHistory.project_id == project_id)\
                .order_by(desc(BalanceHistory.timestamp))\
                .first()
            return record.to_dict() if record else None

        return _db_read(None, "查询最新余额失败", op, exc_info=True)

    @staticmethod
    def get_balance_history(
        project_id: Optional[str] = None,
        provider: Optional[str] = None,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取余额历史记录"""
        def op(session):
            query = session.query(BalanceHistory)
            since = utcnow() - timedelta(days=days)
            query = query.filter(BalanceHistory.timestamp >= since)
            if project_id:
                query = query.filter(BalanceHistory.project_id == project_id)
            if provider:
                query = query.filter(BalanceHistory.provider == provider)
            records = query.order_by(desc(BalanceHistory.timestamp))\
                .limit(limit)\
                .all()
            return [r.to_dict() for r in records]

        return _db_read([], "查询余额历史失败", op, exc_info=True)

    @staticmethod
    def get_balance_trend(project_id: str, days: int = 30) -> Dict[str, Any]:
        """获取余额趋势分析"""
        if not ENABLE_DATABASE:
            return {'error': 'Database disabled'}
        def op(session):
            since = utcnow() - timedelta(days=days)
            records = session.query(BalanceHistory)\
                .filter(BalanceHistory.project_id == project_id)\
                .filter(BalanceHistory.timestamp >= since)\
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
                'current_balance': balances[-1] if balances else 0,
                'min_balance': min(balances) if balances else 0,
                'max_balance': max(balances) if balances else 0,
                'avg_balance': sum(balances) / len(balances) if balances else 0,
                'threshold': records[-1].threshold if records[-1].threshold is not None else 0,
                'first_timestamp': records[0].timestamp.isoformat(),
                'last_timestamp': records[-1].timestamp.isoformat(),
                'history': [
                    {
                        'timestamp': r.timestamp.isoformat(),
                        'balance': r.balance,
                        'need_alarm': r.need_alarm
                    }
                    for r in records
                ]
            }

            if len(balances) >= 2:
                trend_data['change'] = balances[-1] - balances[0]
                trend_data['change_percent'] = ((balances[-1] - balances[0]) / balances[0] * 100) if balances[0] != 0 else 0

            return trend_data

        return _db_read({'error': 'Database not available'}, "获取余额趋势失败", op, exc_info=True)

    @staticmethod
    def get_all_projects_summary() -> List[Dict[str, Any]]:
        """获取所有项目的摘要信息"""
        def op(session):
            subquery = session.query(
                BalanceHistory.project_id,
                func.max(BalanceHistory.timestamp).label('max_timestamp')
            ).group_by(BalanceHistory.project_id).subquery()

            latest_records = session.query(BalanceHistory)\
                .join(
                    subquery,
                    (BalanceHistory.project_id == subquery.c.project_id) &
                    (BalanceHistory.timestamp == subquery.c.max_timestamp)
                )\
                .all()
            return [r.to_dict() for r in latest_records]

        return _db_read([], "获取项目摘要失败", op, exc_info=True)


class AlertRepository:
    """告警历史数据访问"""

    @staticmethod
    def save_alert_record(
        project_id: str,
        project_name: str,
        alert_type: str,
        message: str,
        balance_value: Optional[float] = None,
        threshold_value: Optional[float] = None,
        status: str = 'sent'
    ) -> Optional[int]:
        """保存告警记录"""
        def op(session):
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

        return _db_write(None, "保存告警记录失败", op, exc_info=True)

    @staticmethod
    def has_recent_alert(
        project_id: str,
        alert_type: str,
        within_seconds: int,
        status: str = 'sent'
    ) -> bool:
        """检查指定告警在冷却窗口内是否已经发送过。"""
        if not ENABLE_DATABASE or within_seconds <= 0:
            return False
        def op(session):
            since = utcnow() - timedelta(seconds=within_seconds)
            query = session.query(AlertHistory.id)\
                .filter(AlertHistory.project_id == project_id)\
                .filter(AlertHistory.alert_type == alert_type)\
                .filter(AlertHistory.timestamp >= since)
            if status:
                query = query.filter(AlertHistory.status == status)
            return query.first() is not None

        return _db_read(False, "查询告警冷却记录失败", op, exc_info=True)

    @staticmethod
    def get_recent_alerts(
        project_id: Optional[str] = None,
        alert_type: Optional[str] = None,
        days: int = 7,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取最近的告警记录"""
        def op(session):
            query = session.query(AlertHistory)
            since = utcnow() - timedelta(days=days)
            query = query.filter(AlertHistory.timestamp >= since)
            if project_id:
                query = query.filter(AlertHistory.project_id == project_id)
            if alert_type:
                query = query.filter(AlertHistory.alert_type == alert_type)
            records = query.order_by(desc(AlertHistory.timestamp))\
                .limit(limit)\
                .all()
            return [r.to_dict() for r in records]

        return _db_read([], "查询告警历史失败", op, exc_info=True)

    @staticmethod
    def get_alert_statistics(days: int = 30) -> Dict[str, Any]:
        """获取告警统计信息"""
        if not ENABLE_DATABASE:
            return {'error': 'Database disabled'}
        def op(session):
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
                'top_projects': [
                    {'project': p, 'count': c}
                    for p, c in alerts_by_project
                ]
            }

        return _db_read({'error': 'Database not available'}, "获取告警统计失败", op, exc_info=True)


class SubscriptionRepository:
    """订阅历史数据访问"""

    @staticmethod
    def save_subscription_record(
        subscription_id: str,
        subscription_name: str,
        cycle_type: str,
        days_until_renewal: int,
        amount: float = 0,
        need_renewal: bool = False
    ) -> Optional[int]:
        """保存订阅记录"""
        def op(session):
            record = SubscriptionHistory(
                subscription_id=subscription_id,
                subscription_name=subscription_name,
                cycle_type=cycle_type,
                days_until_renewal=days_until_renewal,
                amount=amount,
                need_renewal=need_renewal,
                timestamp=utcnow()
            )
            session.add(record)
            session.flush()
            logger.debug(f"保存订阅记录: {subscription_name}")
            return record.id

        return _db_write(None, "保存订阅记录失败", op, exc_info=True)

    @staticmethod
    def get_subscription_history(
        subscription_id: Optional[str] = None,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取订阅历史"""
        def op(session):
            query = session.query(SubscriptionHistory)
            since = utcnow() - timedelta(days=days)
            query = query.filter(SubscriptionHistory.timestamp >= since)
            if subscription_id:
                query = query.filter(SubscriptionHistory.subscription_id == subscription_id)
            records = query.order_by(desc(SubscriptionHistory.timestamp))\
                .limit(limit)\
                .all()
            return [r.to_dict() for r in records]

        return _db_read([], "查询订阅历史失败", op, exc_info=True)
