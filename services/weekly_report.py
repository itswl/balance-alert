#!/usr/bin/env python3
"""
周报：把一周的余额、消耗、跑道、订阅、邮箱汇成一张卡片推出去

平时只有出事才会收到通知，周报让「一切正常」也变成可感知的东西：这周烧了多少、
哪个账户最先见底、接下来一个月要准备多少订阅费。数据全部取自看板状态与余额历史，
不额外查上游接口。
"""
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from core.logger import get_logger
from services import runway as runway_service
from services.webhook_adapter import WebhookAdapter

logger = get_logger('weekly_report')

REPORT_WINDOW_DAYS = 7
TOP_N = 3               # 排行榜各取前几名
UPCOMING_DAYS = 30      # 订阅支出预估的时间范围


def _fmt(value: Optional[float]) -> str:
    return '-' if value is None else f"{value:,.2f}"


def _spend_rows(projects: List[Dict[str, Any]], runways: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把消耗画像整理成排行榜用的行；没有历史的账户不出现在榜上"""
    from core.config_loader import make_project_id

    rows = []
    for project in projects:
        profile = runways.get(make_project_id(project.get('provider') or '', project.get('project') or ''))
        if profile is None:
            continue
        rows.append({
            'project': project.get('project'),
            'consumed': profile.consumed,
            'burn_per_day': profile.burn_per_day,
            'runway_days': profile.runway_days,
            'depletion_date': profile.depletion_date,
            'balance': profile.current_balance,
        })
    return rows


def _upcoming(subscriptions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """未来一个月内要续费、且本周期还没续过的订阅，按紧迫程度排序"""
    due = [s for s in subscriptions
           if not s.get('already_renewed') and 0 <= (s.get('days_until_renewal') or 0) <= UPCOMING_DAYS]
    return sorted(due, key=lambda s: s.get('days_until_renewal') or 0)


def _accounts(checked: List[Dict[str, Any]], projects: List[Dict[str, Any]]) -> Dict[str, int]:
    return {
        'total': len(checked),
        'alerting': sum(1 for p in projects if p.get('need_alarm')),
        'failed': len(checked) - len(projects),
    }


def _alerting_rows(projects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{'project': p.get('project'), 'balance': p.get('credits'), 'threshold': p.get('threshold')}
            for p in projects if p.get('need_alarm')]


def _failed_rows(failed: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [{'project': p.get('project'), 'error': p.get('error')} for p in failed]


def _mailbox_stats(email_state: Dict[str, Any]) -> Dict[str, Any]:
    mailboxes = email_state.get('mailboxes') or []
    return {
        'total': len(mailboxes),
        'failed': sum(1 for m in mailboxes if m.get('error')),
        'alerts': (email_state.get('summary') or {}).get('total_alerts'),
    }


def _top(rows: List[Dict[str, Any]], key: str, reverse: bool = False) -> List[Dict[str, Any]]:
    return sorted(rows, key=lambda row: row[key], reverse=reverse)[:TOP_N]


def _period() -> Dict[str, str]:
    today = date.today()
    return {'start': (today - timedelta(days=REPORT_WINDOW_DAYS)).isoformat(), 'end': today.isoformat()}


def build(balance_state: Dict[str, Any], subscription_state: Dict[str, Any],
          email_state: Dict[str, Any], runways: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """汇总一周数据；runways 缺省时现算（需要数据库历史，没有就只报余额部分）"""
    if runways is None:
        runways = runway_service.compute_all(window_days=REPORT_WINDOW_DAYS)

    checked = balance_state.get('projects') or []
    projects = [p for p in checked if p.get('success')]
    failed = [p for p in checked if not p.get('success')]
    spend = _spend_rows(projects, runways)
    upcoming = _upcoming(subscription_state.get('subscriptions') or [])

    return {
        'period': _period(),
        'accounts': _accounts(checked, projects),
        'total_consumed': round(sum(row['consumed'] for row in spend), 2) if spend else None,
        'top_spend': _top(spend, 'consumed', reverse=True),
        'shortest_runway': _top([row for row in spend if row['runway_days'] is not None], 'runway_days'),
        'alerting_projects': _alerting_rows(projects),
        'failed_projects': _failed_rows(failed),
        'upcoming_subscriptions': upcoming,
        'upcoming_amount': round(sum(float(s.get('amount') or 0) for s in upcoming), 2),
        'mailboxes': _mailbox_stats(email_state),
    }


def _headline(summary: Dict[str, Any]) -> List[str]:
    accounts = summary['accounts']
    state = f"，{accounts['alerting']} 个余额告警" if accounts['alerting'] else "，全部正常"
    if accounts['failed']:
        state += f"，{accounts['failed']} 个检查失败"
    lines = [
        f"**统计区间**: {summary['period']['start']} ~ {summary['period']['end']}",
        f"**账户**: 共 {accounts['total']} 个{state}",
    ]
    if summary['total_consumed'] is not None:
        lines.append(f"**本周消耗**: {_fmt(summary['total_consumed'])}")
    return lines


def _section(title: str, rows: List[str]) -> List[str]:
    return ['', f"**{title}**"] + rows if rows else []


def _problems(summary: Dict[str, Any]) -> List[str]:
    rows = [f"- {item['project']}: 余额 {_fmt(item['balance'])} 低于阈值 {_fmt(item['threshold'])}"
            for item in summary['alerting_projects']]
    rows += [f"- {item['project']}: 检查失败，{item['error']}" for item in summary['failed_projects']]
    if summary['mailboxes']['failed']:
        rows.append(f"- 邮箱: {summary['mailboxes']['failed']} 个连接失败")
    return rows


def render(summary: Dict[str, Any]) -> str:
    """渲染成 Markdown 正文；各平台的消息包装由 WebhookAdapter 负责"""
    lines = _headline(summary)
    lines += _section('最先见底', [
        f"- {row['project']}: 还剩 {row['runway_days']:.1f} 天"
        + (f"（预计 {row['depletion_date']} 耗尽）" if row['depletion_date'] else "")
        + f"，余额 {_fmt(row['balance'])}"
        for row in summary['shortest_runway']
    ])
    lines += _section('消耗最多', [
        f"- {row['project']}: {_fmt(row['consumed'])}，日均 {_fmt(row['burn_per_day'])}"
        for row in summary['top_spend']
    ])
    lines += _section(f"未来 {UPCOMING_DAYS} 天订阅支出: {_fmt(summary['upcoming_amount'])}", [
        f"- {sub.get('name')}: {sub.get('days_until_renewal')} 天后续费，{_fmt(sub.get('amount'))}"
        for sub in summary['upcoming_subscriptions']
    ])
    lines += _section('需要处理', _problems(summary))
    return '\n'.join(lines)


def send(summary: Dict[str, Any]) -> bool:
    adapter = WebhookAdapter.from_settings('credit-monitor')
    if adapter is None:
        logger.error("未配置 webhook 地址，周报未发送")
        return False
    return adapter.send_custom_alert("余额周报", render(summary), kind='weekly_report')
