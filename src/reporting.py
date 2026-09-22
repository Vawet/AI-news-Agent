"""报告周期与采集窗口计算。"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

REPORT_TIMEZONE = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class ReportWindow:
    start: datetime
    end: datetime


def twice_weekly_window(now: datetime | None = None) -> ReportWindow:
    """返回当前周三/周日刊期对应的非重叠采集窗口。

    周三刊：(上周日 20:00, 本周三 20:00]
    周日刊：(本周三 20:00, 本周日 20:00]
    """
    local_now = (now or datetime.now(REPORT_TIMEZONE)).astimezone(REPORT_TIMEZONE)
    end = local_now.replace(hour=20, minute=0, second=0, microsecond=0)

    # Monday=0, Wednesday=2, Sunday=6. 手动运行时取最近一个已到达的刊期。
    days_since_wednesday = (local_now.weekday() - 2) % 7
    days_since_sunday = (local_now.weekday() - 6) % 7
    wednesday = end - timedelta(days=days_since_wednesday)
    sunday = end - timedelta(days=days_since_sunday)
    candidates = [candidate for candidate in (wednesday, sunday) if candidate <= local_now]
    if not candidates:
        # 仅会发生在刊期当天 20:00 前：退回上一个刊期。
        candidates = [wednesday - timedelta(days=7), sunday - timedelta(days=7)]
    end = max(candidates)

    span_days = 3 if end.weekday() == 2 else 4
    return ReportWindow(start=end - timedelta(days=span_days), end=end)
