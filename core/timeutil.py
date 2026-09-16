#!/usr/bin/env python3
"""
定时任务用到的纯时间工具，不依赖项目内其它模块（settings / logger 都要 import 它，不能有环）。
"""
import re
from datetime import datetime, time, timedelta, timezone
from typing import List, Optional, Set, Tuple

SCHEDULE_OFF_VALUES = {'off', 'none', 'disabled', 'false', '0', '-'}
_TIME_PATTERN = re.compile(r'(\d{1,2}):(\d{2})')

# 周计划里的星期写法，1=周一 … 7=周日（与 isoweekday 一致）
WEEKDAY_NAMES = {
    'mon': 1, 'monday': 1, '周一': 1, '一': 1,
    'tue': 2, 'tues': 2, 'tuesday': 2, '周二': 2, '二': 2,
    'wed': 3, 'wednesday': 3, '周三': 3, '三': 3,
    'thu': 4, 'thur': 4, 'thurs': 4, 'thursday': 4, '周四': 4, '四': 4,
    'fri': 5, 'friday': 5, '周五': 5, '五': 5,
    'sat': 6, 'saturday': 6, '周六': 6, '六': 6,
    'sun': 7, 'sunday': 7, '周日': 7, '周天': 7, '日': 7, '天': 7,
}


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


def parse_weekdays(text: Optional[str]) -> Set[int]:
    """把 ``"Mon,Thu"`` / ``"周一"`` 解析成 {1, 4}；空表示不限定星期"""
    if not text or not text.strip():
        return set()
    result = set()
    for part in text.replace('、', ',').split(','):
        part = part.strip().lower()
        if not part:
            continue
        if part.isdigit() and 1 <= int(part) <= 7:
            result.add(int(part))
            continue
        if part not in WEEKDAY_NAMES:
            raise ValueError(f'星期格式错误: {part!r}，可写 Mon / 周一 / 1')
        result.add(WEEKDAY_NAMES[part])
    return result


def parse_weekly_schedule(text: Optional[str]) -> Tuple[Set[int], List[time]]:
    """把 ``"Mon 09:00"`` 解析成 ({1}, [09:00])；省略星期表示每天，``off`` 表示关闭。

    星期与时刻之间用空格分隔，各自都能用逗号写多个，例如 ``"Mon,Thu 09:00,18:00"``。
    """
    if text is None:
        return set(), []
    raw = text.strip()
    if not raw or raw.lower() in SCHEDULE_OFF_VALUES:
        return set(), []

    parts = raw.split(None, 1)
    if len(parts) == 1:
        return set(), parse_daily_times(parts[0])
    return parse_weekdays(parts[0]), parse_daily_times(parts[1])


def describe_daily_times(times: List[time], weekdays: Optional[Set[int]] = None) -> str:
    if not times:
        return '已关闭'
    clock = ' / '.join(t.strftime('%H:%M') for t in sorted(times))
    if not weekdays:
        return f'每天 {clock}'
    labels = '、'.join('一二三四五六日'[day - 1] for day in sorted(weekdays))
    return f'每周{labels} {clock}'


def next_daily_occurrence(now: datetime, times: List[time], weekdays: Optional[Set[int]] = None) -> datetime:
    """下一个到点时刻。weekdays 非空时只在这些星期触发。now 与返回值同为本地时间。"""
    ordered = sorted(times)
    for offset in range(8):  # 最多找一周，一定能落到某一天
        day = now.date() + timedelta(days=offset)
        if weekdays and day.isoweekday() not in weekdays:
            continue
        for t in ordered:
            candidate = datetime.combine(day, t, tzinfo=now.tzinfo)
            if candidate > now:
                return candidate
    raise ValueError('无法计算下次运行时间')


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
