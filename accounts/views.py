from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .serializers import (
    GoogleLoginSerializer,
    LoginSerializer,
    LogoutSerializer,
    MeSerializer,
    RefreshSerializer,
    RegisterSerializer,
)

USER_EXAMPLE = {
    "id": 1,
    "full_name": "Samikshya Adhikari",
    "username": "samikshya",
    "email": "sam@example.com",
    "timezone": "Asia/Kathmandu",
}
TOKEN_EXAMPLE = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."


def error_response(description: str, example: dict) -> OpenApiResponse:
    """Swagger docs for an error response with one example body."""
    return OpenApiResponse(
        response=OpenApiTypes.OBJECT,
        description=description,
        examples=[OpenApiExample(description, value=example)],
    )


class PublicTokenView(generics.GenericAPIView):
    """Base for the token endpoints: open to everyone, and bad tokens or
    credentials give a proper 401 (not 403 or a server error)."""

    permission_classes = [AllowAny]
    authentication_classes = []  # These endpoints are how you *get* logged in.

    def get_authenticate_header(self, request) -> str:
        # Without this, DRF turns 401 into 403 when a view has no authentication class.
        return 'Bearer realm="api"'

    def handle_exception(self, exc):
        if isinstance(exc, TokenError):  # expired, tampered with or blacklisted token
            exc = InvalidToken(exc.args[0])
        return super().handle_exception(exc)


# --- Sign up -----------------------------------------------------------------


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
                "Account created", response_only=True, status_codes=["201"], value=USER_EXAMPLE
            ),
        ],
        responses={
            201: RegisterSerializer,
            400: error_response(
                "Invalid data. Each field with a problem has a list of messages.",
                {
                    "email": ["An account with this email already exists."],
                    "password_confirm": ["Passwords don't match."],
                },
            ),
        },
    )
)
class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/: create a new account."""

    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    authentication_classes = []  # Signing up never needs an existing login.


# --- Log in ------------------------------------------------------------------


class LoginView(PublicTokenView):
    """POST /api/auth/login/: swap email + password for JWT tokens."""

    serializer_class = LoginSerializer

    @extend_schema(
        summary="Log in",
        description=(
            "Log in with email and password. Returns an **access** token (15 minutes) and a "
            "**refresh** token (1 day, or 7 days with `remember_me`), plus the user's details.\n\n"
            "Send the access token on later requests as `Authorization: Bearer <access>`. "
            "In Swagger, click **Authorize** and paste the access token."
        ),
        tags=["auth"],
        examples=[
            OpenApiExample(
                "Log in",
                request_only=True,
                value={"email": "sam@example.com", "password": "my-Strong-pass-1", "remember_me": True},
            ),
            OpenApiExample(
                "Logged in",
                response_only=True,
                status_codes=["200"],
                value={"access": TOKEN_EXAMPLE, "refresh": TOKEN_EXAMPLE, "user": USER_EXAMPLE},
            ),
        ],
        responses={
            200: LoginSerializer,
            400: error_response("A field is missing or invalid.", {"email": ["This field is required."]}),
            401: error_response(
                "Wrong email or password.", {"detail": "Email or password is incorrect."}
            ),
        },
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


# --- Refresh -----------------------------------------------------------------


class RefreshView(PublicTokenView):
    """POST /api/auth/token/refresh/: get a new access token."""

    serializer_class = RefreshSerializer

    @extend_schema(
        summary="Get a new access token",
        description=(
            "Send your refresh token to get a new access token **and** a new refresh token. "
            "The old refresh token stops working, so always keep the newest one."
        ),
        tags=["auth"],
        examples=[
            OpenApiExample("Refresh", request_only=True, value={"refresh": TOKEN_EXAMPLE}),
            OpenApiExample(
                "New tokens",
                response_only=True,
                status_codes=["200"],
                value={"access": TOKEN_EXAMPLE, "refresh": TOKEN_EXAMPLE},
            ),
        ],
        responses={
            200: RefreshSerializer,
            401: error_response(
                "The refresh token is expired, invalid or already used.",
                {"detail": "Token is blacklisted", "code": "token_not_valid"},
            ),
        },
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


# --- Log out -----------------------------------------------------------------


class LogoutView(PublicTokenView):
    """POST /api/auth/logout/: make a refresh token unusable."""

    serializer_class = LogoutSerializer

    @extend_schema(
        summary="Log out",
        description=(
            "Blacklists the refresh token so it can't be used again. The frontend should also "
            "delete both tokens. (An access token keeps working until it expires, at most "
            "15 minutes.)"
        ),
        tags=["auth"],
        examples=[OpenApiExample("Log out", request_only=True, value={"refresh": TOKEN_EXAMPLE})],
        responses={
            205: OpenApiResponse(description="Logged out. No response body."),
            401: error_response(
                "The refresh token is expired, invalid or already used.",
                {"detail": "Token is blacklisted", "code": "token_not_valid"},
            ),
        },
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(status=status.HTTP_205_RESET_CONTENT)


# --- Google sign-in ----------------------------------------------------------


class GoogleLoginView(PublicTokenView):
    """POST /api/auth/google/: sign up or log in with a Google account."""

    serializer_class = GoogleLoginSerializer

    @extend_schema(
        summary="Continue with Google",
        description=(
            "Send the ID token (the `credential`) the frontend got from Google's sign-in "
            "button. The backend checks it with Google, then:\n\n"
            "- **email already has an account** → logs in to that account (**200**)\n"
            "- **new email** → creates an account (**201**) with the name from Google and a "
            "username made from the email (e.g. `john_doe`). It has no password.\n\n"
            "Returns the same tokens as normal login, plus `created`."
        ),
        tags=["auth"],
        examples=[
            OpenApiExample(
                "Google sign-in",
                request_only=True,
                value={"id_token": TOKEN_EXAMPLE, "remember_me": True, "timezone": "Asia/Kathmandu"},
            ),
            OpenApiExample(
                "New account",
                response_only=True,
                status_codes=["201"],
                value={
                    "access": TOKEN_EXAMPLE,
                    "refresh": TOKEN_EXAMPLE,
                    "user": USER_EXAMPLE,
                    "created": True,
                },
            ),
        ],
        responses={
            200: GoogleLoginSerializer,
            201: GoogleLoginSerializer,
            400: error_response("`id_token` is missing.", {"id_token": ["This field is required."]}),
            401: error_response(
                "The Google token is fake, expired, for another app, or the email isn't verified.",
                {"detail": "Google sign-in failed. Please try again."},
            ),
            503: error_response(
                "Google sign-in isn't set up on the server, or Google can't be reached.",
                {"detail": "Google sign-in is not available right now. Please use email and password."},
            ),
        },
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        return Response(data, status=status.HTTP_201_CREATED if data["created"] else status.HTTP_200_OK)


# --- Current user ------------------------------------------------------------

NOT_LOGGED_IN = error_response(
    "No valid access token was sent.",
    {"detail": "Authentication credentials were not provided."},
)


@extend_schema_view(
    get=extend_schema(
        summary="Get the logged-in user",
        description=(
            "Returns your own details. Needs `Authorization: Bearer <access token>` "
            "(in Swagger: log in, then click **Authorize** and paste the access token)."
        ),
        tags=["auth"],
        responses={200: MeSerializer, 401: NOT_LOGGED_IN},
    ),
    patch=extend_schema(
        summary="Update the logged-in user",
        description=(
            "Change your `full_name`, `username` and/or `timezone`. Send only the fields you "
            "want to change. Same rules as sign-up. `email` and `id` can't be changed here."
        ),
        tags=["auth"],
        examples=[
            OpenApiExample(
                "Set time zone",
                request_only=True,
                value={"timezone": "Asia/Kathmandu"},
            ),
            OpenApiExample(
                "Updated",
                response_only=True,
                status_codes=["200"],
                value=USER_EXAMPLE,
            ),
        ],
        responses={
            200: MeSerializer,
            400: error_response(
                "Invalid data. Each field with a problem has a list of messages.",
                {"username": ["This username is already taken."]},
            ),
            401: NOT_LOGGED_IN,
        },
    ),
)
class MeView(generics.RetrieveUpdateAPIView):
    """GET / PATCH /api/auth/me/: the logged-in user's own details.

    Uses the project default permission (IsAuthenticated), so a valid access token
    is required.
    """

    serializer_class = MeSerializer
    http_method_names = ["get", "patch", "head", "options"]  # no PUT: always partial updates

    def get_object(self):
        return self.request.user

