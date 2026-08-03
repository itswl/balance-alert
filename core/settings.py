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

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """应用级环境变量配置。

    可选能力（数据库 / 订阅 / 历史 / Prometheus）默认关闭，核心版只跑余额告警。
    取值为 ``None`` 的字段表示"未通过环境变量设置"，由调用方回退到 config.json 或内置默认。
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

    # ---- 配置文件路径 ----
    config_path: str = 'config.json'

    # ---- 可选能力开关 ----
    enable_database: bool = False
    enable_dynamic_config: bool = False
    enable_history_api: bool = False
    enable_subscriptions: bool = False
    enable_prometheus: bool = False
    enable_web_alarm: bool = False

    # ---- 调度与并发（None = 未设置，回退到 config.json/settings 或默认）----
    balance_refresh_interval_seconds: Optional[int] = None
    max_concurrent_checks: Optional[int] = None
    alert_cooldown_seconds: Optional[int] = None
    subscription_alert_cooldown_seconds: Optional[int] = None

    # ---- Webhook（None = 未设置，回退到 config.json/webhook）----
    webhook_url: Optional[str] = None
    webhook_source: Optional[str] = None
    webhook_type: Optional[str] = None

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
