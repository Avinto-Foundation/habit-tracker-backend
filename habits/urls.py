from django.urls import path, register_converter
from rest_framework.routers import DefaultRouter

from .converters import IsoDateConverter
from .views import CheckInDetailView, CheckInListCreateView, HabitViewSet

register_converter(IsoDateConverter, "isodate")

# Gives /habits/ (name "habit-list") and /habits/<id>/ (name "habit-detail").
router = DefaultRouter()
router.include_root_view = False
router.register("habits", HabitViewSet, basename="habit")

urlpatterns = router.urls + [
    path(
        "habits/<int:habit_id>/checkins/",
        CheckInListCreateView.as_view(),
        name="habit-checkins",
    ),
    path(
        "habits/<int:habit_id>/checkins/<isodate:date>/",
        CheckInDetailView.as_view(),
        name="habit-checkin-detail",
    ),
]
