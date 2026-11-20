"""Unit tests for habits/streaks.py: pure date logic, no database needed.

Calendar used below: Monday 2 Nov 2026 starts a week, so
2 Mon, 3 Tue, 4 Wed, 5 Thu, 6 Fri, 7 Sat, 8 Sun, 9 Mon ... 16 Mon ... 30 Mon.
"""

from datetime import date
from types import SimpleNamespace

import pytest

from habits.streaks import (
    completion_rate,
    is_scheduled,
    month_calendar,
    streaks,
    week_goal,
    week_start,
)

MON, WED, FRI = 0, 2, 4


def nov(day: int) -> date:
    return date(2026, 11, day)


def days(*numbers: int) -> set[date]:
    return {nov(n) for n in numbers}


def daily():
    return SimpleNamespace(schedule_type="daily", weekdays=[], times_per_week=None)


def on_days(*weekdays: int):
    return SimpleNamespace(schedule_type="weekdays", weekdays=list(weekdays), times_per_week=None)


def per_week(times: int):
    return SimpleNamespace(schedule_type="times_per_week", weekdays=[], times_per_week=times)


# --- Helpers ---------------------------------------------------------------------


def test_week_start_is_monday():
    assert week_start(nov(2)) == nov(2)
    assert week_start(nov(8)) == nov(2)  # Sunday belongs to the week before
    assert week_start(nov(9)) == nov(9)
    assert week_start(date(2027, 1, 3)) == date(2026, 12, 28)  # across new year


def test_is_scheduled():
    assert is_scheduled(daily(), nov(7))
    assert is_scheduled(on_days(MON, FRI), nov(6))
    assert not is_scheduled(on_days(MON, FRI), nov(4))
    assert not is_scheduled(per_week(3), nov(4))  # weekly habits have no fixed days


@pytest.mark.parametrize(
    "first_day, goal",
    [(nov(2), 3), (nov(6), 3), (nov(7), 2), (nov(8), 1)],  # Mon, Fri, Sat, Sun
)
def test_week_goal_shrinks_when_few_days_are_left(first_day, goal):
    assert week_goal(per_week(3), nov(2), first_day) == goal


# --- Every day ------------------------------------------------------------------


@pytest.mark.parametrize(
    "done, today, expected",
    [
        (set(), nov(5), (0, 0)),
        (days(2, 3, 4, 5), nov(5), (4, 4)),
        (days(2, 3, 4), nov(5), (3, 3)),  # today not done yet: streak still 3
        (days(2, 3, 5), nov(5), (1, 2)),  # missed the 4th
        (days(2, 3), nov(5), (0, 2)),  # missed yesterday: streak gone
        (days(2, 3, 4, 6, 7, 8, 9), nov(9), (4, 4)),
        (days(2, 3, 4, 5, 6, 8), nov(8), (1, 5)),
    ],
)
def test_daily_streaks(done, today, expected):
    assert streaks(daily(), done, nov(2), today) == expected


def test_days_before_the_habit_started_are_not_missed():
    assert streaks(daily(), days(4, 5), nov(4), nov(5)) == (2, 2)


def test_new_habit_today_has_no_streak_yet():
    assert streaks(daily(), set(), nov(5), nov(5)) == (0, 0)
    assert streaks(daily(), days(5), nov(5), nov(5)) == (1, 1)


def test_daily_streak_across_new_year():
    start = date(2026, 12, 29)
    done = {date(2026, 12, 29), date(2026, 12, 30), date(2026, 12, 31), date(2027, 1, 1)}

    assert streaks(daily(), done, start, date(2027, 1, 2)) == (4, 4)


# --- Specific days ------------------------------------------------------------------


@pytest.mark.parametrize(
    "done, today, expected",
    [
        (days(2, 4, 6), nov(6), (3, 3)),  # Mon Wed Fri
        (days(2, 4, 6), nov(8), (3, 3)),  # the weekend is off: still 3
        (days(2, 4, 6), nov(9), (3, 3)),  # Monday, not done yet: still 3
        (days(2, 4, 6), nov(10), (0, 3)),  # Monday the 9th was missed
        (days(2, 6), nov(6), (1, 1)),  # missed Wednesday
        (days(2, 3, 4), nov(4), (2, 2)),  # Tuesday is a bonus: doesn't add
        (days(3, 5), nov(6), (0, 0)),  # only bonus days, all real days pending/missed
    ],
)
def test_specific_days_streaks(done, today, expected):
    assert streaks(on_days(MON, WED, FRI), done, nov(2), today) == expected


# --- Times per week -------------------------------------------------------------------


@pytest.mark.parametrize(
    "done, today, expected",
    [
        (days(2, 3, 4), nov(8), (1, 1)),  # week 1 met
        (days(2, 3), nov(8), (0, 0)),  # week 1 still running on Sunday, not met yet
        (days(2, 3), nov(9), (0, 0)),  # week 1 over and missed
        (days(2, 3, 4, 9, 10, 11), nov(16), (2, 2)),  # week 3 just started: still 2
        (days(2, 3, 4, 9, 10), nov(16), (0, 1)),  # week 2 missed
        (days(2, 3, 4, 9, 10, 11, 16, 17, 18), nov(18), (3, 3)),  # this week already met
        (days(2, 3, 4, 5, 6, 7, 8), nov(9), (1, 1)),  # extra check-ins don't add weeks
    ],
)
def test_weekly_streaks(done, today, expected):
    assert streaks(per_week(3), done, nov(2), today) == expected


def test_first_week_only_needs_the_days_that_were_left():
    """Created on Saturday with 3x a week: only Sat and Sun are left, so 2 is enough."""
    assert streaks(per_week(3), days(7, 8), nov(7), nov(9)) == (1, 1)


def test_weekly_streak_across_new_year():
    start = date(2026, 12, 28)  # Monday
    done = {date(2026, 12, 28), date(2026, 12, 29), date(2027, 1, 4), date(2027, 1, 5)}

    assert streaks(per_week(2), done, start, date(2027, 1, 11)) == (2, 2)


# --- Completion rate --------------------------------------------------------------------


def test_daily_completion_rate_last_30_days():
    start = date(2026, 10, 1)
    every_other_day = {nov(n) for n in range(1, 31, 2)}  # 15 of the 30 days (1..30 Nov)

    assert completion_rate(daily(), every_other_day | {nov(30)}, start, nov(30)) == 53  # 16/30


def test_unfinished_today_does_not_lower_the_rate():
    done = {nov(n) for n in range(1, 30)}

    assert completion_rate(daily(), done, date(2026, 10, 1), nov(30)) == 100


def test_check_ins_older_than_30_days_dont_count():
    done = {date(2026, 10, n) for n in range(1, 31)}

    assert completion_rate(daily(), done, date(2026, 10, 1), nov(30)) == 0


def test_rate_is_none_when_nothing_was_due_yet():
    assert completion_rate(daily(), set(), nov(5), nov(5)) is None
    assert completion_rate(on_days(MON), set(), nov(3), nov(8)) is None


def test_specific_days_completion_rate_ignores_bonus_days():
    # Due: Mon 2, Wed 4, Fri 6. Done: Mon, Wed, and a bonus Tuesday.
    assert completion_rate(on_days(MON, WED, FRI), days(2, 3, 4), nov(2), nov(8)) == 67


def test_weekly_completion_rate():
    habit = per_week(2)
    done = days(2, 3, 9)  # week 1: 2/2, week 2: 1/2

    assert completion_rate(habit, done, nov(2), nov(15)) == 100  # week 2 still running
    assert completion_rate(habit, done, nov(2), nov(16)) == 75  # week 2 over: 3/4


def test_weekly_completion_rate_caps_extra_check_ins():
    assert completion_rate(per_week(2), days(2, 3, 4, 5), nov(2), nov(9)) == 100


# --- Calendar ---------------------------------------------------------------------------


def statuses(calendar_days) -> dict[int, str]:
    return {entry["date"].day: entry["status"] for entry in calendar_days}


def test_daily_calendar():
    result = month_calendar(daily(), 2026, 11, done=days(4), start=nov(4), today=nov(6))

    assert len(result) == 30
    status = statuses(result)
    assert [status[n] for n in (1, 3)] == ["before_start", "before_start"]
    assert status[4] == "done"
    assert status[5] == "missed"
    assert status[6] == "pending"
    assert status[7] == "future"
    assert status[30] == "future"


def test_specific_days_calendar():
    status = statuses(month_calendar(on_days(MON), 2026, 11, days(3, 9), nov(1), nov(10)))

    assert status[2] == "missed"  # Monday, not done
    assert status[3] == "bonus"  # Tuesday, done anyway
    assert status[4] == "off"
    assert status[9] == "done"
    assert status[10] == "off"  # today, but not a Monday


def test_weekly_calendar():
    status = statuses(month_calendar(per_week(3), 2026, 11, days(2), nov(1), nov(4)))

    assert status[2] == "done"
    assert status[3] == "off"
    assert status[4] == "off"  # today, no fixed days: nothing is "pending"
    assert status[5] == "future"


@pytest.mark.parametrize("year, month, length", [(2027, 2, 28), (2028, 2, 29), (2026, 12, 31)])
def test_calendar_has_every_day_of_the_month(year, month, length):
    result = month_calendar(daily(), year, month, set(), nov(1), nov(1))

    assert len(result) == length
    assert result[0]["date"] == date(year, month, 1)
