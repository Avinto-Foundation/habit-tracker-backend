import re
from datetime import datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()
REQUEST_URL = reverse("password-reset")
CONFIRM_URL = reverse("password-reset-confirm")
OLD_PASSWORD = "my-Old-pass-1"
NEW_PASSWORD = "my-New-pass-2"
INVALID_LINK = "This reset link is invalid or has expired. Please ask for a new one."


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="sam@example.com", username="sam", full_name="Sam Adhikari", password=OLD_PASSWORD
    )


def post(url, data):
    return APIClient().post(url, data, format="json")


def link_from_email(mail) -> dict:
    """Find the reset link in an email and return its uid and token."""
    url = re.search(r"https?://\S+", mail.body).group(0)
    query = parse_qs(urlparse(url).query)
    return {"url": url, "uid": query["uid"][0], "token": query["token"][0]}


def request_link(mailoutbox, email="sam@example.com") -> dict:
    post(REQUEST_URL, {"email": email})
    return link_from_email(mailoutbox[-1])


def confirm(link, password=NEW_PASSWORD, confirm_password=None):
    return post(
        CONFIRM_URL,
        {
            "uid": link["uid"],
            "token": link["token"],
            "new_password": password,
            "new_password_confirm": confirm_password or password,
        },
    )


# --- Asking for a link ---------------------------------------------------------


def test_request_emails_a_reset_link(user, mailoutbox):
    response = post(REQUEST_URL, {"email": "sam@example.com"})

    assert response.status_code == 200
    assert "we've sent a link" in response.json()["detail"]
    assert len(mailoutbox) == 1
    mail = mailoutbox[0]
    assert mail.to == ["sam@example.com"]
    assert mail.subject == "Reset your HabitSquad password"
    assert "Hi Sam," in mail.body
    assert "expires in 60 minutes" in mail.body


def test_link_points_to_the_frontend_reset_page(user, mailoutbox, settings):
    settings.FRONTEND_URL = "https://habitsquad.example"

    link = request_link(mailoutbox)

    assert link["url"].startswith("https://habitsquad.example/reset-password?uid=")


def test_unknown_email_gets_the_same_answer_but_no_email(db, mailoutbox):
    response = post(REQUEST_URL, {"email": "nobody@example.com"})

    assert response.status_code == 200
    assert "we've sent a link" in response.json()["detail"]
    assert mailoutbox == []


def test_email_ignores_upper_lower_case(user, mailoutbox):
    post(REQUEST_URL, {"email": "SAM@Example.com"})

    assert len(mailoutbox) == 1


def test_disabled_account_gets_no_email(user, mailoutbox):
    user.is_active = False
    user.save()

    post(REQUEST_URL, {"email": "sam@example.com"})

    assert mailoutbox == []


def test_invalid_email_gives_400(db):
    response = post(REQUEST_URL, {"email": "not-an-email"})

    assert response.status_code == 400
    assert "email" in response.json()


def test_requests_are_limited_to_5_per_hour(user, mailoutbox):
    for _ in range(5):
        assert post(REQUEST_URL, {"email": "sam@example.com"}).status_code == 200

    response = post(REQUEST_URL, {"email": "sam@example.com"})

    assert response.status_code == 429
    assert len(mailoutbox) == 5


# --- Using the link ------------------------------------------------------------


def test_link_sets_the_new_password(user, mailoutbox):
    response = confirm(request_link(mailoutbox))

    assert response.status_code == 200
    assert "password has been changed" in response.json()["detail"]
    assert authenticate(email="sam@example.com", password=NEW_PASSWORD) == user
    assert authenticate(email="sam@example.com", password=OLD_PASSWORD) is None


def test_reset_logs_the_user_out_everywhere(user, mailoutbox):
    login = post(reverse("login"), {"email": "sam@example.com", "password": OLD_PASSWORD})
    old_refresh = login.json()["refresh"]

    confirm(request_link(mailoutbox))

    response = post(reverse("token-refresh"), {"refresh": old_refresh})
    assert response.status_code == 401


def test_link_works_only_once(user, mailoutbox):
    link = request_link(mailoutbox)
    confirm(link)

    response = confirm(link, password="another-Pass-3")

    assert response.status_code == 400
    assert response.json()["token"] == [INVALID_LINK]


def test_link_expires_after_one_hour(user, mailoutbox):
    link = request_link(mailoutbox)
    later = datetime.now() + timedelta(hours=1, minutes=1)

    with patch.object(PasswordResetTokenGenerator, "_now", return_value=later):
        response = confirm(link)

    assert response.status_code == 400
    assert response.json()["token"] == [INVALID_LINK]
    assert authenticate(email="sam@example.com", password=OLD_PASSWORD) == user


@pytest.mark.parametrize(
    "uid, token",
    [
        ("not-a-uid", "whatever"),  # broken uid
        ("OTk5", "whatever"),  # uid of a user that doesn't exist (999)
        (None, "made-up-token"),  # real uid, fake token
    ],
)
def test_broken_links_are_rejected(user, mailoutbox, uid, token):
    real = request_link(mailoutbox)

    response = confirm({"uid": uid or real["uid"], "token": token})

    assert response.status_code == 400
    assert response.json()["token"] == [INVALID_LINK]


def test_passwords_must_match(user, mailoutbox):
    response = confirm(request_link(mailoutbox), confirm_password="something-Else-9")

    assert response.status_code == 400
    assert response.json()["new_password_confirm"] == ["Passwords don't match."]


@pytest.mark.parametrize("weak", ["short", "password123", "4815162342", "samadhikari1"])
def test_weak_new_password_is_rejected(user, mailoutbox, weak):
    response = confirm(request_link(mailoutbox), password=weak)

    assert response.status_code == 400
    assert "new_password" in response.json()
    assert authenticate(email="sam@example.com", password=OLD_PASSWORD) == user


def test_link_still_works_after_a_rejected_attempt(user, mailoutbox):
    link = request_link(mailoutbox)
    confirm(link, password="short")

    assert confirm(link).status_code == 200


def test_google_only_user_can_set_a_password(db, mailoutbox):
    google_user = User.objects.create_user(
        email="g@example.com", username="g_user", full_name="Gee", password=None
    )
    assert not google_user.has_usable_password()

    response = confirm(request_link(mailoutbox, email="g@example.com"))

    assert response.status_code == 200
    assert authenticate(email="g@example.com", password=NEW_PASSWORD) == google_user


def test_missing_fields_give_400(db):
    response = post(CONFIRM_URL, {})

    assert response.status_code == 400
    for field in ["uid", "token", "new_password", "new_password_confirm"]:
        assert response.json()[field] == ["This field is required."]


# --- Docs ----------------------------------------------------------------------


def test_password_reset_endpoints_are_documented(db):
    schema = APIClient().get(reverse("schema"), {"format": "json"}).json()

    assert "post" in schema["paths"]["/api/auth/password-reset/"]
    assert "post" in schema["paths"]["/api/auth/password-reset/confirm/"]
