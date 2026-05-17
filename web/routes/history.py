#!/usr/bin/env python3
import hashlib
from typing import Any, Callable, Dict, List, Tuple

from flask import Blueprint, jsonify, request

from core.logger import get_logger

logger = get_logger('web.routes.history')

history_bp = Blueprint('history', __name__, url_prefix='/api/history')


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
    ok, services = _get_history_services()
    if not ok:
        return jsonify({'status': 'error', 'message': '数据库功能未启用'}), 503

    try:
        project_id = request.args.get('project_id')
        provider = request.args.get('provider')
        days = int(request.args.get('days', 7))
        limit = int(request.args.get('limit', 100))

        if days < 1 or days > 365:
            return jsonify({'status': 'error', 'message': 'days 必须在 1-365 之间'}), 400
        if limit < 1 or limit > 1000:
            return jsonify({'status': 'error', 'message': 'limit 必须在 1-1000 之间'}), 400

        history = services['get_balance_history'](
            project_id=project_id,
            provider=provider,
            days=days,
            limit=limit
        )
        return jsonify({'status': 'success', 'count': len(history), 'data': history})

    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'参数错误: {e}'}), 400
    except Exception as e:
        logger.error(f"查询余额历史失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@history_bp.route('/trend/<project_id>', methods=['GET'])
def get_balance_trend(project_id: str):
    """获取余额趋势分析"""
    ok, services = _get_history_services()
    if not ok:
        return jsonify({'status': 'error', 'message': '数据库功能未启用'}), 503

    try:
        days = int(request.args.get('days', 30))
        if days < 1 or days > 365:
            return jsonify({'status': 'error', 'message': 'days 必须在 1-365 之间'}), 400

        actual_project_id = hashlib.md5(project_id.encode()).hexdigest() if ':' in project_id else project_id
        trend = services['get_balance_trend'](actual_project_id, days)
        if 'error' in trend:
            return jsonify({'status': 'error', 'message': trend['error']}), 404
        return jsonify({'status': 'success', 'data': trend})

    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'参数错误: {e}'}), 400
    except Exception as e:
        logger.error(f"获取余额趋势失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@history_bp.route('/alerts', methods=['GET'])
def get_alert_history():
    """查询告警历史"""
    ok, services = _get_history_services()
    if not ok:
        return jsonify({'status': 'error', 'message': '数据库功能未启用'}), 503

    try:
        project_id = request.args.get('project_id')
        alert_type = request.args.get('alert_type')
        days = int(request.args.get('days', 7))
        limit = int(request.args.get('limit', 50))

        if days < 1 or days > 365:
            return jsonify({'status': 'error', 'message': 'days 必须在 1-365 之间'}), 400
        if limit < 1 or limit > 1000:
            return jsonify({'status': 'error', 'message': 'limit 必须在 1-1000 之间'}), 400

        alerts = services['get_recent_alerts'](
            project_id=project_id,
            alert_type=alert_type,
            days=days,
            limit=limit
        )
        return jsonify({'status': 'success', 'count': len(alerts), 'data': alerts})

    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'参数错误: {e}'}), 400
    except Exception as e:
        logger.error(f"查询告警历史失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@history_bp.route('/stats', methods=['GET'])
def get_alert_statistics():
    """获取告警统计"""
    ok, services = _get_history_services()
    if not ok:
        return jsonify({'status': 'error', 'message': '数据库功能未启用'}), 503

    try:
        days = int(request.args.get('days', 30))
        if days < 1 or days > 365:
            return jsonify({'status': 'error', 'message': 'days 必须在 1-365 之间'}), 400

        stats = services['get_alert_statistics'](days)
        if 'error' in stats:
            return jsonify({'status': 'error', 'message': stats['error']}), 500
        return jsonify({'status': 'success', 'data': stats})

    except ValueError as e:
        return jsonify({'status': 'error', 'message': f'参数错误: {e}'}), 400
    except Exception as e:
        logger.error(f"获取告警统计失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500


@history_bp.route('/projects', methods=['GET'])
def get_all_projects_summary():
    """获取所有项目摘要"""
    ok, services = _get_history_services()
    if not ok:
        return jsonify({'status': 'error', 'message': '数据库功能未启用'}), 503

    try:
        summary: List[Dict[str, Any]] = services['get_all_projects_summary']()
        return jsonify({'status': 'success', 'count': len(summary), 'data': summary})
    except Exception as e:
        logger.error(f"获取项目摘要失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500
