import pytest
from django.contrib.auth import authenticate, get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

User = get_user_model()
URL = reverse("register")


def signup_data(**overrides):
    """A valid sign-up request body; pass keyword args to change any field."""
    data = {
        "full_name": "Samikshya Adhikari",
        "username": "samikshya",
        "email": "sam@example.com",
        "password": "my-Strong-pass-1",
        "password_confirm": "my-Strong-pass-1",
        "timezone": "Asia/Kathmandu",
    }
    data.update(overrides)
    return data


def post(data):
    return APIClient().post(URL, data, format="json")


# --- Success -------------------------------------------------------------------


@pytest.mark.django_db
def test_register_creates_user_and_returns_201():
    response = post(signup_data())

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "full_name": "Samikshya Adhikari",
        "username": "samikshya",
        "email": "sam@example.com",
        "timezone": "Asia/Kathmandu",
    }
    assert User.objects.filter(email="sam@example.com").exists()


@pytest.mark.django_db
def test_response_never_contains_the_password():
    body = post(signup_data()).json()

    assert "password" not in body
    assert "password_confirm" not in body


@pytest.mark.django_db
def test_password_is_hashed_and_user_can_log_in():
    post(signup_data())

    user = User.objects.get(email="sam@example.com")
    assert user.password != "my-Strong-pass-1"  # stored as a hash, not plain text
    assert authenticate(email="sam@example.com", password="my-Strong-pass-1") == user


@pytest.mark.django_db
def test_timezone_is_optional_and_defaults_to_utc():
    data = signup_data()
    del data["timezone"]

    response = post(data)

    assert response.status_code == 201
    assert response.json()["timezone"] == "UTC"


@pytest.mark.django_db
def test_email_is_saved_in_lowercase():
    response = post(signup_data(email="  Sam@Example.COM "))

    assert response.status_code == 201
    assert response.json()["email"] == "sam@example.com"


@pytest.mark.django_db
def test_full_name_spaces_are_trimmed():
    response = post(signup_data(full_name="  Samikshya Adhikari  "))

    assert response.json()["full_name"] == "Samikshya Adhikari"


# --- Duplicate accounts --------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("email", ["sam@example.com", "SAM@example.com"])
def test_duplicate_email_is_rejected(email):
    post(signup_data())

    response = post(signup_data(username="someone_else", email=email))

    assert response.status_code == 400
    assert response.json()["email"] == ["An account with this email already exists."]


@pytest.mark.django_db
@pytest.mark.parametrize("username", ["samikshya", "Samikshya"])
def test_duplicate_username_is_rejected(username):
    post(signup_data())

    response = post(signup_data(username=username, email="other@example.com"))

    assert response.status_code == 400
    assert response.json()["username"] == ["This username is already taken."]


# --- Password rules ------------------------------------------------------------


@pytest.mark.django_db
def test_passwords_must_match():
    response = post(signup_data(password_confirm="something-Else-9"))

    assert response.status_code == 400
    assert response.json()["password_confirm"] == ["Passwords don't match."]


@pytest.mark.django_db
@pytest.mark.parametrize(
    "password, reason",
    [
        ("Ab-1", "too short"),
        ("password123", "too common"),
        ("4815162342", "only numbers"),
        ("samikshya1", "too similar to username"),
    ],
)
def test_weak_password_is_rejected(password, reason):
    response = post(signup_data(password=password, password_confirm=password))

    assert response.status_code == 400, reason
    assert "password" in response.json(), reason
    assert not User.objects.exists()


# --- Field formats -------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("username", ["ab", "a" * 31, "has space", "bad-dash", "émoji"])
def test_invalid_username_is_rejected(username):
    response = post(signup_data(username=username))

    assert response.status_code == 400
    assert response.json()["username"] == [
        "Use 3-30 characters: letters, numbers and underscores only."
    ]


@pytest.mark.django_db
def test_invalid_email_is_rejected():
    response = post(signup_data(email="not-an-email"))

    assert response.status_code == 400
    assert "email" in response.json()


@pytest.mark.django_db
def test_invalid_timezone_is_rejected():
    response = post(signup_data(timezone="Mars/Base"))

    assert response.status_code == 400
    assert response.json()["timezone"] == ["'Mars/Base' is not a valid time zone."]


@pytest.mark.django_db
def test_blank_full_name_is_rejected():
    response = post(signup_data(full_name="   "))

    assert response.status_code == 400
    assert "full_name" in response.json()


@pytest.mark.django_db
def test_missing_fields_are_all_reported():
    response = post({})

    assert response.status_code == 400
    for field in ["full_name", "username", "email", "password", "password_confirm"]:
        assert response.json()[field] == ["This field is required."]


# --- HTTP details --------------------------------------------------------------


@pytest.mark.django_db
def test_get_is_not_allowed():
    response = APIClient().get(URL)

    assert response.status_code == 405


@pytest.mark.django_db
def test_register_is_documented_in_swagger():
    schema = APIClient().get(reverse("schema"), {"format": "json"}).json()

    assert "post" in schema["paths"]["/api/auth/register/"]
