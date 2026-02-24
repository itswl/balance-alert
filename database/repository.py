#!/usr/bin/env python3
"""
数据访问层

提供数据库 CRUD 操作封装
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import func, desc
from logger import get_logger
from .models import BalanceHistory, AlertHistory, SubscriptionHistory
from .engine import get_session, ENABLE_DATABASE

logger = get_logger('repository')


class BalanceRepository:
    """余额历史数据访问"""

    @staticmethod
    def save_balance_record(
        project_id: str,
        project_name: str,
        provider: str,
        balance: float,
        threshold: Optional[float] = None,
        currency: str = 'USD',
        balance_type: str = 'credits',
        need_alarm: bool = False
    ) -> Optional[int]:
        """保存余额记录"""
        if not ENABLE_DATABASE:
            return None

        try:
            session = get_session()
            if session is None:
                return None

            record = BalanceHistory(
                project_id=project_id,
                project_name=project_name,
                provider=provider,
                balance=balance,
                threshold=threshold,
                currency=currency,
                balance_type=balance_type,
                need_alarm=need_alarm,
                timestamp=datetime.utcnow()
            )

            session.add(record)
            session.commit()
            record_id = record.id
            session.close()

            logger.debug(f"保存余额记录: {project_name} = {balance} {currency}")
            return record_id

        except Exception as e:
            logger.error(f"保存余额记录失败: {e}", exc_info=True)
            if session:
                session.rollback()
                session.close()
            return None

    @staticmethod
    def get_latest_balance(project_id: str) -> Optional[Dict[str, Any]]:
        """获取项目最新余额记录"""
        if not ENABLE_DATABASE:
            return None

        try:
            session = get_session()
            if session is None:
                return None

            record = session.query(BalanceHistory)\
                .filter(BalanceHistory.project_id == project_id)\
                .order_by(desc(BalanceHistory.timestamp))\
                .first()

            result = record.to_dict() if record else None
            session.close()
            return result

        except Exception as e:
            logger.error(f"查询最新余额失败: {e}", exc_info=True)
            if session:
                session.close()
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
            session = get_session()
            if session is None:
                return []

            query = session.query(BalanceHistory)

            # 时间范围筛选
            since = datetime.utcnow() - timedelta(days=days)
            query = query.filter(BalanceHistory.timestamp >= since)

            # 项目筛选
            if project_id:
                query = query.filter(BalanceHistory.project_id == project_id)

            # Provider 筛选
            if provider:
                query = query.filter(BalanceHistory.provider == provider)

            # 排序和限制
            records = query.order_by(desc(BalanceHistory.timestamp))\
                .limit(limit)\
                .all()

            result = [r.to_dict() for r in records]
            session.close()
            return result

        except Exception as e:
            logger.error(f"查询余额历史失败: {e}", exc_info=True)
            if session:
                session.close()
            return []

    @staticmethod
    def get_balance_trend(project_id: str, days: int = 30) -> Dict[str, Any]:
        """获取余额趋势分析"""
        if not ENABLE_DATABASE:
            return {'error': 'Database disabled'}

        try:
            session = get_session()
            if session is None:
                return {'error': 'Database not available'}

            since = datetime.utcnow() - timedelta(days=days)

            # 查询原始数据
            records = session.query(BalanceHistory)\
                .filter(BalanceHistory.project_id == project_id)\
                .filter(BalanceHistory.timestamp >= since)\
                .order_by(BalanceHistory.timestamp)\
                .all()

            if not records:
                session.close()
                return {'error': 'No data found'}

            # 计算统计信息
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

            # 计算变化趋势
            if len(balances) >= 2:
                trend_data['change'] = balances[-1] - balances[0]
                trend_data['change_percent'] = ((balances[-1] - balances[0]) / balances[0] * 100) if balances[0] != 0 else 0

            session.close()
            return trend_data

        except Exception as e:
            logger.error(f"获取余额趋势失败: {e}", exc_info=True)
            if session:
                session.close()
            return {'error': str(e)}

    @staticmethod
    def get_all_projects_summary() -> List[Dict[str, Any]]:
        """获取所有项目的摘要信息"""
        if not ENABLE_DATABASE:
            return []

        try:
            session = get_session()
            if session is None:
                return []

            # 获取每个项目的最新记录
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

            result = [r.to_dict() for r in latest_records]
            session.close()
            return result

        except Exception as e:
            logger.error(f"获取项目摘要失败: {e}", exc_info=True)
            if session:
                session.close()
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
            session = get_session()
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
                timestamp=datetime.utcnow()
            )

            session.add(record)
            session.commit()
            record_id = record.id
            session.close()

            logger.debug(f"保存告警记录: {project_name} - {alert_type}")
            return record_id

        except Exception as e:
            logger.error(f"保存告警记录失败: {e}", exc_info=True)
            if session:
                session.rollback()
                session.close()
            return None

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
            session = get_session()
            if session is None:
                return []

            query = session.query(AlertHistory)

            # 时间范围
            since = datetime.utcnow() - timedelta(days=days)
            query = query.filter(AlertHistory.timestamp >= since)

            # 项目筛选
            if project_id:
                query = query.filter(AlertHistory.project_id == project_id)

            # 告警类型筛选
            if alert_type:
                query = query.filter(AlertHistory.alert_type == alert_type)

            records = query.order_by(desc(AlertHistory.timestamp))\
                .limit(limit)\
                .all()

            result = [r.to_dict() for r in records]
            session.close()
            return result

        except Exception as e:
            logger.error(f"查询告警历史失败: {e}", exc_info=True)
            if session:
                session.close()
            return []

    @staticmethod
    def get_alert_statistics(days: int = 30) -> Dict[str, Any]:
        """获取告警统计信息"""
        if not ENABLE_DATABASE:
            return {'error': 'Database disabled'}

        try:
            session = get_session()
            if session is None:
                return {'error': 'Database not available'}

            since = datetime.utcnow() - timedelta(days=days)

            # 总告警数
            total_alerts = session.query(func.count(AlertHistory.id))\
                .filter(AlertHistory.timestamp >= since)\
                .scalar()

            # 按类型统计
            alerts_by_type = session.query(
                AlertHistory.alert_type,
                func.count(AlertHistory.id).label('count')
            ).filter(AlertHistory.timestamp >= since)\
                .group_by(AlertHistory.alert_type)\
                .all()

            # 按项目统计
            alerts_by_project = session.query(
                AlertHistory.project_name,
                func.count(AlertHistory.id).label('count')
            ).filter(AlertHistory.timestamp >= since)\
                .group_by(AlertHistory.project_name)\
                .order_by(desc('count'))\
                .limit(10)\
                .all()

            result = {
                'days': days,
                'total_alerts': total_alerts,
                'by_type': {t: c for t, c in alerts_by_type},
                'top_projects': [
                    {'project': p, 'count': c}
                    for p, c in alerts_by_project
                ]
            }

            session.close()
            return result

        except Exception as e:
            logger.error(f"获取告警统计失败: {e}", exc_info=True)
            if session:
                session.close()
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
        currency: str = 'CNY',
        need_renewal: bool = False
    ) -> Optional[int]:
        """保存订阅记录"""
        if not ENABLE_DATABASE:
            return None

        try:
            session = get_session()
            if session is None:
                return None

            record = SubscriptionHistory(
                subscription_id=subscription_id,
                subscription_name=subscription_name,
                cycle_type=cycle_type,
                days_until_renewal=days_until_renewal,
                amount=amount,
                currency=currency,
                need_renewal=need_renewal,
                timestamp=datetime.utcnow()
            )

            session.add(record)
            session.commit()
            record_id = record.id
            session.close()

            logger.debug(f"保存订阅记录: {subscription_name}")
            return record_id

        except Exception as e:
            logger.error(f"保存订阅记录失败: {e}", exc_info=True)
            if session:
                session.rollback()
                session.close()
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
            session = get_session()
            if session is None:
                return []

            query = session.query(SubscriptionHistory)

            since = datetime.utcnow() - timedelta(days=days)
            query = query.filter(SubscriptionHistory.timestamp >= since)

            if subscription_id:
                query = query.filter(SubscriptionHistory.subscription_id == subscription_id)

            records = query.order_by(desc(SubscriptionHistory.timestamp))\
                .limit(limit)\
                .all()

            result = [r.to_dict() for r in records]
            session.close()
            return result

        except Exception as e:
            logger.error(f"查询订阅历史失败: {e}", exc_info=True)
            if session:
                session.close()
            return []
