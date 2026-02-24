#!/usr/bin/env python3
"""
数据库引擎配置

管理数据库连接和初始化
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from logger import get_logger
from .models import Base

logger = get_logger('database')

# 数据库路径（从环境变量读取，默认在 data 目录）
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///./data/balance_alert.db')

# 是否启用数据持久化（默认启用）
ENABLE_DATABASE = os.environ.get('ENABLE_DATABASE', 'true').lower() == 'true'

# 全局引擎和会话工厂
_engine = None
_session_factory = None


def get_engine():
    """获取数据库引擎（单例）"""
    global _engine
    
    if not ENABLE_DATABASE:
        logger.warning("数据持久化已禁用 (ENABLE_DATABASE=false)")
        return None
    
    if _engine is None:
        # 创建引擎
        _engine = create_engine(
            DATABASE_URL,
            echo=False,  # 生产环境关闭 SQL 日志
            pool_pre_ping=True,  # 连接池健康检查
            connect_args={'check_same_thread': False} if 'sqlite' in DATABASE_URL else {}
        )
        logger.info(f"数据库引擎已创建: {DATABASE_URL}")
    
    return _engine


def get_session_factory():
    """获取会话工厂（线程安全）"""
    global _session_factory
    
    if not ENABLE_DATABASE:
        return None
    
    if _session_factory is None:
        engine = get_engine()
        _session_factory = scoped_session(sessionmaker(bind=engine))
        logger.info("数据库会话工厂已创建")
    
    return _session_factory


def init_database():
    """初始化数据库（创建所有表）"""
    if not ENABLE_DATABASE:
        logger.info("数据持久化已禁用，跳过数据库初始化")
        return False
    
    try:
        engine = get_engine()
        
        # 确保数据目录存在
        if 'sqlite' in DATABASE_URL:
            db_path = DATABASE_URL.replace('sqlite:///', '')
            db_dir = os.path.dirname(db_path)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"创建数据目录: {db_dir}")
        
        # 创建所有表
        Base.metadata.create_all(engine)
        logger.info("✅ 数据库初始化完成")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ 数据库初始化失败: {e}", exc_info=True)
        return False


def get_session():
    """获取数据库会话（上下文管理器）"""
    factory = get_session_factory()
    if factory is None:
        return None
    return factory()


def close_session():
    """关闭会话"""
    if _session_factory:
        _session_factory.remove()
