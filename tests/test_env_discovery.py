"""
环境变量自动发现：项目与邮箱都可以只靠环境变量配置
"""
import pytest

from core.config_loader import MAX_ENV_ACCOUNTS, discover_env_mailboxes, discover_env_projects


def names(projects):
    return [p['name'] for p in projects]


class TestDiscoverEnvProjects:

    def test_nothing_without_keys(self):
        assert discover_env_projects([]) == []

    def test_single_account_uses_provider_name(self, monkeypatch):
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-x')
        project = discover_env_projects([])[0]
        assert project == {
            'name': 'deepseek', 'provider': 'deepseek', 'api_key': 'sk-x',
            'threshold': None, 'owner_project': None, 'from_env': True,
        }

    def test_numbered_key_alone_still_uses_plain_name(self, monkeypatch):
        """只配了 _1_ 序号也算一个账号，名字不加后缀"""
        monkeypatch.setenv('VOLC_1_API_KEY', 'ak:sk')
        assert names(discover_env_projects([])) == ['volc']

    def test_plain_and_numbered_are_the_same_account(self, monkeypatch):
        """DEEPSEEK_API_KEY 与 DEEPSEEK_1_API_KEY 是同一个账号的两种写法，不能建两个"""
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-x')
        monkeypatch.setenv('DEEPSEEK_1_API_KEY', 'sk-x')
        assert names(discover_env_projects([])) == ['deepseek']

    def test_multiple_accounts_get_numbered_names(self, monkeypatch):
        monkeypatch.setenv('VOLC_1_API_KEY', 'ak1:sk1')
        monkeypatch.setenv('VOLC_2_API_KEY', 'ak2:sk2')
        projects = discover_env_projects([])
        assert names(projects) == ['volc-1', 'volc-2']
        assert [p['api_key'] for p in projects] == ['ak1:sk1', 'ak2:sk2']

    def test_threshold_from_env(self, monkeypatch):
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-x')
        monkeypatch.setenv('DEEPSEEK_THRESHOLD', '50')
        assert discover_env_projects([])[0]['threshold'] == 50.0

    def test_numbered_threshold_wins_over_plain(self, monkeypatch):
        monkeypatch.setenv('VOLC_1_API_KEY', 'a:b')
        monkeypatch.setenv('VOLC_2_API_KEY', 'c:d')
        monkeypatch.setenv('VOLC_THRESHOLD', '100')
        monkeypatch.setenv('VOLC_2_THRESHOLD', '7000')
        thresholds = {p['name']: p['threshold'] for p in discover_env_projects([])}
        assert thresholds == {'volc-1': 100.0, 'volc-2': 7000.0}

    def test_bad_threshold_is_ignored(self, monkeypatch):
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-x')
        monkeypatch.setenv('DEEPSEEK_THRESHOLD', '不是数字')
        assert discover_env_projects([])[0]['threshold'] is None

    def test_owner_project_from_env(self, monkeypatch):
        monkeypatch.setenv('GLM_API_KEY', 'a.b')
        monkeypatch.setenv('GLM_OWNER_PROJECT', 'AI 平台')
        assert discover_env_projects([])[0]['owner_project'] == 'AI 平台'

    def test_declared_provider_is_not_duplicated(self, monkeypatch):
        """数据库里已经声明的 provider，不再自动添加"""
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-x')
        monkeypatch.setenv('GLM_API_KEY', 'a.b')
        assert names(discover_env_projects([{'provider': 'DeepSeek'}])) == ['glm']

    def test_unknown_env_keys_are_ignored(self, monkeypatch):
        """不是本项目支持的平台，设了 key 也不会凭空建项目"""
        monkeypatch.setenv('SOMETHING_ELSE_API_KEY', 'x')
        assert discover_env_projects([]) == []

    def test_scan_is_bounded(self, monkeypatch):
        """序号扫描有上限，超出的不认"""
        monkeypatch.setenv(f'VOLC_{MAX_ENV_ACCOUNTS}_API_KEY', 'a:b')
        monkeypatch.setenv(f'VOLC_{MAX_ENV_ACCOUNTS + 1}_API_KEY', 'c:d')
        assert len(discover_env_projects([])) == 1


class TestDiscoverEnvMailboxes:
    """邮箱同样可以只靠环境变量"""

    def test_nothing_without_vars(self):
        assert discover_env_mailboxes([]) == []

    def test_needs_all_three_required_vars(self, monkeypatch):
        monkeypatch.setenv('EMAIL_HOST', 'imap.x.com')
        monkeypatch.setenv('EMAIL_USERNAME', 'u@x.com')
        assert discover_env_mailboxes([]) == []      # 少了密码就不算

    def test_single_mailbox_defaults(self, monkeypatch):
        monkeypatch.setenv('EMAIL_HOST', 'imap.x.com')
        monkeypatch.setenv('EMAIL_USERNAME', 'u@x.com')
        monkeypatch.setenv('EMAIL_PASSWORD', 'pw')
        assert discover_env_mailboxes([]) == [{
            'name': 'u@x.com', 'host': 'imap.x.com', 'port': 993,
            'username': 'u@x.com', 'password': 'pw', 'use_ssl': True, 'from_env': True,
        }]

    def test_port_name_and_ssl_overrides(self, monkeypatch):
        for key, value in {'EMAIL_HOST': 'imap.x.com', 'EMAIL_USERNAME': 'u@x.com', 'EMAIL_PASSWORD': 'pw',
                           'EMAIL_PORT': '143', 'EMAIL_USE_SSL': 'false', 'EMAIL_NAME': '工作邮箱'}.items():
            monkeypatch.setenv(key, value)
        mailbox = discover_env_mailboxes([])[0]
        assert (mailbox['name'], mailbox['port'], mailbox['use_ssl']) == ('工作邮箱', 143, False)

    def test_multiple_mailboxes(self, monkeypatch):
        for key, value in {'EMAIL_1_HOST': 'a.com', 'EMAIL_1_USERNAME': 'a@a.com', 'EMAIL_1_PASSWORD': 'p1',
                           'EMAIL_2_HOST': 'b.com', 'EMAIL_2_USERNAME': 'b@b.com', 'EMAIL_2_PASSWORD': 'p2',
                           'EMAIL_2_NAME': '备用'}.items():
            monkeypatch.setenv(key, value)
        assert [m['name'] for m in discover_env_mailboxes([])] == ['a@a.com', '备用']

    def test_plain_and_numbered_are_one_mailbox(self, monkeypatch):
        for key, value in {'EMAIL_HOST': 'a.com', 'EMAIL_USERNAME': 'a@a.com', 'EMAIL_PASSWORD': 'p',
                           'EMAIL_1_HOST': 'a.com', 'EMAIL_1_USERNAME': 'a@a.com', 'EMAIL_1_PASSWORD': 'p'}.items():
            monkeypatch.setenv(key, value)
        assert len(discover_env_mailboxes([])) == 1

    def test_declared_mailbox_is_not_duplicated(self, monkeypatch):
        """数据库里已经有同名或同账号的邮箱就不再添加"""
        for key, value in {'EMAIL_HOST': 'a.com', 'EMAIL_USERNAME': 'a@a.com', 'EMAIL_PASSWORD': 'p'}.items():
            monkeypatch.setenv(key, value)
        assert discover_env_mailboxes([{'name': 'a@a.com'}]) == []
        assert discover_env_mailboxes([{'name': '别名', 'username': 'a@a.com'}]) == []
