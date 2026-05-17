#!/usr/bin/env python3
"""
数据库模型

定义数据表结构
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, Index
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()


def utcnow() -> datetime:
    """Return naive UTC datetime for compatibility with existing columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class BalanceHistory(Base):
    """余额历史记录"""
    __tablename__ = 'balance_history'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(200), nullable=False, index=True, comment='项目唯一标识')
    project_name = Column(String(200), nullable=False, comment='项目名称')
    provider = Column(String(50), nullable=False, index=True, comment='Provider 类型')
    balance = Column(Float, nullable=False, comment='余额数量')
    threshold = Column(Float, comment='告警阈值')
    balance_type = Column(String(20), default='credits', comment='类型: balance/credits')
    need_alarm = Column(Boolean, default=False, comment='是否需要告警')
    timestamp = Column(DateTime, default=utcnow, index=True, comment='记录时间')
    
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
    timestamp = Column(DateTime, default=utcnow, index=True, comment='告警时间')
    
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


class ProjectConfig(Base):
    """项目配置表"""
    __tablename__ = 'project_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, unique=True, comment='项目名称')
    owner_project = Column(String(200), nullable=True, index=True, comment='所属项目名称')
    provider = Column(String(50), nullable=False, comment='Provider 类型')
    api_key = Column(Text, nullable=False, comment='API Key（可加密存储）')
    threshold = Column(Float, default=100.0, comment='告警阈值')
    type = Column(String(20), default='credits', comment='类型: balance/credits')
    enabled = Column(Boolean, default=True, comment='是否启用')
    created_at = Column(DateTime, default=utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, comment='更新时间')

    __table_args__ = (
        {'comment': '项目配置表'}
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'owner_project': self.owner_project,
            'provider': self.provider,
            'api_key': self.api_key,
            'threshold': self.threshold,
            'type': self.type,
            'enabled': self.enabled
        }


class SubscriptionConfig(Base):
    """订阅配置表"""
    __tablename__ = 'subscription_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, unique=True, comment='订阅名称')
    owner_project = Column(String(200), nullable=True, index=True, comment='所属项目名称')
    cycle_type = Column(String(20), default='monthly', comment='周期类型')
    renewal_day = Column(Integer, default=1, comment='续费日')
    alert_days_before = Column(Integer, default=3, comment='提前告警天数')
    amount = Column(Float, default=0.0, comment='订阅金额')
    enabled = Column(Boolean, default=True, comment='是否启用')
    last_renewed_date = Column(String(20), nullable=True, comment='上次续费日期 (YYYY-MM-DD)')
    created_at = Column(DateTime, default=utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, comment='更新时间')

    __table_args__ = (
        {'comment': '订阅配置表'}
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'owner_project': self.owner_project,
            'cycle_type': self.cycle_type,
            'renewal_day': self.renewal_day,
            'alert_days_before': self.alert_days_before,
            'amount': self.amount,
            'enabled': self.enabled,
            'last_renewed_date': self.last_renewed_date
        }

class EmailConfig(Base):
    """邮箱配置表"""
    __tablename__ = 'email_config'

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, unique=True, comment='邮箱显示名称/别名')
    host = Column(String(200), nullable=False, comment='IMAP 服务器地址')
    port = Column(Integer, default=993, comment='IMAP 端口')
    username = Column(String(200), nullable=False, comment='邮箱账号')
    password = Column(Text, nullable=False, comment='邮箱授权码/密码（可加密存储）')
    use_ssl = Column(Boolean, default=True, comment='是否使用 SSL')
    enabled = Column(Boolean, default=True, comment='是否启用')
    created_at = Column(DateTime, default=utcnow, comment='创建时间')
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, comment='更新时间')

    __table_args__ = (
        {'comment': '邮箱监听配置表'}
    )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'host': self.host,
            'port': self.port,
            'username': self.username,
            'password': self.password,
            'use_ssl': self.use_ssl,
            'enabled': self.enabled
        }


class EmailAlertHistory(Base):
    """邮件告警历史记录"""
    __tablename__ = 'email_alert_history'

    id = Column(Integer, primary_key=True, autoincrement=True)
    mailbox = Column(String(200), nullable=False, index=True, comment='被扫描的邮箱账号')
    sender = Column(String(200), nullable=False, comment='发件人')
    subject = Column(String(500), nullable=False, comment='邮件主题')
    date = Column(String(100), nullable=False, comment='邮件发送日期')
    service_name = Column(String(200), comment='提取到的服务名称')
    amount = Column(Float, comment='提取到的账单金额')
    matched_keywords = Column(Text, comment='匹配到的告警关键词 (JSON 格式)')
    alert_sent = Column(Boolean, default=False, comment='是否成功发送 Webhook 告警')
    timestamp = Column(DateTime, default=utcnow, index=True, comment='扫描入库时间')

    __table_args__ = (
        Index('idx_email_mailbox_time', 'mailbox', 'timestamp'),
        {'comment': '扫描到的告警邮件历史记录'}
    )

    def to_dict(self):
        return {
            'id': self.id,
            'mailbox': self.mailbox,
            'sender': self.sender,
            'subject': self.subject,
            'date': self.date,
            'service_name': self.service_name,
            'amount': self.amount,
            'matched_keywords': self.matched_keywords,
            'alert_sent': self.alert_sent,
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
    need_renewal = Column(Boolean, default=False, comment='是否需要续费')
    timestamp = Column(DateTime, default=utcnow, index=True, comment='记录时间')
    
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
            'need_renewal': self.need_renewal,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None
        }
