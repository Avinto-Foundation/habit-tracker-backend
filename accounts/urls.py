from django.urls import path

from .views import GoogleLoginView, LoginView, LogoutView, RefreshView, RegisterView

# Mounted at /api/auth/ in config/urls.py
urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("login/", LoginView.as_view(), name="login"),
    path("token/refresh/", RefreshView.as_view(), name="token-refresh"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("google/", GoogleLoginView.as_view(), name="google-login"),
]
