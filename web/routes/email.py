from flask import Blueprint, jsonify, request
from ..utils import audit_log, mask_email_config
from core.config_loader import clear_config_cache
from services.config_service import delete_email as delete_email_config, get_all_emails, upsert_email as upsert_email_config
from core.logger import get_logger

logger = get_logger('web.routes.email')
email_bp = Blueprint('email', __name__, url_prefix='/api')

def _error(message: str, status_code: int = 500):
    return jsonify({'status': 'error', 'message': message}), status_code


def _success(payload: dict, status_code: int = 200):
    return jsonify(payload), status_code


def _get_name_from_json():
    data = request.get_json()
    if not data or 'name' not in data:
        return None, None, _error('缺少必要参数: name', 400)
    return data['name'], data, None


@email_bp.route('/config/emails', methods=['GET'])
def get_emails_config():
    """获取所有邮箱配置"""
    try:
        emails = [mask_email_config(email) for email in get_all_emails()]
        return jsonify({'status': 'success', 'emails': emails})
    except Exception as e:
        logger.error(f"获取邮箱配置失败: {e}", exc_info=True)
        return _error(str(e), 500)

@email_bp.route('/config/email', methods=['POST'])
def save_email():
    """添加或更新邮箱配置"""
    try:
        name, data, error_resp = _get_name_from_json()
        if error_resp:
            return error_resp

        success = upsert_email_config(data)
        if success:
            clear_config_cache()
            audit_log('save_email', {'email': name})
            return _success({'status': 'success', 'message': f"邮箱 [{name}] 配置已保存"}, 200)
        return _error('保存失败', 500)
    except Exception as e:
        logger.error(f"保存邮箱配置失败: {e}", exc_info=True)
        return _error(str(e), 500)

@email_bp.route('/config/email/delete', methods=['POST'])
def delete_email_route():
    """删除邮箱配置"""
    try:
        name, _data, error_resp = _get_name_from_json()
        if error_resp:
            return error_resp

        success = delete_email_config(name)
        if success:
            clear_config_cache()
            audit_log('delete_email', {'email': name})
            return _success({'status': 'success', 'message': f"邮箱 [{name}] 已删除"}, 200)
        return _error('删除失败', 500)
    except Exception as e:
        logger.error(f"删除邮箱配置失败: {e}", exc_info=True)
        return _error(str(e), 500)
