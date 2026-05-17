#!/usr/bin/env python3
"""
敏感配置加密工具。

数据库动态配置是可选能力；只有设置 CONFIG_ENCRYPTION_KEY 后才会启用加密。
"""
import base64
import hashlib
import os
from typing import Optional

from core.logger import get_logger

logger = get_logger('secret_crypto')

ENCRYPTED_PREFIX = 'enc:v1:'
KEY_ENV_NAMES = (
    'CONFIG_ENCRYPTION_KEY',
    'BALANCE_ALERT_ENCRYPTION_KEY',
)


def _get_raw_key() -> Optional[str]:
    for env_name in KEY_ENV_NAMES:
        value = (os.environ.get(env_name) or '').strip()
        if value:
            return value
    return None


def encryption_enabled() -> bool:
    return _get_raw_key() is not None


def is_encrypted(value: object) -> bool:
    return isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX)


def _normalize_key(raw_key: str) -> bytes:
    """Accept either a Fernet key or a passphrase."""
    raw_bytes = raw_key.encode('utf-8')
    try:
        from cryptography.fernet import Fernet

        Fernet(raw_bytes)
        return raw_bytes
    except Exception:
        digest = hashlib.sha256(raw_bytes).digest()
        return base64.urlsafe_b64encode(digest)


def _get_fernet():
    raw_key = _get_raw_key()
    if not raw_key:
        return None

    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:
        raise RuntimeError(
            'CONFIG_ENCRYPTION_KEY 已设置，但未安装 cryptography；请安装 requirements-optional.txt'
        ) from exc

    return Fernet(_normalize_key(raw_key))


def encrypt_secret(value: object) -> object:
    if value is None or value == '' or is_encrypted(value):
        return value
    if not isinstance(value, str):
        return value

    fernet = _get_fernet()
    if fernet is None:
        return value

    token = fernet.encrypt(value.encode('utf-8')).decode('utf-8')
    return f'{ENCRYPTED_PREFIX}{token}'


def decrypt_secret(value: object) -> object:
    if not is_encrypted(value):
        return value

    fernet = _get_fernet()
    if fernet is None:
        logger.warning('发现加密配置但未设置 CONFIG_ENCRYPTION_KEY，无法解密')
        return value

    token = value[len(ENCRYPTED_PREFIX):]
    try:
        return fernet.decrypt(token.encode('utf-8')).decode('utf-8')
    except Exception as exc:
        logger.error(f'敏感配置解密失败: {exc}')
        return value
