from flask import Blueprint, jsonify, request
from ..utils import audit_log, mask_email_config
from core.config_loader import clear_config_cache
from database.repository import ConfigRepository
from core.logger import get_logger

logger = get_logger('web.routes.email')
email_bp = Blueprint('email', __name__, url_prefix='/api')

@email_bp.route('/config/emails', methods=['GET'])
def get_emails_config():
    """获取所有邮箱配置"""
    try:
        emails = [mask_email_config(email) for email in ConfigRepository.get_all_emails()]
        return jsonify({'status': 'success', 'emails': emails})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@email_bp.route('/config/email', methods=['POST'])
def save_email():
    """添加或更新邮箱配置"""
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'status': 'error', 'message': '缺少必要参数: name'}), 400

        success = ConfigRepository.upsert_email(data)
        if success:
            clear_config_cache()
            audit_log('save_email', {'email': data['name']})
            return jsonify({'status': 'success', 'message': f"邮箱 [{data['name']}] 配置已保存"})
        else:
            return jsonify({'status': 'error', 'message': '保存失败'}), 500
    except Exception as e:
        logger.error(f"保存邮箱配置失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500

@email_bp.route('/config/email/delete', methods=['POST'])
def delete_email():
    """删除邮箱配置"""
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'status': 'error', 'message': '缺少必要参数: name'}), 400

        name = data['name']
        success = ConfigRepository.delete_email(name)
        if success:
            clear_config_cache()
            audit_log('delete_email', {'email': name})
            return jsonify({'status': 'success', 'message': f"邮箱 [{name}] 已删除"})
        else:
            return jsonify({'status': 'error', 'message': '删除失败'}), 500
    except Exception as e:
        logger.error(f"删除邮箱配置失败: {e}", exc_info=True)
        return jsonify({'status': 'error', 'message': str(e)}), 500
