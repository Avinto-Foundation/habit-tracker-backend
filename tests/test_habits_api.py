import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from habits.models import Habit

User = get_user_model()
LIST_URL = reverse("habit-list")


def detail_url(habit: Habit) -> str:
    return reverse("habit-detail", args=[habit.id])


def make_user(name: str):
    return User.objects.create_user(
        email=f"{name}@example.com", username=name, full_name=name.title(), password="x-Strong-pass-1"
    )


def client_for(user) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    return client


@pytest.fixture
def user(db):
    return make_user("sam")


@pytest.fixture
def api(user):
    """A client logged in as `user`."""
    return client_for(user)


@pytest.fixture
def other_habit(db):
    """A habit that belongs to someone else."""
    return Habit.objects.create(owner=make_user("other"), name="Not yours")


# --- Login required ------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["get", "post"])
def test_list_and_create_need_login(method):
    response = getattr(APIClient(), method)(LIST_URL, {}, format="json")

    assert response.status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_detail_needs_login(method, other_habit):
    response = getattr(APIClient(), method)(detail_url(other_habit), {}, format="json")

    assert response.status_code == 401


# --- Create ----------------------------------------------------------------------


def test_create_with_only_a_name_uses_defaults(user, api):
    response = api.post(LIST_URL, {"name": "Drink water"}, format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Drink water"
    assert body["target"] == ""
    assert body["icon"] == "✅"
    assert body["color"] == "#0F766E"
    assert body["schedule_type"] == "daily"
    assert body["weekdays"] == []
    assert body["times_per_week"] is None
    assert body["archived"] is False
    assert {"id", "created_at", "updated_at"} <= body.keys()
    assert Habit.objects.get(id=body["id"]).owner == user


def test_create_full_habit(api):
    response = api.post(
        LIST_URL,
        {"name": "  Read  ", "target": "20 pages", "icon": "📚", "color": "#b45309"},
        format="json",
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Read"  # spaces trimmed
    assert body["target"] == "20 pages"
    assert body["icon"] == "📚"
    assert body["color"] == "#B45309"  # saved in capitals


def test_create_ignores_owner_and_read_only_fields(user, api, other_habit):
    response = api.post(
        LIST_URL,
        {"name": "Mine", "owner": other_habit.owner.id, "id": 999, "created_at": "2000-01-01"},
        format="json",
    )

    assert response.status_code == 201
    habit = Habit.objects.get(id=response.json()["id"])
    assert habit.owner == user
    assert habit.id != 999


def test_create_weekdays_schedule_sorts_and_dedupes_days(api):
    response = api.post(
        LIST_URL,
        {"name": "Gym", "schedule_type": "weekdays", "weekdays": [4, 0, 2, 0]},
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["weekdays"] == [0, 2, 4]


@pytest.mark.parametrize("times", [1, 7])
def test_create_times_per_week_schedule(api, times):
    response = api.post(
        LIST_URL,
        {"name": "Run", "schedule_type": "times_per_week", "times_per_week": times},
        format="json",
    )

    assert response.status_code == 201
    assert response.json()["times_per_week"] == times


@pytest.mark.parametrize(
    "data, field",
    [
        ({}, "name"),
        ({"name": ""}, "name"),
        ({"name": "   "}, "name"),
        ({"name": "x" * 81}, "name"),
        ({"name": "Read", "target": "x" * 81}, "target"),
        ({"name": "Read", "icon": "book"}, "icon"),
        ({"name": "Read", "icon": "📚 1"}, "icon"),
        ({"name": "Read", "icon": ""}, "icon"),
        ({"name": "Read", "color": "teal"}, "color"),
        ({"name": "Read", "color": "#12345"}, "color"),
        ({"name": "Read", "schedule_type": "monthly"}, "schedule_type"),
        # "specific days" needs days, and only valid day numbers
        ({"name": "Gym", "schedule_type": "weekdays"}, "weekdays"),
        ({"name": "Gym", "schedule_type": "weekdays", "weekdays": []}, "weekdays"),
        ({"name": "Gym", "schedule_type": "weekdays", "weekdays": [7]}, "weekdays"),
        ({"name": "Gym", "schedule_type": "weekdays", "weekdays": [-1]}, "weekdays"),
        ({"name": "Gym", "schedule_type": "weekdays", "weekdays": ["mon"]}, "weekdays"),
        # "times per week" needs a count from 1 to 7
        ({"name": "Run", "schedule_type": "times_per_week"}, "times_per_week"),
        ({"name": "Run", "schedule_type": "times_per_week", "times_per_week": 0}, "times_per_week"),
        ({"name": "Run", "schedule_type": "times_per_week", "times_per_week": 8}, "times_per_week"),
        # extra bits that don't belong to the chosen schedule
        ({"name": "Read", "weekdays": [1]}, "weekdays"),
        ({"name": "Read", "times_per_week": 3}, "times_per_week"),
        (
            {"name": "Gym", "schedule_type": "weekdays", "weekdays": [1], "times_per_week": 2},
            "times_per_week",
        ),
    ],
)
def test_create_rejects_invalid_data(api, data, field):
    response = api.post(LIST_URL, data, format="json")

    assert response.status_code == 400
    assert field in response.json()
    assert not Habit.objects.exists()


# --- List ----------------------------------------------------------------------


def test_list_shows_only_my_active_habits_oldest_first(user, api, other_habit):
    first = Habit.objects.create(owner=user, name="First")
    second = Habit.objects.create(owner=user, name="Second")
    Habit.objects.create(owner=user, name="Old one", archived=True)

    response = api.get(LIST_URL)

    assert response.status_code == 200
    assert [h["id"] for h in response.json()] == [first.id, second.id]


def test_list_archived_true_shows_only_archived(user, api, other_habit):
    Habit.objects.create(owner=user, name="Active")
    old = Habit.objects.create(owner=user, name="Old one", archived=True)
    other_habit.archived = True
    other_habit.save()

    response = api.get(LIST_URL, {"archived": "true"})

    assert [h["id"] for h in response.json()] == [old.id]


def test_list_is_empty_for_a_new_user(api):
    response = api.get(LIST_URL)

    assert response.status_code == 200
    assert response.json() == []


# --- Get one -------------------------------------------------------------------


def test_get_my_habit(user, api):
    habit = Habit.objects.create(owner=user, name="Read", icon="📚")

    response = api.get(detail_url(habit))

    assert response.status_code == 200
    assert response.json()["name"] == "Read"
    assert response.json()["icon"] == "📚"


def test_get_my_archived_habit(user, api):
    habit = Habit.objects.create(owner=user, name="Old", archived=True)

    assert api.get(detail_url(habit)).status_code == 200


def test_unknown_habit_is_404(api):
    assert api.get(reverse("habit-detail", args=[123456])).status_code == 404


# --- Edit ------------------------------------------------------------------------


def test_patch_changes_only_the_fields_sent(user, api):
    habit = Habit.objects.create(owner=user, name="Read", target="10 pages", icon="📚")

    response = api.patch(detail_url(habit), {"target": "20 pages"}, format="json")

    assert response.status_code == 200
    habit.refresh_from_db()
    assert habit.target == "20 pages"
    assert habit.name == "Read"
    assert habit.icon == "📚"


def test_patch_archive_and_unarchive(user, api):
    habit = Habit.objects.create(owner=user, name="Read")

    api.patch(detail_url(habit), {"archived": True}, format="json")
    habit.refresh_from_db()
    assert habit.archived is True
    assert api.get(LIST_URL).json() == []

    api.patch(detail_url(habit), {"archived": False}, format="json")
    habit.refresh_from_db()
    assert habit.archived is False


def test_patch_switch_to_weekdays_needs_days(user, api):
    habit = Habit.objects.create(owner=user, name="Gym")

    response = api.patch(detail_url(habit), {"schedule_type": "weekdays"}, format="json")

    assert response.status_code == 400
    assert "weekdays" in response.json()


def test_patch_switch_to_weekdays_with_days(user, api):
    habit = Habit.objects.create(owner=user, name="Gym")

    response = api.patch(
        detail_url(habit), {"schedule_type": "weekdays", "weekdays": [0, 1]}, format="json"
    )

    assert response.status_code == 200
    habit.refresh_from_db()
    assert (habit.schedule_type, habit.weekdays) == ("weekdays", [0, 1])


def test_patch_switching_schedule_drops_old_days(user, api):
    habit = Habit.objects.create(owner=user, name="Gym", schedule_type="weekdays", weekdays=[0, 2])

    response = api.patch(detail_url(habit), {"schedule_type": "daily"}, format="json")

    assert response.status_code == 200
    habit.refresh_from_db()
    assert (habit.schedule_type, habit.weekdays, habit.times_per_week) == ("daily", [], None)


def test_patch_switching_schedule_drops_old_count(user, api):
    habit = Habit.objects.create(
        owner=user, name="Run", schedule_type="times_per_week", times_per_week=3
    )

    response = api.patch(
        detail_url(habit), {"schedule_type": "weekdays", "weekdays": [5]}, format="json"
    )

    assert response.status_code == 200
    habit.refresh_from_db()
    assert (habit.weekdays, habit.times_per_week) == ([5], None)


def test_patch_days_keeps_weekdays_schedule(user, api):
    habit = Habit.objects.create(owner=user, name="Gym", schedule_type="weekdays", weekdays=[0])

    response = api.patch(detail_url(habit), {"weekdays": [6, 3]}, format="json")

    assert response.status_code == 200
    assert response.json()["weekdays"] == [3, 6]


def test_patch_days_on_a_daily_habit_is_rejected(user, api):
    habit = Habit.objects.create(owner=user, name="Read")

    response = api.patch(detail_url(habit), {"weekdays": [1]}, format="json")

    assert response.status_code == 400
    assert "weekdays" in response.json()


def test_patch_cannot_empty_the_days(user, api):
    habit = Habit.objects.create(owner=user, name="Gym", schedule_type="weekdays", weekdays=[0])

    response = api.patch(detail_url(habit), {"weekdays": []}, format="json")

    assert response.status_code == 400


def test_patch_cannot_change_owner(user, api, other_habit):
    habit = Habit.objects.create(owner=user, name="Read")

    api.patch(detail_url(habit), {"owner": other_habit.owner.id}, format="json")

    habit.refresh_from_db()
    assert habit.owner == user


def test_put_is_not_allowed(user, api):
    habit = Habit.objects.create(owner=user, name="Read")

    response = api.put(detail_url(habit), {"name": "New"}, format="json")

    assert response.status_code == 405


# --- Delete ------------------------------------------------------------------------


def test_delete_my_habit(user, api):
    habit = Habit.objects.create(owner=user, name="Read")

    response = api.delete(detail_url(habit))

    assert response.status_code == 204
    assert not Habit.objects.filter(id=habit.id).exists()


# --- Other people's habits ----------------------------------------------------------


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_other_peoples_habits_are_404(api, other_habit, method):
    response = getattr(api, method)(detail_url(other_habit), {"name": "Hacked"}, format="json")

    assert response.status_code == 404
    other_habit.refresh_from_db()
    assert other_habit.name == "Not yours"


# --- Docs ------------------------------------------------------------------------------


@pytest.mark.django_db
def test_habit_endpoints_are_in_the_api_docs():
    paths = APIClient().get(reverse("schema"), {"format": "json"}).json()["paths"]

    assert set(paths["/api/habits/"]) >= {"get", "post"}
    assert set(paths["/api/habits/{id}/"]) >= {"get", "patch", "delete"}
    assert "put" not in paths["/api/habits/{id}/"]
