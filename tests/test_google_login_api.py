"""Tests for POST /api/auth/google/.

We never call Google in tests: `verify_google_token` is replaced ("mocked") with a
fake that returns whatever Google would have said about the token.
"""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from google.auth.exceptions import TransportError
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.google import unique_username_from_email, verify_google_token

User = get_user_model()
URL = reverse("google-login")
CLIENT_ID = "test-client-id.apps.googleusercontent.com"


def google_says(email="john.doe@gmail.com", name="John Doe", email_verified=True):
    """What Google's library returns for a valid ID token."""
    return {"email": email, "name": name, "email_verified": email_verified}


@pytest.fixture(autouse=True)
def google_configured(settings):
    """Every test runs with a Google Client ID set (unless it changes it)."""
    settings.GOOGLE_CLIENT_ID = CLIENT_ID


def sign_in(claims=None, error=None, **body):
    """POST to the endpoint while pretending Google returned `claims` (or raised `error`)."""
    data = {"id_token": "fake-google-token", **body}
    fake = {"side_effect": error} if error else {"return_value": claims or google_says()}
    with patch("accounts.google.verify_google_token", **fake) as mock:
        response = APIClient().post(URL, data, format="json")
    return response, mock


# --- New users -----------------------------------------------------------------


@pytest.mark.django_db
def test_first_google_sign_in_creates_account_with_201():
    response, _ = sign_in()

    assert response.status_code == 201
    body = response.json()
    assert body["created"] is True
    assert body["user"]["email"] == "john.doe@gmail.com"
    assert body["user"]["full_name"] == "John Doe"
    assert body["user"]["username"] == "john_doe"
    assert {"access", "refresh"} <= set(body)


@pytest.mark.django_db
def test_google_account_has_no_usable_password():
    sign_in()

    assert not User.objects.get(email="john.doe@gmail.com").has_usable_password()


@pytest.mark.django_db
def test_new_account_uses_timezone_from_request():
    response, _ = sign_in(timezone="Asia/Kathmandu")

    assert response.json()["user"]["timezone"] == "Asia/Kathmandu"


@pytest.mark.django_db
def test_google_email_is_saved_in_lowercase():
    response, _ = sign_in(google_says(email="John.Doe@Gmail.com"))

    assert response.json()["user"]["email"] == "john.doe@gmail.com"


@pytest.mark.django_db
def test_missing_name_falls_back_to_email():
    response, _ = sign_in(google_says(name=""))

    assert response.json()["user"]["full_name"] == "john.doe"


# --- Existing users ------------------------------------------------------------


@pytest.mark.django_db
def test_existing_email_logs_in_with_200_without_new_account():
    existing = User.objects.create_user(
        email="john.doe@gmail.com", username="johnny", full_name="Johnny", password="x-Strong-1"
    )

    response, _ = sign_in(google_says(email="JOHN.DOE@gmail.com"))

    assert response.status_code == 200
    assert response.json()["created"] is False
    assert response.json()["user"]["id"] == existing.id
    assert response.json()["user"]["username"] == "johnny"  # not changed by Google
    assert User.objects.count() == 1


@pytest.mark.django_db
def test_signing_in_twice_reuses_the_account():
    first, _ = sign_in()
    second, _ = sign_in()

    assert second.status_code == 200
    assert second.json()["user"]["id"] == first.json()["user"]["id"]


@pytest.mark.django_db
def test_disabled_account_cannot_sign_in():
    User.objects.create_user(
        email="john.doe@gmail.com", username="johnny", full_name="J", is_active=False
    )

    response, _ = sign_in()

    assert response.status_code == 401
    assert response.json() == {"detail": "This account is disabled."}


# --- Tokens --------------------------------------------------------------------


@pytest.mark.django_db
def test_tokens_belong_to_the_google_user():
    response, _ = sign_in()

    refresh = RefreshToken(response.json()["refresh"])
    assert refresh["user_id"] == str(response.json()["user"]["id"])


@pytest.mark.django_db
@pytest.mark.parametrize("remember_me, days", [(False, 1), (True, 7)])
def test_remember_me_sets_refresh_lifetime(remember_me, days):
    response, _ = sign_in(remember_me=remember_me)

    token = RefreshToken(response.json()["refresh"])
    assert timedelta(seconds=token["exp"] - token["iat"]) == timedelta(days=days)


@pytest.mark.django_db
def test_google_token_is_sent_to_the_checker():
    _, mock = sign_in()

    mock.assert_called_once_with("fake-google-token")


# --- Errors --------------------------------------------------------------------


@pytest.mark.django_db
def test_fake_or_expired_google_token_gives_401():
    response, _ = sign_in(error=ValueError("Token expired"))

    assert response.status_code == 401
    assert response.json() == {"detail": "Google sign-in failed. Please try again."}
    assert not User.objects.exists()


@pytest.mark.django_db
def test_unverified_google_email_gives_401():
    response, _ = sign_in(google_says(email_verified=False))

    assert response.status_code == 401
    assert response.json() == {"detail": "Your Google email address is not verified."}
    assert not User.objects.exists()


@pytest.mark.django_db
def test_google_unreachable_gives_503():
    response, _ = sign_in(error=TransportError("no internet"))

    assert response.status_code == 503


@pytest.mark.django_db
def test_google_not_configured_gives_503(settings):
    settings.GOOGLE_CLIENT_ID = ""

    response, mock = sign_in()

    assert response.status_code == 503
    mock.assert_not_called()


@pytest.mark.django_db
def test_missing_id_token_gives_400():
    response = APIClient().post(URL, {}, format="json")

    assert response.status_code == 400
    assert response.json()["id_token"] == ["This field is required."]


@pytest.mark.django_db
def test_invalid_timezone_gives_400():
    response, _ = sign_in(timezone="Mars/Base")

    assert response.status_code == 400


# --- Helpers -------------------------------------------------------------------


def test_verify_google_token_checks_it_was_made_for_our_app(settings):
    with patch("accounts.google.id_token.verify_oauth2_token") as google_check:
        verify_google_token("abc")

    token, _request, audience = google_check.call_args.args
    assert token == "abc"
    assert audience == CLIENT_ID  # tokens made for other apps are rejected by Google's library


@pytest.mark.django_db
@pytest.mark.parametrize(
    "email, expected",
    [
        ("john.doe@gmail.com", "john_doe"),
        ("sam+habits@gmail.com", "sam_habits"),
        ("ab@gmail.com", "user_ab"),
        ("a" * 40 + "@gmail.com", "a" * 26),
    ],
)
def test_username_is_made_from_email(email, expected):
    assert unique_username_from_email(email) == expected


@pytest.mark.django_db
def test_username_gets_a_number_when_taken():
    User.objects.create_user(email="x@example.com", username="john_doe", full_name="X")
    User.objects.create_user(email="y@example.com", username="John_Doe2", full_name="Y")

    assert unique_username_from_email("john.doe@gmail.com") == "john_doe3"


@pytest.mark.django_db
def test_google_endpoint_is_documented():
    schema = APIClient().get(reverse("schema"), {"format": "json"}).json()

    assert "post" in schema["paths"]["/api/auth/google/"]
