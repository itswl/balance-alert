"""
core/settings.py 测试

覆盖环境变量读取语义：
- 空白值（.env 模板常见 KEY=）视为未设置；
- 非法标量值在构造时报错（启动即失败，而非静默忽略）。
"""
import pytest
from pydantic import ValidationError

from core.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_env(monkeypatch):
    for key in (
        'CONFIG_ENCRYPTION_KEY', 'WEB_API_KEY',
        'ENABLE_DATABASE', 'ENABLE_SUBSCRIPTIONS', 'REQUEST_TIMEOUT',
        'WEB_PORT', 'BALANCE_REFRESH_INTERVAL_SECONDS', 'ALERT_COOLDOWN_SECONDS',
        'ALERT_SCHEDULE', 'EMAIL_SCAN_SCHEDULE', 'EMAIL_SCAN_DAYS', 'WEEKLY_REPORT_SCHEDULE',
        'BURN_RATE_WINDOW_DAYS', 'RUNWAY_ALERT_DAYS', 'SPEND_SPIKE_RATIO', 'SPEND_SPIKE_MIN_AMOUNT',
    ):
        monkeypatch.delenv(key, raising=False)


class TestWebApiKey:
    def test_set(self, monkeypatch):
        monkeypatch.setenv('WEB_API_KEY', ' key-with-space ')
        assert get_settings().resolved_web_api_key() == 'key-with-space'

    def test_blank_is_unset(self, monkeypatch):
        monkeypatch.setenv('WEB_API_KEY', '')
        assert get_settings().resolved_web_api_key() == ''

    def test_unset_returns_empty(self):
        assert get_settings().resolved_web_api_key() == ''


class TestEncryptionKey:
    def test_set(self, monkeypatch):
        monkeypatch.setenv('CONFIG_ENCRYPTION_KEY', 'realkey')
        assert get_settings().config_encryption_key == 'realkey'

    def test_blank_is_none(self, monkeypatch):
        # .env 模板常见 KEY=，留空不应被当成空字符串密钥
        monkeypatch.setenv('CONFIG_ENCRYPTION_KEY', '')
        assert get_settings().config_encryption_key is None

    def test_unset_is_none(self):
        assert get_settings().config_encryption_key is None


class TestEnvParsing:
    """空白值视为未设置；非法值在启动时报错。"""

    @pytest.mark.parametrize('value,expected', [
        ('true', True), ('True', True), ('1', True), ('yes', True), ('on', True),
        ('false', False), ('0', False), ('no', False),
    ])
    def test_valid_bool_tokens(self, monkeypatch, value, expected):
        monkeypatch.setenv('ENABLE_DATABASE', value)
        assert get_settings().enable_database is expected

    def test_invalid_bool_raises(self, monkeypatch):
        monkeypatch.setenv('ENABLE_DATABASE', 'enabled')
        with pytest.raises(ValidationError):
            get_settings()

    def test_invalid_int_raises(self, monkeypatch):
        monkeypatch.setenv('REQUEST_TIMEOUT', 'not-a-number')
        with pytest.raises(ValidationError):
            get_settings()

    def test_blank_optional_int_is_none(self, monkeypatch):
        monkeypatch.setenv('ALERT_COOLDOWN_SECONDS', '   ')
        assert get_settings().alert_cooldown_seconds is None

    def test_blank_int_uses_default(self, monkeypatch):
        monkeypatch.setenv('REQUEST_TIMEOUT', '')
        assert get_settings().request_timeout == 10

    def test_valid_int_overrides(self, monkeypatch):
        monkeypatch.setenv('WEB_PORT', '9000')
        assert get_settings().web_port == 9000


class TestCorsOriginList:
    def test_parses_comma_separated(self, monkeypatch):
        monkeypatch.setenv('CORS_ORIGINS', 'https://a.com, https://b.com ,')
        assert get_settings().cors_origin_list == ['https://a.com', 'https://b.com']

    def test_empty_is_empty_list(self):
        assert get_settings().cors_origin_list == []


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


class TestSchedules:
    """进程内定时任务时刻：默认沿用原 crontab，可用 off 关闭，格式错误启动即报错"""

    def test_defaults(self):
        from datetime import time
        settings = get_settings()
        assert settings.alert_schedule_times == [time(9, 0), time(15, 0)]
        assert settings.email_scan_schedule_times == [time(10, 0)]
        assert settings.email_scan_days == 1

    def test_custom_and_off(self, monkeypatch):
        from datetime import time
        monkeypatch.setenv('ALERT_SCHEDULE', '8:30, 15:00')
        monkeypatch.setenv('EMAIL_SCAN_SCHEDULE', 'off')
        monkeypatch.setenv('EMAIL_SCAN_DAYS', '7')
        settings = get_settings()
        assert settings.alert_schedule_times == [time(8, 30), time(15, 0)]
        assert settings.email_scan_schedule_times == []
        assert settings.email_scan_days == 7

    @pytest.mark.parametrize('key,value', [
        ('ALERT_SCHEDULE', '25:00'),
        ('EMAIL_SCAN_SCHEDULE', '9am'),
        ('EMAIL_SCAN_DAYS', '0'),
        ('EMAIL_SCAN_DAYS', '31'),
    ])
    def test_invalid_values_fail_fast(self, monkeypatch, key, value):
        monkeypatch.setenv(key, value)
        with pytest.raises(ValidationError):
            get_settings()


class TestRunwaySettings:
    """消耗分析与周报的配置"""

    def test_defaults(self):
        from datetime import time
        settings = get_settings()
        assert settings.burn_rate_window_days == 7
        assert settings.runway_alert_days == 7.0
        assert settings.spend_spike_ratio == 3.0
        assert settings.weekly_report_plan == ({1}, [time(9, 0)])

    def test_custom_weekly_report_plan(self, monkeypatch):
        from datetime import time
        monkeypatch.setenv('WEEKLY_REPORT_SCHEDULE', '周五 18:00')
        assert get_settings().weekly_report_plan == ({5}, [time(18, 0)])

    def test_weekly_report_can_be_disabled(self, monkeypatch):
        monkeypatch.setenv('WEEKLY_REPORT_SCHEDULE', 'off')
        assert get_settings().weekly_report_plan == (set(), [])

    def test_alerts_can_be_disabled_with_zero(self, monkeypatch):
        monkeypatch.setenv('RUNWAY_ALERT_DAYS', '0')
        monkeypatch.setenv('SPEND_SPIKE_RATIO', '0')
        settings = get_settings()
        assert settings.runway_alert_days == 0 and settings.spend_spike_ratio == 0

    @pytest.mark.parametrize('key,value', [
        ('WEEKLY_REPORT_SCHEDULE', 'Funday 09:00'),
        ('WEEKLY_REPORT_SCHEDULE', 'Mon 25:00'),
        ('BURN_RATE_WINDOW_DAYS', '0'),
        ('BURN_RATE_WINDOW_DAYS', '365'),
    ])
    def test_invalid_values_fail_fast(self, monkeypatch, key, value):
        monkeypatch.setenv(key, value)
        with pytest.raises(ValidationError):
            get_settings()
