from django.db import connection
from django.http import JsonResponse
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .exceptions import build_error


_HealthSerializer = inline_serializer(
    "Health",
    {"status": serializers.CharField(), "database": serializers.CharField()},
)


@extend_schema(
    responses={200: _HealthSerializer, 503: OpenApiResponse(_HealthSerializer, description="Database down")},
    auth=[],
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def health_check(request):
    """Liveness/readiness probe: confirms the API is up and the database answers."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok", "database": "up"})
    except Exception:  # noqa: BLE001 - any DB failure means "not ready"
        return Response(
            {"status": "degraded", "database": "down"},
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


def not_found(request, exception=None):
    """JSON 404 for unknown URLs (used when DEBUG is False)."""
    return JsonResponse(
        build_error(404, "not_found", "The requested resource was not found."), status=404
    )


def server_error(request):
    """JSON 500 for failures outside DRF views (used when DEBUG is False)."""
    return JsonResponse(
        build_error(500, "server_error", "An unexpected error occurred."), status=500
    )
