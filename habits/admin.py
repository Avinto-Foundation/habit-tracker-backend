from django.contrib import admin

from .models import CheckIn, Habit


@admin.register(Habit)
class HabitAdmin(admin.ModelAdmin):
    list_display = ["__str__", "owner", "schedule_type", "archived", "created_at"]
    list_filter = ["schedule_type", "archived"]
    search_fields = ["name", "owner__email", "owner__username"]
    autocomplete_fields = ["owner"]  # search users instead of a huge dropdown
    readonly_fields = ["created_at", "updated_at"]
    fieldsets = (
        (None, {"fields": ("owner", "name", "target", "icon", "color")}),
        ("Schedule", {"fields": ("schedule_type", "weekdays", "times_per_week")}),
        ("Status", {"fields": ("archived", "created_at", "updated_at")}),
    )


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    list_display = ["habit", "owner", "date", "note", "created_at"]
    list_filter = ["date"]
    search_fields = ["habit__name", "habit__owner__email", "note"]
    autocomplete_fields = ["habit"]
    readonly_fields = ["created_at"]
    date_hierarchy = "date"
    list_select_related = ["habit__owner"]

    @admin.display(ordering="habit__owner__email")
    def owner(self, checkin: CheckIn):
        return checkin.habit.owner
