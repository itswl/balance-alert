"""
路由模块

组织所有 Flask Blueprint 路由
"""
from .core import create_core_bp

__all__ = [
    'create_core_bp',
]
