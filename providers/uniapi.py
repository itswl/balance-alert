"""
UniAPI 余额查询适配器
"""
from .base import ProviderSpec, SimpleHTTPProvider


def _check(data):
    if not data.get('success'):
        return "API 返回 success=false"
    return None


def _extract(data):
    balance = (data.get('data') or {}).get('balance')
    if balance is None:
        raise ValueError("无法从响应中解析 balance 字段")
    return float(balance)


class UniAPIProvider(SimpleHTTPProvider):
    """UniAPI 服务商适配器"""

    SPEC = ProviderSpec(
        name="UniAPI",
        url="https://api.uniapi.io/v1/billing/usage",
        params={"unit": "usd"},
        check=_check,
        extract=_extract,
    )
