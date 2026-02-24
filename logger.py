#!/usr/bin/env python3
"""
日志配置模块
统一日志格式和输出
支持结构化日志（JSON 格式）
"""
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from typing import Optional
from datetime import datetime

# 尝试导入 JSON 日志格式器
try:
    from pythonjsonlogger import jsonlogger
    JSON_LOGGING_AVAILABLE = True
except ImportError:
    JSON_LOGGING_AVAILABLE = False


def setup_logging(level: Optional[str] = None, log_file: Optional[str] = None) -> logging.Logger:
    """
    配置日志

    Args:
        level: 日志级别 (DEBUG/INFO/WARNING/ERROR)
        log_file: 日志文件路径，None 表示只输出到控制台

    Returns:
        logging.Logger: 配置好的 logger 实例
    """
    if level is None:
        level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    
    # 创建 logger
    logger = logging.getLogger('balance_alert')
    numeric_level = getattr(logging, level, None)
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO
    logger.setLevel(numeric_level)
    
    # 避免重复添加 handler
    if logger.handlers:
        return logger
    
    # 创建 formatter（支持 JSON 格式）
    log_format = os.environ.get('LOG_FORMAT', 'text').lower()

    if log_format == 'json' and JSON_LOGGING_AVAILABLE:
        # JSON 格式（结构化日志）
        formatter = jsonlogger.JsonFormatter(
            '%(asctime)s %(name)s %(levelname)s %(message)s',
            timestamp=True
        )
    else:
        # 文本格式（传统日志）
        if log_format == 'json' and not JSON_LOGGING_AVAILABLE:
            print("Warning: python-json-logger not installed, falling back to text format", file=sys.stderr)

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
        file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


# 全局 logger 实例（支持 LOG_FILE 环境变量指定日志文件）
logger = setup_logging(log_file=os.environ.get('LOG_FILE'))


def get_logger(name: Optional[str] = None) -> logging.Logger:
    """
    获取 logger 实例

    Args:
        name: logger 名称，None 表示使用根 logger

    Returns:
        logging.Logger: logger 实例
    """
    if name:
        return logging.getLogger(f'balance_alert.{name}')
    return logger
