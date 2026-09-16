"""
项目配置接口测试：读始终可用，增删改需要动态配置
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from core.state_manager import StateManager
from web.app import create_app

AUTH = {'X-API-Key': 'test-key'}

_PROJECT = {
    'name': '火山-主账号', 'provider': 'volc', 'api_key': 'AK:SK', 'threshold': 7000,
    'type': 'balance', 'owner_project': '云服务', 'enabled': True,
}


def _post(client, path, payload):
    return client.post(path, data=json.dumps(payload), content_type='application/json', headers=AUTH)


@pytest.fixture
def state():
    return StateManager()


@pytest.fixture
def client(state, monkeypatch):
    monkeypatch.setenv('WEB_API_KEY', 'test-key')
    app = create_app(state)
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def fake_repo():
    repo = MagicMock()
    repo.upsert.return_value = True
    repo.delete.return_value = True
    with patch('web.routes.project.config_db_write', side_effect=lambda action: bool(action(repo))):
        yield repo


@pytest.fixture(autouse=True)
def no_refresh(request):
    """默认打桩掉改动后的重查，免得真去请求上游；TestRefreshOne 要测它本身，跳过"""
    if getattr(request.cls, '__name__', '') == 'TestRefreshOne':
        yield None
        return
    with patch('web.routes.project._refresh_one') as refresh:
        yield refresh


class TestReadEndpoints:

    def test_providers_list(self, client):
        body = client.get('/api/providers', headers=AUTH).get_json()
        values = {p['value'] for p in body['providers']}
        assert {'deepseek', 'glm', 'volc', 'aliyun', 'openrouter'} <= values
        glm = next(p for p in body['providers'] if p['value'] == 'glm')
        assert glm['label'] == 'GLM' and glm['default_type'] == 'quota'

    def test_projects_masked_and_always_available(self, client, monkeypatch):
        """不开动态配置也能读清单，密钥脱敏"""
        monkeypatch.delenv('ENABLE_DYNAMIC_CONFIG', raising=False)
        with patch('web.routes.project.load_config_safe', return_value={'projects': [dict(_PROJECT)]}):
            body = client.get('/api/config/projects', headers=AUTH).get_json()
        project = body['projects'][0]
        assert project['name'] == '火山-主账号'
        assert project['api_key'] != 'AK:SK' and '***' in project['api_key']

    def test_requires_api_key(self, client):
        assert client.get('/api/config/projects').status_code == 401


class TestWriteGuard:

    def test_writes_need_dynamic_config(self, client, monkeypatch):
        monkeypatch.delenv('ENABLE_DYNAMIC_CONFIG', raising=False)
        assert _post(client, '/api/config/project', dict(_PROJECT)).status_code == 503
        assert _post(client, '/api/config/project/delete', {'name': 'x'}).status_code == 503
        assert _post(client, '/api/config/threshold', {'project_name': 'x', 'new_threshold': 1}).status_code == 503


@pytest.fixture
def dynamic(monkeypatch):
    monkeypatch.setenv('ENABLE_DYNAMIC_CONFIG', 'true')


class TestCreateAndUpdate:

    def test_new_project_needs_provider_and_key(self, client, dynamic, fake_repo):
        with patch('web.routes.project.load_config_safe', return_value={'projects': []}):
            response = _post(client, '/api/config/project', {'name': '新项目'})
        assert response.status_code == 400
        assert 'provider' in response.get_json()['message']
        fake_repo.upsert.assert_not_called()

    def test_create(self, client, dynamic, fake_repo, no_refresh):
        with patch('web.routes.project.load_config_safe', return_value={'projects': []}):
            response = _post(client, '/api/config/project', dict(_PROJECT))
        assert response.status_code == 200 and '添加' in response.get_json()['message']
        section, payload = fake_repo.upsert.call_args.args
        assert section == 'projects'
        assert payload == _PROJECT
        no_refresh.assert_called_once_with('火山-主账号')

    def test_update_keeps_key_when_blank(self, client, dynamic, fake_repo):
        with patch('web.routes.project.load_config_safe', return_value={'projects': [dict(_PROJECT)]}):
            response = _post(client, '/api/config/project',
                             {'name': '火山-主账号', 'threshold': 9999, 'api_key': ''})
        assert response.status_code == 200 and '更新' in response.get_json()['message']
        _, payload = fake_repo.upsert.call_args.args
        assert payload == {'name': '火山-主账号', 'threshold': 9999.0}

    def test_env_project_gets_provider_filled_in(self, client, dynamic, fake_repo):
        """自动发现的项目在页面上保存 = 固化进数据库，provider 不能丢"""
        env_project = {'name': 'deepseek', 'provider': 'deepseek', 'from_env': True}
        with patch('web.routes.project.load_config_safe', return_value={'projects': [env_project]}):
            response = _post(client, '/api/config/project', {'name': 'deepseek', 'threshold': 50})
        assert response.status_code == 200
        _, payload = fake_repo.upsert.call_args.args
        assert payload == {'name': 'deepseek', 'threshold': 50.0, 'provider': 'deepseek'}

    @pytest.mark.parametrize('payload, hint', [
        ({'name': '', 'provider': 'volc', 'api_key': 'k'}, 'name'),
        ({'name': 'x', 'provider': '不存在的平台', 'api_key': 'k'}, 'provider'),
        ({'name': 'x', 'provider': 'volc', 'api_key': 'k', 'threshold': -1}, 'threshold'),
        ({'name': 'x', 'provider': 'volc', 'api_key': 'k', 'type': 'bogus'}, 'type'),
    ])
    def test_validation(self, client, dynamic, fake_repo, payload, hint):
        response = _post(client, '/api/config/project', payload)
        assert response.status_code == 400
        assert hint in json.dumps(response.get_json(), ensure_ascii=False)
        fake_repo.upsert.assert_not_called()

    def test_db_failure_returns_500(self, client, dynamic):
        with patch('web.routes.project.load_config_safe', return_value={'projects': []}), \
             patch('web.routes.project.config_db_write', return_value=False):
            assert _post(client, '/api/config/project', dict(_PROJECT)).status_code == 500


class TestDelete:

    def test_delete(self, client, dynamic, fake_repo, state):
        state.update_balance_state([
            {'project': '火山-主账号', 'success': True, 'need_alarm': False},
            {'project': '留下的', 'success': True, 'need_alarm': False},
        ])
        with patch('web.routes.project.load_config_safe', return_value={'projects': [dict(_PROJECT)]}):
            response = _post(client, '/api/config/project/delete', {'name': '火山-主账号'})
        assert response.status_code == 200
        fake_repo.delete.assert_called_once_with('projects', '火山-主账号')
        assert [p['project'] for p in state.get_balance_state()['projects']] == ['留下的']

    def test_delete_missing(self, client, dynamic, fake_repo):
        with patch('web.routes.project.load_config_safe', return_value={'projects': []}):
            assert _post(client, '/api/config/project/delete', {'name': '没有的'}).status_code == 404
        fake_repo.delete.assert_not_called()

    def test_cannot_delete_env_project(self, client, dynamic, fake_repo):
        """环境变量来的项目删不掉，得先改环境变量"""
        env_project = {'name': 'deepseek', 'provider': 'deepseek', 'from_env': True}
        with patch('web.routes.project.load_config_safe', return_value={'projects': [env_project]}):
            response = _post(client, '/api/config/project/delete', {'name': 'deepseek'})
        assert response.status_code == 400
        assert 'DEEPSEEK_API_KEY' in response.get_json()['message']
        fake_repo.delete.assert_not_called()


class TestThresholdShortcut:

    def test_updates_threshold_and_keeps_other_fields(self, client, dynamic, fake_repo, no_refresh):
        with patch('web.routes.project.load_config_safe', return_value={'projects': [dict(_PROJECT)]}):
            response = _post(client, '/api/config/threshold',
                             {'project_name': '火山-主账号', 'new_threshold': 123})
        assert response.status_code == 200
        _, payload = fake_repo.upsert.call_args.args
        assert payload['threshold'] == 123 and payload['provider'] == 'volc' and payload['api_key'] == 'AK:SK'
        no_refresh.assert_called_once_with('火山-主账号')

    @pytest.mark.parametrize('payload, code', [
        ({'project_name': '没有的', 'new_threshold': 1}, 404),
        ({'project_name': '火山-主账号', 'new_threshold': -1}, 400),
        ({'project_name': '火山-主账号', 'new_threshold': 'abc'}, 400),
        ({'project_name': '火山-主账号'}, 400),
    ])
    def test_rejects_bad_input(self, client, dynamic, fake_repo, payload, code):
        with patch('web.routes.project.load_config_safe', return_value={'projects': [dict(_PROJECT)]}):
            assert _post(client, '/api/config/threshold', payload).status_code == code


class TestRefreshOne:
    """改完配置只重查这一个项目，不把所有上游都打一遍"""

    def test_merges_result_and_updates_metrics(self, state, monkeypatch):
        from web.routes import project as project_routes

        monkeypatch.setenv('WEB_API_KEY', 'test-key')
        state.update_balance_state([
            {'project': '别的', 'provider': 'glm', 'success': True, 'credits': 1, 'need_alarm': False},
        ])
        refreshed = {'project': '火山-主账号', 'provider': 'volc', 'type': 'balance', 'success': True,
                     'credits': 8000, 'threshold': 7000, 'need_alarm': False}
        app = create_app(state)
        with app.test_request_context(), \
             patch.object(project_routes, 'run_credit_monitor',
                          return_value={'success': True, 'results': [refreshed], 'count': 1}) as monitor, \
             patch.object(project_routes, 'metrics_collector') as metrics:
            project_routes._refresh_one('火山-主账号')

        assert monitor.call_args.args[0] == '火山-主账号'      # 只查这一个
        projects = {p['project'] for p in state.get_balance_state()['projects']}
        assert projects == {'别的', '火山-主账号'}             # 合并而不是覆盖
        metrics.update_balance_metrics.assert_called_once()

    def test_failure_does_not_raise(self, state, monkeypatch):
        """重查失败只记日志，不能让保存接口跟着报错"""
        from web.routes import project as project_routes

        monkeypatch.setenv('WEB_API_KEY', 'test-key')
        app = create_app(state)
        with app.test_request_context(), \
             patch.object(project_routes, 'run_credit_monitor', side_effect=RuntimeError('上游挂了')):
            project_routes._refresh_one('火山-主账号')   # 不抛异常即通过


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
