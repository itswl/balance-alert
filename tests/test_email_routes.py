"""
邮箱扫描页面接口测试 — 邮箱配置读写、扫描触发与结果查询、历史告警邮件
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from core.state_manager import StateManager
from web.app import create_app

AUTH = {'X-API-Key': 'test-key'}

_MAILBOX = {
    'name': '工作邮箱', 'host': 'imap.example.com', 'port': 993,
    'username': 'me@example.com', 'password': 'secret', 'use_ssl': True, 'enabled': True,
}


def _scan_summary(**overrides):
    summary = {
        'days': 3,
        'dry_run': True,
        'mailboxes': [{
            'name': '工作邮箱', 'host': 'imap.example.com', 'port': 993, 'username': 'me@example.com',
            'total_emails': 12, 'alert_count': 1, 'success': True, 'error': None,
        }],
        'total_emails': 12,
        'total_alerts': 1,
        'alerts_sent': 0,
        'results': [{
            'mailbox': '工作邮箱', 'subject': '【阿里云】余额不足提醒', 'sender': 'noreply@aliyun.com',
            'date': 'Mon, 01 Sep 2026 10:00:00 +0800', 'keywords': ['余额不足'],
            'service_name': '阿里云', 'amount': 12.5, 'alert_sent': False,
        }],
    }
    summary.update(overrides)
    return summary


def _post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type='application/json', headers=AUTH)


@pytest.fixture
def state_manager():
    return StateManager()


@pytest.fixture
def client(state_manager, monkeypatch):
    monkeypatch.setenv('WEB_API_KEY', 'test-key')
    app = create_app(state_manager)
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def fake_repo():
    """把 config_db_write 换成直接调用假 repo，便于断言写入的数据"""
    repo = MagicMock()
    repo.upsert.return_value = True
    repo.delete.return_value = True
    with patch('web.routes.email.config_db_write', side_effect=lambda action: bool(action(repo))):
        yield repo


# ==================== 邮箱配置 ====================

class TestMailboxConfigEndpoints:

    def test_list_mailboxes_always_available_and_masked(self, client):
        """不开动态配置也能列出邮箱，密码脱敏"""
        with patch('web.routes.email.load_config_safe', return_value={'email': [dict(_MAILBOX)]}):
            response = client.get('/api/config/emails', headers=AUTH)
        assert response.status_code == 200
        emails = response.get_json()['emails']
        assert len(emails) == 1
        assert emails[0]['password'] == '***'
        assert emails[0]['host'] == 'imap.example.com'

    def test_list_requires_api_key(self, client):
        response = client.get('/api/config/emails')
        assert response.status_code == 401

    def test_write_requires_dynamic_config(self, client, monkeypatch):
        """未开 ENABLE_DYNAMIC_CONFIG 时，写接口统一 503，读接口不受影响"""
        monkeypatch.delenv('ENABLE_DYNAMIC_CONFIG', raising=False)
        assert _post(client, '/api/config/email', dict(_MAILBOX)).status_code == 503
        assert _post(client, '/api/config/email/delete', {'name': '工作邮箱'}).status_code == 503
        with patch('web.routes.email.load_config_safe', return_value={'email': []}):
            assert client.get('/api/config/emails', headers=AUTH).status_code == 200

    def test_add_mailbox_requires_connection_fields(self, client, monkeypatch, fake_repo):
        monkeypatch.setenv('ENABLE_DYNAMIC_CONFIG', 'true')
        with patch('web.routes.email.load_config_safe', return_value={'email': []}):
            response = _post(client, '/api/config/email', {'name': '新邮箱', 'host': 'imap.example.com'})
        assert response.status_code == 400
        message = response.get_json()['message']
        assert 'username' in message and 'password' in message
        fake_repo.upsert.assert_not_called()

    def test_add_mailbox_writes_db(self, client, monkeypatch, fake_repo):
        monkeypatch.setenv('ENABLE_DYNAMIC_CONFIG', 'true')
        with patch('web.routes.email.load_config_safe', return_value={'email': []}):
            response = _post(client, '/api/config/email', {
                'name': ' 新邮箱 ', 'host': 'imap.example.com', 'port': 993,
                'username': 'me@example.com', 'password': 'pw', 'use_ssl': True, 'enabled': True,
            })
        assert response.status_code == 200
        assert '添加' in response.get_json()['message']
        section, payload = fake_repo.upsert.call_args.args
        assert section == 'email'
        assert payload == {
            'name': '新邮箱', 'host': 'imap.example.com', 'port': 993,
            'username': 'me@example.com', 'password': 'pw', 'use_ssl': True, 'enabled': True,
        }

    def test_update_mailbox_keeps_password_when_blank(self, client, monkeypatch, fake_repo):
        """编辑时密码留空 → 不下发 password 字段，其它字段按需更新"""
        monkeypatch.setenv('ENABLE_DYNAMIC_CONFIG', 'true')
        with patch('web.routes.email.load_config_safe', return_value={'email': [dict(_MAILBOX)]}):
            response = _post(client, '/api/config/email', {'name': '工作邮箱', 'enabled': False, 'password': ''})
        assert response.status_code == 200
        assert '更新' in response.get_json()['message']
        section, payload = fake_repo.upsert.call_args.args
        assert section == 'email'
        assert payload == {'name': '工作邮箱', 'enabled': False}

    @pytest.mark.parametrize('payload', [
        {'name': '', 'host': 'h', 'username': 'u', 'password': 'p'},   # 空名称
        {'name': 'x', 'host': 'h', 'username': 'u', 'password': 'p', 'port': 70000},  # 端口越界
        {'host': 'h'},                                                # 缺 name
    ])
    def test_validation_error_returns_400(self, client, monkeypatch, fake_repo, payload):
        monkeypatch.setenv('ENABLE_DYNAMIC_CONFIG', 'true')
        response = _post(client, '/api/config/email', payload)
        assert response.status_code == 400
        fake_repo.upsert.assert_not_called()

    def test_db_write_failure_returns_500(self, client, monkeypatch):
        monkeypatch.setenv('ENABLE_DYNAMIC_CONFIG', 'true')
        with patch('web.routes.email.load_config_safe', return_value={'email': []}), \
             patch('web.routes.email.config_db_write', return_value=False):
            response = _post(client, '/api/config/email', dict(_MAILBOX))
        assert response.status_code == 500

    def test_delete_mailbox(self, client, monkeypatch, fake_repo):
        monkeypatch.setenv('ENABLE_DYNAMIC_CONFIG', 'true')
        response = _post(client, '/api/config/email/delete', {'name': '工作邮箱'})
        assert response.status_code == 200
        fake_repo.delete.assert_called_once_with('email', '工作邮箱')

    def test_delete_requires_name(self, client, monkeypatch, fake_repo):
        monkeypatch.setenv('ENABLE_DYNAMIC_CONFIG', 'true')
        assert _post(client, '/api/config/email/delete', {}).status_code == 400
        fake_repo.delete.assert_not_called()


# ==================== 邮箱扫描 ====================

class TestEmailScanEndpoints:

    def test_initial_scan_state_is_empty(self, client):
        response = client.get('/api/email/scan', headers=AUTH)
        assert response.status_code == 200
        state = response.get_json()
        assert state['last_update'] is None
        assert state['alerts'] == []
        assert state['mailboxes'] == []

    @pytest.mark.parametrize('days', [0, 31, 'abc', None])
    def test_scan_rejects_invalid_days(self, client, days):
        response = _post(client, '/api/email/scan', {'days': days})
        assert response.status_code == 400

    def test_scan_without_mailboxes_returns_400(self, client):
        with patch('web.routes.email.EmailScanner') as scanner_cls:
            scanner_cls.return_value.email_configs = []
            response = _post(client, '/api/email/scan', {})
        assert response.status_code == 400
        scanner_cls.return_value.scan_emails.assert_not_called()

    def test_scan_updates_state_and_returns_summary(self, client, state_manager):
        with patch('web.routes.email.EmailScanner') as scanner_cls:
            scanner = scanner_cls.return_value
            scanner.email_configs = [dict(_MAILBOX)]
            scanner.scan_emails.return_value = _scan_summary()
            response = _post(client, '/api/email/scan', {'days': 3})

        assert response.status_code == 200
        body = response.get_json()
        assert body['dry_run'] is True  # 未开 ENABLE_WEB_ALARM，只查不发
        assert body['summary']['total_alerts'] == 1
        assert body['summary']['total_emails'] == 12
        assert body['mailboxes'][0]['name'] == '工作邮箱'
        scanner.scan_emails.assert_called_once_with(days=3, dry_run=True)

        state = client.get('/api/email/scan', headers=AUTH).get_json()
        assert state['last_update'] is not None
        assert state['days'] == 3
        assert len(state['alerts']) == 1
        assert state['alerts'][0]['subject'] == '【阿里云】余额不足提醒'
        assert state['summary']['failed_mailboxes'] == 0

    def test_scan_cooldown_returns_429(self, client):
        with patch('web.routes.email.EmailScanner') as scanner_cls:
            scanner = scanner_cls.return_value
            scanner.email_configs = [dict(_MAILBOX)]
            scanner.scan_emails.return_value = _scan_summary()
            assert _post(client, '/api/email/scan', {'days': 1}).status_code == 200
            second = _post(client, '/api/email/scan', {'days': 1})
        assert second.status_code == 429
        assert scanner.scan_emails.call_count == 1

    def test_scan_sends_real_alerts_when_web_alarm_enabled(self, client, monkeypatch):
        monkeypatch.setenv('ENABLE_WEB_ALARM', 'true')
        with patch('web.routes.email.EmailScanner') as scanner_cls:
            scanner = scanner_cls.return_value
            scanner.email_configs = [dict(_MAILBOX)]
            scanner.scan_emails.return_value = _scan_summary(dry_run=False)
            response = _post(client, '/api/email/scan', {'days': 1})
        assert response.status_code == 200
        assert response.get_json()['dry_run'] is False
        scanner.scan_emails.assert_called_once_with(days=1, dry_run=False)

    def test_scan_failure_returns_500_and_keeps_state(self, client):
        with patch('web.routes.email.EmailScanner') as scanner_cls:
            scanner = scanner_cls.return_value
            scanner.email_configs = [dict(_MAILBOX)]
            scanner.scan_emails.side_effect = RuntimeError('imap down')
            response = _post(client, '/api/email/scan', {'days': 1})
        assert response.status_code == 500
        assert 'imap down' in response.get_json()['message']
        assert client.get('/api/email/scan', headers=AUTH).get_json()['last_update'] is None


# ==================== 历史告警邮件 ====================

class TestEmailHistoryEndpoint:

    @pytest.fixture
    def history_client(self, monkeypatch):
        monkeypatch.setenv('WEB_API_KEY', 'test-key')
        monkeypatch.setenv('ENABLE_HISTORY_API', 'true')
        app = create_app(StateManager())
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client

    def test_history_returns_records(self, history_client):
        record = {
            'id': 1, 'mailbox': '工作邮箱', 'sender': 'noreply@aliyun.com', 'subject': '余额不足',
            'date': 'Mon, 01 Sep 2026 10:00:00 +0800', 'service_name': '阿里云', 'amount': 12.5,
            'matched_keywords': ['余额不足'], 'alert_sent': True, 'timestamp': '2026-09-01T02:00:00',
        }
        from database.repository import EmailRepository
        with patch.object(EmailRepository, 'get_email_alerts', return_value=[record]) as query:
            response = history_client.get('/api/history/email-alerts?days=7&mailbox=工作邮箱', headers=AUTH)
        assert response.status_code == 200
        body = response.get_json()
        assert body['count'] == 1
        assert body['data'][0]['matched_keywords'] == ['余额不足']
        query.assert_called_once_with(mailbox='工作邮箱', days=7, limit=100)

    def test_history_rejects_bad_days(self, history_client):
        response = history_client.get('/api/history/email-alerts?days=0', headers=AUTH)
        assert response.status_code == 400

    def test_history_not_registered_without_flag(self, client):
        assert client.get('/api/history/email-alerts', headers=AUTH).status_code == 404


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
