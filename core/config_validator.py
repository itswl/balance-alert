#!/usr/bin/env python3
"""
配置验证模块

用 pydantic 校验 config.json 的业务数据（projects/subscriptions/email）。

两阶段语义（保持对外接口不变）：
- ``XxxConfig.from_dict(data)`` 宽容构造，非法数值回退默认值，不抛异常；
- ``.validate()`` 返回错误信息列表（business 规则），``AppConfig.validate()`` 汇总成按节分组的字典。

settings 与 webhook 的取值/类型校验已由 :mod:`core.settings` 接管，这里不再重复。
"""
from typing import Dict, Any, List, Optional
from enum import Enum
from datetime import date

from pydantic import BaseModel, ConfigDict, field_validator


def _safe_int(value: Any, default: int) -> int:
    """安全转换为 int，非法值返回默认值"""
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def _safe_float(value: Any, default: float) -> float:
    """安全转换为 float，非法值返回默认值"""
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class CycleType(str, Enum):
    """订阅周期类型"""
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class ProjectType(str, Enum):
    """项目类型"""
    CREDITS = "credits"
    BALANCE = "balance"


class _ConfigBase(BaseModel):
    """允许多余字段、宽容构造的基类。"""
    model_config = ConfigDict(extra='ignore')

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "_ConfigBase":
        return cls.model_validate(data or {})

    def validate(self) -> List[str]:  # noqa: D401 - 返回错误列表，不抛异常
        return []


class EmailConfig(_ConfigBase):
    """邮箱配置"""
    name: str = ''
    host: str = ''
    port: int = 993
    username: str = ''
    password: str = ''
    use_ssl: bool = True
    enabled: bool = True

    @field_validator('port', mode='before')
    @classmethod
    def _coerce_port(cls, v: Any) -> int:
        return _safe_int(v, 993)

    def validate(self) -> List[str]:
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


class SubscriptionConfig(_ConfigBase):
    """订阅配置"""
    name: str = ''
    renewal_day: int = 1
    alert_days_before: int = 3
    amount: float = 0.0
    owner_project: Optional[str] = None
    cycle_type: CycleType = CycleType.MONTHLY
    enabled: bool = True
    last_renewed_date: Optional[str] = None
    renewal_month: Optional[int] = None  # 年周期时使用

    @field_validator('renewal_day', 'alert_days_before', mode='before')
    @classmethod
    def _coerce_int_fields(cls, v: Any, info) -> int:
        defaults = {'renewal_day': 1, 'alert_days_before': 3}
        return _safe_int(v, defaults.get(info.field_name, 0))

    @field_validator('amount', mode='before')
    @classmethod
    def _coerce_amount(cls, v: Any) -> float:
        return _safe_float(v, 0.0)

    @field_validator('cycle_type', mode='before')
    @classmethod
    def _coerce_cycle(cls, v: Any) -> Any:
        try:
            return CycleType(v)
        except ValueError:
            return CycleType.MONTHLY

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SubscriptionConfig":
        data = dict(data or {})
        if not data.get('owner_project') and data.get('project'):
            data['owner_project'] = data['project']
        return cls.model_validate(data)

    def validate(self) -> List[str]:
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
        elif self.cycle_type == CycleType.YEARLY:
            if self.renewal_day <= 31 and self.last_renewed_date:
                pass  # 兼容旧配置：年付日期由 last_renewed_date 推导
            elif self.renewal_day < 101 or self.renewal_day > 1231:
                errors.append("年周期的续费日期必须为 MMDD 格式（如 315 表示 3月15日）")
            else:
                month = self.renewal_day // 100
                day = self.renewal_day % 100
                try:
                    date(2024, month, day)
                except ValueError:
                    errors.append("年周期的续费日期不是有效日期")
        else:
            if self.renewal_day < 1 or self.renewal_day > 31:
                errors.append("续费日期必须在 1-31 之间")

        return errors


class ProjectConfig(_ConfigBase):
    """项目配置"""
    name: str = ''
    provider: str = ''
    api_key: str = ''
    threshold: float = 0.0
    type: ProjectType = ProjectType.CREDITS
    owner_project: Optional[str] = None
    enabled: bool = True

    @field_validator('threshold', mode='before')
    @classmethod
    def _coerce_threshold(cls, v: Any) -> float:
        return _safe_float(v, 0.0)

    @field_validator('type', mode='before')
    @classmethod
    def _coerce_type(cls, v: Any) -> Any:
        try:
            return ProjectType(v)
        except ValueError:
            return ProjectType.CREDITS

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectConfig":
        data = dict(data or {})
        if not data.get('owner_project') and data.get('project'):
            data['owner_project'] = data['project']
        return cls.model_validate(data)

    def validate(self) -> List[str]:
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


class AppConfig(_ConfigBase):
    """应用配置（仅校验业务数据；settings/webhook 由 core.settings 负责）。"""
    version: Optional[str] = None
    email: List[EmailConfig] = []
    subscriptions: List[SubscriptionConfig] = []
    projects: List[ProjectConfig] = []

    @field_validator('email', 'subscriptions', 'projects', mode='before')
    @classmethod
    def _none_to_empty(cls, v: Any) -> Any:
        return v or []

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        data = dict(data or {})
        return cls(
            version=data.get('version'),
            email=[EmailConfig.from_dict(e) for e in (data.get('email') or [])],
            subscriptions=[SubscriptionConfig.from_dict(s) for s in (data.get('subscriptions') or [])],
            projects=[ProjectConfig.from_dict(p) for p in (data.get('projects') or [])],
        )

    def validate(self) -> Dict[str, List[str]]:
        """逐节收集错误，返回 {节名: [错误...]}。无错误返回空字典。"""
        errors: Dict[str, List[str]] = {}

        sections = [
            ('email', self.email),
            ('subscriptions', self.subscriptions),
            ('projects', self.projects),
        ]
        for key, items in sections:
            section_errors: List[str] = []
            for i, item in enumerate(items):
                section_errors.extend([f"{key}[{i}]: {e}" for e in item.validate()])
            if section_errors:
                errors[key] = section_errors

        return errors

    def is_valid(self) -> bool:
        """检查配置是否有效"""
        return not self.validate()
