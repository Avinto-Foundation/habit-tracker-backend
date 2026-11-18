from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics
from rest_framework.permissions import AllowAny

from .serializers import RegisterSerializer


@extend_schema_view(
    post=extend_schema(
        summary="Create an account",
        description=(
            "Sign up with full name, username, email and password. No login needed.\n\n"
            "Email and username are unique (upper/lower case is ignored). The password must "
            "follow Django's rules: at least 8 characters, not too common, not only numbers "
            "and not too similar to your name, username or email. `timezone` is optional "
            "and defaults to `UTC`."
        ),
        tags=["auth"],
        examples=[
            OpenApiExample(
                "Sign up",
                request_only=True,
                value={
                    "full_name": "Samikshya Adhikari",
                    "username": "samikshya",
                    "email": "sam@example.com",
                    "password": "my-Strong-pass-1",
                    "password_confirm": "my-Strong-pass-1",
                    "timezone": "Asia/Kathmandu",
                },
            ),
            OpenApiExample(
                "Account created",
                response_only=True,
                status_codes=["201"],
                value={
                    "id": 1,
                    "full_name": "Samikshya Adhikari",
                    "username": "samikshya",
                    "email": "sam@example.com",
                    "timezone": "Asia/Kathmandu",
                },
            ),
        ],
        responses={
            201: RegisterSerializer,
            400: OpenApiResponse(
                response=OpenApiTypes.OBJECT,
                description="Invalid data. Each field with a problem has a list of messages.",
                examples=[
                    OpenApiExample(
                        "Validation errors",
                        value={
                            "email": ["An account with this email already exists."],
                            "password_confirm": ["Passwords don't match."],
                        },
                    ),
                ],
            ),
        },
    )
)
class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/: create a new account."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []  # Signing up never needs an existing login.
