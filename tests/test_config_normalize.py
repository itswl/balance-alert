"""
配置规范化测试：让 config.json 只写必要字段
"""
import os
from unittest.mock import patch

import pytest

from core.config_loader import (
    coerce_renewal_day,
    is_unresolved_placeholder,
    normalize_config,
    normalize_emails,
    normalize_projects,
    normalize_subscriptions,
    provider_key_env_names,
    resolve_api_key,
)


class TestProviderKeyEnvNames:
    """api_key 省略时的环境变量名约定"""

    def test_single_instance(self):
        assert provider_key_env_names('openrouter', 1) == ['OPENROUTER_API_KEY', 'OPENROUTER_1_API_KEY']

    def test_second_instance(self):
        assert provider_key_env_names('volc', 2) == ['VOLC_2_API_KEY']

    def test_empty_provider(self):
        assert provider_key_env_names('', 1) == []


class TestResolveApiKey:
    """显式 api_key 优先，其次按约定推导"""

    def test_explicit_key_wins(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'from-env'}, clear=True):
            key, source = resolve_api_key({'api_key': 'explicit'}, 'openrouter', 1)
        assert key == 'explicit'
        assert source == 'api_key 字段'

    def test_derived_from_env(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'sk-env'}, clear=True):
            key, source = resolve_api_key({}, 'openrouter', 1)
        assert key == 'sk-env'
        assert source == '环境变量 OPENROUTER_API_KEY'

    def test_numbered_env_for_second_instance(self):
        with patch.dict(os.environ, {'VOLC_2_API_KEY': 'ak:sk'}, clear=True):
            key, source = resolve_api_key({}, 'volc', 2)
        assert key == 'ak:sk'
        assert source == '环境变量 VOLC_2_API_KEY'

    def test_unresolved_placeholder_falls_back_to_env(self):
        """${VAR} 未被替换时不能当密钥用，应回退到约定推导"""
        with patch.dict(os.environ, {'TIKHUB_API_KEY': 'real'}, clear=True):
            key, _ = resolve_api_key({'api_key': '${MISSING_VAR}'}, 'tikhub', 1)
        assert key == 'real'

    def test_missing_everywhere(self):
        with patch.dict(os.environ, {}, clear=True):
            key, source = resolve_api_key({}, 'openrouter', 1)
        assert key == ''
        assert source is None


class TestNormalizeProjects:
    """项目字段补齐"""

    def test_minimal_project(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'sk-x'}, clear=True):
            projects = normalize_projects([{'provider': 'openrouter', 'threshold': 100}])
        p = projects[0]
        assert p['name'] == 'openrouter'
        assert p['type'] == 'credits'      # 按 provider 推导
        assert p['api_key'] == 'sk-x'      # 按环境变量推导

    def test_type_default_by_provider(self):
        with patch.dict(os.environ, {}, clear=True):
            projects = normalize_projects([
                {'provider': 'volc'},
                {'provider': 'uniapi'},
                {'provider': 'unknown-vendor'},
            ])
        assert projects[0]['type'] == 'balance'
        assert projects[1]['type'] == 'credits'
        assert projects[2]['type'] == 'balance'  # 未知 provider 兜底

    def test_explicit_fields_preserved(self):
        with patch.dict(os.environ, {'VOLC_API_KEY': 'env'}, clear=True):
            projects = normalize_projects([
                {'name': '我的火山', 'provider': 'VOLC', 'type': 'credits', 'api_key': 'mine'}
            ])
        p = projects[0]
        assert p['name'] == '我的火山'
        assert p['provider'] == 'volc'  # 统一小写
        assert p['type'] == 'credits'
        assert p['api_key'] == 'mine'

    def test_multiple_instances_get_numbered_keys(self):
        env = {'VOLC_1_API_KEY': 'first', 'VOLC_2_API_KEY': 'second'}
        with patch.dict(os.environ, env, clear=True):
            projects = normalize_projects([
                {'name': 'A', 'provider': 'volc'},
                {'name': 'B', 'provider': 'volc'},
            ])
        assert projects[0]['api_key'] == 'first'
        assert projects[1]['api_key'] == 'second'

    def test_non_dict_entries_ignored(self):
        assert normalize_projects(['garbage', None]) == ['garbage', None]


class TestNormalizeSubscriptions:
    """订阅字段补齐与续费日归一化"""

    def test_cycle_type_default(self):
        subs = normalize_subscriptions([{'name': 'X'}])
        assert subs[0]['cycle_type'] == 'monthly'

    def test_yearly_mm_dd_string(self):
        subs = normalize_subscriptions([{'name': 'X', 'cycle_type': 'yearly', 'renewal_day': '03-15'}])
        assert subs[0]['renewal_day'] == 315

    def test_yearly_chinese_format(self):
        subs = normalize_subscriptions([{'name': 'X', 'cycle_type': 'yearly', 'renewal_day': '3月15日'}])
        assert subs[0]['renewal_day'] == 315

    def test_monthly_string_day(self):
        subs = normalize_subscriptions([{'name': 'X', 'cycle_type': 'monthly', 'renewal_day': '15'}])
        assert subs[0]['renewal_day'] == 15

    def test_monthly_mm_dd_takes_day_part(self):
        """月付误填 MM-DD 时取日，不会变成 315 这种越界值"""
        subs = normalize_subscriptions([{'name': 'X', 'cycle_type': 'monthly', 'renewal_day': '03-15'}])
        assert subs[0]['renewal_day'] == 15

    def test_integer_preserved(self):
        subs = normalize_subscriptions([{'name': 'X', 'cycle_type': 'yearly', 'renewal_day': 315}])
        assert subs[0]['renewal_day'] == 315

    def test_none_renewal_day_untouched(self):
        subs = normalize_subscriptions([{'name': 'X', 'renewal_day': None}])
        assert subs[0]['renewal_day'] is None


class TestCoerceRenewalDay:
    """续费日解析边界"""

    @pytest.mark.parametrize('value,cycle,expected', [
        ('03-15', 'yearly', 315),
        ('3/15', 'yearly', 315),
        ('12-31', 'yearly', 1231),
        ('7', 'weekly', 7),
        (15, 'monthly', 15),
        ('乱写', 'yearly', '乱写'),  # 无法解析时原样返回，交下游兜底
    ])
    def test_cases(self, value, cycle, expected):
        assert coerce_renewal_day(value, cycle) == expected


class TestNormalizeEmails:
    """邮箱字段补齐"""

    def test_port_and_ssl_defaults(self):
        emails = normalize_emails([{'host': 'imap.example.com', 'username': 'u@e.com', 'password': 'p'}])
        assert emails[0]['port'] == 993
        assert emails[0]['use_ssl'] is True
        assert emails[0]['name'] == 'u@e.com'  # 缺省取账号

    def test_explicit_values_preserved(self):
        emails = normalize_emails([{'name': 'work', 'port': 143, 'use_ssl': False}])
        assert emails[0]['port'] == 143
        assert emails[0]['use_ssl'] is False
        assert emails[0]['name'] == 'work'

    def test_unresolved_password_cleared(self):
        emails = normalize_emails([{'name': 'x', 'password': '${NOT_SET}'}])
        assert emails[0]['password'] == ''


class TestIsUnresolvedPlaceholder:
    @pytest.mark.parametrize('value,expected', [
        ('${FOO}', True),
        ('prefix-${FOO}', True),
        ('sk-real-key', False),
        ('', False),
        (None, False),
        (123, False),
    ])
    def test_cases(self, value, expected):
        assert is_unresolved_placeholder(value) is expected


class TestNormalizeConfig:
    """整体规范化入口"""

    def test_all_sections(self):
        with patch.dict(os.environ, {'OPENROUTER_API_KEY': 'sk-x'}, clear=True):
            config = normalize_config({
                'projects': [{'provider': 'openrouter'}],
                'subscriptions': [{'name': 'S', 'cycle_type': 'yearly', 'renewal_day': '06-01'}],
                'email': [{'host': 'h', 'username': 'u'}],
            })
        assert config['projects'][0]['api_key'] == 'sk-x'
        assert config['subscriptions'][0]['renewal_day'] == 601
        assert config['email'][0]['port'] == 993

    def test_missing_sections_tolerated(self):
        assert normalize_config({}) == {}


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
