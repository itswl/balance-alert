#!/usr/bin/env python3
"""
邮箱扫描 API 路由

- 邮箱配置：GET 始终可用（密码脱敏）；增删改需 ENABLE_DYNAMIC_CONFIG，否则统一返回 503
- 邮箱扫描：GET 看上次结果，POST 立即扫描；是否真发通知与余额刷新共用 ENABLE_WEB_ALARM 开关
"""
import time

from flask import Blueprint, request

from core.logger import get_logger
from core.settings import get_settings
from services.email_scanner import EmailScanner
from ..middleware import validate_request
from ..schemas import EmailConfigRequest
from ..utils import (
    audit_log,
    config_db_write,
    handle_errors,
    json_error,
    json_success,
    load_config_safe,
    make_etag_response,
    mask_email_config,
    require_json_fields,
    runtime,
)

logger = get_logger('web.routes.email')

email_bp = Blueprint('email', __name__, url_prefix='/api')

MAX_SCAN_DAYS = 30


@email_bp.before_request
def _require_dynamic_config_for_writes():
    if request.method in ('GET', 'OPTIONS'):
        return None
    if (request.path or '').startswith('/api/config/email') and not get_settings().enable_dynamic_config:
        return json_error('修改邮箱配置需要数据库动态配置，请设置 ENABLE_DYNAMIC_CONFIG=true', 503)
    return None


def _existing_mailboxes():
    return load_config_safe().get('email', []) or []


# ---------- 邮箱配置 ----------

@email_bp.route('/config/emails', methods=['GET'])
@handle_errors('获取邮箱配置')
def get_emails_config():
    """所有邮箱配置（密码脱敏）"""
    return make_etag_response({'status': 'success', 'emails': [mask_email_config(m) for m in _existing_mailboxes()]})


@email_bp.route('/config/email', methods=['POST'])
@validate_request(EmailConfigRequest)
@handle_errors('保存邮箱配置')
def save_email(validated_data: EmailConfigRequest):
    """添加或更新邮箱配置。更新时只改传了的字段，密码留空表示不变。"""
    name = validated_data.name
    is_new = not any(m.get('name') == name for m in _existing_mailboxes())

    payload = {k: v for k, v in validated_data.model_dump().items() if v is not None}
    if not payload.get('password'):
        payload.pop('password', None)
    if is_new:
        missing = [f for f in ('host', 'username', 'password') if not payload.get(f)]
        if missing:
            return json_error(f"新增邮箱缺少必要参数: {', '.join(missing)}", 400)

    if not config_db_write(lambda repo: repo.upsert('email', payload)):
        return json_error('保存失败', 500)

    audit_log('save_email', {'email': name, 'new': is_new, 'fields': sorted(payload)})
    return json_success({'status': 'success', 'message': f"邮箱 [{name}] 已{'添加' if is_new else '更新'}"}, 200)


@email_bp.route('/config/email/delete', methods=['POST'])
@handle_errors('删除邮箱配置')
def delete_email_route():
    """删除邮箱配置"""
    data, error_resp = require_json_fields('name')
    if error_resp:
        return error_resp
    name = data['name']

    if not config_db_write(lambda repo: repo.delete('email', name)):
        return json_error('删除失败', 500)

    audit_log('delete_email', {'email': name})
    return json_success({'status': 'success', 'message': f"邮箱 [{name}] 已删除"}, 200)


# ---------- 邮箱扫描 ----------

@email_bp.route('/email/scan', methods=['GET'])
@handle_errors('获取邮箱扫描状态')
def get_email_scan_state():
    """上次扫描的结果（保存在进程内存，重启后清空）"""
    return make_etag_response(runtime().state_manager.get_email_state())


@email_bp.route('/email/scan', methods=['POST'])
@handle_errors('邮箱扫描')
def run_email_scan():
    """立即扫描所有启用的邮箱，结果写入看板状态"""
    try:
        days = int((request.get_json(silent=True) or {}).get('days', 1))
    except (TypeError, ValueError):
        days = 0
    if not 1 <= days <= MAX_SCAN_DAYS:
        return json_error(f'days 必须是 1-{MAX_SCAN_DAYS} 之间的整数', 400)

    rt = runtime()
    busy = rt.scan_guard.acquire()
    if busy:
        return json_error(f'扫描{busy}', 429)
    try:
        scanner = EmailScanner()
        if not scanner.email_configs:
            return json_error('未配置邮箱或所有邮箱均已停用', 400)

        dry_run = not get_settings().enable_web_alarm
        started = time.time()
        summary = scanner.scan_emails(days=days, dry_run=dry_run)
        rt.state_manager.update_email_state(summary)

        audit_log('email_scan', {'days': days, 'dry_run': dry_run,
                                 'mailboxes': len(summary['mailboxes']), 'alerts': summary['total_alerts']})
        return json_success({
            'status': 'success',
            'message': f"扫描完成：{summary['total_emails']} 封邮件，{summary['total_alerts']} 封告警",
            'summary': rt.state_manager.get_email_state()['summary'],
            'mailboxes': summary['mailboxes'],
            'dry_run': dry_run,
            'execution_time_seconds': round(time.time() - started, 2),
        }, 200)
    finally:
        rt.scan_guard.release()
