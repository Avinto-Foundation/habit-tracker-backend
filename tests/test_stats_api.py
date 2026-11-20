from datetime import date, datetime, timezone as dt_timezone

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from habits.models import CheckIn, Habit

User = get_user_model()

# "Now": Friday 20 Nov 2026, 06:00 UTC (11:45 the same day in Kathmandu).
NOW = datetime(2026, 11, 20, 6, 0, tzinfo=dt_timezone.utc)
CREATED = datetime(2026, 11, 2, 6, 0, tzinfo=dt_timezone.utc)  # Monday 2 Nov


def set_now(monkeypatch, moment):
    monkeypatch.setattr(timezone, "now", lambda: moment)


def make_user(name, tz="Asia/Kathmandu"):
    return User.objects.create_user(
        email=f"{name}@example.com",
        username=name,
        full_name=name.title(),
        password="x-Strong-pass-1",
        timezone=tz,
    )


def make_habit(monkeypatch, owner, **fields):
    set_now(monkeypatch, CREATED)
    habit = Habit.objects.create(owner=owner, name=fields.pop("name", "Read"), **fields)
    set_now(monkeypatch, NOW)
    return habit


def check_in(habit, *days):
    for day in days:
        CheckIn.objects.create(habit=habit, date=date(2026, 11, day))


def stats_url(habit) -> str:
    return reverse("habit-stats", args=[habit.id])


@pytest.fixture
def user(db):
    return make_user("sam")


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def habit(monkeypatch, user):
    return make_habit(monkeypatch, user)


def test_stats_need_login(habit):
    assert APIClient().get(stats_url(habit)).status_code == 401


def test_daily_habit_stats(api, habit):
    check_in(habit, 10, 12, 13, 14, 15, 16, 17, 18, 19)  # 8 days in a row up to yesterday

    response = api.get(stats_url(habit))

    assert response.status_code == 200
    assert response.json() == {
        "habit": habit.id,
        "today": "2026-11-20",
        "current_streak": 8,  # today not done yet, still counts
        "longest_streak": 8,
        "streak_unit": "days",
        "completion_rate": 50,  # 9 of the 18 days 2–19 Nov (today not counted yet)
        "total_checkins": 9,
        "done_today": False,
        "week_progress": None,
        "calendar": None,
    }


def test_done_today(api, habit):
    check_in(habit, 19, 20)

    body = api.get(stats_url(habit)).json()

    assert body["done_today"] is True
    assert body["current_streak"] == 2


def test_weekly_habit_stats(monkeypatch, user, api):
    habit = make_habit(monkeypatch, user, schedule_type="times_per_week", times_per_week=2)
    check_in(habit, 2, 3, 9, 10, 18)  # weeks 1 and 2 met, 1 of 2 this week

    body = api.get(stats_url(habit)).json()

    assert body["streak_unit"] == "weeks"
    assert body["current_streak"] == 2
    assert body["longest_streak"] == 2
    assert body["week_progress"] == {"done": 1, "goal": 2}
    assert body["completion_rate"] == 100  # this week isn't over yet


def test_calendar_for_a_month(api, habit):
    check_in(habit, 2, 3, 20)

    body = api.get(stats_url(habit), {"month": "2026-11"}).json()

    calendar = body["calendar"]
    assert calendar["month"] == "2026-11"
    assert len(calendar["days"]) == 30
    status = {d["date"]: d["status"] for d in calendar["days"]}
    assert status["2026-11-01"] == "before_start"
    assert status["2026-11-02"] == "done"
    assert status["2026-11-04"] == "missed"
    assert status["2026-11-20"] == "done"
    assert status["2026-11-21"] == "future"


def test_calendar_for_another_month(api, habit):
    days = api.get(stats_url(habit), {"month": "2026-10"}).json()["calendar"]["days"]

    assert len(days) == 31
    assert {d["status"] for d in days} == {"before_start"}


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "nov", "2026-11-01", "2026-00"])
def test_bad_month_is_400(api, habit, month):
    response = api.get(stats_url(habit), {"month": month})

    assert response.status_code == 400
    assert response.json()["month"] == ["Use YYYY-MM, e.g. 2026-11."]


def test_stats_use_the_users_time_zone(monkeypatch, user, api, habit):
    """At 20:00 UTC on the 20th it's already the 21st in Kathmandu."""
    check_in(habit, 20, 21)
    set_now(monkeypatch, datetime(2026, 11, 20, 20, 0, tzinfo=dt_timezone.utc))

    body = api.get(stats_url(habit)).json()

    assert body["today"] == "2026-11-21"
    assert body["done_today"] is True
    assert body["current_streak"] == 2


def test_archived_habits_still_have_stats(monkeypatch, user, api):
    habit = make_habit(monkeypatch, user, archived=True)

    assert api.get(stats_url(habit)).status_code == 200


def test_other_peoples_stats_are_404(monkeypatch, api):
    other = make_habit(monkeypatch, make_user("other"))

    assert api.get(stats_url(other)).status_code == 404


@pytest.mark.django_db
def test_stats_endpoint_is_in_the_api_docs():
    paths = APIClient().get(reverse("schema"), {"format": "json"}).json()["paths"]

    assert "get" in paths["/api/habits/{id}/stats/"]
