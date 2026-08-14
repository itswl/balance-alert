"""
微信排名余额查询适配器
"""
import re

from .base import ProviderSpec, SimpleHTTPProvider


def _check(data):
    if data.get('code') != 0:
        return f"API 返回错误: {data.get('msg', '未知错误')}"
    return None


def _extract(data):
    """余额通常写在 msg 文本里（如 "剩余263419余额"），也兼容 data/score/credits 字段"""
    msg = data.get('msg', '')
    matched = re.search(r'(\d+)', msg)
    if matched:
        return float(matched.group(1))

    raw = data.get('data')
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, dict):
        value = raw.get('score') or raw.get('credits')
        if value is not None:
            return float(value)

    value = data.get('score') or data.get('credits')
    if value is None:
        raise ValueError(f"无法从响应中解析余额: {msg}")
    return float(value)


class WxRankProvider(SimpleHTTPProvider):
    """微信排名服务适配器"""

    SPEC = ProviderSpec(
        name="WxRank",
        url="https://data.wxrank.com/weixin/score",
        auth='query',
        auth_param='key',
        check=_check,
        extract=_extract,
    )
