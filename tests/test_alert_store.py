"""
告警去重与留痕：冷却时长优先级与数据库不可用时的降级
"""
import os
from unittest.mock import patch

import pytest

from services import alert_store


@pytest.fixture(autouse=True)
def _clear_cooldown_env(monkeypatch):
    for key in ('ALERT_COOLDOWN_SECONDS', 'SUBSCRIPTION_ALERT_COOLDOWN_SECONDS'):
        monkeypatch.delenv(key, raising=False)


class TestCooldownSeconds:
    """SUBSCRIPTION_ALERT_COOLDOWN_SECONDS > ALERT_COOLDOWN_SECONDS > 默认 24 小时"""

    def test_default(self):
        assert alert_store.cooldown_seconds('balance') == 86400
        assert alert_store.cooldown_seconds('subscription') == 86400

    def test_generic_env_applies_to_both(self, monkeypatch):
        monkeypatch.setenv('ALERT_COOLDOWN_SECONDS', '3600')
        assert alert_store.cooldown_seconds('balance') == 3600
        assert alert_store.cooldown_seconds('subscription') == 3600

    def test_subscription_specific_wins(self, monkeypatch):
        monkeypatch.setenv('ALERT_COOLDOWN_SECONDS', '3600')
        monkeypatch.setenv('SUBSCRIPTION_ALERT_COOLDOWN_SECONDS', '7200')
        assert alert_store.cooldown_seconds('balance') == 3600
        assert alert_store.cooldown_seconds('subscription') == 7200

    def test_subscription_falls_back_to_generic(self, monkeypatch):
        monkeypatch.setenv('ALERT_COOLDOWN_SECONDS', '600')
        assert alert_store.cooldown_seconds('subscription') == 600

    def test_negative_clamped_to_zero(self, monkeypatch):
        monkeypatch.setenv('ALERT_COOLDOWN_SECONDS', '-100')
        assert alert_store.cooldown_seconds('balance') == 0


class TestDatabaseUnavailable:
    """数据库导不进来时全部降级，不能影响告警发送"""

    def test_in_cooldown_allows_alert(self):
        with patch.object(alert_store, 'DB_AVAILABLE', False):
            assert alert_store.in_cooldown('id', 'low_balance', 3600) is False

    def test_email_dedup_allows_alert(self):
        with patch.object(alert_store, 'DB_AVAILABLE', False):
            assert alert_store.email_alert_sent_recently('mb', 's', 'sub', 'd', 7) is False

    def test_writes_are_noop(self):
        with patch.object(alert_store, 'DB_AVAILABLE', False):
            assert alert_store.record_alert('id', 'n', 't', 'm') is None
            assert alert_store.record_balance('id', 'n', 'p', 1.0, 2.0, 'credits', False) is None
            assert alert_store.record_email_alert('mb', 's', 'sub', 'd') is None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
