#!/usr/bin/env python3
"""
消耗速率与跑道分析

余额历史是一串快照，相邻两点之间余额下降就是消耗，上升就是充值。把这串快照还原成
「消耗 / 充值」两类事件，就能算出日均消耗、还能用几天（跑道）、以及今天的消耗是不是
比平时突然放大了。这两件事比静态阈值更早、也更能反映真实风险：

- 跑道：同样是 430 元，日烧 5 元和日烧 200 元是两回事
- 突增：消耗忽然放大数倍，往往意味着 key 泄露或某个任务跑飞了

数据库未启用时没有历史，所有结果为空，调用方自然退回到纯阈值告警。
"""
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import median
from typing import Any, Dict, List, Optional

from core.logger import get_logger
from core.settings import get_settings
from database.repository import BalanceRepository
from services import alert_store
from services.webhook_adapter import WebhookAdapter

logger = get_logger('runway')

# 少于这些数据就不给结论：算出来的速率没有意义
MIN_POINTS = 4
MIN_SPAN_HOURS = 6.0
# 突增判断至少要有几个完整的历史日做基线
MIN_BASELINE_DAYS = 3

CONFIDENCE_ALERTABLE = ('medium', 'high')


def _as_local(timestamp: Any) -> Optional[datetime]:
    """数据库里存的是 naive UTC，转成带时区的本地时间，按用户所在时区分天"""
    if isinstance(timestamp, str):
        try:
            timestamp = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        except ValueError:
            return None
    if not isinstance(timestamp, datetime):
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp.astimezone()


@dataclass
class Runway:
    """一个账户的消耗画像"""
    project_id: str = ''
    project_name: str = ''
    provider: str = ''
    balance_type: str = ''
    current_balance: Optional[float] = None
    window_days: int = 7
    data_points: int = 0
    span_hours: float = 0.0
    consumed: float = 0.0          # 窗口内累计消耗
    topped_up: float = 0.0         # 窗口内累计充值（余额上跳）
    burn_per_day: Optional[float] = None
    runway_days: Optional[float] = None
    depletion_date: Optional[str] = None   # 本地日期 YYYY-MM-DD
    confidence: str = 'none'       # none / low / medium / high
    daily: List[Dict[str, Any]] = field(default_factory=list)  # [{date, consumed}]，按日期升序
    today_consumed: Optional[float] = None
    baseline_consumed: Optional[float] = None   # 之前若干完整日消耗的中位数
    spike_ratio: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def has_estimate(self) -> bool:
        return self.burn_per_day is not None and self.confidence != 'none'


def _confidence(points: int, span_hours: float) -> str:
    """数据太少或跨度太短就不下结论；跨度不足一天的结果不用于告警"""
    if points < MIN_POINTS or span_hours < MIN_SPAN_HOURS:
        return 'none'
    if span_hours < 24:
        return 'low'
    if span_hours < 72:
        return 'medium'
    return 'high'


def _valid_points(records: List[Dict[str, Any]]) -> List[tuple]:
    """(本地时间, 余额) 列表，按时间升序；解析不出时间或余额的记录直接丢掉"""
    points = []
    for record in records or []:
        timestamp = _as_local(record.get('timestamp'))
        balance = record.get('balance')
        if timestamp is not None and balance is not None:
            points.append((timestamp, float(balance)))
    points.sort(key=lambda point: point[0])
    return points


def _split_flows(points: List[tuple]) -> tuple:
    """把余额序列还原成收支：下降是消耗，上升是充值；消耗同时按本地日期归集"""
    consumed = topped_up = 0.0
    per_day: Dict[str, float] = {}
    for (_, before), (timestamp, after) in zip(points, points[1:]):
        delta = before - after
        if delta > 0:
            consumed += delta
            day = timestamp.date().isoformat()
            per_day[day] = per_day.get(day, 0.0) + delta
        elif delta < 0:
            topped_up += -delta
    return round(consumed, 4), round(topped_up, 4), per_day


def _fill_daily(per_day: Dict[str, float], start, end) -> List[Dict[str, Any]]:
    """按日铺平，没有消耗的日子补 0，这样中位数才反映真实的「平时」"""
    return [
        {'date': day.isoformat(), 'consumed': round(per_day.get(day.isoformat(), 0.0), 4)}
        for day in (start + timedelta(days=i) for i in range((end - start).days + 1))
    ]


def _spike(daily: List[Dict[str, Any]], today: str) -> tuple:
    """(今日消耗, 日常中位数, 倍数)；最后一天不是今天或基线不足时后两项为 None"""
    if not daily or daily[-1]['date'] != today:
        return None, None, None
    today_consumed = daily[-1]['consumed']
    baseline_days = [day['consumed'] for day in daily[:-1]]
    if len(baseline_days) < MIN_BASELINE_DAYS:
        return today_consumed, None, None
    baseline = round(median(baseline_days), 4)
    ratio = round(today_consumed / baseline, 2) if baseline > 0 else None
    return today_consumed, baseline, ratio


def compute(records: List[Dict[str, Any]], window_days: int = 7, now: Optional[datetime] = None) -> Runway:
    """从一个账户的余额快照序列算出消耗画像。

    records 至少要有 timestamp 与 balance；账户信息取最后一条的值。
    """
    now = now or datetime.now().astimezone()
    points = _valid_points(records)
    last = (records or [{}])[-1]
    result = Runway(
        project_id=str(last.get('project_id') or ''),
        project_name=str(last.get('project_name') or ''),
        provider=str(last.get('provider') or ''),
        balance_type=str(last.get('balance_type') or ''),
        current_balance=points[-1][1] if points else None,
        window_days=window_days,
        data_points=len(points),
    )
    if len(points) < 2:
        return result

    result.span_hours = round((points[-1][0] - points[0][0]).total_seconds() / 3600, 2)
    result.consumed, result.topped_up, per_day = _split_flows(points)
    result.confidence = _confidence(len(points), result.span_hours)
    if result.confidence == 'none':
        return result

    result.burn_per_day = round(result.consumed / max(result.span_hours / 24, 1 / 24), 4)
    if result.burn_per_day > 0 and result.current_balance is not None:
        result.runway_days = round(max(result.current_balance, 0) / result.burn_per_day, 2)
        result.depletion_date = (now + timedelta(days=result.runway_days)).date().isoformat()

    result.daily = _fill_daily(per_day, points[0][0].date(), points[-1][0].date())
    result.today_consumed, result.baseline_consumed, result.spike_ratio = _spike(result.daily, now.date().isoformat())
    return result


def compute_all(window_days: Optional[int] = None) -> Dict[str, Runway]:
    """读余额历史，算出所有账户的消耗画像；数据库未启用时返回空字典"""
    window_days = window_days or get_settings().burn_rate_window_days
    series = BalanceRepository.get_balance_series(days=window_days)
    if not series:
        return {}

    by_project: Dict[str, List[Dict[str, Any]]] = {}
    for record in series:
        by_project.setdefault(record['project_id'], []).append(record)
    return {pid: compute(records, window_days) for pid, records in by_project.items()}


def attach(results: List[Dict[str, Any]]) -> Dict[str, Runway]:
    """把消耗画像挂到余额检查结果上（键 runway），供看板、指标和告警共用"""
    from core.config_loader import make_project_id

    runways = compute_all()
    if not runways:
        return {}
    for result in results or []:
        if not result.get('success'):
            continue
        runway = runways.get(make_project_id(result.get('provider') or '', result.get('project') or ''))
        if runway is not None:
            result['runway'] = runway.to_dict()
    return runways


# ---------- 趋势告警 ----------

@dataclass
class _Notice:
    """一条待发的趋势告警：alert_type 用于冷却去重，kind 用于指标分类"""
    alert_type: str
    kind: str
    title: str
    lines: List[str]
    message: str
    value: Optional[float] = None
    threshold: Optional[float] = None


def _alert(title: str, lines: List[str], kind: str) -> bool:
    adapter = WebhookAdapter.from_settings('credit-monitor')
    if adapter is None:
        logger.error("未配置 webhook 地址")
        return False
    return adapter.send_custom_alert(title, '\n'.join(lines), kind=kind)


def _head(result: Dict[str, Any]) -> List[str]:
    lines = [f"**账户**: {result.get('project')}"]
    if result.get('owner_project'):
        lines.append(f"**所属项目**: {result['owner_project']}")
    return lines


def _runway_notice(result: Dict[str, Any], runway: Runway, limit_days: float) -> _Notice:
    return _Notice(
        alert_type='low_runway', kind='runway',
        title=f"余额跑道不足: {result.get('project')}",
        lines=_head(result) + [
            f"**服务商**: {result.get('provider')}",
            f"**当前余额**: {runway.current_balance:,.2f}",
            f"**日均消耗**: {runway.burn_per_day:,.2f}（最近 {runway.window_days} 天）",
            f"**预计耗尽**: {runway.depletion_date}，还剩 {runway.runway_days:.1f} 天（阈值 {limit_days:g} 天）",
        ],
        message=f"跑道不足: {runway.runway_days:.1f} 天，预计 {runway.depletion_date} 耗尽",
        value=runway.current_balance, threshold=limit_days,
    )


def _spike_notice(result: Dict[str, Any], runway: Runway) -> _Notice:
    lines = _head(result) + [
        f"**今日消耗**: {runway.today_consumed:,.2f}",
        f"**日常水平**: {runway.baseline_consumed:,.2f}（最近 {runway.window_days} 天中位数）",
        f"**放大倍数**: {runway.spike_ratio:.1f}x",
        f"**当前余额**: {runway.current_balance:,.2f}",
    ]
    if runway.runway_days is not None:
        lines.append(f"**按当前速率**: 还剩 {runway.runway_days:.1f} 天")
    return _Notice(
        alert_type='spend_spike', kind='spend_spike',
        title=f"消耗异常放大: {result.get('project')}", lines=lines,
        message=f"消耗突增: 今日 {runway.today_consumed:,.2f}，是日常的 {runway.spike_ratio:.1f} 倍",
        value=runway.today_consumed, threshold=runway.baseline_consumed,
    )


def _emit(project_id: str, project_name: str, notice: _Notice, cooldown: int) -> bool:
    """冷却窗口内不重复打扰；发出去了才留痕"""
    if alert_store.in_cooldown(project_id, notice.alert_type, cooldown):
        return False
    if not _alert(notice.title, notice.lines, kind=notice.kind):
        return False
    alert_store.record_alert(project_id, project_name, notice.alert_type,
                             notice.message, notice.value, notice.threshold)
    return True


def _runway_due(result: Dict[str, Any], runway: Runway, limit_days: float) -> bool:
    """跑道见底。阈值告警已经在喊的账户不重复喊。"""
    return (limit_days > 0 and runway.runway_days is not None
            and runway.runway_days <= limit_days and not result.get('need_alarm'))


def _spike_due(runway: Runway, settings) -> bool:
    """消耗突增。比例再大，绝对值太小也不值得打扰。"""
    return (settings.spend_spike_ratio > 0 and runway.spike_ratio is not None
            and runway.spike_ratio >= settings.spend_spike_ratio
            and (runway.today_consumed or 0) >= settings.spend_spike_min_amount)


def _alertable(results: List[Dict[str, Any]], runways: Dict[str, Runway]):
    """产出 (project_id, 检查结果, 消耗画像)，跳过失败的检查与置信度不足的估算"""
    from core.config_loader import make_project_id

    for result in results or []:
        if not result.get('success'):
            continue
        project_id = make_project_id(result.get('provider') or '', result.get('project') or '')
        runway = runways.get(project_id)
        if runway is not None and runway.confidence in CONFIDENCE_ALERTABLE:
            yield project_id, result, runway


def check_alerts(results: List[Dict[str, Any]], runways: Dict[str, Runway], dry_run: bool = False) -> Dict[str, int]:
    """跑道与消耗突增告警。阈值设为 0 表示关闭；数据不足时不下结论。"""
    settings = get_settings()
    limit_days = settings.runway_alert_days
    sent = {'runway': 0, 'spike': 0}
    if not runways or (limit_days <= 0 and settings.spend_spike_ratio <= 0):
        return sent

    cooldown = alert_store.cooldown_seconds('balance')
    for project_id, result, runway in _alertable(results, runways):
        name = result.get('project')
        if _runway_due(result, runway, limit_days):
            logger.warning(f"[{name}] 跑道不足: {runway.runway_days:.1f} 天 <= {limit_days}")
            if not dry_run and _emit(project_id, name, _runway_notice(result, runway, limit_days), cooldown):
                sent['runway'] += 1
        if _spike_due(runway, settings):
            logger.warning(f"[{name}] 消耗突增: {runway.spike_ratio:.1f}x")
            if not dry_run and _emit(project_id, name, _spike_notice(result, runway), cooldown):
                sent['spike'] += 1
    return sent


def analyze(results: List[Dict[str, Any]], dry_run: bool = False) -> Dict[str, Runway]:
    """一次余额检查之后的趋势分析：挂画像 + 发跑道 / 突增告警"""
    runways = attach(results)
    if runways:
        check_alerts(results, runways, dry_run=dry_run)
    return runways
