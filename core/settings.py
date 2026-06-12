#!/usr/bin/env python3
"""
统一配置入口。

所有环境变量集中在这里声明（类型、默认值、别名），其它模块通过
``get_settings()`` 读取，不再各自散落地写 ``os.environ.get(...).lower() == 'true'``。

为什么每次都新建实例而不做模块级单例：
配置在运行期可能被改写（测试用 ``monkeypatch.setenv`` / ``patch.dict``，
入口脚本用 ``.env`` 注入），实例化成本极低，按需读取最直观也最不易踩坑。

.env 的加载仍由 :mod:`core.config_loader` 负责（写入 ``os.environ``），
这里只负责读取，从而保持测试用 ``clear=True`` 时的隔离行为。
"""
from typing import Any, Optional, Union, get_args, get_origin

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# pydantic 接受的布尔字面量（不区分大小写）；其余字符串会让 bool 字段校验报错。
_BOOL_TOKENS = frozenset({'true', 'false', '1', '0', 'yes', 'no', 'on', 'off', 't', 'f', 'y', 'n'})


def _field_scalar_types(annotation: Any) -> tuple:
    """从字段注解中提取标量基础类型（解开 Optional/Union）。"""
    if get_origin(annotation) is Union:
        return tuple(t for arg in get_args(annotation) for t in _field_scalar_types(arg))
    return (annotation,) if annotation in (int, float, bool) else ()


def _value_valid_for(value: str, scalar_types: tuple) -> bool:
    """判断字符串能否被对应标量类型接受（与 pydantic 的解析口径一致）。"""
    for scalar_type in scalar_types:
        if scalar_type is bool:
            if value.strip().lower() in _BOOL_TOKENS:
                return True
        else:
            try:
                scalar_type(value)
                return True
            except (TypeError, ValueError):
                continue
    return False


class AppSettings(BaseSettings):
    """应用级环境变量配置。

    可选能力（数据库 / 订阅 / 历史 / Prometheus）默认关闭，核心版只跑余额告警。
    取值为 ``None`` 的字段表示"未通过环境变量设置"，由调用方回退到 config.json 或内置默认。
    """

    model_config = SettingsConfigDict(extra='ignore', case_sensitive=False)

    @model_validator(mode='before')
    @classmethod
    def _lenient_env(cls, data: Any) -> Any:
        """对环境变量做宽容处理，丢弃无效值（回退到默认/None）而非报错。

        - 空白字符串（``.env`` 里常见的 ``KEY=``）一律视为未设置。
        - 标量字段（int/float/bool）拿到无法解析的字符串时也丢弃，沿用旧逻辑"非法即忽略"
          的语义，避免一个手滑的环境变量（如 ``ENABLE_X=enabled``）在 import 期或请求热
          路径里把 ``get_settings()`` 直接拖成报错。
        """
        if not isinstance(data, dict):
            return data

        cleaned = {}
        for key, value in data.items():
            if isinstance(value, str):
                if value.strip() == '':
                    continue
                scalar_types = _field_scalar_types(cls._field_annotation(key))
                if scalar_types and not _value_valid_for(value, scalar_types):
                    continue
            cleaned[key] = value
        return cleaned

    @classmethod
    def _field_annotation(cls, key: str) -> Any:
        """按字段名或别名定位字段注解（在 mode='before' 阶段 key 可能是别名）。"""
        field = cls.model_fields.get(key)
        if field is not None:
            return field.annotation
        for field_info in cls.model_fields.values():
            alias = field_info.validation_alias
            names = list(alias.choices) if isinstance(alias, AliasChoices) else [alias, field_info.alias]
            if key in names:
                return field_info.annotation
        return None

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
    cache_file_path: str = '/tmp/balance_cache.json'

    # ---- 数据库 ----
    database_url: str = 'sqlite:///./data/balance_alert.db'
    strict_database_errors: bool = False
    auto_encrypt_on_read: bool = True

    # ---- 敏感配置加密（接受 Fernet key 或口令）----
    # 拆成两个字段而非 AliasChoices：AliasChoices 是"首个出现即采用"，当
    # CONFIG_ENCRYPTION_KEY="" 留空时会盖过旧变量；这里用属性按"首个非空"解析，与旧逻辑一致。
    config_encryption_key_primary: Optional[str] = Field(default=None, alias='CONFIG_ENCRYPTION_KEY')
    config_encryption_key_legacy: Optional[str] = Field(default=None, alias='BALANCE_ALERT_ENCRYPTION_KEY')

    @property
    def config_encryption_key(self) -> Optional[str]:
        """生效的加密密钥：CONFIG_ENCRYPTION_KEY 优先，其次旧名 BALANCE_ALERT_ENCRYPTION_KEY。"""
        return self.config_encryption_key_primary or self.config_encryption_key_legacy

    # ---- Web 服务 ----
    web_port: int = 8080
    metrics_port: int = 9100
    app_version: str = '1.0.0'
    web_enable_cors: bool = False
    cors_origins: str = ''
    # 认证密钥：优先 WEB_API_KEY，兼容旧的 WEB_AUTH_API_KEY。
    # 同样拆字段 + 按"首个非空"解析，避免 AliasChoices 在主变量留空时吞掉旧变量。
    web_api_key_primary: Optional[str] = Field(default=None, alias='WEB_API_KEY')
    web_api_key_legacy: Optional[str] = Field(default=None, alias='WEB_AUTH_API_KEY')
    allow_legacy_web_api_key: bool = False
    legacy_api_key: Optional[str] = Field(default=None, alias='API_KEY')

    @property
    def cors_origin_list(self) -> list[str]:
        """逗号分隔的 CORS 白名单解析为列表。"""
        return [origin.strip() for origin in self.cors_origins.split(',') if origin.strip()]

    def resolved_web_api_key(self) -> str:
        """返回生效的 Web API Key：WEB_API_KEY > WEB_AUTH_API_KEY > （开关开启时）API_KEY。"""
        primary = self.web_api_key_primary or self.web_api_key_legacy
        if primary:
            return primary.strip()
        if self.allow_legacy_web_api_key and self.legacy_api_key:
            return self.legacy_api_key.strip()
        return ''


def get_settings() -> AppSettings:
    """读取当前环境变量并返回配置实例。

    每次调用都重新读取，以便运行期对环境变量的修改即时生效。
    """
    return AppSettings()
