#!/usr/bin/env python3
"""
统一配置入口。

所有环境变量集中在这里声明（类型、默认值），其它模块通过
``get_settings()`` 读取，不再各自散落地写 ``os.environ.get(...).lower() == 'true'``。

为什么每次都新建实例而不做模块级单例：
配置在运行期可能被改写（测试用 ``monkeypatch.setenv`` / ``patch.dict``，
入口脚本用 ``.env`` 注入），实例化成本极低，按需读取最直观也最不易踩坑。

.env 的加载仍由 :mod:`core.config_loader` 负责（写入 ``os.environ``），
这里只负责读取，从而保持测试用 ``clear=True`` 时的隔离行为。
"""
from typing import Any, Optional

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.timeutil import parse_daily_times, parse_weekly_schedule


class AppSettings(BaseSettings):
    """应用级环境变量配置。

    可选能力（数据库 / 订阅 / 历史 / Prometheus）默认关闭，核心版只跑余额告警。
    取值为 ``None`` 的字段表示"未通过环境变量设置"，由调用方回退到内置默认。
    环境变量值非法（如 ``ENABLE_X=enabled``）会在启动时直接报错，而不是静默忽略。
    """

    model_config = SettingsConfigDict(extra='ignore', case_sensitive=False)

    @model_validator(mode='before')
    @classmethod
    def _drop_blank_env(cls, data: Any) -> Any:
        """``.env`` 里常见的 ``KEY=`` 空值一律视为未设置。"""
        if not isinstance(data, dict):
            return data
        return {k: v for k, v in data.items() if not (isinstance(v, str) and v.strip() == '')}

    # ---- 可选能力开关 ----
    enable_database: bool = False
    enable_dynamic_config: bool = False
    enable_history_api: bool = False
    enable_subscriptions: bool = False
    enable_prometheus: bool = False
    enable_web_alarm: bool = False

    # ---- 调度与并发（None = 未设置，回退到默认）----
    balance_refresh_interval_seconds: Optional[int] = None
    max_concurrent_checks: Optional[int] = None
    alert_cooldown_seconds: Optional[int] = None
    subscription_alert_cooldown_seconds: Optional[int] = None

    # ---- Webhook ----
    webhook_url: Optional[str] = None
    webhook_source: Optional[str] = None
    webhook_type: Optional[str] = None

    # ---- 进程内定时任务（替代 cron；时刻按进程本地时区，容器里由 TZ 决定）----
    # 多个时刻用逗号分隔，填 off 关闭该任务
    alert_schedule: str = '09:00,15:00'         # 余额 + 订阅真实告警检查
    email_scan_schedule: str = '10:00'          # 邮箱扫描（发送真实告警）
    email_scan_days: int = 1                    # 定时邮箱扫描覆盖最近几天
    # 告警关键词：逗号分隔。alert 整体替换默认表，extra 在默认之上追加
    email_alert_keywords: str = ''
    email_extra_alert_keywords: str = ''
    weekly_report_schedule: str = 'Mon 09:00'   # 周报，格式「星期 时刻」，星期可省略表示每天

    # ---- 消耗与跑道分析（需要数据库历史；阈值设 0 关闭对应告警）----
    burn_rate_window_days: int = 7        # 算日均消耗用最近几天
    runway_alert_days: float = 7.0        # 按当前速率还能用几天就告警
    spend_spike_ratio: float = 3.0        # 今日消耗是日常中位数的几倍算突增
    spend_spike_min_amount: float = 1.0   # 今日消耗低于这个绝对值不报突增，避免噪音

    # ---- HTTP / 扫描 ----
    request_timeout: int = 10
    max_emails_to_scan: int = 1000
    response_cache_ttl: int = 300  # 同一 provider+key 的余额结果缓存秒数，防止手动刷新打爆上游

    # ---- 日志 ----
    log_level: str = 'INFO'
    log_format: str = 'text'  # text 或 json
    log_file: Optional[str] = None

    # ---- 数据库 ----
    database_url: str = 'sqlite:///./data/balance_alert.db'
    strict_database_errors: bool = False
    auto_encrypt_on_read: bool = True

    # ---- 敏感配置加密（接受 Fernet key 或口令）----
    config_encryption_key: Optional[str] = None

    # ---- Web 服务 ----
    web_port: int = 8080
    metrics_port: int = 9100
    app_version: str = '1.0.0'
    web_enable_cors: bool = False
    cors_origins: str = ''
    web_api_key: Optional[str] = None

    @field_validator('alert_schedule', 'email_scan_schedule')
    @classmethod
    def _validate_schedule(cls, v: str) -> str:
        parse_daily_times(v)  # 格式不对直接抛 ValueError，启动即报错
        return v

    @field_validator('email_scan_days')
    @classmethod
    def _validate_email_scan_days(cls, v: int) -> int:
        if not 1 <= v <= 30:
            raise ValueError('EMAIL_SCAN_DAYS 必须在 1-30 之间')
        return v

    @field_validator('weekly_report_schedule')
    @classmethod
    def _validate_weekly_schedule(cls, v: str) -> str:
        parse_weekly_schedule(v)  # 格式不对直接抛 ValueError，启动即报错
        return v

    @field_validator('burn_rate_window_days')
    @classmethod
    def _validate_burn_window(cls, v: int) -> int:
        if not 1 <= v <= 90:
            raise ValueError('BURN_RATE_WINDOW_DAYS 必须在 1-90 之间')
        return v

    @property
    def alert_schedule_times(self) -> list:
        return parse_daily_times(self.alert_schedule)

    @property
    def email_scan_schedule_times(self) -> list:
        return parse_daily_times(self.email_scan_schedule)

    @staticmethod
    def _split_list(text: str) -> list:
        return [item.strip() for item in (text or '').split(',') if item.strip()]

    @property
    def alert_keyword_override(self) -> list:
        return self._split_list(self.email_alert_keywords)

    @property
    def alert_keyword_extras(self) -> list:
        return self._split_list(self.email_extra_alert_keywords)

    @property
    def weekly_report_plan(self) -> tuple:
        """(星期集合, 时刻列表)，都为空表示关闭"""
        return parse_weekly_schedule(self.weekly_report_schedule)

    @property
    def cors_origin_list(self) -> list[str]:
        """逗号分隔的 CORS 白名单解析为列表。"""
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]

    def resolved_web_api_key(self) -> str:
        """返回生效的 Web API Key。"""
        return (self.web_api_key or '').strip()


def get_settings() -> AppSettings:
    """读取当前环境变量并返回配置实例。

    每次调用都重新读取，以便运行期对环境变量的修改即时生效。
    """
    return AppSettings()
