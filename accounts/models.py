import uuid
from zoneinfo import available_timezones

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models


def validate_timezone(value: str) -> None:
    """Reject anything that isn't a real time zone name, e.g. 'Asia/Kathmandu'."""
    if value not in available_timezones():
        raise ValidationError(f"'{value}' is not a valid time zone.")


def avatar_upload_path(user: "User", filename: str) -> str:
    """Where a profile photo is saved: media/avatars/<user id>/<random name>.webp.

    A new random name for every upload means browsers never show an old cached
    photo, and nobody can guess another user's photo address.
    """
    return f"avatars/{user.pk}/{uuid.uuid4().hex}.webp"


# Words used in URLs like /api/users/<username>/, so nobody can take them as a username.
RESERVED_USERNAMES = frozenset({"search", "me", "admin", "api"})


class User(AbstractUser):
    """App user. People log in with their email; the username is their public @handle."""

    # Replace Django's first_name / last_name with a single "Full name" field.
    first_name = None
    last_name = None
    full_name = models.CharField("full name", max_length=150)

    email = models.EmailField("email address", unique=True)
    timezone = models.CharField(
        max_length=64,
        default="UTC",
        validators=[validate_timezone],
        help_text="Time zone name, e.g. Asia/Kathmandu. Used to work out daily streaks.",
    )
    bio = models.CharField(
        max_length=160, blank=True, help_text="A short line about yourself, shown on your profile."
    )
    avatar = models.ImageField(
        "profile photo",
        upload_to=avatar_upload_path,
        blank=True,
        help_text="Saved as a 512 px WebP image (see accounts/avatars.py).",
    )

    # Log in with email instead of username.
    USERNAME_FIELD = "email"
    # Extra fields `createsuperuser` asks for (email and password are asked anyway).
    REQUIRED_FIELDS = ["username", "full_name"]

    def __str__(self) -> str:
        return self.email

    def get_full_name(self) -> str:
        return self.full_name

    def get_short_name(self) -> str:
        return self.full_name.split(" ")[0] if self.full_name else self.username
