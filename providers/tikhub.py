"""
TikHub 余额查询适配器
"""
from .base import ProviderSpec, SimpleHTTPProvider


def _extract(data):
    """balance 可能在 user_data / data 下或顶层"""
    scope = data.get('user_data', data.get('data', data))
    balance = scope.get('balance') if isinstance(scope, dict) else None
    if balance is None:
        raise ValueError("无法从响应中解析 balance 字段")
    return float(balance)


class TikHubProvider(SimpleHTTPProvider):
    """TikHub 服务商适配器"""

    SPEC = ProviderSpec(
        name="TikHub",
        url="https://api.tikhub.dev/api/v1/tikhub/user/get_user_info",
        headers={"accept": "application/json"},
        extract=_extract,
    )
