"""
智谱 GLM Coding Plan 配额查询适配器

智谱开放平台没有公开的预付费余额接口，这里查的是 Coding Plan 套餐配额。
接口按时间窗口返回若干条限额（5 小时 / 周 / 月，类型有 TOKENS_LIMIT / TIME_LIMIT /
CREDIT_LIMIT 几种），这里取「剩余比例最低」的那个窗口作为余额，单位是百分比：
100 表示一点没用，0 表示用光。阈值也按百分比填，例如 10 表示剩余不足 10% 时告警。

Z.ai 国际站是同一套接口，host 换成 https://api.z.ai 即可。
"""
from .base import ProviderSpec, SimpleHTTPProvider


def _check(data):
    if not data.get('success') or data.get('code') not in (None, 200):
        return f"API 返回错误: {data.get('msg', '未知错误')}"
    return None


def _remaining_percent(limit):
    """单个窗口的剩余比例。有总量/剩余量就精确算，否则用接口给的已用百分比反推。"""
    usage, remaining = limit.get('usage'), limit.get('remaining')
    if isinstance(usage, (int, float)) and usage > 0 and isinstance(remaining, (int, float)):
        return max(0.0, min(100.0, float(remaining) / usage * 100))

    percentage = limit.get('percentage')
    if isinstance(percentage, (int, float)):
        return max(0.0, min(100.0, 100.0 - percentage))
    return None


def _extract(data):
    limits = (data.get('data') or {}).get('limits')
    if not isinstance(limits, list):
        raise ValueError("无法从响应中解析 data.limits 字段")

    values = [v for v in (_remaining_percent(l) for l in limits if isinstance(l, dict)) if v is not None]
    if not values:
        raise ValueError("data.limits 里没有可解析的配额窗口")
    return round(min(values), 2)


class GLMProvider(SimpleHTTPProvider):
    """智谱 GLM Coding Plan 适配器"""

    SPEC = ProviderSpec(
        name="GLM",
        url="https://open.bigmodel.cn/api/monitor/usage/quota/limit",
        headers={"Accept": "application/json"},
        check=_check,
        extract=_extract,
    )
