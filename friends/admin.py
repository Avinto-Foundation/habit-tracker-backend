from django.contrib import admin

from .models import Friendship


@admin.register(Friendship)
class FriendshipAdmin(admin.ModelAdmin):
    list_display = ["__str__", "from_user", "to_user", "status", "created_at", "accepted_at"]
    list_filter = ["status"]
    search_fields = [
        "from_user__username",
        "from_user__email",
        "to_user__username",
        "to_user__email",
    ]
    autocomplete_fields = ["from_user", "to_user"]
    readonly_fields = ["created_at"]
    list_select_related = ["from_user", "to_user"]
