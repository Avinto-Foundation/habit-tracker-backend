from rest_framework.routers import DefaultRouter

from .views import HabitViewSet

# Gives /habits/ (name "habit-list") and /habits/<id>/ (name "habit-detail").
router = DefaultRouter()
router.include_root_view = False
router.register("habits", HabitViewSet, basename="habit")

urlpatterns = router.urls
