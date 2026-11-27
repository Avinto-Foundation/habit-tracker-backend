from rest_framework import serializers

from .dates import is_today_or_yesterday, user_today
from .models import CheckIn, Habit, schedule_errors


class HabitSerializer(serializers.ModelSerializer):
    """A habit as the API shows it, and the rules for creating or editing one."""

    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        required=False,
        help_text="For 'specific days': 0 = Monday … 6 = Sunday, e.g. [0, 2, 4].",
    )
    times_per_week = serializers.IntegerField(
        min_value=1,
        max_value=7,
        required=False,
        allow_null=True,
        help_text="For 'times per week': 1 to 7.",
    )

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
            "visibility",
            "archived",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_weekdays(self, value: list[int]) -> list[int]:
        return sorted(set(value))  # [4, 0, 0] -> [0, 4]

    def validate_color(self, value: str) -> str:
        return value.upper()

    def validate(self, attrs: dict) -> dict:
        """Check the schedule as a whole.

        When editing (PATCH), fields that weren't sent keep their saved values. If the
        schedule type changes, the old days / count are dropped instead of carried over,
        e.g. switching "specific days" to "every day" clears the days.
        """
        habit = self.instance
        schedule_type = attrs.get(
            "schedule_type", habit.schedule_type if habit else Habit.Schedule.DAILY
        )
        same_type = habit is not None and schedule_type == habit.schedule_type

        weekdays = attrs.get("weekdays", habit.weekdays if same_type else [])
        times_per_week = attrs.get("times_per_week", habit.times_per_week if same_type else None)

        errors = schedule_errors(schedule_type, weekdays, times_per_week)
        if errors:
            raise serializers.ValidationError(errors)

        attrs.update(
            schedule_type=schedule_type, weekdays=weekdays, times_per_week=times_per_week
        )
        return attrs


# --- Check-ins -----------------------------------------------------------------

ONLY_TODAY_OR_YESTERDAY = "You can only check in for today or yesterday."


class CheckInSerializer(serializers.ModelSerializer):
    """A check-in as the API shows it. Also used to check in (POST).

    Needs `habit` in the serializer context. `date` is optional and means "today"
    in the user's time zone when left out.
    """

    date = serializers.DateField(
        required=False, help_text="YYYY-MM-DD. Today or yesterday. Default: today."
    )

    class Meta:
        model = CheckIn
        fields = ["id", "habit", "date", "note", "created_at"]
        read_only_fields = ["id", "habit", "created_at"]

    def validate(self, attrs: dict) -> dict:
        habit = self.context["habit"]
        if habit.archived:
            raise serializers.ValidationError(
                {"habit": "This habit is archived. Unarchive it to check in."}
            )

        day = attrs.get("date", user_today(habit.owner))
        if not is_today_or_yesterday(day, habit.owner):
            raise serializers.ValidationError({"date": ONLY_TODAY_OR_YESTERDAY})
        if day < habit.created_on():
            raise serializers.ValidationError({"date": "That's before you created this habit."})

        attrs["date"] = day
        return attrs

    def create(self, validated_data: dict) -> CheckIn:
        """Check in, or return the existing check-in if this day is already done.

        Tapping twice (or a slow network sending the request twice) must never
        create two check-ins. A note sent the second time replaces the old note.
        """
        checkin, self.was_created = CheckIn.objects.get_or_create(
            habit=self.context["habit"],
            date=validated_data["date"],
            defaults={"note": validated_data.get("note", "")},
        )
        if not self.was_created and "note" in validated_data:
            checkin.note = validated_data["note"]
            checkin.save(update_fields=["note"])
        return checkin


class CheckInNoteSerializer(serializers.ModelSerializer):
    """Editing a check-in: only the note can change."""

    class Meta:
        model = CheckIn
        fields = ["id", "habit", "date", "note", "created_at"]
        read_only_fields = ["id", "habit", "date", "created_at"]
        extra_kwargs = {"note": {"required": True}}


class DateRangeSerializer(serializers.Serializer):
    """The `?from=YYYY-MM-DD&to=YYYY-MM-DD` filter for listing check-ins.

    Fields are added in get_fields() because `from` is a reserved word in Python.
    """

    def get_fields(self) -> dict:
        return {
            "from": serializers.DateField(required=False),
            "to": serializers.DateField(required=False),
        }

    def validate(self, attrs: dict) -> dict:
        start, end = attrs.get("from"), attrs.get("to")
        if start and end and start > end:
            raise serializers.ValidationError({"to": "Must be on or after 'from'."})
        return attrs


# --- Stats -------------------------------------------------------------------------


class MonthQuerySerializer(serializers.Serializer):
    """The optional `?month=YYYY-MM` for the stats calendar."""

    month = serializers.RegexField(
        r"^\d{4}-(0[1-9]|1[0-2])$",
        required=False,
        error_messages={"invalid": "Use YYYY-MM, e.g. 2026-11."},
    )

    def validate_month(self, value: str) -> tuple[int, int]:
        year, month = value.split("-")
        return int(year), int(month)


class CalendarDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    status = serializers.ChoiceField(
        choices=["done", "bonus", "missed", "pending", "off", "future", "before_start"]
    )


class CalendarSerializer(serializers.Serializer):
    month = serializers.CharField(help_text="YYYY-MM")
    days = CalendarDaySerializer(many=True)


class WeekProgressSerializer(serializers.Serializer):
    done = serializers.IntegerField(help_text="Check-ins so far this week (Mon–Sun).")
    goal = serializers.IntegerField(help_text="Check-ins needed this week.")


class HabitStatsSerializer(serializers.Serializer):
    """Read-only: the shape of GET /api/habits/<id>/stats/."""

    habit = serializers.IntegerField()
    today = serializers.DateField(help_text="Today in the user's time zone.")
    current_streak = serializers.IntegerField()
    longest_streak = serializers.IntegerField()
    streak_unit = serializers.ChoiceField(choices=["days", "weeks"])
    completion_rate = serializers.IntegerField(
        allow_null=True,
        help_text="Percent of the plan done in the last 30 days; null if nothing was due yet.",
    )
    total_checkins = serializers.IntegerField()
    done_today = serializers.BooleanField()
    week_progress = WeekProgressSerializer(
        allow_null=True, help_text="Only for 'times per week' habits."
    )
    calendar = CalendarSerializer(allow_null=True, help_text="Only when ?month= is given.")


# --- Today -----------------------------------------------------------------------------


class TodayHabitSerializer(serializers.Serializer):
    """One habit on the Today page."""

    habit = HabitSerializer()
    done_today = serializers.BooleanField()
    checkin = CheckInSerializer(allow_null=True, help_text="Today's check-in, if done.")
    current_streak = serializers.IntegerField()
    streak_unit = serializers.ChoiceField(choices=["days", "weeks"])
    week_progress = WeekProgressSerializer(
        allow_null=True, help_text="Only for 'times per week' habits."
    )


class TodaySummarySerializer(serializers.Serializer):
    done = serializers.IntegerField(help_text="Due habits done today.")
    total = serializers.IntegerField(help_text="Habits due today.")


class TodaySerializer(serializers.Serializer):
    """Read-only: the shape of GET /api/habits/today/."""

    date = serializers.DateField(help_text="Today in the user's time zone.")
    summary = TodaySummarySerializer()
    due = TodayHabitSerializer(many=True)
    not_due = TodayHabitSerializer(many=True, help_text="Can still be ticked off as a bonus.")
