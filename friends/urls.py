from django.urls import path

from .views import (
    FriendListView,
    FriendRequestAcceptView,
    FriendRequestCancelView,
    FriendRequestDeclineView,
    FriendRequestListCreateView,
    UnfriendView,
    UserSearchView,
)

# Mounted at /api/ in config/urls.py
urlpatterns = [
    path("users/search/", UserSearchView.as_view(), name="user-search"),
    path("friends/", FriendListView.as_view(), name="friend-list"),
    path("friends/<int:pk>/", UnfriendView.as_view(), name="friend-detail"),
    path("friends/requests/", FriendRequestListCreateView.as_view(), name="friend-requests"),
    path(
        "friends/requests/<int:pk>/", FriendRequestCancelView.as_view(), name="friend-request"
    ),
    path(
        "friends/requests/<int:pk>/accept/",
        FriendRequestAcceptView.as_view(),
        name="friend-request-accept",
    ),
    path(
        "friends/requests/<int:pk>/decline/",
        FriendRequestDeclineView.as_view(),
        name="friend-request-decline",
    ),
]
