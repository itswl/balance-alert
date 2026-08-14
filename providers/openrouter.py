"""
OpenRouter 余额查询适配器
"""
from .base import ProviderSpec, SimpleHTTPProvider


def _extract(data):
    """余额 = total_credits - total_usage，字段可能在顶层或 data 下"""
    scope = data.get('data', data)
    total = scope.get('total_credits')
    used = scope.get('total_usage')
    if total is None:
        raise ValueError("无法从响应中解析 total_credits 字段")
    if used is None:
        raise ValueError("无法从响应中解析 total_usage 字段")
    return float(total) - float(used)


class OpenRouterProvider(SimpleHTTPProvider):
    """OpenRouter 服务商适配器"""

    SPEC = ProviderSpec(
        name="OpenRouter",
        url="https://openrouter.ai/api/v1/credits",
        extract=_extract,
    )
