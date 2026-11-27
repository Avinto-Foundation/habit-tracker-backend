"""
Django settings for the Social Habit Tracker API.

Secrets and machine-specific values are read from a `.env` file in the
project root (see `.env.example`). Never commit `.env`.
"""

import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")


def env(name: str, default: str | None = None) -> str:
    """Read an environment variable, failing loudly if it is required and missing."""
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Missing environment variable: {name} (see .env.example)")
    return value


def env_list(name: str, default: str = "") -> list[str]:
    """Read a comma-separated environment variable as a list."""
    return [item.strip() for item in env(name, default).split(",") if item.strip()]


# --- Core -------------------------------------------------------------------

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")


# --- Apps -------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    # Local
    "accounts",
    "habits",
    "friends",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Database (PostgreSQL) --------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", "habit_tracker"),
        "USER": env("DB_USER", "postgres"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "5432"),
    }
}


# --- Auth -------------------------------------------------------------------

# Custom user model. Set before the first migration so we can change it later
# (adding fields like time zone or avatar) without rebuilding the database.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        # Reject passwords too similar to these user fields (we use full_name, not first/last).
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
        "OPTIONS": {"user_attributes": ("username", "full_name", "email")},
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --- Django REST Framework --------------------------------------------------

REST_FRAMEWORK = {
    # Requests prove who they are with "Authorization: Bearer <access token>".
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    # Limits for endpoints that could be abused (used with `throttle_scope` on a view).
    "DEFAULT_THROTTLE_RATES": {
        "password_reset": "5/hour",
        # Stops someone with a stolen login from guessing the current password.
        "password_change": "10/hour",
        # Stops anyone from spamming friend requests.
        "friend_request": "20/hour",
    },
}


# --- JWT (login tokens) -----------------------------------------------------

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    # Each refresh gives a new refresh token and blocks the old one.
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}
# How long a refresh token lasts when the user ticks "Remember me".
REMEMBER_ME_REFRESH_LIFETIME = timedelta(days=7)


# --- Password reset & email -------------------------------------------------

# Where the React app lives, for links in emails (e.g. the reset-password page).
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173").rstrip("/")

# Reset links stop working after 1 hour (Django's default is 3 days).
PASSWORD_RESET_TIMEOUT = 60 * 60

# By default emails are printed in the runserver terminal instead of being sent.
# To really send them, set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# and the EMAIL_HOST_* values in .env (see .env.example).
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_USE_TLS = env("EMAIL_USE_TLS", "True").lower() == "true"
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "HabitSquad <no-reply@habitsquad.local>")


# --- Google sign-in ---------------------------------------------------------

# OAuth Client ID from Google Cloud Console (the same one the frontend uses).
# Empty means Google sign-in is switched off and the endpoint answers 503.
GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID", "")


# --- API docs (Swagger / OpenAPI) -------------------------------------------

SPECTACULAR_SETTINGS = {
    "TITLE": "Social Habit Tracker API",
    "DESCRIPTION": "REST API for the Social Habit Tracker (AMPW Capstone).",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}


# --- CORS (lets the React app call the API) ----------------------------------

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")


# --- Internationalisation ---------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"  # Store everything in UTC; convert to the user's zone for streaks.
USE_I18N = True
USE_TZ = True


# --- Static files -----------------------------------------------------------

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# --- Uploaded files (profile photos) ------------------------------------------

# Saved in <project>/media/ and served at /media/... (by Django itself only while
# DEBUG is on; a real server or cloud storage serves them in production).
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
