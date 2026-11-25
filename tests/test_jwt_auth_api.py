from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

User = get_user_model()
PASSWORD = "my-Strong-pass-1"
LOGIN_URL = reverse("login")
REFRESH_URL = reverse("token-refresh")
LOGOUT_URL = reverse("logout")


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="sam@example.com", username="sam", full_name="Sam Adhikari", password=PASSWORD
    )


def post(url, data):
    return APIClient().post(url, data, format="json")


def login(remember_me=None):
    data = {"email": "sam@example.com", "password": PASSWORD}
    if remember_me is not None:
        data["remember_me"] = remember_me
    return post(LOGIN_URL, data)


def lifetime(token_string, token_class=RefreshToken):
    """How long a token was issued for (expiry time minus issue time)."""
    token = token_class(token_string)
    return timedelta(seconds=token["exp"] - token["iat"])


# --- Log in --------------------------------------------------------------------


def test_login_returns_tokens_and_user(user):
    response = login()

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access", "refresh", "user"}
    assert body["user"] == {
        "id": user.id,
        "full_name": "Sam Adhikari",
        "username": "sam",
        "email": "sam@example.com",
        "timezone": "UTC",
        "bio": "",
        "avatar": None,
        "date_joined": user.date_joined.isoformat().replace("+00:00", "Z"),
    }
    assert "password" not in body["user"]


def test_tokens_belong_to_the_user(user):
    body = login().json()

    assert AccessToken(body["access"])["user_id"] == str(user.id)
    assert RefreshToken(body["refresh"])["user_id"] == str(user.id)


def test_login_email_ignores_case_and_spaces(user):
    response = post(LOGIN_URL, {"email": "  SAM@Example.com ", "password": PASSWORD})

    assert response.status_code == 200


def test_login_updates_last_login(user):
    assert user.last_login is None

    login()

    user.refresh_from_db()
    assert user.last_login is not None


@pytest.mark.parametrize(
    "email, password",
    [
        ("sam@example.com", "wrong-password"),  # wrong password
        ("nobody@example.com", PASSWORD),  # no such account
    ],
)
def test_wrong_credentials_give_401_with_same_message(user, email, password):
    response = post(LOGIN_URL, {"email": email, "password": password})

    assert response.status_code == 401
    assert response.json() == {"detail": "Email or password is incorrect."}


def test_inactive_user_cannot_log_in(user):
    user.is_active = False
    user.save()

    assert login().status_code == 401


def test_login_missing_fields_gives_400(db):
    response = post(LOGIN_URL, {})

    assert response.status_code == 400
    assert response.json()["email"] == ["This field is required."]
    assert response.json()["password"] == ["This field is required."]


# --- Token lifetimes / remember me ---------------------------------------------


def test_access_token_lasts_15_minutes(user):
    assert lifetime(login().json()["access"], AccessToken) == timedelta(minutes=15)


def test_refresh_token_lasts_1_day_by_default(user):
    assert lifetime(login().json()["refresh"]) == timedelta(days=1)


def test_remember_me_refresh_token_lasts_7_days(user):
    assert lifetime(login(remember_me=True).json()["refresh"]) == timedelta(days=7)


def test_remember_me_false_lasts_1_day(user):
    assert lifetime(login(remember_me=False).json()["refresh"]) == timedelta(days=1)


# --- Refresh -------------------------------------------------------------------


def test_refresh_returns_new_access_and_refresh_tokens(user):
    old_refresh = login().json()["refresh"]

    response = post(REFRESH_URL, {"refresh": old_refresh})

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"access", "refresh"}
    assert body["refresh"] != old_refresh
    assert AccessToken(body["access"])["user_id"] == str(user.id)


def test_old_refresh_token_cannot_be_used_twice(user):
    old_refresh = login().json()["refresh"]
    post(REFRESH_URL, {"refresh": old_refresh})

    response = post(REFRESH_URL, {"refresh": old_refresh})

    assert response.status_code == 401


def test_remember_me_survives_refresh(user):
    first = login(remember_me=True).json()["refresh"]

    second = post(REFRESH_URL, {"refresh": first}).json()["refresh"]

    assert lifetime(second) == timedelta(days=7)


def test_normal_token_stays_1_day_after_refresh(user):
    first = login().json()["refresh"]

    second = post(REFRESH_URL, {"refresh": first}).json()["refresh"]

    assert lifetime(second) == timedelta(days=1)


def test_refresh_with_garbage_token_gives_401(db):
    response = post(REFRESH_URL, {"refresh": "not-a-real-token"})

    assert response.status_code == 401
    assert response.json()["code"] == "token_not_valid"


def test_access_token_cannot_be_used_as_refresh_token(user):
    access = login().json()["access"]

    assert post(REFRESH_URL, {"refresh": access}).status_code == 401


def test_refresh_for_deleted_user_gives_401(user):
    refresh = login().json()["refresh"]
    user.delete()

    assert post(REFRESH_URL, {"refresh": refresh}).status_code == 401


# --- Log out -------------------------------------------------------------------


def test_logout_returns_205(user):
    refresh = login().json()["refresh"]

    response = post(LOGOUT_URL, {"refresh": refresh})

    assert response.status_code == 205


def test_refresh_token_is_dead_after_logout(user):
    refresh = login().json()["refresh"]
    post(LOGOUT_URL, {"refresh": refresh})

    assert post(REFRESH_URL, {"refresh": refresh}).status_code == 401


def test_logging_out_twice_gives_401(user):
    refresh = login().json()["refresh"]
    post(LOGOUT_URL, {"refresh": refresh})

    assert post(LOGOUT_URL, {"refresh": refresh}).status_code == 401


def test_logout_with_garbage_token_gives_401(db):
    assert post(LOGOUT_URL, {"refresh": "not-a-real-token"}).status_code == 401


def test_logout_without_token_gives_400(db):
    assert post(LOGOUT_URL, {}).status_code == 400


# --- Using the access token ----------------------------------------------------


def test_bearer_access_token_identifies_the_user(user):
    access = login().json()["access"]
    request = APIRequestFactory().get("/", HTTP_AUTHORIZATION=f"Bearer {access}")

    authenticated_user, _ = JWTAuthentication().authenticate(request)

    assert authenticated_user == user


# --- Docs ----------------------------------------------------------------------


def test_auth_endpoints_are_documented_with_bearer_auth(db):
    schema = APIClient().get(reverse("schema"), {"format": "json"}).json()

    for path in ["/api/auth/login/", "/api/auth/token/refresh/", "/api/auth/logout/"]:
        assert "post" in schema["paths"][path]
    assert schema["components"]["securitySchemes"]["jwtAuth"]["scheme"] == "bearer"
