import pytest
from django.urls import reverse
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_openapi_schema_is_public_and_lists_health():
    response = APIClient().get(reverse("schema"), {"format": "json"})

    assert response.status_code == 200
    assert "/api/health/" in response.json()["paths"]


@pytest.mark.django_db
def test_swagger_ui_is_public():
    response = APIClient().get(reverse("swagger-ui"))

    assert response.status_code == 200
