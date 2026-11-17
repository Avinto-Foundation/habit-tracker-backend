import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError


@pytest.mark.django_db
def test_custom_user_model_is_used():
    assert get_user_model()._meta.label == "accounts.User"


@pytest.mark.django_db
def test_email_must_be_unique():
    User = get_user_model()
    User.objects.create_user(username="sam", email="sam@example.com", password="x-Strong-pass-1")

    with pytest.raises(IntegrityError):
        User.objects.create_user(username="sam2", email="sam@example.com", password="x-Strong-pass-1")
