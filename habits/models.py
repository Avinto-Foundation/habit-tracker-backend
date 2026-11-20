from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from .dates import local_date

DEFAULT_ICON = "✅"
DEFAULT_COLOR = "#0F766E"  # the app's teal

validate_hex_color = RegexValidator(
    regex=r"^#[0-9A-Fa-f]{6}$",
    message="Use a colour like #0F766E.",
)


def validate_icon(value: str) -> None:
    """An icon is a single emoji (which may be several characters long, like 🏃‍♀️),
    not a word. So: no spaces and no plain letters or digits."""
    if not value or any(ch.isspace() or (ch.isascii() and ch.isalnum()) for ch in value):
        raise ValidationError("Choose an emoji as the icon.")


def schedule_errors(schedule_type: str, weekdays: list, times_per_week: int | None) -> dict:
    """Check that the schedule's parts fit together.

    Returns ``{field: message}`` for every problem (empty when all is fine). Shared by
    the model (Django admin) and the API serializer so the rules live in one place.
    """
    errors = {}
    if schedule_type == Habit.Schedule.WEEKDAYS:
        if not weekdays:
            errors["weekdays"] = "Pick at least one day."
    elif weekdays:
        errors["weekdays"] = "Days are only used when the schedule is 'specific days'."

    if schedule_type == Habit.Schedule.TIMES_PER_WEEK:
        if times_per_week is None:
            errors["times_per_week"] = "How many times a week? Choose 1 to 7."
    elif times_per_week is not None:
        errors["times_per_week"] = "Only used when the schedule is 'times per week'."
    return errors


class Habit(models.Model):
    """Something a user wants to do regularly, e.g. "Read 📚, 20 pages, every day".

    The schedule says which days the habit is "due"; later it decides how streaks
    are counted:

    * ``daily``: every day.
    * ``weekdays``: only on the days in ``weekdays`` (0 = Monday … 6 = Sunday).
    * ``times_per_week``: any days, ``times_per_week`` times per week (Mon–Sun).
    """

    class Schedule(models.TextChoices):
        DAILY = "daily", "Every day"
        WEEKDAYS = "weekdays", "Specific days"
        TIMES_PER_WEEK = "times_per_week", "Times per week"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="habits"
    )
    name = models.CharField(max_length=80)
    target = models.CharField(
        max_length=80, blank=True, help_text='Optional goal shown with the habit, e.g. "20 pages".'
    )
    icon = models.CharField(max_length=16, default=DEFAULT_ICON, validators=[validate_icon])
    color = models.CharField(max_length=7, default=DEFAULT_COLOR, validators=[validate_hex_color])

    schedule_type = models.CharField(
        max_length=20, choices=Schedule.choices, default=Schedule.DAILY
    )
    weekdays = models.JSONField(
        default=list, blank=True, help_text="For 'specific days': 0 = Monday … 6 = Sunday."
    )
    times_per_week = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(7)],
        help_text="For 'times per week': 1 to 7.",
    )

    archived = models.BooleanField(
        default=False, help_text="Archived habits are hidden but keep their history."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        constraints = [
            # A safety net in the database itself, on top of the validation above.
            models.CheckConstraint(
                condition=models.Q(times_per_week__isnull=True)
                | models.Q(times_per_week__gte=1, times_per_week__lte=7),
                name="habit_times_per_week_1_to_7",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.icon} {self.name}"

    def created_on(self):
        """The day the habit was created, in the owner's time zone."""
        return local_date(self.created_at, self.owner)

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.weekdays, list) or any(
            not isinstance(day, int) or not 0 <= day <= 6 for day in self.weekdays
        ):
            raise ValidationError({"weekdays": "Use a list of day numbers from 0 (Mon) to 6 (Sun)."})
        errors = schedule_errors(self.schedule_type, self.weekdays, self.times_per_week)
        if errors:
            raise ValidationError(errors)


class CheckIn(models.Model):
    """"I did this habit on this day." At most one per habit per day.

    `date` is the user's own calendar day (their profile time zone), not UTC.
    """

    habit = models.ForeignKey(Habit, on_delete=models.CASCADE, related_name="checkins")
    date = models.DateField()
    note = models.CharField(max_length=280, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date"]
        constraints = [
            models.UniqueConstraint(fields=["habit", "date"], name="one_checkin_per_habit_per_day"),
        ]

    def __str__(self) -> str:
        return f"{self.habit} on {self.date}"
