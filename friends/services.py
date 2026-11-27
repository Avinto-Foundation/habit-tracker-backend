"""Who is friends with whom. Used by the friends API and (later) squads and the feed."""

from django.contrib.auth import get_user_model
from django.db.models import Q, QuerySet

from .models import Friendship

User = get_user_model()

# What a user sees about someone else (`friendship_status` in the API).
SELF = "self"
FRIENDS = "friends"
REQUEST_SENT = "request_sent"  # I asked them, waiting for their answer
REQUEST_RECEIVED = "request_received"  # they asked me
NONE = "none"


def between(user_a, user_b) -> Friendship | None:
    """The friendship or request between two people (either direction), or None."""
    return Friendship.objects.filter(
        Q(from_user=user_a, to_user=user_b) | Q(from_user=user_b, to_user=user_a)
    ).first()


def are_friends(user_a, user_b) -> bool:
    friendship = between(user_a, user_b)
    return friendship is not None and friendship.status == Friendship.Status.ACCEPTED


def friends_of(user) -> QuerySet:
    """Everyone `user` is friends with (accepted only)."""
    accepted = Friendship.objects.filter(status=Friendship.Status.ACCEPTED)
    return User.objects.filter(
        Q(pk__in=accepted.filter(from_user=user).values("to_user"))
        | Q(pk__in=accepted.filter(to_user=user).values("from_user"))
    )


def statuses_for(viewer, others) -> dict[int, tuple[str, Friendship | None]]:
    """For each user in `others`: how `viewer` relates to them, plus the row.

    One database query for the whole list (used by search results).
    """
    ids = [other.pk for other in others]
    rows = Friendship.objects.filter(
        Q(from_user=viewer, to_user__in=ids) | Q(to_user=viewer, from_user__in=ids)
    )
    found = {}
    for row in rows:
        other_id = row.to_user_id if row.from_user_id == viewer.pk else row.from_user_id
        found[other_id] = row

    result = {}
    for other in others:
        row = found.get(other.pk)
        if other.pk == viewer.pk:
            result[other.pk] = (SELF, None)
        elif row is None:
            result[other.pk] = (NONE, None)
        elif row.status == Friendship.Status.ACCEPTED:
            result[other.pk] = (FRIENDS, row)
        elif row.from_user_id == viewer.pk:
            result[other.pk] = (REQUEST_SENT, row)
        else:
            result[other.pk] = (REQUEST_RECEIVED, row)
    return result
