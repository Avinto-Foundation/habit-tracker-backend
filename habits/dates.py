"""Dates as the user sees them.

The server stores times in UTC, but "today" depends on where the user lives: at
01:00 on Saturday in Kathmandu it is still Friday evening in UTC. Streaks and
check-ins always use the user's own calendar day, from their profile time zone.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from django.utils import timezone


def user_tz(user) -> ZoneInfo:
    return ZoneInfo(user.timezone)


def local_date(moment: datetime, user) -> date:
    """The calendar day `moment` falls on in the user's time zone."""
    return moment.astimezone(user_tz(user)).date()


def user_today(user) -> date:
    """Today's date for this user."""
    return local_date(timezone.now(), user)


def is_today_or_yesterday(day: date, user) -> bool:
    today = user_today(user)
    return day in (today, today - timedelta(days=1))
