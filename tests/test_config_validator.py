"""
配置验证模块测试
"""
import pytest
from core.config_validator import (
    EmailConfig,
    SubscriptionConfig,
    ProjectConfig,
    WebhookConfig,
    SettingsConfig,
    AppConfig,
    CycleType,
    ProjectType,
    WebhookType
)


class TestEmailConfig:
    """邮箱配置测试"""

    def test_from_dict(self):
        """测试从字典创建配置"""
        data = {
            'name': 'test@example.com',
            'host': 'imap.example.com',
            'port': 993,
            'username': 'test',
            'password': 'pass123',
            'use_ssl': True,
            'enabled': True
        }
        config = EmailConfig.from_dict(data)

        assert config.name == 'test@example.com'
        assert config.host == 'imap.example.com'
        assert config.port == 993
        assert config.username == 'test'
        assert config.password == 'pass123'
        assert config.use_ssl is True
        assert config.enabled is True

    def test_from_dict_defaults(self):
        """测试默认值"""
        data = {
            'name': 'test@example.com',
            'host': 'imap.example.com',
            'port': 993,
            'username': 'test',
            'password': 'pass123'
        }
        config = EmailConfig.from_dict(data)

        assert config.use_ssl is True
        assert config.enabled is True

    def test_validate_success(self):
        """测试验证成功"""
        config = EmailConfig(
            name='test@example.com',
            host='imap.example.com',
            port=993,
            username='test',
            password='pass123'
        )
        errors = config.validate()
        assert errors == []

    def test_validate_missing_fields(self):
        """测试验证缺少字段"""
        config = EmailConfig(
            name='',
            host='',
            port=0,
            username='',
            password=''
        )
        errors = config.validate()
        assert len(errors) == 4  # name, host, port, username, password


class TestSubscriptionConfig:
    """订阅配置测试"""

    def test_from_dict(self):
        """测试从字典创建配置"""
        data = {
            'name': 'Netflix',
            'renewal_day': 15,
            'alert_days_before': 3,
            'amount': 15.99,
            
            'cycle_type': 'monthly',
            'enabled': True
        }
        config = SubscriptionConfig.from_dict(data)

        assert config.name == 'Netflix'
        assert config.renewal_day == 15
        assert config.alert_days_before == 3
        assert config.amount == 15.99
        
        assert config.cycle_type == CycleType.MONTHLY

    def test_validate_success(self):
        """测试验证成功"""
        config = SubscriptionConfig(
            name='Netflix',
            renewal_day=15,
            alert_days_before=3,
            amount=15.99,
            
        )
        errors = config.validate()
        assert errors == []

    def test_validate_negative_amount(self):
        """测试验证负数金额"""
        config = SubscriptionConfig(
            name='Netflix',
            renewal_day=15,
            alert_days_before=3,
            amount=-10,
            
        )
        errors = config.validate()
        assert any('不能为负数' in err for err in errors)

    def test_validate_invalid_renewal_day_monthly(self):
        """测试月周期无效续费日"""
        config = SubscriptionConfig(
            name='Netflix',
            renewal_day=32,
            alert_days_before=3,
            amount=15.99,
            
            cycle_type=CycleType.MONTHLY
        )
        errors = config.validate()
        assert any('续费日期必须在 1-31 之间' in err for err in errors)


class TestProjectConfig:
    """项目配置测试"""

    def test_from_dict(self):
        """测试从字典创建配置"""
        data = {
            'name': 'OpenRouter',
            'provider': 'openrouter',
            'api_key': 'sk-test123',
            'threshold': 5.0,
            'type': 'credits',
            'enabled': True
        }
        config = ProjectConfig.from_dict(data)

        assert config.name == 'OpenRouter'
        assert config.provider == 'openrouter'
        assert config.api_key == 'sk-test123'
        assert config.threshold == 5.0
        assert config.type == ProjectType.CREDITS

    def test_validate_success(self):
        """测试验证成功"""
        config = ProjectConfig(
            name='OpenRouter',
            provider='openrouter',
            api_key='sk-test123',
            threshold=5.0,
            type=ProjectType.CREDITS
        )
        errors = config.validate()
        assert errors == []

    def test_validate_negative_threshold(self):
        """测试验证负数阈值"""
        config = ProjectConfig(
            name='OpenRouter',
            provider='openrouter',
            api_key='sk-test123',
            threshold=-1.0,
            type=ProjectType.CREDITS
        )
        errors = config.validate()
        assert any('不能为负数' in err for err in errors)


class TestAppConfig:
    """应用配置测试"""

    def test_from_dict(self):
        """测试从字典创建配置"""
        data = {
            'settings': {
                'balance_refresh_interval_seconds': 3600,
                'max_concurrent_checks': 5
            },
            'webhook': {
                'url': 'https://example.com/webhook',
                'type': 'custom'
            },
            'projects': [
                {
                    'name': 'OpenRouter',
                    'provider': 'openrouter',
                    'api_key': 'sk-test',
                    'threshold': 5.0,
                    'type': 'credits'
                }
            ],
            'subscriptions': [],
            'email': []
        }
        config = AppConfig.from_dict(data)

        assert config.settings.balance_refresh_interval_seconds == 3600
        assert config.settings.max_concurrent_checks == 5
        assert config.webhook is not None
        assert config.webhook.url == 'https://example.com/webhook'
        assert len(config.projects) == 1
        assert len(config.subscriptions) == 0
        assert len(config.email) == 0

    def test_validate_success(self):
        """测试验证成功"""
        data = {
            'settings': {
                'balance_refresh_interval_seconds': 3600,
                'max_concurrent_checks': 5
            },
            'projects': [
                {
                    'name': 'OpenRouter',
                    'provider': 'openrouter',
                    'api_key': 'sk-test',
                    'threshold': 5.0,
                    'type': 'credits'
                }
            ],
            'subscriptions': [],
            'email': []
        }
        config = AppConfig.from_dict(data)
        errors = config.validate()
        assert errors == {}

    def test_validate_failures(self):
        """测试验证失败"""
        data = {
            'settings': {
                'balance_refresh_interval_seconds': -1,  # 无效值
                'max_concurrent_checks': 25  # 超过最大值
            },
            'projects': [
                {
                    'name': '',  # 无效值
                    'provider': '',
                    'api_key': '',
                    'threshold': -1,
                    'type': 'credits'
                }
            ],
            'subscriptions': [],
            'email': []
        }
        config = AppConfig.from_dict(data)
        errors = config.validate()

        assert 'settings' in errors
        assert 'projects' in errors
        assert len(errors['settings']) > 0
        assert len(errors['projects']) > 0

    def test_is_valid(self):
        """测试 is_valid 方法"""
        valid_data = {
            'settings': {'balance_refresh_interval_seconds': 3600},
            'projects': [
                {
                    'name': 'OpenRouter',
                    'provider': 'openrouter',
                    'api_key': 'sk-test',
                    'threshold': 5.0,
                    'type': 'credits'
                }
            ],
            'subscriptions': [],
            'email': []
        }
        config = AppConfig.from_dict(valid_data)
        assert config.is_valid() is True

        invalid_data = {
            'settings': {'balance_refresh_interval_seconds': -1},
            'projects': [],
            'subscriptions': [],
            'email': []
        }
        config = AppConfig.from_dict(invalid_data)
        assert config.is_valid() is False


class TestSafeTypeConversion:
    """_safe_int / _safe_float 安全转换测试"""

    def test_safe_int_valid(self):
        """正常整数字符串"""
        from core.config_validator import _safe_int
        assert _safe_int('42', 0) == 42

    def test_safe_int_non_numeric_string(self):
        """非数字字符串回退为默认值"""
        from core.config_validator import _safe_int
        assert _safe_int('abc', 5) == 5

    def test_safe_int_none(self):
        """None 回退为默认值"""
        from core.config_validator import _safe_int
        assert _safe_int(None, 10) == 10

    def test_safe_int_empty_string(self):
        """空字符串回退为默认值"""
        from core.config_validator import _safe_int
        assert _safe_int('', 7) == 7

    def test_safe_int_float_string(self):
        """浮点字符串无法直接转 int，回退为默认值"""
        from core.config_validator import _safe_int
        assert _safe_int('3.9', 0) == 0

    def test_safe_float_valid(self):
        """正常浮点字符串"""
        from core.config_validator import _safe_float
        assert _safe_float('3.14', 0.0) == pytest.approx(3.14)

    def test_safe_float_non_numeric_string(self):
        """非数字字符串回退为默认值"""
        from core.config_validator import _safe_float
        assert _safe_float('xyz', 1.5) == 1.5

    def test_safe_float_none(self):
        """None 回退为默认值"""
        from core.config_validator import _safe_float
        assert _safe_float(None, 2.0) == 2.0

    def test_safe_float_empty_string(self):
        """空字符串回退为默认值"""
        from core.config_validator import _safe_float
        assert _safe_float('', 9.9) == 9.9

    def test_subscription_from_dict_non_numeric_renewal_day(self):
        """SubscriptionConfig.from_dict 传入非数字 renewal_day 不崩溃"""
        data = {
            'name': 'Test',
            'renewal_day': 'invalid',
            'alert_days_before': 'bad',
            'amount': 'xyz',
            
        }
        config = SubscriptionConfig.from_dict(data)
        assert config.renewal_day == 1  # 默认值
        assert config.alert_days_before == 3  # 默认值
        assert config.amount == 0.0  # 默认值

    def test_project_from_dict_non_numeric_threshold(self):
        """ProjectConfig.from_dict 传入非数字 threshold 不崩溃"""
        data = {
            'name': 'Test',
            'provider': 'openrouter',
            'api_key': 'sk-test',
            'threshold': 'not_a_number',
            'type': 'credits'
        }
        config = ProjectConfig.from_dict(data)
        assert config.threshold == 0.0  # 默认值

    def test_settings_from_dict_non_numeric_values(self):
        """SettingsConfig.from_dict 传入非数字值不崩溃"""
        data = {
            'balance_refresh_interval_seconds': 'abc',
            'max_concurrent_checks': None,
        }
        config = SettingsConfig.from_dict(data)
        assert config.balance_refresh_interval_seconds == 3600  # 默认值
        assert config.max_concurrent_checks == 5  # 默认值


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
