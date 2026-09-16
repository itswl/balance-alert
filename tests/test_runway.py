"""
消耗速率与跑道分析测试 —— 计算部分是纯函数，告警部分打桩 alert_store 与 Webhook
"""
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from core.config_loader import make_project_id
from services import runway as runway_service
from services.runway import Runway, compute

PROVIDER = 'openrouter'
PROJECT = 'OpenRouter'


def series(values, step_hours=24, now=None, project=PROJECT, provider=PROVIDER):
    """把一串余额值（从旧到新）变成带本地时区时间戳的快照序列，最后一条落在 now"""
    now = now or datetime.now().astimezone()
    last = len(values) - 1
    return [{
        'project_id': make_project_id(provider, project),
        'project_name': project,
        'provider': provider,
        'balance_type': 'balance',
        'balance': value,
        'timestamp': now - timedelta(hours=step_hours * (last - i)),
    } for i, value in enumerate(values)]


class TestCompute:

    def test_empty_and_single_point_give_no_estimate(self):
        assert compute([]).confidence == 'none'
        single = compute(series([100]))
        assert single.data_points == 1
        assert single.current_balance == 100
        assert single.burn_per_day is None and single.runway_days is None

    def test_steady_burn(self):
        """每天掉 10，余额 70：日均 10，跑道 7 天"""
        result = compute(series([100, 90, 80, 70]))
        assert result.data_points == 4
        assert result.span_hours == pytest.approx(72, abs=0.1)
        assert result.consumed == pytest.approx(30)
        assert result.topped_up == 0
        assert result.burn_per_day == pytest.approx(10, abs=0.01)
        assert result.runway_days == pytest.approx(7, abs=0.02)
        assert result.confidence == 'high'
        assert result.current_balance == 70
        assert result.project_name == PROJECT and result.provider == PROVIDER

    def test_depletion_date_follows_runway(self):
        now = datetime.now().astimezone()
        result = compute(series([100, 90, 80, 70], now=now), now=now)
        assert result.depletion_date == (now + timedelta(days=result.runway_days)).date().isoformat()

    def test_topup_is_not_negative_consumption(self):
        """中间充了一次钱：消耗只算下降段，充值单独计"""
        result = compute(series([100, 60, 160, 120]))
        assert result.consumed == pytest.approx(80)    # 40 + 40
        assert result.topped_up == pytest.approx(100)
        assert result.current_balance == 120

    def test_flat_balance_has_no_runway(self):
        result = compute(series([50, 50, 50, 50]))
        assert result.burn_per_day == 0
        assert result.runway_days is None and result.depletion_date is None

    def test_zero_balance_gives_zero_runway(self):
        result = compute(series([40, 30, 20, 0]))
        assert result.runway_days == 0

    @pytest.mark.parametrize('points, step_hours, expected', [
        (3, 24, 'none'),     # 点太少
        (5, 1, 'none'),      # 跨度不足 6 小时
        (5, 2, 'low'),       # 8 小时
        (5, 12, 'medium'),   # 48 小时
        (5, 24, 'high'),     # 96 小时
    ])
    def test_confidence_levels(self, points, step_hours, expected):
        values = [100 - i for i in range(points)]
        assert compute(series(values, step_hours=step_hours)).confidence == expected

    def test_daily_buckets_fill_gaps_with_zero(self):
        result = compute(series([100, 90, 90, 80]))
        assert [d['consumed'] for d in result.daily] == [0, 10, 0, 10]
        assert result.daily[0]['date'] < result.daily[-1]['date']

    def test_spike_ratio_against_median_of_prior_days(self):
        """前几天各花 10，今天花 50，是日常的 5 倍"""
        result = compute(series([100, 90, 80, 70, 20]))
        assert result.today_consumed == pytest.approx(50)
        assert result.baseline_consumed == pytest.approx(10)
        assert result.spike_ratio == pytest.approx(5.0)

    def test_no_spike_without_enough_baseline_days(self):
        result = compute(series([100, 50]))
        assert result.spike_ratio is None

    def test_iso_string_timestamps_are_accepted(self):
        records = series([100, 90, 80, 70])
        for record in records:
            record['timestamp'] = record['timestamp'].isoformat()
        assert compute(records).burn_per_day == pytest.approx(10, abs=0.01)

    def test_to_dict_is_json_friendly(self):
        data = compute(series([100, 90, 80, 70])).to_dict()
        assert data['runway_days'] == pytest.approx(7, abs=0.02)
        assert isinstance(data['daily'], list)


class TestAttach:

    def test_attaches_profile_to_matching_result(self):
        results = [
            {'project': PROJECT, 'provider': PROVIDER, 'success': True, 'credits': 70},
            {'project': '别的', 'provider': 'volc', 'success': True, 'credits': 10},
            {'project': '失败的', 'provider': PROVIDER, 'success': False},
        ]
        profiles = {make_project_id(PROVIDER, PROJECT): compute(series([100, 90, 80, 70]))}
        with patch.object(runway_service, 'compute_all', return_value=profiles):
            returned = runway_service.attach(results)
        assert returned is profiles
        assert results[0]['runway']['runway_days'] == pytest.approx(7, abs=0.02)
        assert 'runway' not in results[1]   # 没有历史的账户不挂
        assert 'runway' not in results[2]   # 失败的检查不挂

    def test_no_history_means_no_change(self):
        results = [{'project': PROJECT, 'provider': PROVIDER, 'success': True}]
        with patch.object(runway_service, 'compute_all', return_value={}):
            assert runway_service.attach(results) == {}
        assert 'runway' not in results[0]


@pytest.fixture
def alert_env():
    """打桩冷却判断与发送，返回 (store, sender)"""
    with patch.object(runway_service, 'alert_store') as store, \
         patch.object(runway_service, '_alert', return_value=True) as sender:
        store.cooldown_seconds.return_value = 86400
        store.in_cooldown.return_value = False
        yield store, sender


def _result(need_alarm=False, success=True):
    return {'project': PROJECT, 'provider': PROVIDER, 'owner_project': 'AI 平台',
            'success': success, 'need_alarm': need_alarm, 'credits': 70}


def _profiles(profile):
    return {make_project_id(PROVIDER, PROJECT): profile}


class TestRunwayAlert:

    def test_fires_when_runway_below_limit(self, alert_env, monkeypatch):
        monkeypatch.setenv('RUNWAY_ALERT_DAYS', '10')
        store, sender = alert_env
        profile = compute(series([100, 90, 80, 70]))   # 跑道 7 天
        sent = runway_service.check_alerts([_result()], _profiles(profile))
        assert sent['runway'] == 1
        assert sender.call_args.kwargs['kind'] == 'runway'
        assert store.record_alert.call_args.args[2] == 'low_runway'

    def test_silent_when_runway_is_long(self, alert_env, monkeypatch):
        monkeypatch.setenv('RUNWAY_ALERT_DAYS', '3')
        _, sender = alert_env
        profile = compute(series([100, 90, 80, 70]))
        assert runway_service.check_alerts([_result()], _profiles(profile))['runway'] == 0
        sender.assert_not_called()

    def test_skipped_when_threshold_alert_already_firing(self, alert_env, monkeypatch):
        """阈值告警已经在喊了，不再为同一个账户重复喊跑道"""
        monkeypatch.setenv('RUNWAY_ALERT_DAYS', '10')
        _, sender = alert_env
        profile = compute(series([100, 90, 80, 70]))
        assert runway_service.check_alerts([_result(need_alarm=True)], _profiles(profile))['runway'] == 0
        sender.assert_not_called()

    def test_respects_cooldown(self, alert_env, monkeypatch):
        monkeypatch.setenv('RUNWAY_ALERT_DAYS', '10')
        store, sender = alert_env
        store.in_cooldown.return_value = True
        profile = compute(series([100, 90, 80, 70]))
        assert runway_service.check_alerts([_result()], _profiles(profile))['runway'] == 0
        sender.assert_not_called()

    def test_dry_run_does_not_send(self, alert_env, monkeypatch):
        monkeypatch.setenv('RUNWAY_ALERT_DAYS', '10')
        _, sender = alert_env
        profile = compute(series([100, 90, 80, 70]))
        assert runway_service.check_alerts([_result()], _profiles(profile), dry_run=True)['runway'] == 0
        sender.assert_not_called()

    def test_zero_setting_disables(self, alert_env, monkeypatch):
        monkeypatch.setenv('RUNWAY_ALERT_DAYS', '0')
        monkeypatch.setenv('SPEND_SPIKE_RATIO', '0')
        _, sender = alert_env
        profile = compute(series([100, 90, 80, 70]))
        assert runway_service.check_alerts([_result()], _profiles(profile)) == {'runway': 0, 'spike': 0}
        sender.assert_not_called()

    def test_low_confidence_data_is_not_alerted(self, alert_env, monkeypatch):
        monkeypatch.setenv('RUNWAY_ALERT_DAYS', '100')
        _, sender = alert_env
        profile = compute(series([100, 99, 98, 97, 96], step_hours=1))  # 跨度 4 小时
        assert runway_service.check_alerts([_result()], _profiles(profile))['runway'] == 0
        sender.assert_not_called()


class TestSpikeAlert:

    def test_fires_on_spend_spike(self, alert_env, monkeypatch):
        monkeypatch.setenv('SPEND_SPIKE_RATIO', '3')
        monkeypatch.setenv('RUNWAY_ALERT_DAYS', '0')
        store, sender = alert_env
        profile = compute(series([100, 90, 80, 70, 20]))   # 今天 50，是日常 10 的 5 倍
        sent = runway_service.check_alerts([_result()], _profiles(profile))
        assert sent['spike'] == 1
        assert sender.call_args.kwargs['kind'] == 'spend_spike'
        assert store.record_alert.call_args.args[2] == 'spend_spike'

    def test_below_ratio_is_silent(self, alert_env, monkeypatch):
        monkeypatch.setenv('SPEND_SPIKE_RATIO', '10')
        monkeypatch.setenv('RUNWAY_ALERT_DAYS', '0')
        _, sender = alert_env
        profile = compute(series([100, 90, 80, 70, 20]))
        assert runway_service.check_alerts([_result()], _profiles(profile))['spike'] == 0
        sender.assert_not_called()

    def test_tiny_absolute_amounts_are_ignored(self, alert_env, monkeypatch):
        """比例再大，绝对值太小也不值得打扰"""
        monkeypatch.setenv('SPEND_SPIKE_RATIO', '3')
        monkeypatch.setenv('RUNWAY_ALERT_DAYS', '0')
        monkeypatch.setenv('SPEND_SPIKE_MIN_AMOUNT', '100')
        _, sender = alert_env
        profile = compute(series([100, 90, 80, 70, 20]))
        assert runway_service.check_alerts([_result()], _profiles(profile))['spike'] == 0
        sender.assert_not_called()


class TestAnalyze:

    def test_analyze_attaches_then_alerts(self, monkeypatch):
        monkeypatch.setenv('RUNWAY_ALERT_DAYS', '10')
        results = [_result()]
        profile = compute(series([100, 90, 80, 70]))
        with patch.object(runway_service, 'compute_all', return_value=_profiles(profile)), \
             patch.object(runway_service, '_alert', return_value=True) as sender, \
             patch.object(runway_service, 'alert_store') as store:
            store.cooldown_seconds.return_value = 0
            store.in_cooldown.return_value = False
            runway_service.analyze(results, dry_run=False)
        assert results[0]['runway']['runway_days'] == pytest.approx(7, abs=0.02)
        sender.assert_called_once()

    def test_analyze_without_history_is_noop(self):
        results = [_result()]
        with patch.object(runway_service, 'compute_all', return_value={}), \
             patch.object(runway_service, '_alert') as sender:
            assert runway_service.analyze(results) == {}
        sender.assert_not_called()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
