import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.urls import reverse

from habits.models import Habit

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="sam@example.com", username="sam", full_name="Sam", password="x-Strong-pass-1"
    )


def test_defaults_and_str(user):
    habit = Habit.objects.create(owner=user, name="Read")

    assert habit.icon == "✅"
    assert habit.color == "#0F766E"
    assert habit.schedule_type == Habit.Schedule.DAILY
    assert habit.weekdays == []
    assert habit.times_per_week is None
    assert habit.archived is False
    assert str(habit) == "✅ Read"


def test_valid_habits_pass_full_clean(user):
    Habit(owner=user, name="Read", icon="🏃‍♀️").full_clean()
    Habit(owner=user, name="Gym", schedule_type="weekdays", weekdays=[0, 2]).full_clean()
    Habit(owner=user, name="Run", schedule_type="times_per_week", times_per_week=3).full_clean()


@pytest.mark.parametrize(
    "fields, bad_field",
    [
        ({"schedule_type": "weekdays", "weekdays": []}, "weekdays"),
        ({"schedule_type": "weekdays", "weekdays": [9]}, "weekdays"),
        ({"schedule_type": "weekdays", "weekdays": "mon"}, "weekdays"),
        ({"schedule_type": "times_per_week"}, "times_per_week"),
        ({"schedule_type": "times_per_week", "times_per_week": 8}, "times_per_week"),
        ({"weekdays": [1]}, "weekdays"),
        ({"times_per_week": 2}, "times_per_week"),
        ({"icon": "abc"}, "icon"),
        ({"color": "red"}, "color"),
    ],
)
def test_full_clean_rejects_bad_habits(user, fields, bad_field):
    with pytest.raises(ValidationError) as error:
        Habit(owner=user, name="Habit", **fields).full_clean()

    assert bad_field in error.value.message_dict


def test_database_blocks_times_per_week_out_of_range(user):
    with pytest.raises(IntegrityError):
        Habit.objects.create(owner=user, name="Run", schedule_type="times_per_week", times_per_week=9)


def test_deleting_a_user_deletes_their_habits(user):
    Habit.objects.create(owner=user, name="Read")

    user.delete()

    assert not Habit.objects.exists()


# --- Admin ---------------------------------------------------------------------


@pytest.fixture
def admin_client(client, db):
    admin = User.objects.create_superuser(
        email="admin@example.com", username="admin", full_name="Admin", password="x-Strong-pass-1"
    )
    client.force_login(admin)
    return client


def test_admin_habit_pages_load(admin_client, user):
    habit = Habit.objects.create(owner=user, name="Read")

    assert admin_client.get(reverse("admin:habits_habit_changelist")).status_code == 200
    assert admin_client.get(reverse("admin:habits_habit_add")).status_code == 200
    assert admin_client.get(reverse("admin:habits_habit_change", args=[habit.pk])).status_code == 200
