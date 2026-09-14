"""
路由模块：五个蓝图，均为模块级对象，由 web.app.create_app 按开关注册
"""
from .core import core_bp
from .email import email_bp
from .history import history_bp
from .project import project_bp
from .subscription import subscription_bp

__all__ = ['core_bp', 'email_bp', 'history_bp', 'project_bp', 'subscription_bp']
