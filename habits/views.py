from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
)
from rest_framework import viewsets

from .models import Habit
from .serializers import HabitSerializer

DAILY_EXAMPLE = {
    "name": "Read",
    "target": "20 pages",
    "icon": "📚",
    "color": "#0F766E",
    "schedule_type": "daily",
}
WEEKDAYS_EXAMPLE = {
    "name": "Gym",
    "icon": "🏋️",
    "color": "#B45309",
    "schedule_type": "weekdays",
    "weekdays": [0, 2, 4],
}
TIMES_EXAMPLE = {
    "name": "Call family",
    "icon": "📞",
    "schedule_type": "times_per_week",
    "times_per_week": 2,
}

ONLY_YOURS = "You only ever see and change your own habits; other people's give 404."


@extend_schema_view(
    list=extend_schema(
        summary="List my habits",
        description=(
            "Your habits, oldest first. Archived habits are left out unless you ask for "
            "them with `?archived=true` (then you get only the archived ones)."
        ),
        parameters=[
            OpenApiParameter(
                "archived",
                OpenApiTypes.BOOL,
                description="`true` = only archived habits. Default: only active habits.",
            )
        ],
    ),
    create=extend_schema(
        summary="Create a habit",
        description=(
            "Only `name` is required. Defaults: icon ✅, colour #0F766E, schedule `daily`.\n\n"
            "Schedules:\n"
            "* `daily`: every day.\n"
            "* `weekdays`: also send `weekdays`, the days as numbers, 0 = Monday … 6 = Sunday.\n"
            "* `times_per_week`: also send `times_per_week`, 1 to 7."
        ),
        examples=[
            OpenApiExample("Every day", value=DAILY_EXAMPLE, request_only=True),
            OpenApiExample("Mon / Wed / Fri", value=WEEKDAYS_EXAMPLE, request_only=True),
            OpenApiExample("Twice a week", value=TIMES_EXAMPLE, request_only=True),
        ],
    ),
    retrieve=extend_schema(summary="Get one habit", description=ONLY_YOURS),
    partial_update=extend_schema(
        summary="Edit a habit (or archive / unarchive it)",
        description=(
            "Send only the fields you want to change. Send `{\"archived\": true}` to archive "
            "(hide it but keep its history) and `{\"archived\": false}` to bring it back.\n\n"
            "Changing `schedule_type` drops the old days / count, so send the new ones with it. "
            + ONLY_YOURS
        ),
        examples=[
            OpenApiExample("Archive", value={"archived": True}, request_only=True),
            OpenApiExample(
                "Switch to Mon–Fri",
                value={"schedule_type": "weekdays", "weekdays": [0, 1, 2, 3, 4]},
                request_only=True,
            ),
        ],
    ),
    destroy=extend_schema(
        summary="Delete a habit",
        description="Deletes it for good, with its history. To keep the history, archive it. "
        + ONLY_YOURS,
    ),
)
@extend_schema(tags=["habits"])
class HabitViewSet(viewsets.ModelViewSet):
    """/api/habits/ and /api/habits/<id>/: the logged-in user's habits.

    Login is required (project default permission). The queryset only contains the
    user's own habits, so someone else's habit id simply isn't found (404). That way
    we don't even reveal that it exists.
    """

    serializer_class = HabitSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]  # no PUT

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # Swagger docs being built: no user
            return Habit.objects.none()
        habits =Habit.objects.filter(owner=self.request.user)
        if self.action == "list":
            show_archived = self.request.query_params.get("archived", "").lower() == "true"
            habits = habits.filter(archived=show_archived)
        return habits

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
