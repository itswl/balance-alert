"""
路由模块

组织所有 Flask Blueprint 路由
"""
from .core import core_bp, init_core_routes

__all__ = [
    'core_bp',
    'init_core_routes',
]
