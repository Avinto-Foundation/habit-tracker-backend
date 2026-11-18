import pytest
from django.contrib.auth import authenticate, get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError

User = get_user_model()
PASSWORD = "x-Strong-pass-1"


def make_user(**overrides):
    """Create a user with sensible defaults; pass keyword args to change any field."""
    data = {
        "email": "sam@example.com",
        "username": "sam",
        "full_name": "Sam Adhikari",
        "password": PASSWORD,
    }
    data.update(overrides)
    return User.objects.create_user(**data)


def test_custom_user_model_is_used():
    assert User._meta.label == "accounts.User"


def test_login_field_is_email():
    assert User.USERNAME_FIELD == "email"


def test_first_and_last_name_are_removed():
    field_names = [field.name for field in User._meta.get_fields()]

    assert "first_name" not in field_names
    assert "last_name" not in field_names


@pytest.mark.django_db
def test_user_can_log_in_with_email_and_password():
    user = make_user()

    assert authenticate(email="sam@example.com", password=PASSWORD) == user


@pytest.mark.django_db
def test_wrong_password_does_not_log_in():
    make_user()

    assert authenticate(email="sam@example.com", password="wrong-password") is None


@pytest.mark.django_db
def test_email_must_be_unique():
    make_user()

    with pytest.raises(IntegrityError):
        make_user(username="sam2")


@pytest.mark.django_db
def test_username_must_be_unique():
    make_user()

    with pytest.raises(IntegrityError):
        make_user(email="other@example.com")


@pytest.mark.django_db
def test_timezone_defaults_to_utc():
    assert make_user().timezone == "UTC"


@pytest.mark.django_db
def test_real_timezone_is_accepted():
    user = make_user(timezone="Asia/Kathmandu")

    user.full_clean()  # raises ValidationError if anything is invalid


@pytest.mark.django_db
def test_fake_timezone_is_rejected():
    user = make_user(timezone="Mars/Base")

    with pytest.raises(ValidationError) as error:
        user.full_clean()

    assert "timezone" in error.value.message_dict


@pytest.mark.django_db
def test_full_name_and_str():
    user = make_user()

    assert user.get_full_name() == "Sam Adhikari"
    assert user.get_short_name() == "Sam"
    assert str(user) == "sam@example.com"


@pytest.mark.django_db
def test_create_superuser_with_email():
    admin = User.objects.create_superuser(
        email="admin@example.com", username="admin", full_name="Admin", password=PASSWORD
    )

    assert admin.is_staff and admin.is_superuser
