from django.contrib import admin

from .models import Habit


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
