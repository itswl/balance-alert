"""
core/settings.py 测试

重点覆盖从散落 os.environ 迁移到 pydantic-settings 时容易回归的语义：
- 多变量名回退按"首个非空"解析（AliasChoices 默认是"首个出现"，留空主变量会吞掉旧变量）；
- 非法标量环境变量（含 bool）宽容降级，不在 import / 请求热路径抛错。
"""
import pytest

from core.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_env(monkeypatch):
    for key in (
        'CONFIG_ENCRYPTION_KEY', 'BALANCE_ALERT_ENCRYPTION_KEY',
        'WEB_API_KEY', 'WEB_AUTH_API_KEY', 'API_KEY', 'ALLOW_LEGACY_WEB_API_KEY',
        'ENABLE_DATABASE', 'ENABLE_SUBSCRIPTIONS', 'REQUEST_TIMEOUT',
        'WEB_PORT', 'BALANCE_REFRESH_INTERVAL_SECONDS', 'ALERT_COOLDOWN_SECONDS',
    ):
        monkeypatch.delenv(key, raising=False)


class TestWebApiKeyPrecedence:
    """Web API Key 的多变量回退（WEB_API_KEY > WEB_AUTH_API_KEY > API_KEY）。"""

    def test_empty_primary_falls_back_to_legacy(self, monkeypatch):
        # 关键回归：主变量留空（.env 模板常见 KEY=）时应回退到旧变量，而非返回空。
        monkeypatch.setenv('WEB_API_KEY', '')
        monkeypatch.setenv('WEB_AUTH_API_KEY', 'realkey')
        assert get_settings().resolved_web_api_key() == 'realkey'

    def test_primary_wins_over_legacy(self, monkeypatch):
        monkeypatch.setenv('WEB_API_KEY', 'primary')
        monkeypatch.setenv('WEB_AUTH_API_KEY', 'secondary')
        assert get_settings().resolved_web_api_key() == 'primary'

    def test_legacy_only(self, monkeypatch):
        monkeypatch.setenv('WEB_AUTH_API_KEY', 'realkey')
        assert get_settings().resolved_web_api_key() == 'realkey'

    def test_api_key_used_only_when_allowed(self, monkeypatch):
        monkeypatch.setenv('API_KEY', 'legacy')
        assert get_settings().resolved_web_api_key() == ''  # 开关未开

        monkeypatch.setenv('ALLOW_LEGACY_WEB_API_KEY', 'true')
        assert get_settings().resolved_web_api_key() == 'legacy'

    def test_unset_returns_empty(self):
        assert get_settings().resolved_web_api_key() == ''


class TestEncryptionKeyPrecedence:
    """加密密钥的多变量回退（CONFIG_ENCRYPTION_KEY > BALANCE_ALERT_ENCRYPTION_KEY）。"""

    def test_empty_primary_falls_back_to_legacy(self, monkeypatch):
        # 关键回归：主变量留空不应吞掉旧变量，否则密钥变 None → 明文落库。
        monkeypatch.setenv('CONFIG_ENCRYPTION_KEY', '')
        monkeypatch.setenv('BALANCE_ALERT_ENCRYPTION_KEY', 'realkey')
        assert get_settings().config_encryption_key == 'realkey'

    def test_primary_wins(self, monkeypatch):
        monkeypatch.setenv('CONFIG_ENCRYPTION_KEY', 'prim')
        monkeypatch.setenv('BALANCE_ALERT_ENCRYPTION_KEY', 'leg')
        assert get_settings().config_encryption_key == 'prim'

    def test_unset_is_none(self):
        assert get_settings().config_encryption_key is None


class TestLenientEnv:
    """非法/空白环境变量宽容降级，不抛错。"""

    def test_invalid_bool_falls_back_to_default(self, monkeypatch):
        # 旧代码 .lower()=='true' 永不报错；迁移后 bool 字段不能因手滑值在 import 期崩溃。
        monkeypatch.setenv('ENABLE_DATABASE', 'enabled')
        assert get_settings().enable_database is False

    @pytest.mark.parametrize('value,expected', [
        ('true', True), ('True', True), ('1', True), ('yes', True), ('on', True),
        ('false', False), ('0', False), ('no', False),
    ])
    def test_valid_bool_tokens(self, monkeypatch, value, expected):
        monkeypatch.setenv('ENABLE_DATABASE', value)
        assert get_settings().enable_database is expected

    def test_invalid_int_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv('REQUEST_TIMEOUT', 'not-a-number')
        assert get_settings().request_timeout == 10  # 默认值

    def test_blank_optional_int_is_none(self, monkeypatch):
        monkeypatch.setenv('ALERT_COOLDOWN_SECONDS', '   ')
        assert get_settings().alert_cooldown_seconds is None

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
