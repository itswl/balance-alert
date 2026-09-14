"""
DeepSeek 余额查询适配器
"""
from .base import ProviderSpec, SimpleHTTPProvider


def _extract(data):
    """余额在 balance_infos 列表里，优先取人民币账户，没有就退回第一条"""
    infos = data.get('balance_infos')
    if not isinstance(infos, list) or not infos:
        raise ValueError("无法从响应中解析 balance_infos 字段")

    chosen = next((i for i in infos if isinstance(i, dict) and i.get('currency') == 'CNY'), infos[0])
    total = chosen.get('total_balance') if isinstance(chosen, dict) else None
    if total is None:
        raise ValueError("无法从响应中解析 total_balance 字段")
    return float(total)


class DeepSeekProvider(SimpleHTTPProvider):
    """DeepSeek 服务商适配器"""

    SPEC = ProviderSpec(
        name="DeepSeek",
        url="https://api.deepseek.com/user/balance",
        headers={"Accept": "application/json"},
        extract=_extract,
    )
