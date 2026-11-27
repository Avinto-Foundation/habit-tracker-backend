from django.contrib.auth import get_user_model
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from accounts.serializers import AvatarUrlMixin
from habits.models import Habit
from habits.serializers import WeekProgressSerializer

from . import services
from .models import Friendship

User = get_user_model()


class UserCardSerializer(AvatarUrlMixin, serializers.ModelSerializer):
    """What anyone may see about another user: name, @username, photo and bio.

    Never the email, time zone or anything private.
    """

    avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["username", "full_name", "bio", "avatar"]
        read_only_fields = fields


class SearchResultSerializer(UserCardSerializer):
    """A search result: the user card plus how the searcher relates to them.

    Needs `statuses` (from services.statuses_for) in the context.
    """

    friendship_status = serializers.SerializerMethodField()
    friendship_id = serializers.SerializerMethodField()

    class Meta(UserCardSerializer.Meta):
        fields = [*UserCardSerializer.Meta.fields, "friendship_status", "friendship_id"]
        read_only_fields = fields

    def _status(self, user):
        return self.context["statuses"].get(user.pk, (services.NONE, None))

    @extend_schema_field(
        serializers.ChoiceField(
            choices=[services.NONE, services.REQUEST_SENT, services.REQUEST_RECEIVED, services.FRIENDS]
        )
    )
    def get_friendship_status(self, user) -> str:
        """`none`, `request_sent`, `request_received` or `friends`."""
        return self._status(user)[0]

    def get_friendship_id(self, user) -> int | None:
        """Id of the request or friendship (to accept / cancel / unfriend), or null."""
        row = self._status(user)[1]
        return row.pk if row else None


class SharedHabitInfoSerializer(serializers.ModelSerializer):
    """The habit itself, as friends see it: what it is and how often, nothing more."""

    class Meta:
        model = Habit
        fields = [
            "id",
            "name",
            "target",
            "icon",
            "color",
            "schedule_type",
            "weekdays",
            "times_per_week",
        ]
        read_only_fields = fields


class SharedHabitSerializer(serializers.Serializer):
    """One habit on a friend's profile, with its streak (from habits.streaks.shared_habits)."""

    habit = SharedHabitInfoSerializer()
    current_streak = serializers.IntegerField()
    longest_streak = serializers.IntegerField()
    streak_unit = serializers.ChoiceField(choices=["days", "weeks"])
    done_today = serializers.BooleanField(help_text="Done today, in the owner's time zone.")
    week_progress = WeekProgressSerializer(
        allow_null=True, help_text="Only for 'times per week' habits."
    )


class ProfileSerializer(SearchResultSerializer):
    """Someone's profile page. Needs `statuses` and `habits` in the context.

    `habits` is null when the viewer isn't allowed to see them (not friends), so the
    app can tell "not friends" apart from "friends, but nothing shared".
    """

    date_joined = serializers.DateTimeField(read_only=True)
    habits = serializers.SerializerMethodField()

    class Meta(SearchResultSerializer.Meta):
        fields = [*SearchResultSerializer.Meta.fields, "date_joined", "habits"]
        read_only_fields = fields

    @extend_schema_field(
        serializers.ChoiceField(
            choices=[
                services.SELF,
                services.NONE,
                services.REQUEST_SENT,
                services.REQUEST_RECEIVED,
                services.FRIENDS,
            ]
        )
    )
    def get_friendship_status(self, user) -> str:
        """`self` (your own profile), `none`, `request_sent`, `request_received` or `friends`."""
        return super().get_friendship_status(user)

    @extend_schema_field(SharedHabitSerializer(many=True, allow_null=True))
    def get_habits(self, user) -> list | None:
        """Habits shared with friends, with streaks. Null if you're not friends."""
        habits = self.context["habits"]
        return None if habits is None else SharedHabitSerializer(habits, many=True).data


class FriendshipSerializer(serializers.ModelSerializer):
    """A friend request or a friendship, seen by the logged-in user.

    `user` is always **the other person**; `direction` says who asked:
    `incoming` (they asked me) or `outgoing` (I asked them).
    """

    user = serializers.SerializerMethodField()
    direction = serializers.SerializerMethodField()

    class Meta:
        model = Friendship
        fields = ["id", "user", "status", "direction", "created_at", "accepted_at"]
        read_only_fields = fields

    def _me(self):
        return self.context["request"].user

    @extend_schema_field(UserCardSerializer)
    def get_user(self, friendship) -> dict:
        return UserCardSerializer(friendship.other(self._me()), context=self.context).data

    @extend_schema_field(serializers.ChoiceField(choices=["incoming", "outgoing"]))
    def get_direction(self, friendship) -> str:
        return "outgoing" if friendship.from_user_id == self._me().pk else "incoming"


class SendRequestSerializer(serializers.Serializer):
    """Body for sending a friend request."""

    username = serializers.CharField(help_text="The @username of the person to add (no @).")

    def validate_username(self, value: str):
        username = value.strip().lstrip("@")
        user = User.objects.filter(username__iexact=username, is_active=True).first()
        if user is None:
            raise serializers.ValidationError("We couldn't find anyone with that username.")
        if user.pk == self.context["request"].user.pk:
            raise serializers.ValidationError("You can't send a friend request to yourself.")
        return user


class RequestListSerializer(serializers.Serializer):
    """Read-only: the shape of GET /api/friends/requests/."""

    incoming = FriendshipSerializer(many=True, help_text="Requests waiting for my answer.")
    outgoing = FriendshipSerializer(many=True, help_text="My requests waiting for their answer.")
