"""
配置加载：只有数据库动态配置与环境变量两个来源
"""
from unittest.mock import patch

import pytest

from core import config_loader
from core.config_loader import load_config, load_env_file


def _db(projects=None, subscriptions=None, email=None):
    """打桩数据库三段清单"""
    return patch.object(config_loader, '_db_sections', return_value={
        'projects': projects or [], 'subscriptions': subscriptions or [], 'email': email or [],
    })


class TestLoadConfig:

    def test_empty_when_nothing_configured(self):
        with _db():
            assert load_config() == {'projects': [], 'subscriptions': [], 'email': []}

    def test_returns_fresh_dict_each_time(self):
        with _db(projects=[{'name': 'A', 'provider': 'volc', 'api_key': 'a:b'}]):
            first, second = load_config(), load_config()
        first['projects'].clear()
        assert len(second['projects']) == 1

    def test_db_rows_lose_meta_fields(self):
        row = {'id': 7, 'created_at': 'x', 'updated_at': 'y',
               'name': 'A', 'provider': 'volc', 'api_key': 'a:b', 'threshold': 1}
        with _db(projects=[row]):
            project = load_config()['projects'][0]
        assert not {'id', 'created_at', 'updated_at'} & set(project)
        assert project['name'] == 'A'

    def test_env_projects_appended_after_db(self, monkeypatch):
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-x')
        with _db(projects=[{'name': '库里的', 'provider': 'volc', 'api_key': 'a:b'}]):
            projects = load_config()['projects']
        assert [(p['name'], p.get('from_env', False)) for p in projects] == [('库里的', False), ('deepseek', True)]

    def test_db_provider_suppresses_env_discovery(self, monkeypatch):
        monkeypatch.setenv('VOLC_API_KEY', 'a:b')
        with _db(projects=[{'name': '火山-主账号', 'provider': 'volc', 'api_key': 'x:y'}]):
            projects = load_config()['projects']
        assert [p['name'] for p in projects] == ['火山-主账号']

    def test_fields_are_normalized(self, monkeypatch):
        monkeypatch.setenv('GLM_API_KEY', 'a.b')
        with _db(subscriptions=[{'name': '域名', 'cycle_type': 'YEARLY', 'renewal_day': '03-15'}],
                 email=[{'host': 'imap.x.com', 'username': 'u@x.com', 'password': 'p'}]):
            config = load_config()
        assert config['projects'][0]['type'] == 'quota'          # 按 provider 推导
        assert config['subscriptions'][0]['renewal_day'] == 315   # MM-DD 转 MMDD
        assert config['email'][0] == {
            'host': 'imap.x.com', 'username': 'u@x.com', 'password': 'p',
            'port': 993, 'use_ssl': True, 'name': 'u@x.com',
        }

    def test_db_failure_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv('ENABLE_DYNAMIC_CONFIG', 'true')
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-x')
        with patch('database.repository.ConfigRepository.get_all', side_effect=RuntimeError('库挂了')):
            projects = load_config()['projects']
        assert [p['name'] for p in projects] == ['deepseek']

    def test_database_not_queried_without_dynamic_config(self, monkeypatch):
        monkeypatch.delenv('ENABLE_DYNAMIC_CONFIG', raising=False)
        with patch('database.repository.ConfigRepository.get_all') as get_all:
            load_config()
        get_all.assert_not_called()


class TestLoadEnvFile:

    @patch('core.config_loader.load_dotenv')
    def test_loads_when_present(self, mock_dotenv, tmp_path):
        env_file = tmp_path / '.env'
        env_file.write_text('A=1', encoding='utf-8')
        load_env_file(str(env_file))
        mock_dotenv.assert_called_once_with(str(env_file), override=True)

    @patch('core.config_loader.load_dotenv')
    def test_skips_when_missing(self, mock_dotenv, tmp_path):
        load_env_file(str(tmp_path / 'absent'))
        mock_dotenv.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
