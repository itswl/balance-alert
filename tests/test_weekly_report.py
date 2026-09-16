"""
周报汇总与渲染测试
"""
from unittest.mock import patch

import pytest

from core.config_loader import make_project_id
from services import weekly_report
from services.runway import Runway

PROVIDER = 'openrouter'


def _profile(project, consumed, runway_days, balance, burn=None, depletion='2026-09-20'):
    return Runway(
        project_id=make_project_id(PROVIDER, project), project_name=project, provider=PROVIDER,
        current_balance=balance, consumed=consumed, burn_per_day=burn if burn is not None else consumed / 7,
        runway_days=runway_days, depletion_date=depletion, confidence='high',
    )


@pytest.fixture
def states():
    balance = {'projects': [
        {'project': 'A', 'provider': PROVIDER, 'success': True, 'credits': 70, 'threshold': 50, 'need_alarm': False},
        {'project': 'B', 'provider': PROVIDER, 'success': True, 'credits': 10, 'threshold': 100, 'need_alarm': True},
        {'project': 'C', 'provider': PROVIDER, 'success': False, 'error': 'HTTP 401'},
    ]}
    subscriptions = {'subscriptions': [
        {'name': 'ChatGPT Plus', 'days_until_renewal': 3, 'amount': 20, 'already_renewed': False},
        {'name': '域名', 'days_until_renewal': 200, 'amount': 88, 'already_renewed': False},
        {'name': '已续费的', 'days_until_renewal': 2, 'amount': 30, 'already_renewed': True},
    ]}
    email = {'mailboxes': [{'name': '工作', 'error': None}, {'name': '备用', 'error': 'login failed'}],
             'summary': {'total_alerts': 2}}
    return balance, subscriptions, email


@pytest.fixture
def profiles():
    return {
        make_project_id(PROVIDER, 'A'): _profile('A', consumed=700, runway_days=7, balance=70),
        make_project_id(PROVIDER, 'B'): _profile('B', consumed=100, runway_days=2, balance=10),
    }


class TestBuild:

    def test_counts_accounts_and_consumption(self, states, profiles):
        summary = weekly_report.build(*states, runways=profiles)
        assert summary['accounts'] == {'total': 3, 'alerting': 1, 'failed': 1}
        assert summary['total_consumed'] == pytest.approx(800)
        assert summary['period']['start'] < summary['period']['end']

    def test_rankings(self, states, profiles):
        summary = weekly_report.build(*states, runways=profiles)
        assert [s['project'] for s in summary['top_spend']] == ['A', 'B']        # 消耗从多到少
        assert [s['project'] for s in summary['shortest_runway']] == ['B', 'A']  # 跑道从短到长

    def test_upcoming_subscriptions_within_window_only(self, states, profiles):
        summary = weekly_report.build(*states, runways=profiles)
        assert [s['name'] for s in summary['upcoming_subscriptions']] == ['ChatGPT Plus']
        assert summary['upcoming_amount'] == pytest.approx(20)   # 200 天后的和已续费的都不算

    def test_problems_are_collected(self, states, profiles):
        summary = weekly_report.build(*states, runways=profiles)
        assert summary['alerting_projects'] == [{'project': 'B', 'balance': 10, 'threshold': 100}]
        assert summary['failed_projects'] == [{'project': 'C', 'error': 'HTTP 401'}]
        assert summary['mailboxes'] == {'total': 2, 'failed': 1, 'alerts': 2}

    def test_without_history_still_reports_accounts(self, states):
        summary = weekly_report.build(*states, runways={})
        assert summary['total_consumed'] is None
        assert summary['top_spend'] == [] and summary['shortest_runway'] == []
        assert summary['accounts']['total'] == 3

    def test_empty_states(self):
        summary = weekly_report.build({}, {}, {}, runways={})
        assert summary['accounts'] == {'total': 0, 'alerting': 0, 'failed': 0}
        assert summary['upcoming_amount'] == 0

    def test_computes_profiles_when_not_given(self, states):
        with patch.object(weekly_report.runway_service, 'compute_all', return_value={}) as compute_all:
            weekly_report.build(*states)
        compute_all.assert_called_once_with(window_days=weekly_report.REPORT_WINDOW_DAYS)


class TestRender:

    def test_contains_every_section(self, states, profiles):
        text = weekly_report.render(weekly_report.build(*states, runways=profiles))
        for fragment in ['统计区间', '本周消耗', '最先见底', '消耗最多', '订阅支出', '需要处理',
                         'B: 还剩 2.0 天', 'A: 700.00', 'ChatGPT Plus', 'HTTP 401', '邮箱: 1 个连接失败']:
            assert fragment in text, fragment

    def test_all_clear_report_is_short(self):
        summary = weekly_report.build(
            {'projects': [{'project': 'A', 'provider': PROVIDER, 'success': True, 'need_alarm': False}]},
            {}, {}, runways={})
        text = weekly_report.render(summary)
        assert '全部正常' in text
        assert '需要处理' not in text


class TestSend:

    def test_sends_via_webhook(self, states, profiles):
        summary = weekly_report.build(*states, runways=profiles)
        with patch.object(weekly_report.WebhookAdapter, 'from_settings') as from_settings:
            adapter = from_settings.return_value
            adapter.send_custom_alert.return_value = True
            assert weekly_report.send(summary) is True
        assert adapter.send_custom_alert.call_args.args[0] == '余额周报'
        assert adapter.send_custom_alert.call_args.kwargs['kind'] == 'weekly_report'

    def test_without_webhook_configured(self, states, profiles):
        summary = weekly_report.build(*states, runways=profiles)
        with patch.object(weekly_report.WebhookAdapter, 'from_settings', return_value=None):
            assert weekly_report.send(summary) is False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
