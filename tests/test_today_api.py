from datetime import date, datetime, timezone as dt_timezone
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from habits.models import CheckIn, Habit
from habits.streaks import is_due_today, week_progress

User = get_user_model()
URL = reverse("habit-today")

# "Now": Friday 20 Nov 2026, 06:00 UTC (11:45 the same day in Kathmandu).
# This week runs Monday 16 to Sunday 22 Nov.
NOW = datetime(2026, 11, 20, 6, 0, tzinfo=dt_timezone.utc)
CREATED = datetime(2026, 11, 2, 6, 0, tzinfo=dt_timezone.utc)
MON, WED, FRI = 0, 2, 4


def nov(day: int) -> date:
    return date(2026, 11, day)


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


@pytest.fixture
def user(db):
    return make_user("sam")


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def make_habit(monkeypatch, user):
    """make_habit(name, checkins=[days of Nov], **fields): a habit created on 2 Nov."""

    def make(name, checkins=(), owner=None, **fields):
        set_now(monkeypatch, CREATED)
        habit = Habit.objects.create(owner=owner or user, name=name, **fields)
        set_now(monkeypatch, NOW)
        for day in checkins:
            CheckIn.objects.create(habit=habit, date=nov(day))
        return habit

    return make


def names(entries) -> list[str]:
    return [entry["habit"]["name"] for entry in entries]


# --- Endpoint -------------------------------------------------------------------------


def test_today_needs_login(db):
    assert APIClient().get(URL).status_code == 401


def test_new_user_has_an_empty_today(api):
    response = api.get(URL)

    assert response.status_code == 200
    assert response.json() == {
        "date": "2026-11-20",
        "summary": {"done": 0, "total": 0},
        "due": [],
        "not_due": [],
    }


def test_which_habits_are_due_today(api, make_habit):
    make_habit("Read", checkins=[18, 19, 20])
    make_habit("Water")
    make_habit("Gym Mon/Wed", schedule_type="weekdays", weekdays=[MON, WED])
    make_habit("Yoga Fri", schedule_type="weekdays", weekdays=[FRI])
    make_habit("Run 2x, met", checkins=[16, 17], schedule_type="times_per_week", times_per_week=2)
    make_habit("Swim 2x, 1 so far", checkins=[17], schedule_type="times_per_week", times_per_week=2)
    make_habit("Call 2x, done today", checkins=[16, 20], schedule_type="times_per_week", times_per_week=2)
    make_habit("Old", archived=True)

    body = api.get(URL).json()

    assert names(body["due"]) == [
        "Read",
        "Water",
        "Yoga Fri",
        "Swim 2x, 1 so far",
        "Call 2x, done today",
    ]
    assert names(body["not_due"]) == ["Gym Mon/Wed", "Run 2x, met"]
    assert body["summary"] == {"done": 2, "total": 5}  # Read + Call


def test_each_entry_has_status_streak_and_check_in(api, make_habit):
    habit = make_habit("Read", icon="📚", target="20 pages", checkins=[18, 19])
    CheckIn.objects.create(habit=habit, date=nov(20), note="On the bus")

    entry = api.get(URL).json()["due"][0]

    assert entry["habit"]["id"] == habit.id
    assert entry["habit"]["icon"] == "📚"
    assert entry["habit"]["target"] == "20 pages"
    assert entry["done_today"] is True
    assert entry["checkin"]["note"] == "On the bus"
    assert entry["checkin"]["date"] == "2026-11-20"
    assert entry["current_streak"] == 3
    assert entry["streak_unit"] == "days"
    assert entry["week_progress"] is None


def test_not_done_entry(api, make_habit):
    make_habit("Water", checkins=[19])

    entry = api.get(URL).json()["due"][0]

    assert entry["done_today"] is False
    assert entry["checkin"] is None
    assert entry["current_streak"] == 1  # today isn't missed yet


def test_weekly_entry_has_week_progress(api, make_habit):
    make_habit("Swim", checkins=[2, 3, 9, 10, 17], schedule_type="times_per_week", times_per_week=2)

    entry = api.get(URL).json()["due"][0]

    assert entry["streak_unit"] == "weeks"
    assert entry["current_streak"] == 2
    assert entry["week_progress"] == {"done": 1, "goal": 2}


def test_other_peoples_habits_are_not_shown(api, make_habit):
    make_habit("Mine")
    make_habit("Theirs", owner=make_user("other"))

    body = api.get(URL).json()

    assert names(body["due"]) == ["Mine"]


def test_today_uses_the_users_time_zone(monkeypatch, api, make_habit):
    """At 20:00 UTC on Friday the 20th it is already Saturday the 21st in Kathmandu."""
    make_habit("Yoga Fri", schedule_type="weekdays", weekdays=[FRI])
    make_habit("Hike Sat", schedule_type="weekdays", weekdays=[5])
    set_now(monkeypatch, datetime(2026, 11, 20, 20, 0, tzinfo=dt_timezone.utc))

    body = api.get(URL).json()

    assert body["date"] == "2026-11-21"
    assert names(body["due"]) == ["Hike Sat"]


def test_number_of_queries_does_not_grow_with_habits(api, make_habit, django_assert_num_queries):
    for n in range(10):
        make_habit(f"Habit {n}", checkins=[18, 19, 20])

    with django_assert_num_queries(2):  # 1 for habits + 1 for all their check-ins
        response = api.get(URL)

    assert len(response.json()["due"]) == 10


def test_today_is_not_mistaken_for_a_habit_id(api):
    """/habits/today/ must reach the Today view, not "habit with id 'today'"."""
    assert api.get("/api/habits/today/").status_code == 200


@pytest.mark.django_db
def test_today_endpoint_is_in_the_api_docs():
    paths = APIClient().get(reverse("schema"), {"format": "json"}).json()["paths"]

    assert "get" in paths["/api/habits/today/"]


# --- Logic (no database) --------------------------------------------------------------


def habit(schedule_type="daily", weekdays=(), times_per_week=None):
    return SimpleNamespace(
        schedule_type=schedule_type, weekdays=list(weekdays), times_per_week=times_per_week
    )


def test_week_progress_counts_this_week_only():
    weekly = habit("times_per_week", times_per_week=3)

    assert week_progress(weekly, {nov(15), nov(16), nov(18)}, nov(2), nov(20)) == {
        "done": 2,
        "goal": 3,
    }


def test_week_progress_goal_in_the_first_week():
    weekly = habit("times_per_week", times_per_week=3)

    assert week_progress(weekly, set(), nov(21), nov(21))["goal"] == 2  # Sat: 2 days left


@pytest.mark.parametrize(
    "the_habit, done, expected",
    [
        (habit(), set(), True),
        (habit("weekdays", [FRI]), set(), True),
        (habit("weekdays", [MON]), set(), False),
        (habit("weekdays", [MON]), {nov(20)}, False),  # bonus today: still not "due"
        (habit("times_per_week", times_per_week=2), {nov(16)}, True),
        (habit("times_per_week", times_per_week=2), {nov(16), nov(17)}, False),
        (habit("times_per_week", times_per_week=2), {nov(16), nov(20)}, True),
    ],
)
def test_is_due_today(the_habit, done, expected):
    assert is_due_today(the_habit, done, nov(2), nov(20)) is expected
