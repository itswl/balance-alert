#!/usr/bin/env python3
"""
数据访问层

提供数据库 CRUD 操作封装
"""
from typing import List, Optional, Dict, Any, Iterator
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from sqlalchemy import func, desc
from core.logger import get_logger
from .models import BalanceHistory, AlertHistory, SubscriptionHistory, ProjectConfig, SubscriptionConfig, EmailConfig, EmailAlertHistory
import json
from .engine import get_session, ENABLE_DATABASE

logger = get_logger('repository')

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


class ConfigRepository:
    """配置数据访问"""
    
    @staticmethod
    def get_all_emails() -> List[Dict[str, Any]]:
        """获取所有邮箱配置"""
        if not ENABLE_DATABASE:
            return []
            
        try:
            with session_scope() as session:
                if session is None:
                    return []
                emails = session.query(EmailConfig).all()
                return [e.to_dict() for e in emails]
        except Exception as e:
            logger.error(f"获取邮箱配置失败: {e}")
            return []

    @staticmethod
    def upsert_email(email_data: Dict[str, Any]) -> bool:
        """添加或更新邮箱"""
        if not ENABLE_DATABASE:
            return False
            
        try:
            with session_scope(commit=True) as session:
                if session is None:
                    return False

                email = session.query(EmailConfig).filter_by(name=email_data['name']).first()
                if email:
                    for k, v in email_data.items():
                        if k == 'password' and v == '***':
                            continue
                        setattr(email, k, v)
                else:
                    email = EmailConfig(**email_data)
                    session.add(email)
                return True
        except Exception as e:
            logger.error(f"保存邮箱配置失败: {e}")
            return False
            
    @staticmethod
    def delete_email(name: str) -> bool:
        """删除邮箱"""
        if not ENABLE_DATABASE:
            return False
            
        try:
            with session_scope(commit=True) as session:
                if session is None:
                    return False

                email = session.query(EmailConfig).filter_by(name=name).first()
                if email:
                    session.delete(email)
                return True
        except Exception as e:
            logger.error(f"删除邮箱失败: {e}")
            return False
            
    @staticmethod
    def get_all_projects() -> List[Dict[str, Any]]:
        """获取所有启用的项目配置"""
        if not ENABLE_DATABASE:
            return []
        
        try:
            with session_scope() as session:
                if session is None:
                    return []
                projects = session.query(ProjectConfig).all()
                return [p.to_dict() for p in projects]
        except Exception as e:
            logger.error(f"获取项目配置失败: {e}")
            return []

    @staticmethod
    def get_all_subscriptions() -> List[Dict[str, Any]]:
        """获取所有启用的订阅配置"""
        if not ENABLE_DATABASE:
            return []
            
        try:
            with session_scope() as session:
                if session is None:
                    return []
                subs = session.query(SubscriptionConfig).all()
                return [s.to_dict() for s in subs]
        except Exception as e:
            logger.error(f"获取订阅配置失败: {e}")
            return []

    @staticmethod
    def upsert_project(project_data: Dict[str, Any]) -> bool:
        """添加或更新项目"""
        if not ENABLE_DATABASE:
            return False
            
        try:
            with session_scope(commit=True) as session:
                if session is None:
                    return False

                project = session.query(ProjectConfig).filter_by(name=project_data['name']).first()
                if project:
                    for k, v in project_data.items():
                        if k == 'api_key' and v == '***':
                            continue
                        setattr(project, k, v)
                else:
                    project = ProjectConfig(**project_data)
                    session.add(project)
                return True
        except Exception as e:
            logger.error(f"保存项目配置失败: {e}")
            return False

    @staticmethod
    def upsert_subscription(sub_data: Dict[str, Any]) -> bool:
        """添加或更新订阅"""
        if not ENABLE_DATABASE:
            return False
            
        try:
            with session_scope(commit=True) as session:
                if session is None:
                    return False

                sub = session.query(SubscriptionConfig).filter_by(name=sub_data['name']).first()
                if sub:
                    for k, v in sub_data.items():
                        setattr(sub, k, v)
                else:
                    sub = SubscriptionConfig(**sub_data)
                    session.add(sub)
                return True
        except Exception as e:
            logger.error(f"保存订阅配置失败: {e}")
            return False
            
    @staticmethod
    def delete_subscription(name: str) -> bool:
        """删除订阅"""
        if not ENABLE_DATABASE:
            return False
            
        try:
            with session_scope(commit=True) as session:
                if session is None:
                    return False
                sub = session.query(SubscriptionConfig).filter_by(name=name).first()
                if sub:
                    session.delete(sub)
                return True
        except Exception as e:
            logger.error(f"删除订阅失败: {e}")
            return False


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
        if not ENABLE_DATABASE:
            return None

        try:
            with session_scope(commit=True) as session:
                if session is None:
                    return None

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

        except Exception as e:
            logger.error(f"保存邮件告警记录失败: {e}", exc_info=True)
            return None

    @staticmethod
    def has_recent_email_alert(
        mailbox: str,
        sender: str,
        subject: str,
        date: str,
        days: int = 30
    ) -> bool:
        """检查近期是否已经成功发送过同一封告警邮件。"""
        if not ENABLE_DATABASE:
            return False

        try:
            with session_scope() as session:
                if session is None:
                    return False
                since = utcnow() - timedelta(days=days)
                return session.query(EmailAlertHistory.id)\
                    .filter(EmailAlertHistory.mailbox == mailbox)\
                    .filter(EmailAlertHistory.sender == sender)\
                    .filter(EmailAlertHistory.subject == subject)\
                    .filter(EmailAlertHistory.date == date)\
                    .filter(EmailAlertHistory.alert_sent.is_(True))\
                    .filter(EmailAlertHistory.timestamp >= since)\
                    .first() is not None

        except Exception as e:
            logger.error(f"查询邮件告警去重记录失败: {e}", exc_info=True)
            return False


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
        if not ENABLE_DATABASE:
            return None

        try:
            with session_scope(commit=True) as session:
                if session is None:
                    return None

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

        except Exception as e:
            logger.error(f"保存余额记录失败: {e}", exc_info=True)
            return None

    @staticmethod
    def get_latest_balance(project_id: str) -> Optional[Dict[str, Any]]:
        """获取项目最新余额记录"""
        if not ENABLE_DATABASE:
            return None

        try:
            with session_scope() as session:
                if session is None:
                    return None
                record = session.query(BalanceHistory)\
                    .filter(BalanceHistory.project_id == project_id)\
                    .order_by(desc(BalanceHistory.timestamp))\
                    .first()
                return record.to_dict() if record else None

        except Exception as e:
            logger.error(f"查询最新余额失败: {e}", exc_info=True)
            return None

    @staticmethod
    def get_balance_history(
        project_id: Optional[str] = None,
        provider: Optional[str] = None,
        days: int = 7,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取余额历史记录"""
        if not ENABLE_DATABASE:
            return []

        try:
            with session_scope() as session:
                if session is None:
                    return []
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

        except Exception as e:
            logger.error(f"查询余额历史失败: {e}", exc_info=True)
            return []

    @staticmethod
    def get_balance_trend(project_id: str, days: int = 30) -> Dict[str, Any]:
        """获取余额趋势分析"""
        if not ENABLE_DATABASE:
            return {'error': 'Database disabled'}

        try:
            with session_scope() as session:
                if session is None:
                    return {'error': 'Database not available'}

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

        except Exception as e:
            logger.error(f"获取余额趋势失败: {e}", exc_info=True)
            return {'error': str(e)}

    @staticmethod
    def get_all_projects_summary() -> List[Dict[str, Any]]:
        """获取所有项目的摘要信息"""
        if not ENABLE_DATABASE:
            return []

        try:
            with session_scope() as session:
                if session is None:
                    return []

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

        except Exception as e:
            logger.error(f"获取项目摘要失败: {e}", exc_info=True)
            return []


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
        if not ENABLE_DATABASE:
            return None

        try:
            with session_scope(commit=True) as session:
                if session is None:
                    return None

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

        except Exception as e:
            logger.error(f"保存告警记录失败: {e}", exc_info=True)
            return None

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

        try:
            with session_scope() as session:
                if session is None:
                    return False
                since = utcnow() - timedelta(seconds=within_seconds)
                query = session.query(AlertHistory.id)\
                    .filter(AlertHistory.project_id == project_id)\
                    .filter(AlertHistory.alert_type == alert_type)\
                    .filter(AlertHistory.timestamp >= since)
                if status:
                    query = query.filter(AlertHistory.status == status)
                return query.first() is not None

        except Exception as e:
            logger.error(f"查询告警冷却记录失败: {e}", exc_info=True)
            return False

    @staticmethod
    def get_recent_alerts(
        project_id: Optional[str] = None,
        alert_type: Optional[str] = None,
        days: int = 7,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取最近的告警记录"""
        if not ENABLE_DATABASE:
            return []

        try:
            with session_scope() as session:
                if session is None:
                    return []

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

        except Exception as e:
            logger.error(f"查询告警历史失败: {e}", exc_info=True)
            return []

    @staticmethod
    def get_alert_statistics(days: int = 30) -> Dict[str, Any]:
        """获取告警统计信息"""
        if not ENABLE_DATABASE:
            return {'error': 'Database disabled'}

        try:
            with session_scope() as session:
                if session is None:
                    return {'error': 'Database not available'}

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

        except Exception as e:
            logger.error(f"获取告警统计失败: {e}", exc_info=True)
            return {'error': str(e)}


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
        if not ENABLE_DATABASE:
            return None

        try:
            with session_scope(commit=True) as session:
                if session is None:
                    return None

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

        except Exception as e:
            logger.error(f"保存订阅记录失败: {e}", exc_info=True)
            return None

    @staticmethod
    def get_subscription_history(
        subscription_id: Optional[str] = None,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """获取订阅历史"""
        if not ENABLE_DATABASE:
            return []

        try:
            with session_scope() as session:
                if session is None:
                    return []

                query = session.query(SubscriptionHistory)
                since = utcnow() - timedelta(days=days)
                query = query.filter(SubscriptionHistory.timestamp >= since)

                if subscription_id:
                    query = query.filter(SubscriptionHistory.subscription_id == subscription_id)

                records = query.order_by(desc(SubscriptionHistory.timestamp))\
                    .limit(limit)\
                    .all()
                return [r.to_dict() for r in records]

        except Exception as e:
            logger.error(f"查询订阅历史失败: {e}", exc_info=True)
            return []
