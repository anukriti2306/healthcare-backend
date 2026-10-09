"""
Centralised API error handling.

Every error response has the same shape so clients only need one parser::

    {
      "error": {
        "status": 400,
        "code": "validation_error",
        "message": "Validation failed.",
        "details": {"email": ["Enter a valid email address."]}
      }
    }

``details`` is only present for validation errors.
"""
import logging

from django.conf import settings
from django.db import IntegrityError
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler
from rest_framework.views import set_rollback

logger = logging.getLogger(__name__)


def build_error(status_code: int, code: str, message: str, details=None) -> dict:
    error = {"status": status_code, "code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {"error": error}


def custom_exception_handler(exc, context):
    # A unique/foreign-key violation that slipped past serializer validation
    # (e.g. two simultaneous requests creating the same record).
    if isinstance(exc, IntegrityError):
        set_rollback()
        logger.warning("IntegrityError: %s", exc)
        return Response(
            build_error(
                status.HTTP_409_CONFLICT,
                "conflict",
                "The request conflicts with existing data.",
            ),
            status=status.HTTP_409_CONFLICT,
        )

    response = drf_exception_handler(exc, context)

    if response is None:
        # Unhandled exception. In DEBUG let Django show its debug page.
        if settings.DEBUG:
            return None
        set_rollback()
        logger.error("Unhandled exception in %s", context.get("view"), exc_info=exc)
        return Response(
            build_error(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                "server_error",
                "An unexpected error occurred. Please try again later.",
            ),
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Mutate the DRF response in place so headers (WWW-Authenticate,
    # Retry-After, ...) are preserved.
    if isinstance(exc, exceptions.ValidationError):
        response.data = build_error(
            response.status_code, "validation_error", "Validation failed.", response.data
        )
        return response

    data = response.data
    detail = data.get("detail") if isinstance(data, dict) else None
    message = str(detail) if detail else "Request failed."
    code = getattr(detail, "code", None) or getattr(exc, "default_code", "error")
    response.data = build_error(response.status_code, str(code), message)
    return response
