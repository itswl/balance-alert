#!/usr/bin/env python3
"""
数据库模型

定义数据表结构
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, Index
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()


class BalanceHistory(Base):
    """余额历史记录"""
    __tablename__ = 'balance_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(200), nullable=False, index=True, comment='项目唯一标识')
    project_name = Column(String(200), nullable=False, comment='项目名称')
    provider = Column(String(50), nullable=False, index=True, comment='Provider 类型')
    balance = Column(Float, nullable=False, comment='余额或积分数量')
    threshold = Column(Float, comment='告警阈值')
    currency = Column(String(10), default='USD', comment='货币单位')
    balance_type = Column(String(20), default='credits', comment='类型: balance/credits')
    need_alarm = Column(Boolean, default=False, comment='是否需要告警')
    timestamp = Column(DateTime, default=datetime.utcnow, index=True, comment='记录时间')
    
    __table_args__ = (
        Index('idx_project_time', 'project_id', 'timestamp'),
        Index('idx_provider_time', 'provider', 'timestamp'),
        {'comment': '余额历史记录表'}
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'project_id': self.project_id,
            'project_name': self.project_name,
            'provider': self.provider,
            'balance': self.balance,
            'threshold': self.threshold,
            'currency': self.currency,
            'balance_type': self.balance_type,
            'need_alarm': self.need_alarm,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


class AlertHistory(Base):
    """告警历史记录"""
    __tablename__ = 'alert_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(200), nullable=False, index=True, comment='项目唯一标识')
    project_name = Column(String(200), nullable=False, comment='项目名称')
    alert_type = Column(String(50), nullable=False, index=True, comment='告警类型')
    status = Column(String(20), default='sent', comment='发送状态: sent/pending/failed')
    message = Column(Text, comment='告警消息')
    balance_value = Column(Float, comment='触发告警时的余额')
    threshold_value = Column(Float, comment='阈值')
    timestamp = Column(DateTime, default=datetime.utcnow, index=True, comment='告警时间')
    
    __table_args__ = (
        Index('idx_project_type_time', 'project_id', 'alert_type', 'timestamp'),
        {'comment': '告警历史记录表'}
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'project_id': self.project_id,
            'project_name': self.project_name,
            'alert_type': self.alert_type,
            'status': self.status,
            'message': self.message,
            'balance_value': self.balance_value,
            'threshold_value': self.threshold_value,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }


class SubscriptionHistory(Base):
    """订阅历史记录"""
    __tablename__ = 'subscription_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    subscription_id = Column(String(200), nullable=False, index=True, comment='订阅唯一标识')
    subscription_name = Column(String(200), nullable=False, comment='订阅名称')
    cycle_type = Column(String(20), nullable=False, comment='周期类型')
    days_until_renewal = Column(Integer, comment='距离续费天数')
    amount = Column(Float, default=0, comment='订阅金额')
    currency = Column(String(10), default='CNY', comment='货币')
    need_renewal = Column(Boolean, default=False, comment='是否需要续费')
    timestamp = Column(DateTime, default=datetime.utcnow, index=True, comment='记录时间')
    
    __table_args__ = (
        Index('idx_subscription_time', 'subscription_id', 'timestamp'),
        {'comment': '订阅历史记录表'}
    )
    
    def to_dict(self):
        """转换为字典"""
        return {
            'id': self.id,
            'subscription_id': self.subscription_id,
            'subscription_name': self.subscription_name,
            'cycle_type': self.cycle_type,
            'days_until_renewal': self.days_until_renewal,
            'amount': self.amount,
            'currency': self.currency,
            'need_renewal': self.need_renewal,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }
