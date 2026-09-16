"""
环境变量自动发现项目：不写 config.json 也能监控
"""
import pytest

from core.config_loader import MAX_ENV_ACCOUNTS, discover_env_projects


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
        """config.json 或数据库里已经声明的 provider，不再自动添加"""
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


class TestLoadConfigIntegration:
    """load_config 把自动发现的项目并进清单，且不影响已有来源"""

    def test_env_projects_appended_to_file_projects(self, monkeypatch, tmp_path):
        import json
        from core.config_loader import load_config

        config_file = tmp_path / 'config.json'
        config_file.write_text(json.dumps(
            {'projects': [{'name': 'Test', 'provider': 'openrouter', 'api_key': 'k', 'threshold': 100}]}
        ), encoding='utf-8')
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-x')

        projects = load_config(str(config_file))['projects']
        assert [(p['name'], p.get('from_env', False)) for p in projects] == [('Test', False), ('deepseek', True)]

    def test_works_without_any_config_file(self, monkeypatch, tmp_path):
        from core.config_loader import load_config

        monkeypatch.setenv('GLM_API_KEY', 'a.b')
        monkeypatch.setenv('GLM_THRESHOLD', '10')
        projects = load_config(str(tmp_path / 'absent.json'))['projects']
        assert len(projects) == 1
        assert projects[0]['name'] == 'glm'
        assert projects[0]['type'] == 'quota'     # 仍然走 provider 类型推导
        assert projects[0]['threshold'] == 10.0

    def test_no_keys_means_no_projects(self, tmp_path):
        from core.config_loader import load_config

        assert load_config(str(tmp_path / 'absent.json'))['projects'] == []


class TestConfigFileEdgeCases:
    """配置文件缺失、空、被挂载成目录时都不该让服务起不来"""

    def test_empty_file_is_treated_as_no_config(self, monkeypatch, tmp_path):
        from core.config_loader import load_config

        config_file = tmp_path / 'config.json'
        config_file.write_text('', encoding='utf-8')
        monkeypatch.setenv('DEEPSEEK_API_KEY', 'sk-x')

        projects = load_config(str(config_file))['projects']
        assert names(projects) == ['deepseek']

    def test_whitespace_only_file(self, tmp_path):
        from core.config_loader import load_config

        config_file = tmp_path / 'config.json'
        config_file.write_text('  \n\t ', encoding='utf-8')
        assert load_config(str(config_file))['projects'] == []

    def test_directory_in_place_of_file_is_ignored(self, monkeypatch, tmp_path):
        """docker-compose 挂载不存在的文件时会建出目录，不能因此崩溃"""
        from core.config_loader import load_config

        as_dir = tmp_path / 'config.json'
        as_dir.mkdir()
        monkeypatch.setenv('GLM_API_KEY', 'a.b')
        assert names(load_config(str(as_dir))['projects']) == ['glm']

    def test_malformed_json_still_raises(self, tmp_path):
        """真正写错的 JSON 仍然要报错，不能悄悄当成空配置"""
        from core.config_loader import load_config

        config_file = tmp_path / 'config.json'
        config_file.write_text('{"projects": [', encoding='utf-8')
        with pytest.raises(ValueError, match='配置文件格式错误'):
            load_config(str(config_file))
