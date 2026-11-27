"""Talking to Google: checking the ID token the frontend gets from "Continue with Google"."""

import re

from django.conf import settings
from django.contrib.auth import get_user_model
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from .models import RESERVED_USERNAMES

User = get_user_model()


def verify_google_token(token: str) -> dict:
    """Check a Google ID token and return what it says about the user.

    Google's library checks the signature, that it hasn't expired, that Google
    issued it and that it was made for *our* app (`GOOGLE_CLIENT_ID`).
    Raises `ValueError` (or a `google.auth.exceptions` error) if anything is wrong.
    """
    return id_token.verify_oauth2_token(
        token, google_requests.Request(), settings.GOOGLE_CLIENT_ID
    )


def unique_username_from_email(email: str) -> str:
    """Make a free username from an email, e.g. 'john.doe@gmail.com' -> 'john_doe'.

    Follows the sign-up rules (3-30 characters: letters, numbers, underscores) and
    adds a number if the name is taken: 'john_doe2', 'john_doe3', ...
    """
    base = re.sub(r"[^A-Za-z0-9_]+", "_", email.split("@")[0]).strip("_")[:26]
    if len(base) < 3:
        base = f"user_{base}".rstrip("_")

    username, number = base, 2
    while (
        username.lower() in RESERVED_USERNAMES
        or User.objects.filter(username__iexact=username).exists()
    ):
        username = f"{base}{number}"
        number += 1
    return username
