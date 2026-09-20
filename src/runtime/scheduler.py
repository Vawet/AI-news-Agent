"""Cloud schedule definitions."""

from __future__ import annotations

from apscheduler.triggers.cron import CronTrigger

SCHEDULE_TIMEZONE = "Asia/Shanghai"


def build_schedule_trigger() -> CronTrigger:
    """Run every Wednesday and Sunday at 10:00 Beijing time."""
    return CronTrigger(
        day_of_week="wed,sun",
        hour=10,
        minute=0,
        timezone=SCHEDULE_TIMEZONE,
    )
