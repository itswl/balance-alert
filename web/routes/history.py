#!/usr/bin/env python3
"""
历史数据 API 路由（需 ENABLE_DATABASE + ENABLE_HISTORY_API）
"""
import hashlib
from functools import wraps

from flask import Blueprint, request

from core.logger import get_logger
from ..utils import handle_errors, json_error, json_success, parse_int_arg

logger = get_logger('web.routes.history')

history_bp = Blueprint('history', __name__, url_prefix='/api/history')


def with_repositories(action: str):
    """注入 (BalanceRepository, AlertRepository)，数据库不可用时直接返回 503。"""
    def decorator(func):
        @wraps(func)
        @handle_errors(action, bad_request_on_value_error=True)
        def wrapper(*args, **kwargs):
            try:
                from database.repository import AlertRepository, BalanceRepository
            except Exception:
                return json_error('数据库功能未启用', 503)
            return func(BalanceRepository, AlertRepository, *args, **kwargs)
        return wrapper
    return decorator


@history_bp.route('/balance', methods=['GET'])
@with_repositories('查询余额历史')
def get_balance_history(balance_repo, _alert_repo):
    """查询余额历史"""
    history = balance_repo.get_balance_history(
        project_id=request.args.get('project_id'),
        provider=request.args.get('provider'),
        days=parse_int_arg('days', 7, 1, 365),
        limit=parse_int_arg('limit', 100, 1, 1000),
    )
    return json_success({'status': 'success', 'count': len(history), 'data': history}, 200)


@history_bp.route('/trend/<project_id>', methods=['GET'])
@with_repositories('获取余额趋势')
def get_balance_trend(balance_repo, _alert_repo, project_id: str):
    """获取余额趋势分析"""
    days = parse_int_arg('days', 30, 1, 365)
    # 前端可能传 "provider:name" 原文，这里换算成入库时的项目 ID
    actual_project_id = hashlib.md5(project_id.encode()).hexdigest() if ':' in project_id else project_id

    trend = balance_repo.get_balance_trend(actual_project_id, days)
    if 'error' in trend:
        return json_error(trend['error'], 404)
    return json_success({'status': 'success', 'data': trend}, 200)


@history_bp.route('/alerts', methods=['GET'])
@with_repositories('查询告警历史')
def get_alert_history(_balance_repo, alert_repo):
    """查询告警历史"""
    alerts = alert_repo.get_recent_alerts(
        project_id=request.args.get('project_id'),
        alert_type=request.args.get('alert_type'),
        days=parse_int_arg('days', 7, 1, 365),
        limit=parse_int_arg('limit', 50, 1, 1000),
    )
    return json_success({'status': 'success', 'count': len(alerts), 'data': alerts}, 200)


@history_bp.route('/stats', methods=['GET'])
@with_repositories('获取告警统计')
def get_alert_statistics(_balance_repo, alert_repo):
    """获取告警统计"""
    stats = alert_repo.get_alert_statistics(parse_int_arg('days', 30, 1, 365))
    if 'error' in stats:
        return json_error(stats['error'], 500)
    return json_success({'status': 'success', 'data': stats}, 200)
