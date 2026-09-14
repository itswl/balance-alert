#!/usr/bin/env python3
"""
定时任务用到的纯时间工具，不依赖项目内其它模块（settings / logger 都要 import 它，不能有环）。
"""
import re
from datetime import datetime, time, timedelta, timezone
from typing import List, Optional

SCHEDULE_OFF_VALUES = {'off', 'none', 'disabled', 'false', '0', '-'}
_TIME_PATTERN = re.compile(r'(\d{1,2}):(\d{2})')


def parse_daily_times(text: Optional[str]) -> List[time]:
    """把 ``"09:00,15:30"`` 解析成去重排序后的 time 列表；``off`` / ``none`` 等表示关闭。

    格式不对时抛 ValueError，配合 settings 的校验在启动时直接报错。
    """
    if text is None:
        return []
    raw = text.strip()
    if not raw or raw.lower() in SCHEDULE_OFF_VALUES:
        return []

    result = set()
    for part in raw.split(','):
        part = part.strip()
        if not part:
            continue
        matched = _TIME_PATTERN.fullmatch(part)
        if not matched:
            raise ValueError(f'时刻格式错误: {part!r}，应为 HH:MM，多个时刻用逗号分隔')
        hour, minute = int(matched.group(1)), int(matched.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            raise ValueError(f'时刻越界: {part!r}')
        result.add(time(hour, minute))
    return sorted(result)


def describe_daily_times(times: List[time]) -> str:
    if not times:
        return '已关闭'
    return '每天 ' + ' / '.join(t.strftime('%H:%M') for t in sorted(times))


def next_daily_occurrence(now: datetime, times: List[time]) -> datetime:
    """今天还没到的最早时刻；今天都过了就取明天的第一个。now 与返回值同为本地时间。"""
    ordered = sorted(times)
    today = now.date()
    for t in ordered:
        candidate = datetime.combine(today, t, tzinfo=now.tzinfo)
        if candidate > now:
            return candidate
    return datetime.combine(today + timedelta(days=1), ordered[0], tzinfo=now.tzinfo)


def local_now() -> datetime:
    """带时区的本地当前时间（容器里由 TZ 决定）"""
    return datetime.now().astimezone()


def to_utc_iso(value: Optional[datetime]) -> Optional[str]:
    """datetime → UTC ISO 字符串（Z 结尾）；naive 值按本地时间理解"""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.astimezone()
    return value.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
