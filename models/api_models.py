#!/usr/bin/env python3
"""
API 请求验证模型

使用 Pydantic 进行请求数据验证，确保 API 输入安全可靠
"""
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator
from datetime import date


class AddSubscriptionRequest(BaseModel):
    """添加订阅请求"""
    name: str = Field(..., min_length=1, max_length=200, description="订阅名称")
    cycle_type: Literal['weekly', 'monthly', 'yearly'] = Field(..., description="续费周期类型")
    renewal_day: int = Field(..., ge=1, le=31, description="续费日期（1-31）")
    alert_days_before: int = Field(..., ge=0, le=365, description="提前告警天数")
    amount: float = Field(..., ge=0, description="订阅金额")
    currency: str = Field(default='CNY', min_length=3, max_length=3, description="货币代码（如 CNY, USD）")
    enabled: bool = Field(default=True, description="是否启用")
    last_renewed_date: Optional[str] = Field(default=None, description="上次续费日期（YYYY-MM-DD）")

    @field_validator('currency')
    @classmethod
    def validate_currency(cls, v: str) -> str:
        """验证货币代码"""
        v = v.upper()
        valid_currencies = ['CNY', 'USD', 'EUR', 'GBP', 'JPY', 'HKD', 'SGD']
        if v not in valid_currencies:
            raise ValueError(f'不支持的货币代码: {v}，支持: {", ".join(valid_currencies)}')
        return v

    @field_validator('last_renewed_date')
    @classmethod
    def validate_last_renewed_date(cls, v: Optional[str]) -> Optional[str]:
        """验证日期格式"""
        if v is None:
            return v
        try:
            date.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError('日期格式错误，应为 YYYY-MM-DD')

    @field_validator('renewal_day')
    @classmethod
    def validate_renewal_day(cls, v: int, info) -> int:
        """根据周期类型验证续费日期"""
        cycle_type = info.data.get('cycle_type')
        if cycle_type == 'weekly' and v > 7:
            raise ValueError('周循环的续费日期应在 1-7 之间')
        elif cycle_type == 'monthly' and v > 31:
            raise ValueError('月循环的续费日期应在 1-31 之间')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "name": "ChatGPT Plus 订阅",
                "cycle_type": "monthly",
                "renewal_day": 15,
                "alert_days_before": 3,
                "amount": 20.0,
                "currency": "USD",
                "enabled": True,
                "last_renewed_date": "2026-01-15"
            }
        }


class UpdateSubscriptionRequest(BaseModel):
    """更新订阅请求"""
    name: str = Field(..., min_length=1, max_length=200, description="订阅名称（用于查找）")
    new_name: Optional[str] = Field(default=None, min_length=1, max_length=200, description="新订阅名称")
    cycle_type: Optional[Literal['weekly', 'monthly', 'yearly']] = Field(default=None, description="续费周期类型")
    renewal_day: Optional[int] = Field(default=None, ge=1, le=31, description="续费日期（1-31）")
    alert_days_before: Optional[int] = Field(default=None, ge=0, le=365, description="提前告警天数")
    amount: Optional[float] = Field(default=None, ge=0, description="订阅金额")
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3, description="货币代码")
    enabled: Optional[bool] = Field(default=None, description="是否启用")
    last_renewed_date: Optional[str] = Field(default=None, description="上次续费日期（YYYY-MM-DD）")

    @field_validator('currency')
    @classmethod
    def validate_currency(cls, v: Optional[str]) -> Optional[str]:
        """验证货币代码"""
        if v is None:
            return v
        v = v.upper()
        valid_currencies = ['CNY', 'USD', 'EUR', 'GBP', 'JPY', 'HKD', 'SGD']
        if v not in valid_currencies:
            raise ValueError(f'不支持的货币代码: {v}')
        return v

    @field_validator('last_renewed_date')
    @classmethod
    def validate_last_renewed_date(cls, v: Optional[str]) -> Optional[str]:
        """验证日期格式"""
        if v is None:
            return v
        try:
            date.fromisoformat(v)
            return v
        except ValueError:
            raise ValueError('日期格式错误，应为 YYYY-MM-DD')


class DeleteSubscriptionRequest(BaseModel):
    """删除订阅请求"""
    name: str = Field(..., min_length=1, max_length=200, description="订阅名称")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "ChatGPT Plus 订阅"
            }
        }


class RefreshRequest(BaseModel):
    """刷新余额请求"""
    project_name: Optional[str] = Field(default=None, description="项目名称（可选，不指定则刷新所有）")
    force: bool = Field(default=False, description="是否强制刷新（忽略缓存）")

    class Config:
        json_schema_extra = {
            "example": {
                "project_name": "OpenRouter",
                "force": False
            }
        }


class AddEmailRequest(BaseModel):
    """添加邮箱配置请求"""
    name: str = Field(..., min_length=1, max_length=100, description="邮箱名称")
    host: str = Field(..., min_length=1, max_length=255, description="IMAP 服务器地址")
    port: int = Field(..., ge=1, le=65535, description="IMAP 端口")
    username: str = Field(..., min_length=1, max_length=255, description="邮箱用户名")
    password: str = Field(..., min_length=1, max_length=255, description="邮箱密码")
    use_ssl: bool = Field(default=True, description="是否使用 SSL")
    enabled: bool = Field(default=True, description="是否启用")

    @field_validator('host')
    @classmethod
    def validate_host(cls, v: str) -> str:
        """验证主机名"""
        if not v or v.isspace():
            raise ValueError('IMAP 主机不能为空')
        # 简单的主机名验证（允许域名和 IP）
        if not all(c.isalnum() or c in '.-_' for c in v):
            raise ValueError('IMAP 主机格式无效')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Gmail 邮箱",
                "host": "imap.gmail.com",
                "port": 993,
                "username": "user@gmail.com",
                "password": "app-password",
                "use_ssl": True,
                "enabled": True
            }
        }


class UpdateEmailRequest(BaseModel):
    """更新邮箱配置请求"""
    name: str = Field(..., min_length=1, max_length=100, description="邮箱名称（用于查找）")
    new_name: Optional[str] = Field(default=None, min_length=1, max_length=100, description="新邮箱名称")
    host: Optional[str] = Field(default=None, min_length=1, max_length=255, description="IMAP 服务器地址")
    port: Optional[int] = Field(default=None, ge=1, le=65535, description="IMAP 端口")
    username: Optional[str] = Field(default=None, min_length=1, max_length=255, description="邮箱用户名")
    password: Optional[str] = Field(default=None, min_length=1, max_length=255, description="邮箱密码")
    use_ssl: Optional[bool] = Field(default=None, description="是否使用 SSL")
    enabled: Optional[bool] = Field(default=None, description="是否启用")


class DeleteEmailRequest(BaseModel):
    """删除邮箱配置请求"""
    name: str = Field(..., min_length=1, max_length=100, description="邮箱名称")

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Gmail 邮箱"
            }
        }
