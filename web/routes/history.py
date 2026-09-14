#!/usr/bin/env python3
"""
历史数据 API 路由（需 ENABLE_DATABASE + ENABLE_HISTORY_API）

数据库未启用时 repository 层直接返回空结果，这里不再额外判断。
"""
import hashlib

from flask import Blueprint, request

from database.repository import AlertRepository, BalanceRepository, EmailRepository
from ..utils import handle_errors, json_error, json_success, parse_int_arg

history_bp = Blueprint('history', __name__, url_prefix='/api/history')


@history_bp.route('/balance', methods=['GET'])
@handle_errors('查询余额历史', bad_request_on_value_error=True)
def get_balance_history():
    """查询余额历史"""
    history = BalanceRepository.get_balance_history(
        project_id=request.args.get('project_id'),
        provider=request.args.get('provider'),
        days=parse_int_arg('days', 7, 1, 365),
        limit=parse_int_arg('limit', 100, 1, 1000),
    )
    return json_success({'status': 'success', 'count': len(history), 'data': history}, 200)


@history_bp.route('/trend/<project_id>', methods=['GET'])
@handle_errors('获取余额趋势', bad_request_on_value_error=True)
def get_balance_trend(project_id: str):
    """获取余额趋势分析"""
    days = parse_int_arg('days', 30, 1, 365)
    # 前端可能传 "provider:name" 原文，这里换算成入库时的项目 ID
    actual_project_id = hashlib.md5(project_id.encode()).hexdigest() if ':' in project_id else project_id

    trend = BalanceRepository.get_balance_trend(actual_project_id, days)
    if 'error' in trend:
        return json_error(trend['error'], 404)
    return json_success({'status': 'success', 'data': trend}, 200)


@history_bp.route('/alerts', methods=['GET'])
@handle_errors('查询告警历史', bad_request_on_value_error=True)
def get_alert_history():
    """查询告警历史"""
    alerts = AlertRepository.get_recent_alerts(
        project_id=request.args.get('project_id'),
        alert_type=request.args.get('alert_type'),
        days=parse_int_arg('days', 7, 1, 365),
        limit=parse_int_arg('limit', 50, 1, 1000),
    )
    return json_success({'status': 'success', 'count': len(alerts), 'data': alerts}, 200)


@history_bp.route('/stats', methods=['GET'])
@handle_errors('获取告警统计', bad_request_on_value_error=True)
def get_alert_statistics():
    """获取告警统计"""
    stats = AlertRepository.get_alert_statistics(parse_int_arg('days', 30, 1, 365))
    if 'error' in stats:
        return json_error(stats['error'], 500)
    return json_success({'status': 'success', 'data': stats}, 200)


@history_bp.route('/email-alerts', methods=['GET'])
@handle_errors('查询邮件告警历史', bad_request_on_value_error=True)
def get_email_alert_history():
    """查询扫描到的告警邮件历史"""
    alerts = EmailRepository.get_email_alerts(
        mailbox=request.args.get('mailbox'),
        days=parse_int_arg('days', 30, 1, 365),
        limit=parse_int_arg('limit', 100, 1, 1000),
    )
    return json_success({'status': 'success', 'count': len(alerts), 'data': alerts}, 200)
