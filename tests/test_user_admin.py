import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

User = get_user_model()


@pytest.fixture
def admin_client(client):
    """A test browser that is logged in to the Django admin."""
    admin = User.objects.create_superuser(
        email="admin@example.com", username="admin", full_name="Admin", password="x-Strong-pass-1"
    )
    client.force_login(admin)
    return client, admin


@pytest.mark.django_db
def test_admin_user_list_page_loads(admin_client):
    client, _ = admin_client

    response = client.get(reverse("admin:accounts_user_changelist"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_add_user_page_loads(admin_client):
    client, _ = admin_client

    response = client.get(reverse("admin:accounts_user_add"))

    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_edit_user_page_loads(admin_client):
    client, admin = admin_client

    response = client.get(reverse("admin:accounts_user_change", args=[admin.pk]))

    assert response.status_code == 200


@pytest.mark.django_db
def test_admin_can_create_user(admin_client):
    client, _ = admin_client

    client.post(
        reverse("admin:accounts_user_add"),
        {
            "email": "new@example.com",
            "username": "newbie",
            "full_name": "New Person",
            "timezone": "Asia/Kathmandu",
            "password1": "x-Strong-pass-1",
            "password2": "x-Strong-pass-1",
            "usable_password": "true",
        },
    )

    user = User.objects.get(email="new@example.com")
    assert user.full_name == "New Person"
    assert user.timezone == "Asia/Kathmandu"
    assert user.check_password("x-Strong-pass-1")
