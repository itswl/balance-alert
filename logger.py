#!/usr/bin/env python3
"""
日志配置模块
统一日志格式和输出
"""
import logging
import os
from datetime import datetime


def setup_logging(level=None, log_file=None):
    """
    配置日志
    
    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        log_file: 日志文件路径，None 表示只输出到控制台
    """
    if level is None:
        level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    
    # 创建 logger
    logger = logging.getLogger('balance_alert')
    logger.setLevel(getattr(logging, level))
    
    # 避免重复添加 handler
    if logger.handlers:
        return logger
    
    # 创建 formatter
    formatter = logging.Formatter(
        fmt='%(asctime)s [%(levelname)-8s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台 handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件 handler（可选）
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


# 全局 logger 实例
logger = setup_logging()


def get_logger(name=None):
    """
    获取 logger 实例
    
    Args:
        name: logger 名称，None 表示使用根 logger
        
    Returns:
        logging.Logger
    """
    if name:
        return logging.getLogger(f'balance_alert.{name}')
    return logger
