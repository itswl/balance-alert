from flask import Blueprint, request

from core.config_loader import clear_config_cache
from core.logger import get_logger
from ..utils import audit_log, config_db_write, json_error, json_success, load_config_safe, make_etag_response, mask_email_config

logger = get_logger('web.routes.email')
email_bp = Blueprint('email', __name__, url_prefix='/api')


def _get_name_from_json():
    data = request.get_json(silent=True)
    if not data or 'name' not in data:
        return None, None, json_error('缺少必要参数: name', 400)
    return data['name'], data, None


@email_bp.route('/config/emails', methods=['GET'])
def get_emails_config():
    """获取所有邮箱配置"""
    try:
        config = load_config_safe()
        emails = [mask_email_config(email) for email in config.get('email', [])]
        return make_etag_response({'status': 'success', 'emails': emails})
    except Exception as e:
        logger.error(f"获取邮箱配置失败: {e}", exc_info=True)
        return json_error(str(e), 500)


@email_bp.route('/config/email', methods=['POST'])
def save_email():
    """添加或更新邮箱配置"""
    try:
        name, data, error_resp = _get_name_from_json()
        if error_resp:
            return error_resp

        success = config_db_write(lambda repo: repo.upsert_email(data))
        if success:
            clear_config_cache()
            audit_log('save_email', {'email': name})
            return json_success({'status': 'success', 'message': f"邮箱 [{name}] 配置已保存"}, 200)
        return json_error('保存失败', 500)
    except Exception as e:
        logger.error(f"保存邮箱配置失败: {e}", exc_info=True)
        return json_error(str(e), 500)


@email_bp.route('/config/email/delete', methods=['POST'])
def delete_email_route():
    """删除邮箱配置"""
    try:
        name, _data, error_resp = _get_name_from_json()
        if error_resp:
            return error_resp

        success = config_db_write(lambda repo: repo.delete_email(name))
        if success:
            clear_config_cache()
            audit_log('delete_email', {'email': name})
            return json_success({'status': 'success', 'message': f"邮箱 [{name}] 已删除"}, 200)
        return json_error('删除失败', 500)
    except Exception as e:
        logger.error(f"删除邮箱配置失败: {e}", exc_info=True)
        return json_error(str(e), 500)
