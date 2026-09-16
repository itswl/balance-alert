#!/usr/bin/env python3
"""
Prometheus Exporter - 暴露监控指标

指标服务器由 main.py 的 prometheus_client.start_http_server 启动（独立端口）。
所有定时任务都在 Web 进程内执行，指标只在这一个进程里更新；
命令行手动跑 services.monitor / services.email_scanner 时的结果不会进指标。

指标一览（* 为 prometheus_client 自动补的 _total 后缀）：
- balance_alert_balance / _threshold / _ratio / _status {project, provider, type}
- balance_alert_check_status {project, provider, type}           1=本次检查成功 0=失败（失败时保留上次余额）
- balance_alert_burn_rate_per_day / _runway_days {project, provider, type}   日均消耗、按此速率还能用几天
- balance_alert_subscription_days / _amount / _status {name, cycle_type}
- balance_alert_email_mailbox_status {mailbox}                   1=上次扫描连接正常 0=失败
- balance_alert_email_last_scan_emails / _alerts {mailbox}       上次扫描的邮件数 / 命中告警数
- balance_alert_email_scan_total / balance_alert_email_alerts_total* {mailbox}   累计
- balance_alert_job_last_run_timestamp / _last_success_timestamp / _last_status / _last_duration_seconds {task}
- balance_alert_job_runs_total* {task, status}
  （标签叫 task 而不是 job：Prometheus 抓取时会把自带的 job 标签冲突项改名成 exported_job）
- balance_alert_notifications_total* {kind, status}              Webhook 通知发送次数
- balance_alert_last_check_timestamp {check_type}                balance / subscription / email
"""
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from prometheus_client import REGISTRY, Counter, Gauge

from core.logger import get_logger

logger = get_logger('prometheus_exporter')

BALANCE_LABELS = ['project', 'provider', 'type']


class MetricsCollector:
    """指标收集器。

    Gauge 按标签组合记录，项目 / 订阅 / 邮箱被删除或改名后旧序列会在下一次更新时清掉，
    避免 Grafana 里的 count() 把已删项目算进去。
    """

    def __init__(self, registry=None):
        registry = registry if registry is not None else REGISTRY
        kw = {'registry': registry}

        # 余额指标
        self.balance_gauge = Gauge('balance_alert_balance', 'Current balance or credits', BALANCE_LABELS, **kw)
        self.balance_threshold_gauge = Gauge('balance_alert_threshold', 'Alert threshold', BALANCE_LABELS, **kw)
        self.balance_ratio_gauge = Gauge('balance_alert_ratio', 'Balance to threshold ratio', BALANCE_LABELS, **kw)
        self.balance_status_gauge = Gauge('balance_alert_status', 'Balance status (1=ok, 0=alert)', BALANCE_LABELS, **kw)
        self.balance_check_status_gauge = Gauge(
            'balance_alert_check_status',
            'Result of the last balance check (1=success, 0=failed; balance keeps its last good value)',
            BALANCE_LABELS, **kw
        )
        self.burn_rate_gauge = Gauge(
            'balance_alert_burn_rate_per_day', 'Average daily consumption over the burn-rate window',
            BALANCE_LABELS, **kw
        )
        self.runway_days_gauge = Gauge(
            'balance_alert_runway_days', 'Days of runway left at the current burn rate', BALANCE_LABELS, **kw
        )

        # 订阅续费指标
        self.subscription_days_gauge = Gauge(
            'balance_alert_subscription_days', 'Days until subscription renewal', ['name', 'cycle_type'], **kw
        )
        self.subscription_amount_gauge = Gauge(
            'balance_alert_subscription_amount', 'Subscription renewal amount', ['name', 'cycle_type'], **kw
        )
        self.subscription_status_gauge = Gauge(
            'balance_alert_subscription_status',
            'Subscription status (1=normal, 0=needs_renewal, -1=renewed_in_cycle)',
            ['name', 'cycle_type'], **kw
        )

        # 邮箱扫描指标
        self.email_scan_total_counter = Counter('balance_alert_email_scan_total', 'Total emails scanned', ['mailbox'], **kw)
        self.email_alert_counter = Counter('balance_alert_email_alerts', 'Total alert emails found', ['mailbox'], **kw)
        self.email_mailbox_status_gauge = Gauge(
            'balance_alert_email_mailbox_status', 'Mailbox status in the last scan (1=ok, 0=failed)', ['mailbox'], **kw
        )
        self.email_last_scan_emails_gauge = Gauge(
            'balance_alert_email_last_scan_emails', 'Emails scanned in the last scan', ['mailbox'], **kw
        )
        self.email_last_scan_alerts_gauge = Gauge(
            'balance_alert_email_last_scan_alerts', 'Alert emails found in the last scan', ['mailbox'], **kw
        )

        # 定时任务指标
        self.job_last_run_timestamp = Gauge('balance_alert_job_last_run_timestamp', 'Unix time of the last run', ['task'], **kw)
        self.job_last_success_timestamp = Gauge(
            'balance_alert_job_last_success_timestamp', 'Unix time of the last successful run', ['task'], **kw
        )
        self.job_last_status = Gauge('balance_alert_job_last_status', 'Result of the last run (1=success, 0=failed)', ['task'], **kw)
        self.job_last_duration_seconds = Gauge(
            'balance_alert_job_last_duration_seconds', 'Duration of the last run in seconds', ['task'], **kw
        )
        self.job_runs_counter = Counter('balance_alert_job_runs', 'Job runs by result', ['task', 'status'], **kw)

        # 通知指标
        self.notifications_counter = Counter(
            'balance_alert_notifications', 'Webhook notifications by kind and result', ['kind', 'status'], **kw
        )

        # 各类检查最近一次更新时间
        self.last_check_timestamp = Gauge('balance_alert_last_check_timestamp', 'Timestamp of last check', ['check_type'], **kw)

        # 每个带标签 Gauge 当前存在的标签组合，用来清理过期序列
        self._series: Dict[str, Set[Tuple[str, ...]]] = {}

    # ---------- 序列管理 ----------

    def _set(self, gauge: Gauge, key: str, labels: Tuple[str, ...], value: float) -> None:
        gauge.labels(*labels).set(value)
        self._series.setdefault(key, set()).add(labels)

    def _prune(self, gauges: Iterable[Gauge], key: str, keep: Set[Tuple[str, ...]]) -> None:
        """把 key 下不在 keep 里的旧标签组合从所有相关 Gauge 移除"""
        stale = self._series.get(key, set()) - keep
        for gauge in gauges:
            for labels in stale:
                try:
                    gauge.remove(*labels)
                except KeyError:
                    pass
        self._series[key] = set(keep)

    # ---------- 余额 ----------

    def update_balance_metrics(self, results: List[Dict[str, Any]]) -> None:
        """更新余额指标。失败的项目只把 check_status 置 0，余额保留上次成功值。"""
        keep_balance: Set[Tuple[str, ...]] = set()
        keep_check: Set[Tuple[str, ...]] = set()

        for result in results or []:
            labels = (
                str(result.get('project') or 'unknown'),
                str(result.get('provider') or 'unknown'),
                str(result.get('type') or 'unknown'),
            )
            keep_check.add(labels)
            if result.get('success'):
                self._record_balance(labels, result)
                keep_balance.add(labels)
            else:
                self._set(self.balance_check_status_gauge, 'check', labels, 0)
                keep_balance |= {s for s in self._series.get('balance', set()) if s[:2] == labels[:2]}

        self._prune(
            [self.balance_gauge, self.balance_threshold_gauge, self.balance_ratio_gauge, self.balance_status_gauge,
             self.burn_rate_gauge, self.runway_days_gauge],
            'balance', keep_balance,
        )
        self._prune([self.balance_check_status_gauge], 'check', keep_check)
        self.last_check_timestamp.labels(check_type='balance').set(time.time())

    def _record_balance(self, labels: Tuple[str, ...], result: Dict[str, Any]) -> None:
        credits = float(result.get('credits') or 0)
        threshold = float(result.get('threshold') or 0)
        self._set(self.balance_check_status_gauge, 'check', labels, 1)
        self._set(self.balance_gauge, 'balance', labels, credits)
        self._set(self.balance_threshold_gauge, 'balance', labels, threshold)
        self._set(self.balance_ratio_gauge, 'balance', labels, credits / threshold if threshold > 0 else 0)
        self._set(self.balance_status_gauge, 'balance', labels, 0 if result.get('need_alarm', False) else 1)

        # 消耗画像只有攒够历史才有；没有就不写，Grafana 里表现为无数据而不是 0
        runway = result.get('runway') or {}
        if runway.get('burn_per_day') is not None:
            self._set(self.burn_rate_gauge, 'balance', labels, float(runway['burn_per_day']))
        if runway.get('runway_days') is not None:
            self._set(self.runway_days_gauge, 'balance', labels, float(runway['runway_days']))

    # ---------- 订阅 ----------

    def update_subscription_metrics(self, results: List[Dict[str, Any]]) -> None:
        keep: Set[Tuple[str, ...]] = set()
        for result in results or []:
            labels = (str(result.get('name') or 'unknown'), str(result.get('cycle_type') or 'monthly'))
            already_renewed = result.get('already_renewed', result.get('already_renewed_in_cycle', False))
            if already_renewed:
                status = -1
            elif result.get('need_alert', False):
                status = 0
            else:
                status = 1

            self._set(self.subscription_days_gauge, 'subscription', labels, float(result.get('days_until_renewal') or 0))
            self._set(self.subscription_amount_gauge, 'subscription', labels, float(result.get('amount') or 0))
            self._set(self.subscription_status_gauge, 'subscription', labels, status)
            keep.add(labels)

        self._prune(
            [self.subscription_days_gauge, self.subscription_amount_gauge, self.subscription_status_gauge],
            'subscription', keep,
        )
        self.last_check_timestamp.labels(check_type='subscription').set(time.time())

    # ---------- 邮箱扫描 ----------

    def update_email_metrics(self, summary: Dict[str, Any]) -> None:
        """入参为 EmailScanner.scan_emails 的返回值；累计 Counter 只增，Gauge 反映上次扫描。"""
        keep: Set[Tuple[str, ...]] = set()
        for mailbox in (summary or {}).get('mailboxes') or []:
            labels = (str(mailbox.get('name') or 'unknown'),)
            total_emails = int(mailbox.get('total_emails') or 0)
            alert_count = int(mailbox.get('alert_count') or 0)
            ok = mailbox.get('error') is None and mailbox.get('success', True)

            self._set(self.email_mailbox_status_gauge, 'mailbox', labels, 1 if ok else 0)
            self._set(self.email_last_scan_emails_gauge, 'mailbox', labels, total_emails)
            self._set(self.email_last_scan_alerts_gauge, 'mailbox', labels, alert_count)
            self.email_scan_total_counter.labels(*labels).inc(total_emails)
            self.email_alert_counter.labels(*labels).inc(alert_count)
            keep.add(labels)

        self._prune(
            [self.email_mailbox_status_gauge, self.email_last_scan_emails_gauge, self.email_last_scan_alerts_gauge],
            'mailbox', keep,
        )
        self.last_check_timestamp.labels(check_type='email').set(time.time())

    # ---------- 定时任务 / 通知 ----------

    def record_job_run(self, task: str, success: bool, duration_seconds: float,
                       started_at: Optional[datetime] = None) -> None:
        timestamp = started_at.timestamp() if started_at else time.time()
        self.job_last_run_timestamp.labels(task).set(timestamp)
        self.job_last_status.labels(task).set(1 if success else 0)
        self.job_last_duration_seconds.labels(task).set(duration_seconds)
        self.job_runs_counter.labels(task, 'success' if success else 'failed').inc()
        if success:
            self.job_last_success_timestamp.labels(task).set(timestamp)

    def record_notification(self, kind: str, success: bool) -> None:
        self.notifications_counter.labels(kind, 'success' if success else 'failed').inc()


# 进程唯一实例，注册到默认 REGISTRY；测试用 MetricsCollector(registry=CollectorRegistry()) 隔离
metrics_collector = MetricsCollector()
