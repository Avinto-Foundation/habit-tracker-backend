from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.models import update_last_login
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import exceptions, serializers
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken

from .models import validate_timezone
from .tokens import RememberMeRefreshToken, refresh_token_for

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    """The public details of a user, as sent to the frontend."""

    class Meta:
        model = User
        fields = ["id", "full_name", "username", "email", "timezone"]
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    """Checks sign-up data and creates the user.

    Passwords are write-only, so they are never sent back in a response.
    """

    full_name = serializers.CharField(max_length=150)
    username = serializers.RegexField(
        r"^[A-Za-z0-9_]{3,30}$",
        error_messages={
            "invalid": "Use 3-30 characters: letters, numbers and underscores only.",
        },
    )
    # Declared by hand so we can check uniqueness ourselves, ignoring upper/lower case.
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )
    password_confirm = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )
    timezone = serializers.CharField(
        max_length=64,
        required=False,
        default="UTC",
        validators=[validate_timezone],
        help_text="Time zone name, e.g. Asia/Kathmandu. Defaults to UTC.",
    )

    class Meta:
        model = User
        fields = ["id", "full_name", "username", "email", "password", "password_confirm", "timezone"]
        read_only_fields = ["id"]

    def validate_full_name(self, value: str) -> str:
        return value.strip()

    def validate_email(self, value: str) -> str:
        email = value.strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return email

    def validate_username(self, value: str) -> str:
        if User.objects.filter(username__iexact=value).exists():
            raise serializers.ValidationError("This username is already taken.")
        return value

    def validate(self, attrs: dict) -> dict:
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "Passwords don't match."})

        # Run Django's password rules (length, common passwords, all numbers, and
        # "too similar to your name/email"). The similarity check needs an unsaved
        # user with the other details filled in.
        candidate = User(
            full_name=attrs["full_name"], username=attrs["username"], email=attrs["email"]
        )
        try:
            validate_password(attrs["password"], user=candidate)
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": list(error.messages)})

        return attrs

    def create(self, validated_data: dict):
        validated_data.pop("password_confirm")
        # create_user hashes the password; never store it as plain text.
        return User.objects.create_user(**validated_data)


class LoginSerializer(serializers.Serializer):
    """Checks email + password and returns JWT tokens plus the user's details."""

    email = serializers.EmailField(write_only=True)
    password = serializers.CharField(
        write_only=True, trim_whitespace=False, style={"input_type": "password"}
    )
    remember_me = serializers.BooleanField(
        write_only=True,
        required=False,
        default=False,
        help_text="Stay logged in for 7 days instead of 1.",
    )
    access = serializers.CharField(
        read_only=True, help_text="Send as 'Authorization: Bearer <access>'. Lasts 15 minutes."
    )
    refresh = serializers.CharField(
        read_only=True, help_text="Gets a new access token. Lasts 1 day (7 with remember_me)."
    )
    user = UserSerializer(read_only=True)

    def validate(self, attrs: dict) -> dict:
        user = authenticate(
            request=self.context.get("request"),
            email=attrs["email"].strip().lower(),  # emails are stored in lowercase
            password=attrs["password"],
        )
        # Same message for "no such email" and "wrong password", so nobody can
        # use this form to find out which emails have accounts.
        if user is None or not user.is_active:
            raise exceptions.AuthenticationFailed("Email or password is incorrect.")

        refresh = refresh_token_for(user, remember_me=attrs["remember_me"])
        update_last_login(None, user)
        return {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        }


class RefreshSerializer(TokenRefreshSerializer):
    """Swaps a refresh token for a new access token (and a new refresh token).

    A "Remember me" token stays a 7-day token after refreshing.
    """

    def validate(self, attrs: dict) -> dict:
        # Reading the token also checks its signature, expiry and the blacklist.
        token = RefreshToken(attrs["refresh"])
        if token.get("remember_me"):
            self.token_class = RememberMeRefreshToken
        try:
            return super().validate(attrs)
        except User.DoesNotExist:
            raise exceptions.AuthenticationFailed("This account no longer exists.")


class LogoutSerializer(serializers.Serializer):
    """Blacklists a refresh token so it can never be used again."""

    refresh = serializers.CharField(write_only=True)

    def validate(self, attrs: dict) -> dict:
        RefreshToken(attrs["refresh"]).blacklist()
        return {}
