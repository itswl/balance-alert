"""
进程内定时任务调度器与时间工具测试
"""
import threading
import time
from datetime import datetime, time as dtime, timedelta, timezone

import pytest

from core.scheduler import Job, JobResult, JobScheduler
from core.timeutil import describe_daily_times, next_daily_occurrence, parse_daily_times, to_utc_iso

CST = timezone(timedelta(hours=8))


class TestParseDailyTimes:

    def test_parses_and_sorts(self):
        assert parse_daily_times('15:30, 9:00,09:00') == [dtime(9, 0), dtime(15, 30)]

    @pytest.mark.parametrize('text', [None, '', '   ', 'off', 'OFF', 'none', 'disabled', '-', '0'])
    def test_off_values_mean_disabled(self, text):
        assert parse_daily_times(text) == []

    @pytest.mark.parametrize('text', ['9am', '25:00', '12:60', '09:00;15:00', '9'])
    def test_invalid_raises(self, text):
        with pytest.raises(ValueError):
            parse_daily_times(text)

    def test_describe(self):
        assert describe_daily_times([]) == '已关闭'
        assert describe_daily_times([dtime(15, 0), dtime(9, 0)]) == '每天 09:00 / 15:00'


class TestNextDailyOccurrence:
    times = [dtime(9, 0), dtime(15, 0)]

    def test_before_first_time_today(self):
        now = datetime(2026, 9, 14, 8, 0, tzinfo=CST)
        assert next_daily_occurrence(now, self.times) == datetime(2026, 9, 14, 9, 0, tzinfo=CST)

    def test_between_times(self):
        now = datetime(2026, 9, 14, 10, 0, tzinfo=CST)
        assert next_daily_occurrence(now, self.times) == datetime(2026, 9, 14, 15, 0, tzinfo=CST)

    def test_after_last_time_rolls_to_tomorrow(self):
        now = datetime(2026, 9, 14, 16, 0, tzinfo=CST)
        assert next_daily_occurrence(now, self.times) == datetime(2026, 9, 15, 9, 0, tzinfo=CST)

    def test_exactly_at_time_goes_to_next(self):
        now = datetime(2026, 9, 14, 9, 0, tzinfo=CST)
        assert next_daily_occurrence(now, self.times) == datetime(2026, 9, 14, 15, 0, tzinfo=CST)

    def test_to_utc_iso(self):
        assert to_utc_iso(datetime(2026, 9, 14, 9, 0, tzinfo=CST)) == '2026-09-14T01:00:00Z'
        assert to_utc_iso(None) is None


class TestJob:

    def test_enabled_and_schedule_text(self):
        assert Job('a', lambda: None).enabled is False
        assert Job('a', lambda: None).schedule_text() == '已关闭'
        assert Job('b', lambda: None, interval_seconds=60).schedule_text() == '每 60 秒'
        assert Job('c', lambda: None, daily_times=[dtime(9, 0)]).schedule_text() == '每天 09:00'
        assert Job('d', lambda: None, interval_seconds=0).enabled is False

    def test_initial_next_run(self):
        now = datetime(2026, 9, 14, 8, 0, tzinfo=CST)
        assert Job('a', lambda: None, interval_seconds=60, run_at_start=True).initial_next_run(now) == now
        assert Job('b', lambda: None, interval_seconds=60).initial_next_run(now) == now + timedelta(seconds=60)
        assert Job('c', lambda: None, daily_times=[dtime(9, 0)]).initial_next_run(now) == datetime(2026, 9, 14, 9, 0, tzinfo=CST)
        assert Job('d', lambda: None).initial_next_run(now) is None


class TestJobScheduler:

    def test_runs_due_job_and_advances(self):
        calls = []
        results = []
        job = Job('refresh', lambda: calls.append(1) or {'ok': True}, interval_seconds=3600, run_at_start=True)
        scheduler = JobScheduler([job], on_result=lambda j, r: results.append((j.name, r)))

        executed = scheduler.run_pending()
        assert len(executed) == 1 and executed[0].success is True and executed[0].detail == {'ok': True}
        assert calls == [1]
        assert results[0][0] == 'refresh' and results[0][1].error is None
        assert job.next_run > datetime.now().astimezone() + timedelta(seconds=3500)

        # 还没到点，不再执行
        assert scheduler.run_pending() == []
        assert calls == [1]

    def test_failure_is_recorded_not_raised(self):
        results = []

        def boom():
            raise RuntimeError('imap down')

        job = Job('email_scan', boom, interval_seconds=60, run_at_start=True)
        scheduler = JobScheduler([job], on_result=lambda j, r: results.append(r))
        executed = scheduler.run_pending()
        assert executed[0].success is False
        assert 'imap down' in executed[0].error
        assert results[0].success is False
        assert job.next_run is not None  # 失败也照常排下一次

    def test_disabled_and_future_jobs_do_not_run(self):
        ran = []
        disabled = Job('off', lambda: ran.append('off'))
        later = Job('later', lambda: ran.append('later'), daily_times=[dtime(23, 59)])
        later_now = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        scheduler = JobScheduler([disabled, later])
        assert scheduler.run_pending(now=later_now) == []
        assert ran == []
        assert disabled.next_run is None

    def test_on_result_exception_is_swallowed(self):
        def bad_handler(job, result):
            raise ValueError('handler broke')

        job = Job('a', lambda: 1, interval_seconds=60, run_at_start=True)
        scheduler = JobScheduler([job], on_result=bad_handler)
        assert scheduler.run_pending()[0].success is True

    def test_seconds_until_next_is_bounded(self):
        soon = Job('soon', lambda: 1, interval_seconds=10, run_at_start=True)
        scheduler = JobScheduler([soon], max_wait_seconds=60)
        assert 0.1 <= scheduler._seconds_until_next() <= 60
        far = Job('far', lambda: 1, interval_seconds=100000)
        assert JobScheduler([far], max_wait_seconds=60)._seconds_until_next() == 60
        assert JobScheduler([Job('off', lambda: 1)], max_wait_seconds=60)._seconds_until_next() == 60

    def test_run_job_directly(self):
        job = Job('manual', lambda: 'done', daily_times=[dtime(3, 0)])
        result = JobScheduler([job]).run_job(job)
        assert result.success and result.detail == 'done'

    def test_background_thread_runs_and_stops(self):
        done = threading.Event()
        stop = threading.Event()
        job = Job('tick', lambda: done.set(), interval_seconds=3600, run_at_start=True)
        scheduler = JobScheduler([job], stop_event=stop)
        scheduler.start()
        assert done.wait(timeout=5), '后台线程没有执行到点的任务'
        scheduler.stop(timeout=5)
        assert stop.is_set()
        assert not scheduler._thread.is_alive()
