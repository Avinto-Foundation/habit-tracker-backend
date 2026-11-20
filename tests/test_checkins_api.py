from datetime import date, datetime, timezone as dt_timezone

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from habits.dates import user_today
from habits.models import CheckIn, Habit

User = get_user_model()

# "Now" in these tests: 20 Nov 2026, 06:00 UTC = 11:45 the same day in Kathmandu.
NOW = datetime(2026, 11, 20, 6, 0, tzinfo=dt_timezone.utc)
TODAY = date(2026, 11, 20)
YESTERDAY = date(2026, 11, 19)
LONG_AGO = datetime(2026, 11, 1, 6, 0, tzinfo=dt_timezone.utc)


def set_now(monkeypatch, moment: datetime) -> None:
    """Pretend the current time is `moment` (for the code and for auto_now fields)."""
    monkeypatch.setattr(timezone, "now", lambda: moment)


def make_user(name: str, tz: str = "Asia/Kathmandu"):
    return User.objects.create_user(
        email=f"{name}@example.com",
        username=name,
        full_name=name.title(),
        password="x-Strong-pass-1",
        timezone=tz,
    )


def make_habit(monkeypatch, owner, created=LONG_AGO, **fields) -> Habit:
    """A habit created at `created`, with the clock then set back to NOW."""
    set_now(monkeypatch, created)
    habit = Habit.objects.create(owner=owner, name=fields.pop("name", "Read"), **fields)
    set_now(monkeypatch, NOW)
    return habit


def logged_in(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client


def checkins_url(habit_or_id) -> str:
    return reverse("habit-checkins", args=[getattr(habit_or_id, "id", habit_or_id)])


def checkin_url(habit, day) -> str:
    return f"{checkins_url(habit)}{day}/"


@pytest.fixture
def user(db):
    return make_user("sam")


@pytest.fixture
def api(user):
    return logged_in(user)


@pytest.fixture
def habit(monkeypatch, user):
    return make_habit(monkeypatch, user)


@pytest.fixture
def other_habit(monkeypatch, db):
    return make_habit(monkeypatch, make_user("other"), name="Not yours")


# --- Login required ------------------------------------------------------------


def test_checkins_need_login(habit):
    client = APIClient()

    assert client.get(checkins_url(habit)).status_code == 401
    assert client.post(checkins_url(habit), {}, format="json").status_code == 401
    assert client.patch(checkin_url(habit, TODAY), {}, format="json").status_code == 401
    assert client.delete(checkin_url(habit, TODAY)).status_code == 401


# --- Check in -------------------------------------------------------------------


def test_check_in_today_by_default(api, habit):
    response = api.post(checkins_url(habit), {}, format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["date"] == "2026-11-20"
    assert body["habit"] == habit.id
    assert body["note"] == ""
    assert {"id", "created_at"} <= body.keys()
    assert CheckIn.objects.filter(habit=habit, date=TODAY).exists()


def test_check_in_yesterday_with_a_note(api, habit):
    response = api.post(
        checkins_url(habit), {"date": "2026-11-19", "note": "  Read on the bus  "}, format="json"
    )

    assert response.status_code == 201
    assert response.json()["date"] == "2026-11-19"
    assert response.json()["note"] == "Read on the bus"


def test_today_uses_the_users_time_zone(monkeypatch, db):
    """20 Nov 20:00 UTC is already 21 Nov 01:45 in Kathmandu, but still 20 Nov in London."""
    nepal = make_user("nepal", tz="Asia/Kathmandu")
    london = make_user("london", tz="Europe/London")
    nepal_habit = make_habit(monkeypatch, nepal)
    london_habit = make_habit(monkeypatch, london)
    set_now(monkeypatch, datetime(2026, 11, 20, 20, 0, tzinfo=dt_timezone.utc))

    nepal_day = logged_in(nepal).post(checkins_url(nepal_habit), {}, format="json")
    london_day = logged_in(london).post(checkins_url(london_habit), {}, format="json")

    assert nepal_day.json()["date"] == "2026-11-21"
    assert london_day.json()["date"] == "2026-11-20"


def test_checking_in_twice_does_not_duplicate(api, habit):
    first = api.post(checkins_url(habit), {"note": "first"}, format="json")
    second = api.post(checkins_url(habit), {}, format="json")

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["note"] == "first"  # no note sent: the old note stays
    assert CheckIn.objects.count() == 1


def test_checking_in_again_with_a_note_replaces_it(api, habit):
    api.post(checkins_url(habit), {"note": "first"}, format="json")

    response = api.post(checkins_url(habit), {"note": "second"}, format="json")

    assert response.status_code == 200
    assert CheckIn.objects.get().note == "second"


@pytest.mark.parametrize(
    "data",
    [
        {"date": "2026-11-18"},  # 2 days ago
        {"date": "2026-11-21"},  # tomorrow
        {"date": "2025-11-20"},  # a year ago
    ],
)
def test_only_today_or_yesterday(api, habit, data):
    response = api.post(checkins_url(habit), data, format="json")

    assert response.status_code == 400
    assert response.json()["date"] == ["You can only check in for today or yesterday."]
    assert not CheckIn.objects.exists()


@pytest.mark.parametrize(
    "data, field",
    [
        ({"date": "20-11-2026"}, "date"),
        ({"date": "2026-02-30"}, "date"),
        ({"note": "x" * 281}, "note"),
    ],
)
def test_check_in_rejects_bad_input(api, habit, data, field):
    response = api.post(checkins_url(habit), data, format="json")

    assert response.status_code == 400
    assert field in response.json()


def test_note_can_be_280_characters(api, habit):
    response = api.post(checkins_url(habit), {"note": "x" * 280}, format="json")

    assert response.status_code == 201


def test_cannot_check_in_before_the_habit_existed(monkeypatch, user, api):
    new_habit = make_habit(monkeypatch, user, created=NOW)  # created today

    response = api.post(checkins_url(new_habit), {"date": "2026-11-19"}, format="json")

    assert response.status_code == 400
    assert response.json()["date"] == ["That's before you created this habit."]


def test_cannot_check_in_an_archived_habit(monkeypatch, user, api):
    archived = make_habit(monkeypatch, user, archived=True)

    response = api.post(checkins_url(archived), {}, format="json")

    assert response.status_code == 400
    assert "habit" in response.json()


def test_bonus_check_in_on_an_unscheduled_day_is_allowed(monkeypatch, user, api):
    """20 Nov 2026 is a Friday; the habit is only for Mon (0) and Wed (2)."""
    gym = make_habit(monkeypatch, user, schedule_type="weekdays", weekdays=[0, 2])

    response = api.post(checkins_url(gym), {}, format="json")

    assert response.status_code == 201


# --- Other people's / unknown habits ------------------------------------------------


def test_other_peoples_habits_are_404(api, other_habit):
    CheckIn.objects.create(habit=other_habit, date=TODAY, note="secret")

    assert api.get(checkins_url(other_habit)).status_code == 404
    assert api.post(checkins_url(other_habit), {}, format="json").status_code == 404
    assert api.patch(checkin_url(other_habit, TODAY), {"note": "x"}, format="json").status_code == 404
    assert api.delete(checkin_url(other_habit, TODAY)).status_code == 404
    assert CheckIn.objects.get(habit=other_habit).note == "secret"


def test_unknown_habit_is_404(api):
    assert api.post(checkins_url(999999), {}, format="json").status_code == 404


# --- List --------------------------------------------------------------------------


def test_list_check_ins_oldest_first(api, habit, other_habit):
    CheckIn.objects.create(habit=habit, date=date(2026, 11, 10))
    CheckIn.objects.create(habit=habit, date=date(2026, 11, 5))
    CheckIn.objects.create(habit=other_habit, date=date(2026, 11, 6))

    response = api.get(checkins_url(habit))

    assert response.status_code == 200
    assert [c["date"] for c in response.json()] == ["2026-11-05", "2026-11-10"]


def test_list_filters_by_date_range(api, habit):
    for day in (1, 5, 10, 15):
        CheckIn.objects.create(habit=habit, date=date(2026, 11, day))

    response = api.get(checkins_url(habit), {"from": "2026-11-05", "to": "2026-11-10"})

    assert [c["date"] for c in response.json()] == ["2026-11-05", "2026-11-10"]
    only_from = api.get(checkins_url(habit), {"from": "2026-11-10"}).json()
    assert [c["date"] for c in only_from] == ["2026-11-10", "2026-11-15"]
    only_to = api.get(checkins_url(habit), {"to": "2026-11-01"}).json()
    assert [c["date"] for c in only_to] == ["2026-11-01"]


@pytest.mark.parametrize(
    "params, field",
    [
        ({"from": "2026-11-10", "to": "2026-11-01"}, "to"),
        ({"from": "yesterday"}, "from"),
    ],
)
def test_list_rejects_bad_ranges(api, habit, params, field):
    response = api.get(checkins_url(habit), params)

    assert response.status_code == 400
    assert field in response.json()


def test_list_works_for_archived_habits(monkeypatch, user, api):
    archived = make_habit(monkeypatch, user, archived=True)
    CheckIn.objects.create(habit=archived, date=date(2026, 11, 3))

    assert len(api.get(checkins_url(archived)).json()) == 1


# --- Edit note -----------------------------------------------------------------------


def test_edit_note(api, habit):
    CheckIn.objects.create(habit=habit, date=date(2026, 11, 3), note="old")

    response = api.patch(checkin_url(habit, "2026-11-03"), {"note": "new"}, format="json")

    assert response.status_code == 200
    assert response.json()["note"] == "new"
    assert CheckIn.objects.get().note == "new"


def test_edit_cannot_move_the_date(api, habit):
    CheckIn.objects.create(habit=habit, date=TODAY)

    api.patch(checkin_url(habit, TODAY), {"note": "x", "date": "2026-11-01"}, format="json")

    assert CheckIn.objects.get().date == TODAY


def test_edit_needs_a_note(api, habit):
    CheckIn.objects.create(habit=habit, date=TODAY)

    response = api.patch(checkin_url(habit, TODAY), {}, format="json")

    assert response.status_code == 400
    assert "note" in response.json()


def test_edit_missing_check_in_is_404(api, habit):
    assert api.patch(checkin_url(habit, TODAY), {"note": "x"}, format="json").status_code == 404


# --- Undo --------------------------------------------------------------------------------


@pytest.mark.parametrize("day", [TODAY, YESTERDAY])
def test_undo_today_or_yesterday(api, habit, day):
    CheckIn.objects.create(habit=habit, date=day)

    response = api.delete(checkin_url(habit, day))

    assert response.status_code == 204
    assert not CheckIn.objects.exists()


def test_cannot_undo_older_check_ins(api, habit):
    CheckIn.objects.create(habit=habit, date=date(2026, 11, 10))

    response = api.delete(checkin_url(habit, "2026-11-10"))

    assert response.status_code == 400
    assert "date" in response.json()
    assert CheckIn.objects.exists()


def test_undo_missing_check_in_is_404(api, habit):
    assert api.delete(checkin_url(habit, TODAY)).status_code == 404


@pytest.mark.parametrize("bad_day", ["2026-02-30", "not-a-date"])
def test_impossible_dates_in_the_url_are_404(api, habit, bad_day):
    assert api.delete(f"{checkins_url(habit)}{bad_day}/").status_code == 404


# --- Model, helpers, admin, docs ------------------------------------------------------------


def test_database_allows_one_check_in_per_habit_per_day(habit):
    CheckIn.objects.create(habit=habit, date=TODAY)

    with pytest.raises(IntegrityError):
        CheckIn.objects.create(habit=habit, date=TODAY)


def test_deleting_a_habit_deletes_its_check_ins(habit):
    CheckIn.objects.create(habit=habit, date=TODAY)

    habit.delete()

    assert not CheckIn.objects.exists()


def test_check_in_str(habit):
    assert str(CheckIn(habit=habit, date=TODAY)) == "✅ Read on 2026-11-20"


@pytest.mark.parametrize(
    "tz, expected",
    [
        ("UTC", date(2026, 11, 20)),
        ("Asia/Kathmandu", date(2026, 11, 21)),  # UTC+5:45
        ("America/Los_Angeles", date(2026, 11, 20)),  # UTC-8
        ("Pacific/Kiritimati", date(2026, 11, 21)),  # UTC+14
    ],
)
def test_user_today_per_time_zone(monkeypatch, tz, expected):
    set_now(monkeypatch, datetime(2026, 11, 20, 20, 0, tzinfo=dt_timezone.utc))

    assert user_today(User(timezone=tz)) == expected


def test_habit_created_on_uses_the_owners_time_zone(monkeypatch, user):
    late = make_habit(monkeypatch, user, created=datetime(2026, 11, 20, 20, 0, tzinfo=dt_timezone.utc))

    assert late.created_on() == date(2026, 11, 21)  # already the 21st in Kathmandu


def test_admin_check_in_pages_load(client, habit):
    admin = User.objects.create_superuser(
        email="admin@example.com", username="admin", full_name="Admin", password="x-Strong-pass-1"
    )
    client.force_login(admin)
    checkin = CheckIn.objects.create(habit=habit, date=TODAY)

    assert client.get(reverse("admin:habits_checkin_changelist")).status_code == 200
    assert client.get(reverse("admin:habits_checkin_add")).status_code == 200
    assert client.get(reverse("admin:habits_checkin_change", args=[checkin.pk])).status_code == 200


@pytest.mark.django_db
def test_check_in_endpoints_are_in_the_api_docs():
    paths = APIClient().get(reverse("schema"), {"format": "json"}).json()["paths"]

    assert set(paths["/api/habits/{habit_id}/checkins/"]) >= {"get", "post"}
    assert set(paths["/api/habits/{habit_id}/checkins/{date}/"]) >= {"patch", "delete"}
