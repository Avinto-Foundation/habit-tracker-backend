from django.conf import settings
from rest_framework_simplejwt.tokens import RefreshToken


class RememberMeRefreshToken(RefreshToken):
    """A refresh token that lasts longer (7 days) because the user ticked "Remember me".

    It carries a `remember_me` claim, so when it is refreshed the new token is
    given the same long lifetime instead of the default 1 day.
    """

    lifetime = settings.REMEMBER_ME_REFRESH_LIFETIME


def refresh_token_for(user, remember_me: bool = False) -> RefreshToken:
    """Create a refresh token for `user` (its `.access_token` is the matching access token)."""
    if remember_me:
        token = RememberMeRefreshToken.for_user(user)
        token["remember_me"] = True
        return token
    return RefreshToken.for_user(user)
