from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Django's user admin, adjusted for email login, full name, time zone, bio and photo."""

    ordering = ["email"]
    list_display = ["email", "username", "full_name", "timezone", "is_staff"]
    search_fields = ["email", "username", "full_name"]

    # The "edit user" page
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("username", "full_name", "timezone", "bio", "avatar")}),
        (
            "Permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Important dates", {"fields": ("last_login", "date_joined")}),
    )

    # The "add user" page
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "username", "full_name", "timezone", "password1", "password2"),
            },
        ),
    )
