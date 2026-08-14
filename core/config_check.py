#!/usr/bin/env python3
"""
配置自检：一条命令看清「配了什么、从哪来、哪里不对」。

    python -m services.monitor --show-config

有问题时返回非零退出码，可用于部署前校验。
"""
import os
from typing import Any, Dict, List, Tuple

from core.config_loader import (
    get_config,
    load_config,
    provider_key_env_names,
)
from core.settings import get_settings

OK, BAD, WARN = '✓', '✗', '!'


def _mask(value: str, keep: int = 4) -> str:
    if not value:
        return ''
    return f"{value[:keep]}***" if len(value) > keep else '***'


def _api_key_source(project: Dict[str, Any], ordinal: int) -> Tuple[str, List[str]]:
    """反查 api_key 实际来自哪里；缺失时返回可用的环境变量名供提示。"""
    key = project.get('api_key') or ''
    candidates = provider_key_env_names(project.get('provider') or '', ordinal)
    if not key:
        return '', candidates
    for name in candidates:
        if os.environ.get(name) == key:
            return f"环境变量 {name}", []
    return "配置里的 api_key 字段", []


def _check_projects(projects: List[Dict[str, Any]], lines: List[str]) -> int:
    problems = 0
    lines.append(f"\n项目 ({len(projects)})")
    if not projects:
        lines.append(f"  {BAD} 没有任何项目，余额检查不会执行")
        return 1

    ordinals: Dict[str, int] = {}
    for project in projects:
        name = project.get('name') or '(未命名)'
        provider = project.get('provider') or '(未填 provider)'
        ordinals[provider] = ordinals.get(provider, 0) + 1
        threshold = project.get('threshold')
        source, candidates = _api_key_source(project, ordinals[provider])

        if not project.get('provider'):
            lines.append(f"  {BAD} {name}: 缺少 provider 字段")
            problems += 1
            continue
        if not source:
            hint = ' 或 '.join(candidates) if candidates else '?'
            lines.append(f"  {BAD} {name} [{provider}]: 缺少 API Key，请设置 {hint}")
            problems += 1
            continue

        detail = f"  {OK} {name} [{provider}/{project.get('type')}] 阈值 {threshold} — Key 来自 {source}"
        if threshold in (None, 0):
            detail = f"  {WARN}{detail[3:]}（阈值为 {threshold}，不会触发告警）"
            problems += 1
        lines.append(detail)

    return problems


def _check_subscriptions(subscriptions: List[Dict[str, Any]], lines: List[str]) -> int:
    from services.webhook_adapter import WebhookAdapter

    problems = 0
    lines.append(f"\n订阅 ({len(subscriptions)})")
    if not subscriptions:
        lines.append("  — 未配置")
        return 0

    for sub in subscriptions:
        name = sub.get('name') or '(未命名)'
        cycle_type = sub.get('cycle_type')
        renewal_day = sub.get('renewal_day')

        if not isinstance(renewal_day, int):
            lines.append(f"  {BAD} {name}: 续费日 {renewal_day!r} 无法识别（年付可填 \"03-15\"，月付填 1-31）")
            problems += 1
            continue

        readable = WebhookAdapter._format_subscription_cycle(cycle_type, renewal_day)
        if readable == '未知周期':
            lines.append(f"  {BAD} {name}: 周期类型 {cycle_type!r} 不支持（weekly/monthly/yearly）")
            problems += 1
            continue

        alert_days = sub.get('alert_days_before', 3)
        amount = sub.get('amount', 0)
        lines.append(f"  {OK} {name}: {readable}，提前 {alert_days} 天提醒，金额 {amount}")

    return problems


def _check_emails(emails: List[Dict[str, Any]], lines: List[str]) -> int:
    problems = 0
    lines.append(f"\n邮箱 ({len(emails)})")
    if not emails:
        lines.append("  — 未配置")
        return 0

    for cfg in emails:
        name = cfg.get('name') or '(未命名)'
        missing = [f for f in ('host', 'username', 'password') if not cfg.get(f)]
        if missing:
            lines.append(f"  {BAD} {name}: 缺少 {', '.join(missing)}")
            problems += 1
            continue
        ssl_text = 'SSL' if cfg.get('use_ssl') else '明文'
        lines.append(f"  {OK} {name}: {cfg['host']}:{cfg['port']} {ssl_text}，账号 {cfg['username']}")

    return problems


def _check_alert_channel(lines: List[str]) -> int:
    from services.webhook_adapter import WebhookAdapter, _mask_webhook_url

    settings = get_settings()
    problems = 0
    lines.append("\n告警与访问")

    if settings.webhook_url:
        webhook_type = (settings.webhook_type or 'custom').lower()
        marker = OK if webhook_type in WebhookAdapter.SUPPORTED_TYPES else BAD
        if marker == BAD:
            problems += 1
            note = f"（不支持的类型，可选 {'/'.join(WebhookAdapter.SUPPORTED_TYPES)}）"
        else:
            note = ''
        lines.append(f"  {marker} Webhook [{webhook_type}] → {_mask_webhook_url(settings.webhook_url)} {note}".rstrip())
    else:
        lines.append(f"  {BAD} 未设置 WEBHOOK_URL，余额不足时无法发出告警")
        problems += 1

    if settings.resolved_web_api_key():
        lines.append(f"  {OK} WEB_API_KEY 已设置（{_mask(settings.resolved_web_api_key())}）")
    else:
        lines.append(f"  {BAD} 未设置 WEB_API_KEY，所有 /api/* 请求会返回 503")
        problems += 1

    if settings.enable_dynamic_config and not settings.config_encryption_key:
        lines.append(f"  {WARN} 数据库动态配置已开启但未设置 CONFIG_ENCRYPTION_KEY，密钥将明文入库")

    return problems


def _section_sources(config_path: str) -> Dict[str, str]:
    """判断三类业务清单最终来自文件还是数据库（与 load_config 的覆盖语义一致）。"""
    settings = get_settings()
    db_counts: Dict[str, int] = {}
    if settings.enable_dynamic_config:
        try:
            from database.repository import ConfigRepository
            db_counts = {
                'projects': len(ConfigRepository.get_all_projects()),
                'subscriptions': len(ConfigRepository.get_all_subscriptions()),
                'email': len(ConfigRepository.get_all_emails()),
            }
        except Exception as e:
            db_counts = {}
            print(f"  {WARN} 读取数据库动态配置失败: {e}")

    file_config = get_config(config_path, use_cache=False)
    sources = {}
    for section in ('projects', 'subscriptions', 'email'):
        if db_counts.get(section):
            sources[section] = '数据库'
        elif file_config.get(section):
            sources[section] = config_path
        else:
            sources[section] = '(空)'
    return sources


def check_config(config_path: str) -> int:
    """打印配置自检报告，返回发现的问题数量。"""
    settings = get_settings()
    config = load_config(config_path, use_cache=False)
    sources = _section_sources(config_path)

    lines = [
        "配置自检",
        f"  配置文件: {config_path}{'' if os.path.exists(config_path) else ' (不存在)'}",
        f"  数据库: {settings.database_url.split('://')[0] if settings.enable_database else '未启用'}",
    ]

    distinct = set(sources.values())
    if len(distinct) == 1:
        lines.append(f"  业务清单来源: 全部来自 {distinct.pop()}")
    else:
        labels = {'projects': '项目', 'subscriptions': '订阅', 'email': '邮箱'}
        lines.append("  业务清单来源: " + '  '.join(f"{labels[k]}={v}" for k, v in sources.items()))

    features = [
        ('数据库', settings.enable_database),
        ('动态配置', settings.enable_dynamic_config),
        ('历史 API', settings.enable_history_api),
        ('订阅提醒', settings.enable_subscriptions),
        ('Prometheus', settings.enable_prometheus),
        ('Web 告警', settings.enable_web_alarm),
    ]
    lines.append("  可选能力: " + '  '.join(f"{name}{OK if on else '✗'}" for name, on in features))

    problems = _check_projects(config.get('projects') or [], lines)
    if settings.enable_subscriptions:
        problems += _check_subscriptions(config.get('subscriptions') or [], lines)
    if config.get('email'):
        problems += _check_emails(config.get('email') or [], lines)
    problems += _check_alert_channel(lines)

    lines.append("")
    lines.append("配置无问题" if problems == 0 else f"发现 {problems} 个问题（上面标 {BAD} / {WARN} 的条目）")
    print('\n'.join(lines))
    return problems
