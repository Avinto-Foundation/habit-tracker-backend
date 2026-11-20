from rest_framework import serializers

from .models import Habit, schedule_errors


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
