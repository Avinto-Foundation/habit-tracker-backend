"""Password reset: making and checking one-time reset links, and sending the email."""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

User = get_user_model()

APP_NAME = "HabitSquad"


def reset_link(user) -> str:
    """The frontend link that lets `user` choose a new password.

    `uid` is the user id in a URL-safe form; `token` is Django's reset token. The
    token stops working after `PASSWORD_RESET_TIMEOUT` (1 hour) and as soon as the
    password changes, so each link can only be used once.
    """
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    return f"{settings.FRONTEND_URL}/reset-password?uid={uid}&token={token}"


def send_reset_email(user) -> None:
    """Email the reset link (printed in the terminal during development)."""
    link = reset_link(user)
    minutes = settings.PASSWORD_RESET_TIMEOUT // 60
    name = user.get_short_name()
    send_mail(
        subject=f"Reset your {APP_NAME} password",
        message=(
            f"Hi {name},\n\n"
            f"Someone (hopefully you) asked to reset the password for your {APP_NAME} "
            f"account. Click the link below to choose a new one:\n\n"
            f"{link}\n\n"
            f"This link works once and expires in {minutes} minutes.\n\n"
            f"If you didn't ask for this, you can ignore this email; your password "
            f"won't change.\n\n"
            f"The {APP_NAME} team"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
    )


def user_from_link(uid: str, token: str):
    """The user a reset link belongs to, or None if the link is broken, used or expired."""
    try:
        user = User.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return None
    if not user.is_active or not default_token_generator.check_token(user, token):
        return None
    return user


def log_out_everywhere(user) -> None:
    """Block every refresh token the user has, so all devices must log in again."""
    for token in OutstandingToken.objects.filter(user=user):
        BlacklistedToken.objects.get_or_create(token=token)
