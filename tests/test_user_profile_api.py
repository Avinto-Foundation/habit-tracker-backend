"""Someone's profile (GET /api/users/<username>/) and habit privacy (`visibility`)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.google import unique_username_from_email
from friends.models import Friendship
from habits.models import CheckIn, Habit

User = get_user_model()
KTM = ZoneInfo("Asia/Kathmandu")
CREATED = datetime(2026, 11, 1, 9, 0, tzinfo=KTM)  # a Sunday
NOW = datetime(2026, 11, 27, 18, 0, tzinfo=KTM)  # Friday evening in Kathmandu
TODAY = date(2026, 11, 27)


def set_now(monkeypatch, moment):
    monkeypatch.setattr(timezone, "now", lambda: moment)


def make_user(username, full_name=None, **fields):
    return User.objects.create_user(
        email=f"{username}@example.com",
        username=username,
        full_name=full_name or username.title(),
        password="x-Strong-pass-1",
        timezone="Asia/Kathmandu",
        **fields,
    )


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def profile_url(username):
    return reverse("user-profile", args=[username])


def befriend(a, b):
    return Friendship.objects.create(
        from_user=a, to_user=b, status=Friendship.Status.ACCEPTED, accepted_at=timezone.now()
    )


def make_habit(monkeypatch, owner, **fields):
    set_now(monkeypatch, CREATED)
    habit = Habit.objects.create(owner=owner, **fields)
    set_now(monkeypatch, NOW)
    return habit


def check_in(habit, *days):
    for day in days:
        CheckIn.objects.create(habit=habit, date=day, note="secret note")


@pytest.fixture
def sam(db):
    return make_user("sam", "Sam Adhikari")


@pytest.fixture
def aarav(db):
    return make_user("aarav", "Aarav Shrestha", bio="Running every morning")


@pytest.fixture
def as_sam(sam):
    return client_for(sam)


# --- The card: everyone sees it --------------------------------------------------


def test_login_is_required(aarav):
    response = APIClient().get(profile_url("aarav"))

    assert response.status_code == 401


def test_a_stranger_sees_the_card_but_no_habits(monkeypatch, as_sam, aarav):
    make_habit(monkeypatch, aarav, name="Run")

    response = as_sam.get(profile_url("aarav"))

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "aarav"
    assert body["full_name"] == "Aarav Shrestha"
    assert body["bio"] == "Running every morning"
    assert body["avatar"] is None
    assert body["date_joined"]
    assert body["friendship_status"] == "none"
    assert body["friendship_id"] is None
    assert body["habits"] is None


def test_private_details_are_never_shown(as_sam, aarav):
    body = as_sam.get(profile_url("aarav")).json()

    assert "email" not in body
    assert "timezone" not in body
    assert "id" not in body


def test_username_is_not_case_sensitive(as_sam, aarav):
    response = as_sam.get(profile_url("AARAV"))

    assert response.status_code == 200
    assert response.json()["username"] == "aarav"


def test_unknown_user_gives_404(as_sam):
    assert as_sam.get(profile_url("nobody")).status_code == 404


def test_deactivated_user_gives_404(as_sam, aarav):
    aarav.is_active = False
    aarav.save()

    assert as_sam.get(profile_url("aarav")).status_code == 404


@pytest.mark.parametrize(
    "who_asked, expected", [("sam", "request_sent"), ("aarav", "request_received")]
)
def test_pending_requests_show_no_habits(monkeypatch, as_sam, sam, aarav, who_asked, expected):
    make_habit(monkeypatch, aarav, name="Run")
    sender, receiver = (sam, aarav) if who_asked == "sam" else (aarav, sam)
    request = Friendship.objects.create(from_user=sender, to_user=receiver)

    body = as_sam.get(profile_url("aarav")).json()

    assert body["friendship_status"] == expected
    assert body["friendship_id"] == request.pk
    assert body["habits"] is None


# --- Friends see shared habits --------------------------------------------------


def test_a_friend_sees_shared_habits_with_streaks(monkeypatch, as_sam, sam, aarav):
    friendship = befriend(aarav, sam)
    run = make_habit(
        monkeypatch, aarav, name="Run", target="5 km", icon="ðŸƒ", color="#B45309"
    )
    check_in(run, TODAY - timedelta(days=2), TODAY - timedelta(days=1), TODAY)

    body = as_sam.get(profile_url("aarav")).json()

    assert body["friendship_status"] == "friends"
    assert body["friendship_id"] == friendship.pk
    assert body["habits"] == [
        {
            "habit": {
                "id": run.pk,
                "name": "Run",
                "target": "5 km",
                "icon": "ðŸƒ",
                "color": "#B45309",
                "schedule_type": "daily",
                "weekdays": [],
                "times_per_week": None,
            },
            "current_streak": 3,
            "longest_streak": 3,
            "streak_unit": "days",
            "done_today": True,
            "week_progress": None,
        }
    ]


def test_check_in_notes_are_never_shown(monkeypatch, as_sam, sam, aarav):
    befriend(sam, aarav)
    check_in(make_habit(monkeypatch, aarav, name="Run"), TODAY)

    response = as_sam.get(profile_url("aarav"))

    assert "secret note" not in response.content.decode()


def test_private_habits_are_hidden_from_friends(monkeypatch, as_sam, sam, aarav):
    befriend(sam, aarav)
    make_habit(monkeypatch, aarav, name="Run")
    make_habit(monkeypatch, aarav, name="Therapy", visibility=Habit.Visibility.PRIVATE)

    habits = as_sam.get(profile_url("aarav")).json()["habits"]

    assert [h["habit"]["name"] for h in habits] == ["Run"]


def test_archived_habits_are_hidden(monkeypatch, as_sam, sam, aarav):
    befriend(sam, aarav)
    make_habit(monkeypatch, aarav, name="Old", archived=True)

    assert as_sam.get(profile_url("aarav")).json()["habits"] == []


def test_a_friend_with_nothing_shared_gets_an_empty_list(as_sam, sam, aarav):
    befriend(sam, aarav)

    assert as_sam.get(profile_url("aarav")).json()["habits"] == []


def test_weekly_habit_shows_week_progress(monkeypatch, as_sam, sam, aarav):
    befriend(sam, aarav)
    gym = make_habit(
        monkeypatch, aarav, name="Gym", schedule_type="times_per_week", times_per_week=3
    )
    check_in(gym, date(2026, 11, 24), date(2026, 11, 25))  # Tue, Wed this week

    habit = as_sam.get(profile_url("aarav")).json()["habits"][0]

    assert habit["streak_unit"] == "weeks"
    assert habit["week_progress"] == {"done": 2, "goal": 3}
    assert habit["done_today"] is False


def test_done_today_uses_the_owners_time_zone(monkeypatch, as_sam, sam, aarav):
    """At 01:00 Saturday in Kathmandu it's still Friday in New York."""
    aarav.timezone = "America/New_York"
    aarav.save()
    befriend(sam, aarav)
    run = make_habit(monkeypatch, aarav, name="Run")
    check_in(run, TODAY)  # Friday, Aarav's today
    set_now(monkeypatch, datetime(2026, 11, 28, 1, 0, tzinfo=KTM))

    habit = as_sam.get(profile_url("aarav")).json()["habits"][0]

    assert habit["done_today"] is True


def test_after_unfriending_habits_are_hidden_again(monkeypatch, as_sam, sam, aarav):
    friendship = befriend(sam, aarav)
    make_habit(monkeypatch, aarav, name="Run")
    friendship.delete()

    assert as_sam.get(profile_url("aarav")).json()["habits"] is None


def test_query_count_does_not_grow_with_habits(
    monkeypatch, as_sam, sam, aarav, django_assert_max_num_queries
):
    befriend(sam, aarav)
    for name in ["Run", "Read", "Gym", "Sleep", "Water"]:
        check_in(make_habit(monkeypatch, aarav, name=name), TODAY)

    with django_assert_max_num_queries(5):
        as_sam.get(profile_url("aarav"))


# --- Your own profile -------------------------------------------------------------


def test_own_profile_shows_what_friends_see(monkeypatch, as_sam, sam):
    make_habit(monkeypatch, sam, name="Read")
    make_habit(monkeypatch, sam, name="Journal", visibility=Habit.Visibility.PRIVATE)

    body = as_sam.get(profile_url("sam")).json()

    assert body["friendship_status"] == "self"
    assert body["friendship_id"] is None
    assert [h["habit"]["name"] for h in body["habits"]] == ["Read"]


# --- Habit visibility setting ----------------------------------------------------


def test_new_habits_are_shared_with_friends_by_default(as_sam):
    response = as_sam.post(reverse("habit-list"), {"name": "Read"}, format="json")

    assert response.status_code == 201
    assert response.json()["visibility"] == "friends"


def test_a_habit_can_be_created_private(as_sam):
    response = as_sam.post(
        reverse("habit-list"), {"name": "Journal", "visibility": "private"}, format="json"
    )

    assert response.json()["visibility"] == "private"


def test_visibility_can_be_changed(monkeypatch, as_sam, sam):
    habit = make_habit(monkeypatch, sam, name="Read")

    response = as_sam.patch(
        reverse("habit-detail", args=[habit.pk]), {"visibility": "private"}, format="json"
    )

    assert response.status_code == 200
    habit.refresh_from_db()
    assert habit.visibility == Habit.Visibility.PRIVATE


def test_unknown_visibility_is_refused(as_sam):
    response = as_sam.post(
        reverse("habit-list"), {"name": "Read", "visibility": "public"}, format="json"
    )

    assert response.status_code == 400
    assert "visibility" in response.json()


# --- Reserved usernames (they're words in the URLs) -------------------------------


@pytest.mark.parametrize("username", ["search", "Search", "admin"])
@pytest.mark.django_db
def test_reserved_usernames_cannot_be_taken(username):
    response = APIClient().post(
        reverse("register"),
        {
            "full_name": "Test Person",
            "username": username,
            "email": "test@example.com",
            "password": "my-Strong-pass-1",
            "password_confirm": "my-Strong-pass-1",
            "timezone": "Asia/Kathmandu",
        },
        format="json",
    )

    assert response.status_code == 400
    assert response.json()["username"] == ["This username isn't available. Try another one."]


def test_reserved_username_cannot_be_chosen_later(as_sam):
    response = as_sam.patch(reverse("me"), {"username": "search"}, format="json")

    assert response.status_code == 400


@pytest.mark.django_db
def test_google_sign_in_skips_reserved_usernames():
    assert unique_username_from_email("search@gmail.com") == "search2"


def test_search_still_works(as_sam, aarav):
    response = as_sam.get(reverse("user-search"), {"q": "aar"})

    assert response.status_code == 200
    assert [u["username"] for u in response.json()] == ["aarav"]
