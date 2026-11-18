from django.urls import path

from .views import RegisterView

# Mounted at /api/auth/ in config/urls.py
urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
]
