from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response


@extend_schema(
    summary="Health check",
    description="Returns `ok` when the API is running. No login needed.",
    responses=inline_serializer("HealthResponse", fields={"status": serializers.CharField()}),
    tags=["system"],
)
@api_view(["GET"])
@permission_classes([AllowAny])
def health(request: Request) -> Response:
    """Simple check that the API is up. Used by the frontend and for deploys."""
    return Response({"status": "ok"})
