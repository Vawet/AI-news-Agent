from datetime import datetime
from zoneinfo import ZoneInfo

from src.reporting import twice_weekly_window

SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_wednesday_window_starts_previous_sunday():
    window = twice_weekly_window(datetime(2026, 9, 23, 20, 0, tzinfo=SHANGHAI))

    assert window.start == datetime(2026, 9, 20, 20, 0, tzinfo=SHANGHAI)
    assert window.end == datetime(2026, 9, 23, 20, 0, tzinfo=SHANGHAI)


def test_sunday_window_starts_previous_wednesday():
    window = twice_weekly_window(datetime(2026, 9, 27, 20, 0, tzinfo=SHANGHAI))

    assert window.start == datetime(2026, 9, 23, 20, 0, tzinfo=SHANGHAI)
    assert window.end == datetime(2026, 9, 27, 20, 0, tzinfo=SHANGHAI)


def test_before_scheduled_time_uses_previous_period():
    window = twice_weekly_window(datetime(2026, 9, 23, 10, 0, tzinfo=SHANGHAI))

    assert window.start == datetime(2026, 9, 16, 20, 0, tzinfo=SHANGHAI)
    assert window.end == datetime(2026, 9, 20, 20, 0, tzinfo=SHANGHAI)
