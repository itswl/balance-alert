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
