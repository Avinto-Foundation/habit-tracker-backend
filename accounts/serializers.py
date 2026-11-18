from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import validate_timezone

User = get_user_model()


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
