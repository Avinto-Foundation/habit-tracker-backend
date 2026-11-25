from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

User = get_user_model()
URL = reverse("me")
PASSWORD = "my-Strong-pass-1"


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="sam@example.com",
        username="sam",
        full_name="Sam Adhikari",
        password=PASSWORD,
        timezone="Asia/Kathmandu",
    )


def client_with(token=None):
    """A test client that sends `Authorization: Bearer <token>` (or nothing)."""
    client = APIClient()
    if token is not None:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def logged_in(user):
    """A client logged in as `user` with a real access token."""
    return client_with(AccessToken.for_user(user))


# --- GET -----------------------------------------------------------------------


def test_get_me_returns_the_logged_in_user(user, logged_in):
    response = logged_in.get(URL)

    assert response.status_code == 200
    assert response.json() == {
        "id": user.id,
        "full_name": "Sam Adhikari",
        "username": "sam",
        "email": "sam@example.com",
        "timezone": "Asia/Kathmandu",
        "bio": "",
        "avatar": None,
        "date_joined": user.date_joined.isoformat().replace("+00:00", "Z"),
    }


def test_full_flow_login_then_me(user):
    """The real journey: log in, then use the access token from the response."""
    access = (
        APIClient()
        .post(reverse("login"), {"email": "sam@example.com", "password": PASSWORD}, format="json")
        .json()["access"]
    )

    response = client_with(access).get(URL)

    assert response.status_code == 200
    assert response.json()["email"] == "sam@example.com"


def test_each_user_only_sees_themselves(user):
    other = User.objects.create_user(
        email="other@example.com", username="other", full_name="Other", password=PASSWORD
    )

    response = client_with(AccessToken.for_user(other)).get(URL)

    assert response.json()["email"] == "other@example.com"


# --- Not logged in -------------------------------------------------------------


def test_no_token_gives_401(db):
    response = client_with().get(URL)

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication credentials were not provided."}


def test_garbage_token_gives_401(db):
    assert client_with("not-a-real-token").get(URL).status_code == 401


def test_expired_token_gives_401(user):
    token = AccessToken.for_user(user)
    token.set_exp(from_time=timezone.now() - timedelta(hours=1))

    assert client_with(token).get(URL).status_code == 401


def test_refresh_token_cannot_be_used_as_access_token(user):
    assert client_with(RefreshToken.for_user(user)).get(URL).status_code == 401


def test_inactive_user_gives_401(user, logged_in):
    user.is_active = False
    user.save()

    assert logged_in.get(URL).status_code == 401


def test_patch_without_token_gives_401(db):
    assert client_with().patch(URL, {"full_name": "X"}, format="json").status_code == 401


# --- PATCH ---------------------------------------------------------------------


def test_patch_updates_only_the_fields_sent(user, logged_in):
    response = logged_in.patch(URL, {"timezone": "Europe/London"}, format="json")

    assert response.status_code == 200
    assert response.json()["timezone"] == "Europe/London"
    user.refresh_from_db()
    assert user.timezone == "Europe/London"
    assert user.full_name == "Sam Adhikari"  # untouched


def test_patch_can_change_name_and_username(user, logged_in):
    response = logged_in.patch(
        URL, {"full_name": "  Samikshya A  ", "username": "samikshya"}, format="json"
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.full_name == "Samikshya A"
    assert user.username == "samikshya"


def test_can_keep_own_username_with_different_capitals(user, logged_in):
    response = logged_in.patch(URL, {"username": "Sam"}, format="json")

    assert response.status_code == 200
    assert response.json()["username"] == "Sam"


def test_username_taken_by_someone_else_is_rejected(user, logged_in):
    User.objects.create_user(
        email="other@example.com", username="taken", full_name="Other", password=PASSWORD
    )

    response = logged_in.patch(URL, {"username": "TAKEN"}, format="json")

    assert response.status_code == 400
    assert response.json()["username"] == ["This username is already taken."]


@pytest.mark.parametrize("username", ["ab", "has space", "bad-dash"])
def test_invalid_username_is_rejected(user, logged_in, username):
    response = logged_in.patch(URL, {"username": username}, format="json")

    assert response.status_code == 400
    assert "username" in response.json()


def test_fake_timezone_is_rejected(user, logged_in):
    response = logged_in.patch(URL, {"timezone": "Mars/Base"}, format="json")

    assert response.status_code == 400
    assert response.json()["timezone"] == ["'Mars/Base' is not a valid time zone."]


def test_blank_full_name_is_rejected(user, logged_in):
    response = logged_in.patch(URL, {"full_name": "   "}, format="json")

    assert response.status_code == 400
    assert "full_name" in response.json()


def test_email_and_id_cannot_be_changed(user, logged_in):
    response = logged_in.patch(URL, {"email": "hacker@example.com", "id": 999}, format="json")

    assert response.status_code == 200  # read-only fields are simply ignored
    user.refresh_from_db()
    assert user.email == "sam@example.com"
    assert user.id != 999


def test_password_cannot_be_changed_here(user, logged_in):
    logged_in.patch(URL, {"password": "new-Strong-pass-9"}, format="json")

    user.refresh_from_db()
    assert user.check_password(PASSWORD)


def test_put_is_not_allowed(user, logged_in):
    response = logged_in.put(URL, {"full_name": "X"}, format="json")

    assert response.status_code == 405


# --- Docs ----------------------------------------------------------------------


def test_me_is_documented_and_needs_a_token(db):
    schema = APIClient().get(reverse("schema"), {"format": "json"}).json()
    path = schema["paths"]["/api/auth/me/"]

    assert set(path) >= {"get", "patch"}
    assert "put" not in path
    assert {"jwtAuth": []} in path["get"]["security"]
