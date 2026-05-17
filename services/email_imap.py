#!/usr/bin/env python3
from contextlib import contextmanager
import imaplib
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from core.logger import get_logger

logger = get_logger('email_imap')


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((imaplib.IMAP4.error, ConnectionError, TimeoutError)),
    reraise=True
)
def open_imap(host: str, port: int, username: str, password: str, use_ssl: bool = True):
    logger.info(f"正在连接IMAP服务器 {host}:{port} (SSL: {use_ssl})")
    if use_ssl:
        mail = imaplib.IMAP4_SSL(host, port)
    else:
        mail = imaplib.IMAP4(host, port)

    mail.login(username, password)
    mail.select('INBOX')
    logger.info("✅ IMAP连接成功")
    return mail


@contextmanager
def imap_connection(host: str, port: int, username: str, password: str, use_ssl: bool = True):
    mail = None
    try:
        mail = open_imap(host, port, username, password, use_ssl)
        logger.info(f"✅ 成功连接到邮箱 {username}@{host}")
        yield mail
    except Exception as e:
        logger.error(f"❌ 邮箱连接失败: {e}")
        raise
    finally:
        if mail:
            try:
                mail.logout()
                logger.info(f"   已断开邮箱连接 {username}@{host}")
            except Exception as e:
                logger.warning(f"   断开连接时出错: {e}")

