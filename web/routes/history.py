#!/usr/bin/env python3
"""
历史数据 API 路由（需 ENABLE_DATABASE + ENABLE_HISTORY_API）
"""
import hashlib

from flask import Blueprint, request

from core.logger import get_logger
from ..utils import json_error, json_success, parse_int_arg

logger = get_logger('web.routes.history')

history_bp = Blueprint('history', __name__, url_prefix='/api/history')


def _repositories():
    """返回 (BalanceRepository, AlertRepository)，数据库不可用时返回 None"""
    try:
        from database.repository import AlertRepository, BalanceRepository
        return BalanceRepository, AlertRepository
    except Exception:
        return None


@history_bp.route('/balance', methods=['GET'])
def get_balance_history():
    """查询余额历史"""
    repos = _repositories()
    if repos is None:
        return json_error('数据库功能未启用', 503)
    balance_repo, _ = repos

    try:
        history = balance_repo.get_balance_history(
            project_id=request.args.get('project_id'),
            provider=request.args.get('provider'),
            days=parse_int_arg('days', 7, 1, 365),
            limit=parse_int_arg('limit', 100, 1, 1000),
        )
        return json_success({'status': 'success', 'count': len(history), 'data': history}, 200)

    except ValueError as e:
        return json_error(f'参数错误: {e}', 400)
    except Exception as e:
        logger.error(f"查询余额历史失败: {e}", exc_info=True)
        return json_error(str(e), 500)


@history_bp.route('/trend/<project_id>', methods=['GET'])
def get_balance_trend(project_id: str):
    """获取余额趋势分析"""
    repos = _repositories()
    if repos is None:
        return json_error('数据库功能未启用', 503)
    balance_repo, _ = repos

    try:
        days = parse_int_arg('days', 30, 1, 365)

        actual_project_id = hashlib.md5(project_id.encode()).hexdigest() if ':' in project_id else project_id
        trend = balance_repo.get_balance_trend(actual_project_id, days)
        if 'error' in trend:
            return json_error(trend['error'], 404)
        return json_success({'status': 'success', 'data': trend}, 200)

    except ValueError as e:
        return json_error(f'参数错误: {e}', 400)
    except Exception as e:
        logger.error(f"获取余额趋势失败: {e}", exc_info=True)
        return json_error(str(e), 500)


@history_bp.route('/alerts', methods=['GET'])
def get_alert_history():
    """查询告警历史"""
    repos = _repositories()
    if repos is None:
        return json_error('数据库功能未启用', 503)
    _, alert_repo = repos

    try:
        alerts = alert_repo.get_recent_alerts(
            project_id=request.args.get('project_id'),
            alert_type=request.args.get('alert_type'),
            days=parse_int_arg('days', 7, 1, 365),
            limit=parse_int_arg('limit', 50, 1, 1000),
        )
        return json_success({'status': 'success', 'count': len(alerts), 'data': alerts}, 200)

    except ValueError as e:
        return json_error(f'参数错误: {e}', 400)
    except Exception as e:
        logger.error(f"查询告警历史失败: {e}", exc_info=True)
        return json_error(str(e), 500)


@history_bp.route('/stats', methods=['GET'])
def get_alert_statistics():
    """获取告警统计"""
    repos = _repositories()
    if repos is None:
        return json_error('数据库功能未启用', 503)
    _, alert_repo = repos

    try:
        stats = alert_repo.get_alert_statistics(parse_int_arg('days', 30, 1, 365))
        if 'error' in stats:
            return json_error(stats['error'], 500)
        return json_success({'status': 'success', 'data': stats}, 200)

    except ValueError as e:
        return json_error(f'参数错误: {e}', 400)
    except Exception as e:
        logger.error(f"获取告警统计失败: {e}", exc_info=True)
        return json_error(str(e), 500)
