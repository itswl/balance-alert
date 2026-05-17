#!/usr/bin/env python3
import hashlib
from typing import Any, Callable, Dict, List, Tuple

from flask import Blueprint, jsonify, request

from core.logger import get_logger

logger = get_logger('web.routes.history')

history_bp = Blueprint('history', __name__, url_prefix='/api/history')


def _error(message: str, status_code: int = 500):
    return jsonify({'status': 'error', 'message': message}), status_code


def _success(payload: dict, status_code: int = 200):
    return jsonify(payload), status_code


def _parse_int_arg(name: str, default: int, min_value: int, max_value: int) -> int:
    value = int(request.args.get(name, default))
    if value < min_value or value > max_value:
        raise ValueError(f'{name} 必须在 {min_value}-{max_value} 之间')
    return value


def _require_db_services():
    ok, services = _get_history_services()
    if not ok:
        return None, _error('数据库功能未启用', 503)
    return services, None


def _get_history_services() -> Tuple[bool, Dict[str, Callable[..., Any]]]:
    try:
        from services.history_service import (
            DB_AVAILABLE as _DB_AVAILABLE,
            get_alert_statistics as _get_alert_statistics,
            get_all_projects_summary as _get_all_projects_summary,
            get_balance_history as _get_balance_history,
            get_balance_trend as _get_balance_trend,
            get_recent_alerts as _get_recent_alerts,
        )
        if not _DB_AVAILABLE:
            return False, {}
        return True, {
            'get_balance_history': _get_balance_history,
            'get_balance_trend': _get_balance_trend,
            'get_recent_alerts': _get_recent_alerts,
            'get_alert_statistics': _get_alert_statistics,
            'get_all_projects_summary': _get_all_projects_summary,
        }
    except Exception:
        return False, {}


@history_bp.route('/balance', methods=['GET'])
def get_balance_history():
    """查询余额历史"""
    services, error_resp = _require_db_services()
    if error_resp:
        return error_resp

    try:
        project_id = request.args.get('project_id')
        provider = request.args.get('provider')
        days = _parse_int_arg('days', 7, 1, 365)
        limit = _parse_int_arg('limit', 100, 1, 1000)

        history = services['get_balance_history'](
            project_id=project_id,
            provider=provider,
            days=days,
            limit=limit
        )
        return _success({'status': 'success', 'count': len(history), 'data': history}, 200)

    except ValueError as e:
        return _error(f'参数错误: {e}', 400)
    except Exception as e:
        logger.error(f"查询余额历史失败: {e}", exc_info=True)
        return _error(str(e), 500)


@history_bp.route('/trend/<project_id>', methods=['GET'])
def get_balance_trend(project_id: str):
    """获取余额趋势分析"""
    services, error_resp = _require_db_services()
    if error_resp:
        return error_resp

    try:
        days = _parse_int_arg('days', 30, 1, 365)

        actual_project_id = hashlib.md5(project_id.encode()).hexdigest() if ':' in project_id else project_id
        trend = services['get_balance_trend'](actual_project_id, days)
        if 'error' in trend:
            return _error(trend['error'], 404)
        return _success({'status': 'success', 'data': trend}, 200)

    except ValueError as e:
        return _error(f'参数错误: {e}', 400)
    except Exception as e:
        logger.error(f"获取余额趋势失败: {e}", exc_info=True)
        return _error(str(e), 500)


@history_bp.route('/alerts', methods=['GET'])
def get_alert_history():
    """查询告警历史"""
    services, error_resp = _require_db_services()
    if error_resp:
        return error_resp

    try:
        project_id = request.args.get('project_id')
        alert_type = request.args.get('alert_type')
        days = _parse_int_arg('days', 7, 1, 365)
        limit = _parse_int_arg('limit', 50, 1, 1000)

        alerts = services['get_recent_alerts'](
            project_id=project_id,
            alert_type=alert_type,
            days=days,
            limit=limit
        )
        return _success({'status': 'success', 'count': len(alerts), 'data': alerts}, 200)

    except ValueError as e:
        return _error(f'参数错误: {e}', 400)
    except Exception as e:
        logger.error(f"查询告警历史失败: {e}", exc_info=True)
        return _error(str(e), 500)


@history_bp.route('/stats', methods=['GET'])
def get_alert_statistics():
    """获取告警统计"""
    services, error_resp = _require_db_services()
    if error_resp:
        return error_resp

    try:
        days = _parse_int_arg('days', 30, 1, 365)

        stats = services['get_alert_statistics'](days)
        if 'error' in stats:
            return _error(stats['error'], 500)
        return _success({'status': 'success', 'data': stats}, 200)

    except ValueError as e:
        return _error(f'参数错误: {e}', 400)
    except Exception as e:
        logger.error(f"获取告警统计失败: {e}", exc_info=True)
        return _error(str(e), 500)


@history_bp.route('/projects', methods=['GET'])
def get_all_projects_summary():
    """获取所有项目摘要"""
    services, error_resp = _require_db_services()
    if error_resp:
        return error_resp

    try:
        summary: List[Dict[str, Any]] = services['get_all_projects_summary']()
        return _success({'status': 'success', 'count': len(summary), 'data': summary}, 200)
    except Exception as e:
        logger.error(f"获取项目摘要失败: {e}", exc_info=True)
        return _error(str(e), 500)
