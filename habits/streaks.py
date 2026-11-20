"""Streaks and progress for a habit.

Everything here works on plain dates in the user's own calendar (see dates.py), so
the functions are easy to test: give them a habit, the set of days it was done,
the day it started and "today", and they answer.

The rules (decisions log, 20 Nov 2026):

* Every day / specific days: the streak is the number of *scheduled* days in a row
  that were done. Unscheduled days are skipped. A check-in on an unscheduled day is
  a "bonus": it neither breaks nor extends the streak.
* Times per week: the streak counts *weeks* (Monday to Sunday) in a row that met
  the goal. The first week only asks for as many days as were left after the habit
  was created (created on Saturday with a 3x goal: 2 is enough that week).
* Today, or the current week, is never "missed" yet: until it is over, the streak
  still shows the number up to yesterday / last week.
* Days before the habit was created never count as missed.
"""

import calendar
from collections import Counter
from collections.abc import Iterator
from datetime import date, timedelta

from .dates import local_date, user_today
from .models import Habit

DAY = timedelta(days=1)
WEEK = timedelta(days=7)
COMPLETION_WINDOW_DAYS = 30


class Status:
    """What a calendar day shows."""

    DONE = "done"  # checked in on a day that counts
    BONUS = "bonus"  # checked in on a day the habit isn't scheduled
    MISSED = "missed"  # scheduled, gone by, not done
    PENDING = "pending"  # scheduled today, not done yet
    OFF = "off"  # not scheduled (or a weekly habit's day without a check-in)
    FUTURE = "future"  # hasn't happened yet
    BEFORE_START = "before_start"  # before the habit was created


def days_between(first: date, last: date) -> Iterator[date]:
    """Every day from `first` to `last`, both included."""
    day = first
    while day <= last:
        yield day
        day += DAY


def week_start(day: date) -> date:
    """The Monday of `day`'s week."""
    return day - timedelta(days=day.weekday())


def is_weekly(habit) -> bool:
    return habit.schedule_type == Habit.Schedule.TIMES_PER_WEEK


def is_scheduled(habit, day: date) -> bool:
    """Is the habit due on this exact day? Weekly habits have no fixed days."""
    if habit.schedule_type == Habit.Schedule.DAILY:
        return True
    if habit.schedule_type == Habit.Schedule.WEEKDAYS:
        return day.weekday() in habit.weekdays
    return False


def week_goal(habit, monday: date, first_day: date) -> int:
    """How many check-ins the week starting `monday` asks for.

    If the week is only partly counted (it starts before `first_day`), the goal
    shrinks to the days that are left, e.g. 3x a week but only 2 days left -> 2.
    """
    days_left = 7 - max(0, (first_day - monday).days)
    return min(habit.times_per_week, days_left)


# --- Streaks ------------------------------------------------------------------


def day_streaks(habit, done: set[date], start: date, today: date) -> tuple[int, int]:
    """(current, longest) streak in days, for "every day" and "specific days"."""
    current = longest = 0
    for day in days_between(start, today):
        if not is_scheduled(habit, day):
            continue  # days off don't count either way
        if day in done:
            current += 1
            longest = max(longest, current)
        elif day != today:  # today isn't missed until it's over
            current = 0
    return current, longest


def week_streaks(habit, done: set[date], start: date, today: date) -> tuple[int, int]:
    """(current, longest) streak in weeks, for "times per week"."""
    per_week = Counter(week_start(day) for day in done if start <= day <= today)
    this_monday = week_start(today)

    current = longest = 0
    monday = week_start(start)
    while monday <= this_monday:
        if per_week[monday] >= week_goal(habit, monday, start):
            current += 1
            longest = max(longest, current)
        elif monday != this_monday:  # this week isn't missed until it's over
            current = 0
        monday += WEEK
    return current, longest


def streaks(habit, done: set[date], start: date, today: date) -> tuple[int, int]:
    """(current, longest) streak, in weeks for weekly habits and days otherwise."""
    if is_weekly(habit):
        return week_streaks(habit, done, start, today)
    return day_streaks(habit, done, start, today)


# --- Completion rate --------------------------------------------------------------


def completion_rate(
    habit, done: set[date], start: date, today: date, days: int = COMPLETION_WINDOW_DAYS
) -> int | None:
    """How much of the plan was done in the last `days` days, as a whole percent.

    Day habits: done scheduled days / scheduled days. Weekly habits: check-ins (up to
    the goal) / goal, week by week. Today / this week only count once they're done,
    so an unfinished day never drags the number down. None when nothing was due yet.
    """
    first = max(start, today - (days - 1) * DAY)
    achieved = expected = 0

    if is_weekly(habit):
        per_week = Counter(week_start(day) for day in done if first <= day <= today)
        this_monday = week_start(today)
        monday = week_start(first)
        while monday <= this_monday:
            goal = week_goal(habit, monday, first)
            count = per_week[monday]
            if monday != this_monday or count >= goal:
                achieved += min(count, goal)
                expected += goal
            monday += WEEK
    else:
        for day in days_between(first, today):
            if not is_scheduled(habit, day) or (day == today and day not in done):
                continue
            expected += 1
            achieved += day in done

    if expected == 0:
        return None
    return round(100 * achieved / expected)


# --- Calendar -------------------------------------------------------------------


def day_status(habit, day: date, done: set[date], start: date, today: date) -> str:
    if day > today:
        return Status.FUTURE
    if day < start:
        return Status.BEFORE_START
    weekly = is_weekly(habit)
    if day in done:
        return Status.DONE if weekly or is_scheduled(habit, day) else Status.BONUS
    if weekly or not is_scheduled(habit, day):
        return Status.OFF
    return Status.PENDING if day == today else Status.MISSED


def month_calendar(
    habit, year: int, month: int, done: set[date], start: date, today: date
) -> list[dict]:
    """One entry per day of the month: {"date": date, "status": Status...}."""
    last_day = calendar.monthrange(year, month)[1]
    return [
        {"date": day, "status": day_status(habit, day, done, start, today)}
        for day in days_between(date(year, month, 1), date(year, month, last_day))
    ]


# --- This week / today -------------------------------------------------------------


def week_progress(habit, done: set[date], start: date, today: date) -> dict:
    """{"done": check-ins so far this week, "goal": how many this week needs}."""
    this_monday = week_start(today)
    return {
        "done": sum(1 for day in done if this_monday <= day <= today),
        "goal": week_goal(habit, this_monday, start),
    }


def is_due_today(habit, done: set[date], start: date, today: date) -> bool:
    """Should the habit be on today's list?

    Day habits: when today is one of its days. Weekly habits: until this week's goal
    is met, and also on the day it was ticked off (so it doesn't vanish on tap).
    """
    if is_weekly(habit):
        progress = week_progress(habit, done, start, today)
        return today in done or progress["done"] < progress["goal"]
    return is_scheduled(habit, today)


def today_overview(user, habits) -> dict:
    """Everything for GET /api/habits/today/.

    `habits` must be the user's active habits with `checkins` prefetched, so this
    runs no extra database queries however many habits there are.
    """
    today = user_today(user)
    due, not_due = [], []
    for habit in habits:
        checkins = list(habit.checkins.all())  # prefetched, no query
        start = local_date(habit.created_at, user)
        done = {c.date for c in checkins if start <= c.date <= today}
        current, _ = streaks(habit, done, start, today)
        todays_checkin = next((c for c in checkins if c.date == today), None)

        entry = {
            "habit": habit,
            "done_today": todays_checkin is not None,
            "checkin": todays_checkin,
            "current_streak": current,
            "streak_unit": "weeks" if is_weekly(habit) else "days",
            "week_progress": week_progress(habit, done, start, today) if is_weekly(habit) else None,
        }
        (due if is_due_today(habit, done, start, today) else not_due).append(entry)

    return {
        "date": today,
        "summary": {"done": sum(e["done_today"] for e in due), "total": len(due)},
        "due": due,
        "not_due": not_due,
    }


# --- Everything for the stats endpoint ---------------------------------------------


def habit_stats(habit: Habit, month: tuple[int, int] | None = None) -> dict:
    """All the numbers for GET /api/habits/<id>/stats/ (plus a calendar if asked)."""
    today = user_today(habit.owner)
    start = habit.created_on()
    all_days = set(habit.checkins.values_list("date", flat=True))
    done = {day for day in all_days if start <= day <= today}

    current, longest = streaks(habit, done, start, today)
    stats = {
        "habit": habit.id,
        "today": today,
        "current_streak": current,
        "longest_streak": longest,
        "streak_unit": "weeks" if is_weekly(habit) else "days",
        "completion_rate": completion_rate(habit, done, start, today),
        "total_checkins": len(all_days),
        "done_today": today in all_days,
        "week_progress": None,
        "calendar": None,
    }
    if is_weekly(habit):
        stats["week_progress"] = week_progress(habit, done, start, today)
    if month:
        year, month_number = month
        stats["calendar"] = {
            "month": f"{year:04d}-{month_number:02d}",
            "days": month_calendar(habit, year, month_number, done, start, today),
        }
    return stats
