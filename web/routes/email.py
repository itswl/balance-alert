from flask import Blueprint, request

from core.config_loader import clear_config_cache
from ..utils import (
    audit_log,
    config_db_write,
    handle_errors,
    json_error,
    json_success,
    load_config_safe,
    make_etag_response,
    mask_email_config,
)

email_bp = Blueprint('email', __name__, url_prefix='/api')


def _get_name_from_json():
    data = request.get_json(silent=True)
    if not data or 'name' not in data:
        return None, None, json_error('缺少必要参数: name', 400)
    return data['name'], data, None


@email_bp.route('/config/emails', methods=['GET'])
@handle_errors('获取邮箱配置')
def get_emails_config():
    """获取所有邮箱配置"""
    emails = [mask_email_config(email) for email in load_config_safe().get('email', [])]
    return make_etag_response({'status': 'success', 'emails': emails})


@email_bp.route('/config/email', methods=['POST'])
@handle_errors('保存邮箱配置')
def save_email():
    """添加或更新邮箱配置"""
    name, data, error_resp = _get_name_from_json()
    if error_resp:
        return error_resp

    if not config_db_write(lambda repo: repo.upsert_email(data)):
        return json_error('保存失败', 500)

    clear_config_cache()
    audit_log('save_email', {'email': name})
    return json_success({'status': 'success', 'message': f"邮箱 [{name}] 配置已保存"}, 200)


@email_bp.route('/config/email/delete', methods=['POST'])
@handle_errors('删除邮箱配置')
def delete_email_route():
    """删除邮箱配置"""
    name, _data, error_resp = _get_name_from_json()
    if error_resp:
        return error_resp

    if not config_db_write(lambda repo: repo.delete_email(name)):
        return json_error('删除失败', 500)

    clear_config_cache()
    audit_log('delete_email', {'email': name})
    return json_success({'status': 'success', 'message': f"邮箱 [{name}] 已删除"}, 200)
