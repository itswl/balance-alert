#!/usr/bin/env python3
"""
核心 API 路由：首页、健康检查、余额与订阅状态、定时任务状态、手动刷新
"""
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template, request

from core.config_loader import get_default_config_path, get_refresh_interval
from core.logger import get_logger
from core.settings import get_settings
from services.monitor import run_credit_monitor
from services.prometheus_exporter import metrics_collector
from ..utils import json_error, json_success, make_etag_response, runtime

logger = get_logger('web.routes.core')

core_bp = Blueprint('core', __name__)

# 余额数据超过多少个刷新周期没更新就算过期
STALENESS_MULTIPLIER = 3


def _is_stale(last_update) -> bool:
    if not last_update:
        return False
    try:
        updated_at = datetime.fromisoformat(last_update.replace('Z', '+00:00')) if isinstance(last_update, str) else last_update
        now = datetime.now(updated_at.tzinfo) if updated_at.tzinfo else datetime.now()
        return now - updated_at > timedelta(seconds=get_refresh_interval() * STALENESS_MULTIPLIER)
    except Exception:
        return False


@core_bp.route('/')
def index():
    """首页 - Dashboard"""
    return render_template('index.html')


@core_bp.route('/health')
def health():
    """就绪检查：有数据、数据没过期、定时任务上次都成功才 200，否则 503"""
    state_manager = runtime().state_manager
    balance_state = state_manager.get_balance_state()
    last_update = balance_state.get('last_update')
    has_data = bool(balance_state.get('projects'))
    is_stale = _is_stale(last_update)

    job_state = state_manager.get_job_state()
    failed_jobs = [job['name'] for job in job_state['jobs'] if job.get('last_error')]
    healthy = has_data and not is_stale and job_state['healthy']

    return jsonify({
        'status': 'healthy' if healthy else 'degraded',
        'has_data': has_data,
        'is_stale': is_stale,
        'jobs_healthy': job_state['healthy'],
        'failed_jobs': failed_jobs,
        'last_update': last_update if isinstance(last_update, str) else (last_update.isoformat() if last_update else None),
        'uptime_seconds': int(state_manager.uptime_seconds()),
        'version': get_settings().app_version,
    }), 200 if healthy else 503


@core_bp.route('/live')
def live():
    """存活检查：进程能响应即 200"""
    return json_success({
        'status': 'alive',
        'uptime_seconds': int(runtime().state_manager.uptime_seconds()),
        'version': get_settings().app_version,
    }, 200)


@core_bp.route('/api/features')
def get_features():
    """当前启用的可选能力，前端据此隐藏高级入口"""
    settings = get_settings()
    return jsonify({
        'status': 'success',
        'features': {
            'subscriptions': settings.enable_subscriptions,
            'dynamic_config': settings.enable_dynamic_config,
            'history': settings.enable_history_api,
        },
    })


@core_bp.route('/api/credits')
def get_credits():
    """所有项目的余额状态"""
    balance_state = runtime().state_manager.get_balance_state()
    if not balance_state.get('projects'):
        return json_error('余额数据未初始化，请稍后重试', 503)
    return make_etag_response(balance_state)


@core_bp.route('/api/subscriptions')
def get_subscriptions():
    """订阅状态（功能未启用时为空状态）"""
    return make_etag_response(runtime().state_manager.get_subscription_state())


@core_bp.route('/api/jobs')
def get_jobs():
    """进程内定时任务的运行情况：计划、上次运行、上次成功、错误"""
    return make_etag_response(runtime().state_manager.get_job_state())


@core_bp.route('/api/refresh', methods=['GET', 'POST'])
def refresh_credits_route():
    """立即检查余额；POST 带 project_name 时只刷新该项目并合并进现有状态"""
    project_name = None
    if request.method == 'POST':
        project_name = (request.get_json(silent=True) or {}).get('project_name')
        if project_name is not None and not isinstance(project_name, str):
            return json_error('project_name 必须是字符串', 400)
        project_name = (project_name or '').strip() or None

    rt = runtime()
    busy = rt.refresh_guard.acquire()
    if busy:
        return json_error(f'刷新{busy}', 429)
    try:
        started = datetime.now()
        dry_run = not get_settings().enable_web_alarm
        result = run_credit_monitor(get_default_config_path(), project_name, dry_run)
        if not result['success']:
            return json_error(f"刷新失败: {result.get('error', 'Unknown error')}", 500)

        if project_name is not None:
            rt.state_manager.merge_balance_state(result['results'])
        else:
            rt.state_manager.update_balance_state(result['results'])
        metrics_collector.update_balance_metrics(rt.state_manager.get_balance_state()['projects'])

        return json_success({
            'status': 'success',
            'message': f"刷新完成{'（项目: ' + project_name + '）' if project_name else ''}",
            'refreshed_count': result['count'],
            'execution_time_seconds': round((datetime.now() - started).total_seconds(), 2),
            'dry_run': dry_run,
        }, 200)
    except Exception as e:
        logger.error(f"刷新失败: {e}", exc_info=True)
        return json_error(f'刷新失败: {str(e)}', 500)
    finally:
        rt.refresh_guard.release()
