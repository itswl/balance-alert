"""
配置加载模块测试
"""
import pytest
import json
import os
import tempfile
from unittest.mock import patch, MagicMock
from core.config_loader import (
    load_config_with_env_vars,
    get_config,
    mask_sensitive_data,
    load_env_file,
    clear_config_cache,
)


class TestLoadConfigWithEnvVars:
    """环境变量替换加载配置测试"""

    def _create_config_file(self, config_data):
        """创建临时配置文件"""
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8')
        json.dump(config_data, f, ensure_ascii=False)
        f.close()
        return f.name

    def _create_config_file_raw(self, content):
        """创建原始内容的临时配置文件（用于 ${VAR} 占位符测试）"""
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8')
        f.write(content)
        f.close()
        return f.name

    @patch('core.config_loader.load_env_file')
    def test_env_var_substitution(self, mock_load_env):
        """测试环境变量占位符替换"""
        raw_config = json.dumps({
            'projects': [
                {
                    'name': 'TestProject',
                    'provider': 'openrouter',
                    'api_key': '${TEST_API_KEY}',
                    'threshold': 10.0,
                    'type': 'credits',
                    'enabled': True
                }
            ],
            'subscriptions': [],
            'email': [],
            'settings': {'balance_refresh_interval_seconds': 3600}
        })
        config_path = self._create_config_file_raw(raw_config)
        try:
            with patch.dict(os.environ, {'TEST_API_KEY': 'sk-replaced-key'}, clear=True):
                config = load_config_with_env_vars(config_path, validate=False)
                assert config['projects'][0]['api_key'] == 'sk-replaced-key'
        finally:
            os.unlink(config_path)

    @patch('core.config_loader.load_env_file')
    def test_env_var_not_set_keeps_placeholder(self, mock_load_env):
        """测试环境变量不存在时保持占位符"""
        raw_config = json.dumps({
            'projects': [],
            'subscriptions': [],
            'email': [],
            'settings': {'balance_refresh_interval_seconds': 3600},
            'custom_field': '${NONEXISTENT_VAR_12345}'
        })
        config_path = self._create_config_file_raw(raw_config)
        try:
            env = os.environ.copy()
            env.pop('NONEXISTENT_VAR_12345', None)
            with patch.dict(os.environ, env, clear=True):
                config = load_config_with_env_vars(config_path, validate=False)
                assert config['custom_field'] == '${NONEXISTENT_VAR_12345}'
        finally:
            os.unlink(config_path)

    @patch('core.config_loader.load_env_file')
    def test_webhook_placeholder_substitution(self, mock_load_env):
        """webhook 使用 ${VAR} 时会被环境变量替换"""
        config_data = {
            'projects': [],
            'subscriptions': [],
            'email': [],
            'settings': {'balance_refresh_interval_seconds': 3600},
            'webhook': {'url': '${WEBHOOK_URL}', 'type': 'feishu'}
        }
        config_path = self._create_config_file(config_data)
        try:
            with patch.dict(os.environ, {'WEBHOOK_URL': 'https://env.com/hook'}, clear=True):
                config = load_config_with_env_vars(config_path, validate=False)
                assert config['webhook']['url'] == 'https://env.com/hook'
        finally:
            os.unlink(config_path)

    @patch('core.config_loader.load_env_file')
    def test_email_password_placeholder_substitution(self, mock_load_env):
        """邮箱 password 使用 ${VAR} 时会被环境变量替换"""
        config_data = {
            'projects': [],
            'subscriptions': [],
            'email': [
                {'name': 'work', 'host': 'imap.example.com', 'port': 993,
                 'username': 'user', 'password': '${EMAIL_PASSWORD}'}
            ],
            'settings': {'balance_refresh_interval_seconds': 3600}
        }
        config_path = self._create_config_file(config_data)
        try:
            with patch.dict(os.environ, {'EMAIL_PASSWORD': 'env_pass'}, clear=True):
                config = load_config_with_env_vars(config_path, validate=False)
                assert config['email'][0]['password'] == 'env_pass'
        finally:
            os.unlink(config_path)

    @patch('core.config_loader.load_env_file')
    def test_refresh_interval_env_override(self, mock_load_env):
        """测试刷新间隔环境变量覆盖"""
        config_data = {
            'projects': [],
            'subscriptions': [],
            'email': [],
            'settings': {'balance_refresh_interval_seconds': 3600}
        }
        config_path = self._create_config_file(config_data)
        try:
            with patch.dict(os.environ, {'BALANCE_REFRESH_INTERVAL_SECONDS': '1800'}, clear=True):
                config = load_config_with_env_vars(config_path, validate=False)
                assert config['settings']['balance_refresh_interval_seconds'] == 1800
        finally:
            os.unlink(config_path)

    def test_file_not_found(self):
        """测试配置文件不存在"""
        config = load_config_with_env_vars('/nonexistent/config.json', validate=False)
        assert 'settings' in config
        assert 'projects' in config


class TestMaskSensitiveData:
    """敏感数据脱敏测试"""

    def test_mask_api_key_long(self):
        """测试脱敏长 API Key（保留首尾各4位）"""
        config = {
            'projects': [
                {'name': 'Test', 'api_key': 'sk-1234567890abcdef'}
            ]
        }
        masked = mask_sensitive_data(config)
        assert masked['projects'][0]['api_key'] == 'sk-1***cdef'

    def test_mask_api_key_short(self):
        """测试脱敏短 API Key（全部替换）"""
        config = {
            'projects': [
                {'name': 'Test', 'api_key': 'short'}
            ]
        }
        masked = mask_sensitive_data(config)
        assert masked['projects'][0]['api_key'] == '***'

    def test_mask_api_key_exactly_8_chars(self):
        """测试脱敏恰好8位的 API Key"""
        config = {
            'projects': [
                {'name': 'Test', 'api_key': '12345678'}
            ]
        }
        masked = mask_sensitive_data(config)
        assert masked['projects'][0]['api_key'] == '***'

    def test_mask_api_key_9_chars(self):
        """测试脱敏9位 API Key"""
        config = {
            'projects': [
                {'name': 'Test', 'api_key': '123456789'}
            ]
        }
        masked = mask_sensitive_data(config)
        assert masked['projects'][0]['api_key'] == '1234***6789'

    def test_mask_webhook_url(self):
        """测试脱敏 Webhook URL"""
        config = {
            'webhook': {
                'url': 'https://open.feishu.cn/open-apis/bot/v2/hook/abc123def456'
            }
        }
        masked = mask_sensitive_data(config)
        assert masked['webhook']['url'].endswith('***')
        assert 'hook/' in masked['webhook']['url']
        assert 'abc123def456' not in masked['webhook']['url']

    def test_mask_webhook_url_without_hook_prefix(self):
        """测试无 hook/ 前缀的 URL 不脱敏"""
        config = {
            'webhook': {
                'url': 'https://example.com/api/webhook'
            }
        }
        masked = mask_sensitive_data(config)
        assert masked['webhook']['url'] == 'https://example.com/api/webhook'

    def test_mask_email_password(self):
        """测试脱敏邮箱密码"""
        config = {
            'email': [
                {'name': 'work', 'password': 'my_secret_password'},
                {'name': 'personal', 'password': 'another_secret'}
            ]
        }
        masked = mask_sensitive_data(config)
        assert masked['email'][0]['password'] == '***'
        assert masked['email'][1]['password'] == '***'

    def test_mask_does_not_modify_original(self):
        """测试脱敏不修改原始配置"""
        config = {
            'projects': [
                {'name': 'Test', 'api_key': 'sk-1234567890abcdef'}
            ],
            'email': [
                {'name': 'work', 'password': 'secret'}
            ]
        }
        original_api_key = config['projects'][0]['api_key']
        original_password = config['email'][0]['password']

        mask_sensitive_data(config)

        assert config['projects'][0]['api_key'] == original_api_key
        assert config['email'][0]['password'] == original_password

    def test_mask_missing_sections(self):
        """测试缺少可选节时不报错"""
        config = {'settings': {'balance_refresh_interval_seconds': 3600}}
        masked = mask_sensitive_data(config)
        assert 'settings' in masked

    def test_mask_empty_config(self):
        """测试空配置不报错"""
        config = {}
        masked = mask_sensitive_data(config)
        assert masked == {}


class TestGetConfig:
    """配置缓存行为测试"""

    def setup_method(self):
        """每个测试前清除缓存"""
        clear_config_cache()

    def teardown_method(self):
        """每个测试后清除缓存"""
        clear_config_cache()

    @patch('core.config_loader.load_config_with_env_vars')
    def test_first_call_loads_config(self, mock_load):
        """测试首次调用加载配置"""
        mock_load.return_value = {'projects': [], 'settings': {}}
        result = get_config('config.json', use_cache=True)

        assert result == {'projects': [], 'settings': {}}
        mock_load.assert_called_once()

    @patch('core.config_loader.load_config_with_env_vars')
    def test_cached_second_call(self, mock_load):
        """测试第二次调用使用缓存"""
        mock_load.return_value = {'projects': [], 'settings': {}}

        result1 = get_config('config.json', use_cache=True)
        result2 = get_config('config.json', use_cache=True)

        assert result1 == result2
        mock_load.assert_called_once()  # 只调用一次

    @patch('core.config_loader.load_config_with_env_vars')
    def test_no_cache_reloads(self, mock_load):
        """测试禁用缓存时每次重新加载"""
        mock_load.return_value = {'projects': [], 'settings': {}}

        get_config('config.json', use_cache=False)
        get_config('config.json', use_cache=False)

        assert mock_load.call_count == 2

    @patch('core.config_loader.load_config_with_env_vars')
    def test_clear_cache_forces_reload(self, mock_load):
        """测试清除缓存后重新加载"""
        mock_load.return_value = {'projects': [], 'settings': {}}

        get_config('config.json', use_cache=True)
        clear_config_cache()
        get_config('config.json', use_cache=True)

        assert mock_load.call_count == 2


class TestLoadEnvFile:
    """加载 .env 文件测试"""

    @patch('core.config_loader.load_dotenv')
    def test_load_existing_env_file(self, mock_load_dotenv):
        """测试加载存在的 .env 文件"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.write('TEST_VAR=value\n')
            env_path = f.name
        try:
            load_env_file(env_path)
            mock_load_dotenv.assert_called_once_with(env_path, override=True)
        finally:
            os.unlink(env_path)

    @patch('core.config_loader.load_dotenv')
    def test_load_nonexistent_env_file(self, mock_load_dotenv):
        """测试加载不存在的 .env 文件不报错"""
        load_env_file('/nonexistent/.env')
        mock_load_dotenv.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
