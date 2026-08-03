#!/usr/bin/env python3
"""
API 请求验证模型

使用 Pydantic 进行请求数据验证，配合 web.middleware.validate_request 使用
"""
from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


def _validate_iso_date(v: Optional[str]) -> Optional[str]:
    if v is None:
        return v
    try:
        date.fromisoformat(v)
        return v
    except ValueError:
        raise ValueError('日期格式错误，应为 YYYY-MM-DD')


def _validate_renewal_day(cycle_type: Optional[str], renewal_day: int) -> None:
    if cycle_type == 'weekly' and renewal_day > 7:
        raise ValueError('周循环的续费日期应在 1-7 之间')
    if cycle_type == 'monthly' and renewal_day > 31:
        raise ValueError('月循环的续费日期应在 1-31 之间')
    if cycle_type == 'yearly' and renewal_day > 31:
        try:
            date(2024, renewal_day // 100, renewal_day % 100)
        except ValueError:
            raise ValueError('年循环的续费日期应为有效 MMDD，如 315 表示 3月15日')


class AddSubscriptionRequest(BaseModel):
    """添加订阅请求"""
    name: str = Field(..., min_length=1, max_length=200, description="订阅名称")
    owner_project: Optional[str] = Field(default=None, min_length=1, max_length=200, description="所属项目名称")
    cycle_type: Literal['weekly', 'monthly', 'yearly'] = Field(..., description="续费周期类型")
    renewal_day: int = Field(..., ge=1, le=1231, description="续费日期（月/周使用 1-31，年付使用 MMDD）")
    alert_days_before: int = Field(..., ge=0, le=365, description="提前告警天数")
    amount: float = Field(..., ge=0, description="订阅金额")
    enabled: bool = Field(default=True, description="是否启用")
    last_renewed_date: Optional[str] = Field(default=None, description="上次续费日期（YYYY-MM-DD）")

    @field_validator('last_renewed_date')
    @classmethod
    def validate_last_renewed_date(cls, v: Optional[str]) -> Optional[str]:
        return _validate_iso_date(v)

    @field_validator('renewal_day')
    @classmethod
    def validate_renewal_day(cls, v: int, info) -> int:
        _validate_renewal_day(info.data.get('cycle_type'), v)
        return v


class UpdateSubscriptionRequest(BaseModel):
    """更新订阅请求"""
    name: str = Field(..., min_length=1, max_length=200, description="订阅名称（用于查找）")
    new_name: Optional[str] = Field(default=None, min_length=1, max_length=200, description="新订阅名称")
    owner_project: Optional[str] = Field(default=None, min_length=1, max_length=200, description="所属项目名称")
    cycle_type: Optional[Literal['weekly', 'monthly', 'yearly']] = Field(default=None, description="续费周期类型")
    renewal_day: Optional[int] = Field(default=None, ge=1, le=1231, description="续费日期（月/周使用 1-31，年付使用 MMDD）")
    alert_days_before: Optional[int] = Field(default=None, ge=0, le=365, description="提前告警天数")
    amount: Optional[float] = Field(default=None, ge=0, description="订阅金额")
    enabled: Optional[bool] = Field(default=None, description="是否启用")
    last_renewed_date: Optional[str] = Field(default=None, description="上次续费日期（YYYY-MM-DD）")

    @field_validator('last_renewed_date')
    @classmethod
    def validate_last_renewed_date(cls, v: Optional[str]) -> Optional[str]:
        return _validate_iso_date(v)

    @model_validator(mode='after')
    def validate_cycle_renewal_day(self):
        if self.renewal_day is not None and self.cycle_type is not None:
            _validate_renewal_day(self.cycle_type, self.renewal_day)
        return self


class DeleteSubscriptionRequest(BaseModel):
    """删除订阅请求"""
    name: str = Field(..., min_length=1, max_length=200, description="订阅名称")
