from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .dates import is_today_or_yesterday
from .models import CheckIn, Habit
from .serializers import (
    CheckInNoteSerializer,
    CheckInSerializer,
    DateRangeSerializer,
    HabitSerializer,
    HabitStatsSerializer,
    MonthQuerySerializer,
    TodaySerializer,
)
from .streaks import habit_stats, today_overview

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
        habits = Habit.objects.filter(owner=self.request.user)
        if self.action == "list":
            show_archived = self.request.query_params.get("archived", "").lower() == "true"
            habits = habits.filter(archived=show_archived)
        return habits

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

    @extend_schema(
        summary="Today's habits",
        description=(
            "Everything for the Today page in one request, in your profile time zone.\n\n"
            "* `due`: active habits due today. Every day: always. Specific days: when today is "
            "one of them. Times per week: until this week's goal is met (and on the day it "
            "was ticked off).\n"
            "* `not_due`: your other active habits (they can still be ticked off as a bonus).\n"
            "* `summary`: how many of the `due` habits are done.\n\n"
            "Archived habits are left out."
        ),
        responses=TodaySerializer,
    )
    @action(detail=False, methods=["get"])
    def today(self, request):
        habits = (
            Habit.objects.filter(owner=request.user, archived=False)
            .prefetch_related("checkins")
            .order_by("created_at", "id")
        )
        return Response(TodaySerializer(today_overview(request.user, habits)).data)

    @extend_schema(
        summary="Streaks and progress for a habit",
        description=(
            "Works in your profile time zone.\n\n"
            "* `current_streak` / `longest_streak`: in **days** (every day / specific days: "
            "scheduled days in a row that were done) or **weeks** (times per week: weeks in "
            "a row that met the goal), see `streak_unit`. Today / this week only breaks the "
            "streak once it's over.\n"
            "* `completion_rate`: percent of the plan done in the last 30 days.\n"
            "* `week_progress`: this week's check-ins vs goal (weekly habits only).\n"
            "* `calendar`: add `?month=YYYY-MM` to get every day of that month as `done`, "
            "`bonus` (done on a day off), `missed`, `pending` (today, not done yet), `off`, "
            "`future` or `before_start`.\n\n" + ONLY_YOURS
        ),
        parameters=[
            OpenApiParameter(
                "month", OpenApiTypes.STR, description="YYYY-MM, e.g. 2026-11. Adds `calendar`."
            )
        ],
        responses=HabitStatsSerializer,
    )
    @action(detail=True, methods=["get"])
    def stats(self, request, pk=None):
        habit = self.get_object()
        query = MonthQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        stats = habit_stats(habit, month=query.validated_data.get("month"))
        return Response(HabitStatsSerializer(stats).data)


# --- Check-ins -------------------------------------------------------------------

CHECKIN_EXAMPLE = {
    "id": 7,
    "habit": 1,
    "date": "2026-11-20",
    "note": "Read on the bus",
    "created_at": "2026-11-20T08:15:00Z",
}
DATE_PARAM = OpenApiParameter(
    "date", OpenApiTypes.DATE, OpenApiParameter.PATH, description="The check-in day, YYYY-MM-DD."
)


class HabitCheckInsMixin:
    """Finds the habit in the URL, but only among the logged-in user's habits."""

    def get_habit(self) -> Habit:
        return get_object_or_404(Habit, pk=self.kwargs["habit_id"], owner=self.request.user)


@extend_schema(tags=["check-ins"])
class CheckInListCreateView(HabitCheckInsMixin, generics.GenericAPIView):
    """GET / POST /api/habits/<habit_id>/checkins/"""

    serializer_class = CheckInSerializer

    @extend_schema(
        summary="List a habit's check-ins",
        description="Oldest first. Filter with `?from=` and/or `?to=` (YYYY-MM-DD, inclusive). "
        + ONLY_YOURS,
        parameters=[
            OpenApiParameter("from", OpenApiTypes.DATE, description="First day to include."),
            OpenApiParameter("to", OpenApiTypes.DATE, description="Last day to include."),
        ],
        responses=CheckInSerializer(many=True),
    )
    def get(self, request, habit_id):
        habit = self.get_habit()
        dates = DateRangeSerializer(data=request.query_params)
        dates.is_valid(raise_exception=True)

        checkins = habit.checkins.all()
        if "from" in dates.validated_data:
            checkins = checkins.filter(date__gte=dates.validated_data["from"])
        if "to" in dates.validated_data:
            checkins = checkins.filter(date__lte=dates.validated_data["to"])
        return Response(CheckInSerializer(checkins, many=True).data)

    @extend_schema(
        summary="Check in (tick off the habit)",
        description=(
            "Marks the habit done for **today** (in your profile time zone), or for "
            "**yesterday** with `date`. Older or future days are refused, and so are days "
            "before the habit was created and archived habits.\n\n"
            "Safe to send twice: if the day is already checked in you get the existing "
            "check-in back with **200** (a new `note` replaces the old one). A new check-in "
            "gives **201**. " + ONLY_YOURS
        ),
        examples=[
            OpenApiExample("Today", value={}, request_only=True),
            OpenApiExample("Today, with a note", value={"note": "Read on the bus"}, request_only=True),
            OpenApiExample("Yesterday", value={"date": "2026-11-19"}, request_only=True),
            OpenApiExample("Check-in", value=CHECKIN_EXAMPLE, response_only=True),
        ],
        responses={200: CheckInSerializer, 201: CheckInSerializer},
    )
    def post(self, request, habit_id):
        serializer = CheckInSerializer(data=request.data, context={"habit": self.get_habit()})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        code = status.HTTP_201_CREATED if serializer.was_created else status.HTTP_200_OK
        return Response(serializer.data, status=code)


@extend_schema(tags=["check-ins"], parameters=[DATE_PARAM])
class CheckInDetailView(HabitCheckInsMixin, generics.GenericAPIView):
    """PATCH / DELETE /api/habits/<habit_id>/checkins/<date>/"""

    serializer_class = CheckInNoteSerializer

    def get_object(self) -> CheckIn:
        return get_object_or_404(CheckIn, habit=self.get_habit(), date=self.kwargs["date"])

    @extend_schema(
        summary="Edit a check-in's note",
        examples=[OpenApiExample("Note", value={"note": "Only 10 pages today"}, request_only=True)],
    )
    def patch(self, request, habit_id, date):
        serializer = CheckInNoteSerializer(self.get_object(), data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @extend_schema(
        summary="Undo a check-in",
        description="Only for today or yesterday, like checking in. " + ONLY_YOURS,
        responses={204: None},
    )
    def delete(self, request, habit_id, date):
        checkin = self.get_object()
        if not is_today_or_yesterday(checkin.date, request.user):
            raise ValidationError({"date": "You can only undo today's or yesterday's check-in."})
        checkin.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
