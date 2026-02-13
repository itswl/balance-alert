#!/usr/bin/env python3
"""
配置验证模块
使用 dataclasses 验证配置文件结构
"""
from typing import Dict, Any, List, Optional, Literal
from dataclasses import dataclass, field
from enum import Enum


class CycleType(str, Enum):
    """订阅周期类型"""
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class ProjectType(str, Enum):
    """项目类型"""
    CREDITS = "credits"
    BALANCE = "balance"


class WebhookType(str, Enum):
    """Webhook 类型"""
    FEISHU = "feishu"
    DINGTALK = "dingtalk"
    WECOM = "wecom"
    CUSTOM = "custom"


@dataclass
class EmailConfig:
    """邮箱配置"""
    name: str
    host: str
    port: int
    username: str
    password: str
    use_ssl: bool = True
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EmailConfig":
        """从字典创建配置"""
        return cls(
            name=data.get('name', ''),
            host=data.get('host', ''),
            port=data.get('port', 993),
            username=data.get('username', ''),
            password=data.get('password', ''),
            use_ssl=data.get('use_ssl', True),
            enabled=data.get('enabled', True)
        )

    def validate(self) -> List[str]:
        """验证配置，返回错误列表"""
        errors = []
        if not self.host:
            errors.append("邮箱 host 不能为空")
        if not self.port or self.port <= 0:
            errors.append("邮箱 port 必须大于 0")
        if not self.username:
            errors.append("邮箱 username 不能为空")
        if not self.password:
            errors.append("邮箱 password 不能为空")
        return errors


@dataclass
class SubscriptionConfig:
    """订阅配置"""
    name: str
    renewal_day: int
    alert_days_before: int
    amount: float
    currency: str
    cycle_type: CycleType = CycleType.MONTHLY
    enabled: bool = True
    last_renewed_date: Optional[str] = None
    renewal_month: Optional[int] = None  # 年周期时使用

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubscriptionConfig":
        """从字典创建配置"""
        cycle_type_str = data.get('cycle_type', 'monthly')
        try:
            cycle_type = CycleType(cycle_type_str)
        except ValueError:
            cycle_type = CycleType.MONTHLY

        return cls(
            name=data.get('name', ''),
            renewal_day=int(data.get('renewal_day', 1)),
            alert_days_before=int(data.get('alert_days_before', 3)),
            amount=float(data.get('amount', 0)),
            currency=data.get('currency', 'CNY'),
            cycle_type=cycle_type,
            enabled=data.get('enabled', True),
            last_renewed_date=data.get('last_renewed_date'),
            renewal_month=data.get('renewal_month')
        )

    def validate(self) -> List[str]:
        """验证配置，返回错误列表"""
        errors = []
        if not self.name:
            errors.append("订阅 name 不能为空")

        if self.alert_days_before < 0:
            errors.append("alert_days_before 不能为负数")

        if self.amount < 0:
            errors.append("amount 不能为负数")

        # 根据周期类型验证 renewal_day
        if self.cycle_type == CycleType.WEEKLY:
            if self.renewal_day < 1 or self.renewal_day > 7:
                errors.append("周周期的续费日期必须在 1-7 之间")
        else:
            if self.renewal_day < 1 or self.renewal_day > 31:
                errors.append("续费日期必须在 1-31 之间")

        return errors


@dataclass
class ProjectConfig:
    """项目配置"""
    name: str
    provider: str
    api_key: str
    threshold: float
    type: ProjectType
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectConfig":
        """从字典创建配置"""
        type_str = data.get('type', 'credits')
        try:
            project_type = ProjectType(type_str)
        except ValueError:
            project_type = ProjectType.CREDITS

        return cls(
            name=data.get('name', ''),
            provider=data.get('provider', ''),
            api_key=data.get('api_key', ''),
            threshold=float(data.get('threshold', 0)),
            type=project_type,
            enabled=data.get('enabled', True)
        )

    def validate(self) -> List[str]:
        """验证配置，返回错误列表"""
        errors = []
        if not self.name:
            errors.append("项目 name 不能为空")
        if not self.provider:
            errors.append("项目 provider 不能为空")
        if not self.api_key:
            errors.append("项目 api_key 不能为空")
        if self.threshold < 0:
            errors.append("项目 threshold 不能为负数")
        return errors


@dataclass
class WebhookConfig:
    """Webhook 配置"""
    url: str
    type: WebhookType = WebhookType.FEISHU
    source: str = "credit-monitor"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WebhookConfig":
        """从字典创建配置"""
        type_str = data.get('type', 'feishu')
        try:
            webhook_type = WebhookType(type_str)
        except ValueError:
            webhook_type = WebhookType.CUSTOM

        return cls(
            url=data.get('url', ''),
            type=webhook_type,
            source=data.get('source', 'credit-monitor')
        )

    def validate(self) -> List[str]:
        """验证配置，返回错误列表"""
        errors = []
        if not self.url:
            errors.append("Webhook URL 不能为空")
        return errors


@dataclass
class SettingsConfig:
    """系统设置配置"""
    balance_refresh_interval_seconds: int = 3600
    max_concurrent_checks: int = 5
    min_refresh_interval_seconds: int = 60
    enable_smart_refresh: bool = False
    smart_refresh_threshold_percent: int = 5

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SettingsConfig":
        """从字典创建配置"""
        return cls(
            balance_refresh_interval_seconds=int(data.get('balance_refresh_interval_seconds', 3600)),
            max_concurrent_checks=int(data.get('max_concurrent_checks', 5)),
            min_refresh_interval_seconds=int(data.get('min_refresh_interval_seconds', 60)),
            enable_smart_refresh=bool(data.get('enable_smart_refresh', False)),
            smart_refresh_threshold_percent=int(data.get('smart_refresh_threshold_percent', 5))
        )

    def validate(self) -> List[str]:
        """验证配置，返回错误列表"""
        errors = []
        if self.balance_refresh_interval_seconds <= 0:
            errors.append("balance_refresh_interval_seconds 必须大于 0")
        if self.max_concurrent_checks < 1 or self.max_concurrent_checks > 20:
            errors.append("max_concurrent_checks 必须在 1-20 之间")
        if self.min_refresh_interval_seconds <= 0:
            errors.append("min_refresh_interval_seconds 必须大于 0")
        return errors


@dataclass
class AppConfig:
    """应用完整配置"""
    version: Optional[str] = None
    settings: SettingsConfig = field(default_factory=SettingsConfig)
    webhook: Optional[WebhookConfig] = None
    email: List[EmailConfig] = field(default_factory=list)
    subscriptions: List[SubscriptionConfig] = field(default_factory=list)
    projects: List[ProjectConfig] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        """从字典创建配置"""
        return cls(
            version=data.get('version'),
            settings=SettingsConfig.from_dict(data.get('settings', {})),
            webhook=WebhookConfig.from_dict(data.get('webhook', {})) if data.get('webhook') else None,
            email=[EmailConfig.from_dict(e) for e in data.get('email', [])],
            subscriptions=[SubscriptionConfig.from_dict(s) for s in data.get('subscriptions', [])],
            projects=[ProjectConfig.from_dict(p) for p in data.get('projects', [])]
        )

    def validate(self) -> Dict[str, List[str]]:
        """
        验证配置

        Returns:
            Dict[str, List[str]]: 各模块的错误信息列表
        """
        errors: Dict[str, List[str]] = {}

        # 验证设置
        settings_errors = self.settings.validate()
        if settings_errors:
            errors['settings'] = settings_errors

        # 验证 Webhook
        if self.webhook:
            webhook_errors = self.webhook.validate()
            if webhook_errors:
                errors['webhook'] = webhook_errors

        # 验证邮箱配置
        email_errors: List[str] = []
        for i, email in enumerate(self.email):
            email_errors.extend([f"email[{i}]: {e}" for e in email.validate()])
        if email_errors:
            errors['email'] = email_errors

        # 验证订阅配置
        subscription_errors: List[str] = []
        for i, sub in enumerate(self.subscriptions):
            subscription_errors.extend([f"subscriptions[{i}]: {e}" for e in sub.validate()])
        if subscription_errors:
            errors['subscriptions'] = subscription_errors

        # 验证项目配置
        project_errors: List[str] = []
        for i, project in enumerate(self.projects):
            project_errors.extend([f"projects[{i}]: {e}" for e in project.validate()])
        if project_errors:
            errors['projects'] = project_errors

        return errors

    def is_valid(self) -> bool:
        """检查配置是否有效"""
        return not self.validate()
