"""
路由模块

组织所有 Flask Blueprint 路由
"""
from .core import create_core_bp
from .email import email_bp
from .history import history_bp
from .project import project_bp

__all__ = [
    'create_core_bp',
    'create_subscription_bp',
    'email_bp',
    'history_bp',
    'project_bp',
]


def create_subscription_bp(state_manager):
    from .subscription import create_subscription_bp as _create_subscription_bp
    return _create_subscription_bp(state_manager)
