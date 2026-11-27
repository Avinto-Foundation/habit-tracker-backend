from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Case, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle

from . import services
from .models import Friendship
from .serializers import (
    FriendshipSerializer,
    RequestListSerializer,
    SearchResultSerializer,
    SendRequestSerializer,
)

User = get_user_model()

SEARCH_LIMIT = 20
NOT_FOUND = OpenApiResponse(description="No such request or friendship of yours.")


def _pending(**lookup) -> Friendship:
    """A pending request matching `lookup`, or 404."""
    return get_object_or_404(Friendship, status=Friendship.Status.PENDING, **lookup)


# --- Search -----------------------------------------------------------------------


class UserSearchView(generics.GenericAPIView):
    """GET /api/users/search/?q=: find people to add as friends."""

    serializer_class = SearchResultSerializer

    @extend_schema(
        summary="Find people",
        description=(
            "Searches **usernames and names** (not emails) for `q`, at least 2 characters; a "
            "leading `@` is ignored. Best matches first (exact username, then usernames "
            f"starting with `q`), at most {SEARCH_LIMIT}. You're never in the results.\n\n"
            "Each result has `friendship_status` (`none`, `request_sent`, `request_received`, "
            "`friends`) and `friendship_id` to accept / cancel / unfriend."
        ),
        tags=["friends"],
        parameters=[OpenApiParameter("q", OpenApiTypes.STR, required=True)],
        responses={200: SearchResultSerializer(many=True)},
    )
    def get(self, request):
        query = request.query_params.get("q", "").strip().lstrip("@").strip()
        if len(query) < 2:
            raise ValidationError({"q": ["Type at least 2 characters."]})

        users = list(
            User.objects.filter(is_active=True)
            .exclude(pk=request.user.pk)
            .filter(Q(username__icontains=query) | Q(full_name__icontains=query))
            .annotate(
                rank=Case(
                    When(username__iexact=query, then=Value(0)),
                    When(username__istartswith=query, then=Value(1)),
                    When(full_name__istartswith=query, then=Value(2)),
                    default=Value(3),
                    output_field=IntegerField(),
                )
            )
            .order_by("rank", "full_name", "username")[:SEARCH_LIMIT]
        )
        statuses = services.statuses_for(request.user, users)
        context = {**self.get_serializer_context(), "statuses": statuses}
        return Response(SearchResultSerializer(users, many=True, context=context).data)


# --- Requests ---------------------------------------------------------------------


class FriendRequestListCreateView(generics.GenericAPIView):
    """GET / POST /api/friends/requests/"""

    serializer_class = SendRequestSerializer
    throttle_scope = "friend_request"

    def get_throttles(self):
        # Only sending is limited (20 an hour), not looking at your requests.
        return [ScopedRateThrottle()] if self.request.method == "POST" else []

    @extend_schema(
        summary="My pending friend requests",
        description="`incoming`: waiting for your answer. `outgoing`: waiting for theirs. "
        "Newest first.",
        tags=["friends"],
        responses={200: RequestListSerializer},
    )
    def get(self, request):
        pending = Friendship.objects.filter(status=Friendship.Status.PENDING).select_related(
            "from_user", "to_user"
        )
        context = self.get_serializer_context()
        return Response(
            {
                "incoming": FriendshipSerializer(
                    pending.filter(to_user=request.user), many=True, context=context
                ).data,
                "outgoing": FriendshipSerializer(
                    pending.filter(from_user=request.user), many=True, context=context
                ).data,
            }
        )

    @extend_schema(
        summary="Send a friend request",
        description=(
            "Ask someone (by `username`) to be friends. **201** with the new request.\n\n"
            "If **they already asked you**, this accepts their request instead and you're "
            "friends straight away: **200** with `status: accepted`.\n\n"
            "Refused: unknown username, yourself, already friends, already asked. "
            "Limited to 20 per hour."
        ),
        tags=["friends"],
        examples=[OpenApiExample("Send", value={"username": "aarav"}, request_only=True)],
        responses={
            201: FriendshipSerializer,
            200: FriendshipSerializer,
            400: OpenApiResponse(description="e.g. {\"username\": [\"You're already friends.\"]}"),
        },
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        me, them = request.user, serializer.validated_data["username"]
        context = self.get_serializer_context()

        existing = services.between(me, them)
        if existing is not None:
            if existing.status == Friendship.Status.ACCEPTED:
                raise ValidationError({"username": ["You're already friends."]})
            if existing.from_user_id == me.pk:
                raise ValidationError({"username": ["You've already sent them a request."]})
            # They asked me first: sending one back means yes.
            existing.status = Friendship.Status.ACCEPTED
            existing.accepted_at = timezone.now()
            existing.save(update_fields=["status", "accepted_at"])
            return Response(FriendshipSerializer(existing, context=context).data)

        try:
            with transaction.atomic():
                friendship = Friendship.objects.create(from_user=me, to_user=them)
        except IntegrityError:
            # Two taps at the same moment: the first one already made it.
            raise ValidationError({"username": ["You've already sent them a request."]}) from None
        return Response(
            FriendshipSerializer(friendship, context=context).data, status=status.HTTP_201_CREATED
        )


class FriendRequestCancelView(generics.GenericAPIView):
    """DELETE /api/friends/requests/<id>/: take back a request you sent."""

    serializer_class = FriendshipSerializer

    @extend_schema(
        summary="Cancel a request you sent",
        description="Deletes it. The other person isn't told.",
        tags=["friends"],
        responses={204: None, 404: NOT_FOUND},
    )
    def delete(self, request, pk):
        _pending(pk=pk, from_user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class FriendRequestAcceptView(generics.GenericAPIView):
    """POST /api/friends/requests/<id>/accept/"""

    serializer_class = FriendshipSerializer

    @extend_schema(
        summary="Accept a friend request",
        description="Only for requests sent **to you**. You're now friends.",
        tags=["friends"],
        request=None,
        responses={200: FriendshipSerializer, 404: NOT_FOUND},
    )
    def post(self, request, pk):
        friendship = _pending(pk=pk, to_user=request.user)
        friendship.status = Friendship.Status.ACCEPTED
        friendship.accepted_at = timezone.now()
        friendship.save(update_fields=["status", "accepted_at"])
        return Response(self.get_serializer(friendship).data)


class FriendRequestDeclineView(generics.GenericAPIView):
    """POST /api/friends/requests/<id>/decline/"""

    serializer_class = FriendshipSerializer

    @extend_schema(
        summary="Decline a friend request",
        description="Only for requests sent **to you**. Deletes it; the sender isn't told and "
        "may ask again later.",
        tags=["friends"],
        request=None,
        responses={204: None, 404: NOT_FOUND},
    )
    def post(self, request, pk):
        _pending(pk=pk, to_user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# --- Friends ----------------------------------------------------------------------


class FriendListView(generics.GenericAPIView):
    """GET /api/friends/"""

    serializer_class = FriendshipSerializer

    @extend_schema(
        summary="My friends",
        description="Everyone you're friends with, sorted by name. `user` is the friend; "
        "`accepted_at` is when you became friends; `id` is used to unfriend.",
        tags=["friends"],
        responses={200: FriendshipSerializer(many=True)},
    )
    def get(self, request):
        me = request.user
        friendships = Friendship.objects.filter(
            Q(from_user=me) | Q(to_user=me), status=Friendship.Status.ACCEPTED
        ).select_related("from_user", "to_user")
        ordered = sorted(friendships, key=lambda f: f.other(me).full_name.casefold())
        return Response(self.get_serializer(ordered, many=True).data)


class UnfriendView(generics.GenericAPIView):
    """DELETE /api/friends/<id>/"""

    serializer_class = FriendshipSerializer

    @extend_schema(
        summary="Unfriend",
        description="Ends the friendship (either of you can). The other person isn't told.",
        tags=["friends"],
        responses={204: None, 404: NOT_FOUND},
    )
    def delete(self, request, pk):
        me = request.user
        friendship = get_object_or_404(
            Friendship.objects.filter(Q(from_user=me) | Q(to_user=me)),
            pk=pk,
            status=Friendship.Status.ACCEPTED,
        )
        friendship.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

